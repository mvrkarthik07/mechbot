"""Run paired candidate gates, recalibrate to real scores, or generate REPORT.md."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from functools import lru_cache
from pathlib import Path

from . import sim

REFS = dict(v3="49501d3", cand1="fb04a6e", cand11="b7bdc6b", cand20="fe235ea")
TOLERANCE = 0.4


@lru_cache(maxsize=1)
def arena():
    hello = sim.load_hello(sim.KIT)
    return hello, sim.Arena(hello)


@lru_cache(maxsize=20)
def bot(spec):
    path = Path(spec)
    if path.is_file():
        return sim.load_bot(path)
    return sim.load_git_bot(REFS.get(spec, spec))


@lru_cache(maxsize=1)
def roster():
    return sim.ffa_roster(sim.KIT)


def run_block(job):
    spec, free_for_all, seeds, aim_scale, pressure = job
    hello, world = arena()
    opponents = roster() if free_for_all else ()
    bot_type = bot(spec)
    return [sim.Match(hello, world, bot_type, seed, profile=sim.opposition(seed, aim_scale, pressure),
                      roster=opponents).run() for seed in seeds]


def evaluate(pool, batches, settings, *, progress=False):
    jobs = {}
    for key, (spec, free_for_all, seeds) in batches.items():
        jobs[key] = [
            pool.submit(run_block, (spec, free_for_all, seeds[i:i + 10], settings["aim_scale"], settings["pressure"]))
            for i in range(0, len(seeds), 10)
        ]
    out = {}
    for key, futures in jobs.items():
        _, _, seeds = batches[key]
        summary = sim.summarize([r for future in futures for r in future.result()])
        out[key] = dict(seeds=seeds, **summary)
        if progress:
            print(f"Completed {key[0]} {key[1]} ({len(seeds)} matches)", file=sys.stderr, flush=True)
    return out


def paired_delta(before, after, band=None):
    if before["seeds"] != after["seeds"]:
        raise ValueError("paired summaries must use the same seeds in the same order")
    return statistics.mean(b - a for seed, a, b in zip(
        before["seeds"], before["points_by_seed"], after["points_by_seed"], strict=True)
        if band is None or sim.BANDS[seed % 2] == band)


def decision(before, after):
    if set(before) != {"tuning", "validation", "ffa"} or set(after) != set(before):
        raise ValueError("the keep gate uses tuning, validation, and validation FFA only")
    for split in before:
        expected = sim.SEEDS["validation" if split == "ffa" else split]
        if tuple(before[split]["seeds"]) != expected or tuple(after[split]["seeds"]) != expected:
            raise ValueError("the keep gate requires the complete benchmark splits")
    delta = {split: paired_delta(before[split], after[split]) for split in before}
    band_deltas = {split: {band: paired_delta(before[split], after[split], band) for band in sim.BANDS}
                   for split in ("tuning", "validation")}
    p99 = max(summary["act_p99_ms"] for summary in after.values())
    keep = (delta["tuning"] >= 0.25 and delta["validation"] >= 0.20 and delta["ffa"] >= -0.30 and p99 < 15
            and all(d >= -0.20 for bands in band_deltas.values() for d in bands.values()))
    return dict(keep=keep, delta=delta, band_deltas=band_deltas, max_act_p99_ms=p99)


def predictions(pool, scores, settings, seeds):
    batches = {spec: (spec, False, seeds) for spec in scores}
    return {spec: summary["mean_points"]
            for spec, summary in evaluate(pool, batches, settings).items()}


def calibration_error(scores, predicted):
    if not scores.keys() <= predicted.keys():
        return math.inf
    return max(abs(score - predicted[name]) for name, score in scores.items())


def save_calibration(settings):
    file = sim.DEFAULT_CALIBRATION
    pending = file.with_suffix(".tmp")
    pending.write_text(json.dumps(settings, indent=2, sort_keys=True) + "\n")
    pending.replace(file)


def calibrate(pool, settings, scores):
    seeds = sim.SEEDS["validation"]
    guess = {k: settings[k] for k in ("aim_scale", "pressure")}
    tried = [(guess, predictions(pool, scores, guess, seeds))]
    if calibration_error(scores, tried[0][1]) > TOLERANCE + 1e-9:
        # Screen only on validation. Confirm every real score using the full split.
        pilot = seeds[:40]
        grid = [dict(aim_scale=aim, pressure=pressure)
                for aim, pressure in itertools.product((0.5, 0.7, 0.85, 1.0, 1.2, 1.45, 1.8), (-2, 0, 2))
                if (aim, pressure) != (guess["aim_scale"], guess["pressure"])]
        rankings = [(calibration_error(scores, predictions(pool, scores, g, pilot)), i, g)
                    for i, g in enumerate(grid)]
        for _, _, g in sorted(rankings):
            predicted = predictions(pool, scores, g, seeds)
            tried.append((g, predicted))
            if calibration_error(scores, predicted) <= TOLERANCE + 1e-9:
                break
    params, predicted = min(tried, key=lambda item: calibration_error(scores, item[1]))
    if calibration_error(scores, predicted) > TOLERANCE + 1e-9:
        # Preserve the existing model and block keep decisions until all real scores can be matched.
        params, predicted = tried[0]
    return dict(**params, scores=scores, validation_predictions=predicted)


def compare(pool, settings, args):
    stages = ("tuning", "validation", "ffa")
    summaries = [{}, {}]
    for stage in stages:
        ffa = stage == "ffa"
        seeds = sim.SEEDS["validation" if ffa else stage]
        before, after = evaluate(pool, {0: (args.base, ffa, seeds), 1: (args.candidate, ffa, seeds)}, settings).values()
        summaries[0][stage], summaries[1][stage] = before, after
        if stage == "tuning" and (paired_delta(before, after) < 0.25 or after["act_p99_ms"] >= 15
                                  or any(paired_delta(before, after, band) < -0.20 for band in sim.BANDS)):
            print(json.dumps(dict(keep=False, rejected_at=stage, tuning_delta=paired_delta(before, after),
                                  bands={band: paired_delta(before, after, band) for band in sim.BANDS},
                                  act_p99_ms=after["act_p99_ms"]), indent=2))
            return
    print(json.dumps(decision(*summaries), indent=2))


def report_text(results, settings):
    lines = ["# Mech Royale evaluation", "",
             "Each row uses 200 matches per split. Practice columns show the mean followed by the lenient and strict bands.",
             "Free-for-all uses the validation seeds with the same fixed opponent roster for every row.", "",
             "| Bot | Commit | Practice tuning | Practice validation | Final holdout | FFA validation | Validation act p99 |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]

    def practice(s):
        return f'{s["mean_points"]:.3f} ({s["bands"]["lenient"]["mean_points"]:.2f} / {s["bands"]["strict"]["mean_points"]:.2f})'

    for name, ref in REFS.items():
        t, v, h, f = (results[name, split] for split in ("tuning", "validation", "holdout", "ffa"))
        lines.append(f'| `{name}` | `{ref}` | {practice(t)} | {practice(v)} | {practice(h)} | '
                     f'{f["mean_points"]:.3f} | {v["act_p99_ms"]:.2f} ms |')
    lines.extend(["", "## Paired checks against the preceding historical bot", "",
                  "These comparisons use only tuning, validation, and validation FFA. Historical commits retain their tags.",
                  "", "| Candidate vs. base | Tuning Δ | Validation Δ | Validation lenient / strict Δ | FFA Δ | Gate |",
                  "| --- | ---: | ---: | ---: | ---: | --- |"])
    for base, candidate in itertools.pairwise(REFS):
        before, after = [{split: results[name, split] for split in ("tuning", "validation", "ffa")}
                         for name in (base, candidate)]
        gate = decision(before, after)
        d, b = gate["delta"], gate["band_deltas"]["validation"]
        lines.append(f'| `{candidate}` vs. `{base}` | {d["tuning"]:+.3f} | {d["validation"]:+.3f} | '
                     f'{b["lenient"]:+.2f} / {b["strict"]:+.2f} | {d["ffa"]:+.3f} | '
                     f'{"Pass" if gate["keep"] else "Fail"} |')
    lines.extend(["", "## Real-score calibration", "",
                  "| Bot | Real practice | Sim validation | Absolute error | Within ±0.40 |",
                  "| --- | ---: | ---: | ---: | --- |"])
    scores = settings["scores"]
    predicted = settings["validation_predictions"]
    for name, real in sorted(scores.items()):
        value = predicted[name]
        lines.append(f'| `{name}` | {real:.2f} | {value:.3f} | {abs(real - value):.3f} | '
                     f'{"Yes" if abs(real - value) <= TOLERANCE + 1e-9 else "No"} |')
    lines.extend(["", "## Protocol", "",
                  "Tuning uses seeds 1000–1199, validation 1200–1399, and final holdout 1400–1599. Each practice split contains "
                  "100 lenient and 100 strict profiles. Only tuning, validation, and validation FFA feed the keep gate.",
                  "",
                  "FFA seats one candidate, one copy each of five fixed historical revisions, the kit starter, and nine "
                  "independent house mechs. It uses the same ground-only arena approximation as practice.",
                  "",
                  "The old 100-seed results remain in [EXPERIMENTS.md](EXPERIMENTS.md). "
                  "The profile ranges, score update command, and limits of calibration are in [sim/CALIBRATION.md](sim/CALIBRATION.md)."])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, choices=range(1, 11), default=4, metavar="1–10")
    sub = parser.add_subparsers(dest="command", required=True)
    gate = sub.add_parser("compare", help="make a keep decision without the final holdout")
    gate.add_argument("--base", required=True, help="historical label, Git ref, or bot.py path")
    gate.add_argument("--candidate", required=True, help="historical label, Git ref, or bot.py path")
    sub.add_parser("report", help="write the fixed four-version benchmark to REPORT.md")
    fit = sub.add_parser("calibrate", help="fit the randomized house on real-scored validation matches")
    fit.add_argument("--score", action="append", default=[], metavar="REF=POINTS",
                     help="record a real score by historical label or immutable commit hash")
    args = parser.parse_args()
    settings = sim.read_calibration()
    if args.command == "compare" and calibration_error(settings["scores"], settings.get("validation_predictions", {})) > TOLERANCE + 1e-9:
        parser.error("calibrate all known real scores before making keep decisions")

    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        if args.command == "calibrate":
            scores = settings["scores"].copy()
            for pair in args.score:
                name, sep, raw = pair.partition("=")
                try:
                    score = float(raw)
                    if not sep or not name or not 0 <= score <= 15:
                        raise ValueError()
                    if name not in REFS:
                        name = subprocess.check_output(
                            ["git", "rev-parse", "--verify", "--end-of-options", f"{name}^{{commit}}"], cwd=sim.ROOT, text=True).strip()
                except (ValueError, subprocess.CalledProcessError):
                    parser.error(f"expected a bot label or commit and a score from 0 to 15, got {pair!r}")
                scores[name] = score
            settings = calibrate(pool, settings, scores)
            save_calibration(settings)
            print(json.dumps(settings, indent=2))
            if calibration_error(scores, settings["validation_predictions"]) > TOLERANCE + 1e-9:
                parser.exit(1, "The bounded calibration search could not match all recorded real scores. Keep decisions are blocked.\n")
        elif args.command == "compare":
            compare(pool, settings, args)
        else:
            if not settings.get("validation_predictions"):
                parser.error("run calibrate before generating the report")
            # Compute selection data separately. The final holdout is read only by the report formatter.
            batches = {(name, split): (name, split == "ffa", sim.SEEDS["validation" if split == "ffa" else split])
                       for name in REFS for split in ("tuning", "validation", "ffa")}
            results = evaluate(pool, batches, settings, progress=True)
            print("Running final holdout for REPORT.md", file=sys.stderr, flush=True)
            results.update(evaluate(pool, {(name, "holdout"): (name, False, sim.SEEDS["holdout"])
                                           for name in REFS}, settings))
            (sim.ROOT / "REPORT.md").write_text(report_text(results, settings))
            print("Wrote REPORT.md")


if __name__ == "__main__":
    main()

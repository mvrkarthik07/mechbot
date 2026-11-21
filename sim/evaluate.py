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

REFS = dict(v1="c0a9f2e31640efbe1fe483dfa3ebb8971ff904d9",
            v3="49501d3408b991ff2f53501e28fc7e4cc6348491",
            cand1="fb04a6eb349752f1e6930da5b8d0239915f0a34d",
            cand11="b7bdc6bfb234d08fac7d90b4858fa2fa601f6b26",
            cand20="fe235ea72c91623e545759413d153ca889134348",
            candB4="653ceb448ad9f261f3c2024cf32159a1e11ebbff")
TOLERANCE = 0.3


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
    spec, free_for_all, seeds, aim_scale, pressure, hitscan, pursuit = job
    hello, world = arena()
    opponents = roster() if free_for_all else ()
    bot_type = bot(spec)
    return [sim.Match(hello, world, bot_type, seed, profile=sim.opposition(seed, aim_scale, pressure, hitscan, pursuit),
                      roster=opponents).run() for seed in seeds]


def evaluate(pool, batches, settings, *, progress=False):
    jobs = {}
    for key, (spec, free_for_all, seeds) in batches.items():
        jobs[key] = [
            pool.submit(run_block, (spec, free_for_all, seeds[i:i + 10], settings["aim_scale"], settings["pressure"], settings.get("hitscan", 0.45), settings.get("pursuit", 1.0)))
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


def decision(before, after, settings=None):
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
    slope = (settings or {}).get("linear_fit", {}).get("a", 1.0)
    real_gain = slope * delta["validation"]
    keep = (delta["tuning"] > 0 and real_gain >= 0.30 - 1e-9 and delta["ffa"] >= -0.30 and p99 < 15
            and all(d >= -0.20 for bands in band_deltas.values() for d in bands.values()))
    return dict(keep=keep, predicted_real_gain=real_gain, delta=delta, band_deltas=band_deltas, max_act_p99_ms=p99)


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


def ranking_loss(p):
    if not REFS.keys() <= p.keys():
        return math.inf
    groups = (("v1", "v3"), ("cand1",), ("cand20", "candB4"), ("cand11",))
    loss = sum(max(0, p[low] - p[high] + 0.005)
               for lower, higher in itertools.pairwise(groups) for low in lower for high in higher)
    return loss + sum(max(0, abs(p[a] - p[b]) - 0.245)
                      for a, b in (groups[0], groups[2]))


def correct_order(p):
    return ranking_loss(p) < 1e-9


def fit_linear(scores, predicted):
    x, y = list(predicted.values()), [scores[name] for name in predicted]
    a, b = statistics.linear_regression(x, y) if len(set(x)) > 1 else (0.0, statistics.mean(y))
    # Reverse-order and negative gains are not usable as a positive calibration curve.
    return dict(a=a, b=b)


def model_key(scores, predicted):
    fit = fit_linear(scores, predicted)
    estimates = {name: fit["a"] * points + fit["b"] for name, points in predicted.items()}
    return (fit["a"] <= 0, max(0, calibration_error(scores, estimates) - TOLERANCE),
            ranking_loss(predicted), calibration_error(scores, predicted))


def fitted_model(scores, trials):
    params, predicted = min(trials, key=lambda item: model_key(scores, item[1]))
    result = dict(**params, scores=scores, validation_predictions=predicted)
    if not correct_order(predicted) or calibration_error(scores, predicted) > TOLERANCE + 1e-9:
        result["linear_fit"] = fit_linear(scores, predicted)
    return result


def mapped_score(settings, points):
    fit = settings.get("linear_fit")
    return points if fit is None else fit["a"] * points + fit["b"]


def calibrate(pool, settings, scores):
    seeds = sim.SEEDS["validation"]
    guess = {k: settings[k] for k in ("aim_scale", "pressure")}
    guess["hitscan"] = settings.get("hitscan", 0.45)
    guess["pursuit"] = settings.get("pursuit", 1.0)
    fitted = predictions(pool, scores, guess, seeds)
    tried = [(guess, fitted)]
    print(f"Current model validation {fitted}", file=sys.stderr, flush=True)
    if calibration_error(scores, fitted) > TOLERANCE + 1e-9 or not correct_order(fitted):
        # Screen a small stratified validation subset. Only full-split results can select a model.
        grid = [dict(aim_scale=aim, pressure=guess["pressure"], hitscan=0.80, pursuit=pursuit)
                for aim, pursuit in itertools.product((0.75, 1.05), (0.45, 1.5))]
        pilot = []
        for g in grid:
            estimate = predictions(pool, scores, g, seeds[:24])
            pilot.append((g, estimate))
        pilot.sort(key=lambda item: model_key(scores, item[1]))
        for g, _ in pilot[:2]:
            predicted = predictions(pool, scores, g, seeds)
            tried.append((g, predicted))
            print(f"Challenger validation {g} {predicted}", file=sys.stderr, flush=True)
            if correct_order(predicted) and calibration_error(scores, predicted) <= TOLERANCE + 1e-9:
                break
    return fitted_model(scores, tried)


def compare(pool, settings, args):
    stages = ("tuning", "validation", "ffa")
    summaries = [{}, {}]
    for stage in stages:
        ffa = stage == "ffa"
        seeds = sim.SEEDS["validation" if ffa else stage]
        before, after = evaluate(pool, {0: (args.base, ffa, seeds), 1: (args.candidate, ffa, seeds)}, settings).values()
        summaries[0][stage], summaries[1][stage] = before, after
        if stage == "tuning" and (paired_delta(before, after) <= 0 or after["act_p99_ms"] >= 15
                                  or any(paired_delta(before, after, band) < -0.20 for band in sim.BANDS)):
            print(json.dumps(dict(keep=False, rejected_at=stage, tuning_delta=paired_delta(before, after),
                                  bands={band: paired_delta(before, after, band) for band in sim.BANDS},
                                  act_p99_ms=after["act_p99_ms"]), indent=2))
            return
    result = decision(*summaries, settings)
    result["scores"] = {stage: {label: {k: summary[k] for k in ("mean_points", "bands", "killed_by")}
                                for label, summary in zip(("base", "candidate"), (summaries[0][stage], summaries[1][stage]))}
                        for stage in stages}
    result["pred_real"] = mapped_score(settings, summaries[1]["validation"]["mean_points"])
    print(json.dumps(result, indent=2))


def report_text(results, settings, versions=REFS):
    lines = ["# Mech Royale evaluation", "",
             "Each row uses 200 matches per split. Practice columns show the mean followed by the lenient and strict bands.",
             "Free-for-all uses the validation seeds with the same fixed opponent roster for every row.", "",
             "| Bot | Commit | Practice tuning | Practice validation | Final holdout | FFA validation | Predicted real | Validation act p99 |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]

    def practice(s):
        return f'{s["mean_points"]:.3f} ({s["bands"]["lenient"]["mean_points"]:.2f} / {s["bands"]["strict"]["mean_points"]:.2f})'

    for name, ref in versions.items():
        t, v, h, f = (results[name, split] for split in ("tuning", "validation", "holdout", "ffa"))
        lines.append(f'| `{name}` | `{ref}` | {practice(t)} | {practice(v)} | {practice(h)} | '
                     f'{f["mean_points"]:.3f} | {mapped_score(settings, v["mean_points"]):.3f} | {v["act_p99_ms"]:.2f} ms |')
    lines.extend(["", "## Paired checks against the preceding historical bot", "",
                  "These comparisons use only tuning, validation, and validation FFA. Historical commits retain their tags.",
                  "", "| Candidate vs. base | Tuning Δ | Validation Δ | Validation lenient / strict Δ | FFA Δ | Gate |",
                  "| --- | ---: | ---: | ---: | ---: | --- |"])
    for base, candidate in itertools.pairwise(REFS):
        before, after = [{split: results[name, split] for split in ("tuning", "validation", "ffa")}
                         for name in (base, candidate)]
        gate = decision(before, after, settings)
        d, b = gate["delta"], gate["band_deltas"]["validation"]
        lines.append(f'| `{candidate}` vs. `{base}` | {d["tuning"]:+.3f} | {d["validation"]:+.3f} | '
                     f'{b["lenient"]:+.2f} / {b["strict"]:+.2f} | {d["ffa"]:+.3f} | '
                     f'{"Pass" if gate["keep"] else "Fail"} |')
    lines.extend(["", "## Real-score calibration", ""])
    predicted = settings["validation_predictions"]
    if fit := settings.get("linear_fit"):
        lines.extend([f'Fallback fit: predicted real = {fit["a"]:.4f} × simulated validation + {fit["b"]:.4f}.',
                      "The map was fitted to the recorded real scores. Errors in the table are fitted residuals.", ""])
    lines.extend([f'Raw simulated ordering matches the real ordering: {"yes" if correct_order(predicted) else "no"}. Rank loss: {ranking_loss(predicted):.3f}.', "",
                  "| Bot | Real practice | Raw sim validation | Predicted real | Absolute prediction error |",
                  "| --- | ---: | ---: | ---: | ---: |"])
    for name, real in sorted(settings["scores"].items()):
        value = predicted[name]
        estimate = mapped_score(settings, value)
        lines.append(f'| `{name}` | {real:.2f} | {value:.3f} | {estimate:.3f} | {abs(real - estimate):.3f} |')
    best_real = max((name for name in REFS if name in settings["scores"]), key=settings["scores"].get)
    deaths = list(results[best_real, "validation"]["killed_by"].items())[:3]
    lines.extend(["", f"## Deaths for the best real-scored bot, {best_real}", ""])
    lines.extend(f"- {cause} in {n} validation matches" for cause, n in deaths)
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
    report = sub.add_parser("report", help="write the historical benchmark and selected candidates to REPORT.md")
    report.add_argument("--candidate", action="append", default=[], help="selected candidate tag to include")
    fit = sub.add_parser("calibrate", help="fit the randomized house on real-scored validation matches")
    fit.add_argument("--score", action="append", default=[], metavar="REF=POINTS",
                     help="record a real score by historical label or immutable commit hash")
    args = parser.parse_args()
    settings = sim.read_calibration()
    if args.command in ("compare", "report") and (not REFS.keys() <= settings["scores"].keys()
            or settings["scores"].keys() != settings.get("validation_predictions", {}).keys()):
        parser.error("calibrate all known real scores before evaluating candidates")

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
                        name = next((label for label, ref in REFS.items() if ref == name), name)
                except (ValueError, subprocess.CalledProcessError):
                    parser.error(f"expected a bot label or commit and a score from 0 to 15, got {pair!r}")
                scores[name] = score
            settings = calibrate(pool, settings, scores)
            save_calibration(settings)
            print(json.dumps(settings, indent=2))
        elif args.command == "compare":
            compare(pool, settings, args)
        else:
            if not settings.get("validation_predictions"):
                parser.error("run calibrate before generating the report")
            # Compute selection data separately. The final holdout is read only by the report formatter.
            versions = dict(REFS)
            for tag in args.candidate:
                versions[tag] = subprocess.check_output(
                    ["git", "rev-parse", "--verify", "--end-of-options", f"{tag}^{{commit}}"],
                    cwd=sim.ROOT, text=True).strip()
            batches = {(name, split): (ref, split == "ffa", sim.SEEDS["validation" if split == "ffa" else split])
                       for name, ref in versions.items() for split in ("tuning", "validation", "ffa")}
            results = evaluate(pool, batches, settings, progress=True)
            print("Running final holdout for REPORT.md", file=sys.stderr, flush=True)
            results.update(evaluate(pool, {(name, "holdout"): (ref, False, sim.SEEDS["holdout"])
                                           for name, ref in versions.items()}, settings))
            (sim.ROOT / "REPORT.md").write_text(report_text(results, settings, versions))
            print("Wrote REPORT.md")


if __name__ == "__main__":
    main()

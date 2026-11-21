"""Policy tests on small fake results with the real split lengths."""
import unittest

from sim import evaluate, sim


class EvaluationTest(unittest.TestCase):
    def test_seed_bands_and_draw_bounds(self):
        seeds = [seed for split in sim.SEEDS.values() for seed in split]
        self.assertEqual(len(seeds), len(set(seeds)))
        for split in sim.SEEDS.values():
            profiles = [sim.opposition(seed) for seed in split]
            self.assertEqual(len(split), 200)
            self.assertEqual(sum(p.band == "strict" for p in profiles), 100)
            for seed, profile in zip(split, profiles):
                self.assertEqual(profile, sim.opposition(seed))
                self.assertTrue(0.5 <= profile.aim <= 1.5)
                self.assertTrue(0.3 <= profile.lead <= 1.0)
                self.assertTrue(0.1 <= profile.reaction <= 1.0)
                self.assertTrue(0.25 <= profile.per_kill <= 1.0)
                self.assertTrue(240 <= profile.all_after <= 360)
            self.assertGreater(len({p.weapons for p in profiles}), 1)

    def test_gates_use_paired_splits_and_thresholds(self):
        outer = {split: dict(seeds=sim.SEEDS["validation" if split == "ffa" else split],
                             points_by_seed=[5] * 200, act_p99_ms=2)
                 for split in ("tuning", "validation", "ffa")}
        updated = {split: dict(result, points_by_seed=result["points_by_seed"].copy())
                   for split, result in outer.items()}
        updated["tuning"]["points_by_seed"][:50] = [6] * 50
        updated["validation"]["points_by_seed"][:40] = [6] * 40
        updated["ffa"]["points_by_seed"][:60] = [4] * 60
        self.assertTrue(evaluate.decision(outer, updated)["keep"])
        updated["ffa"]["points_by_seed"][60] = 4
        self.assertFalse(evaluate.decision(outer, updated)["keep"])
        updated["ffa"]["points_by_seed"][60] = 5
        updated["validation"]["points_by_seed"] = [6 if i % 2 else 4 for i in range(200)]
        updated["validation"]["points_by_seed"][0:122:2] = [5] * 61
        self.assertGreater(evaluate.paired_delta(outer["validation"], updated["validation"]), 0.2)
        gate = evaluate.decision(outer, updated)
        self.assertFalse(gate["keep"])
        self.assertEqual(gate["band_deltas"]["validation"]["lenient"], -0.39)
        with self.assertRaises(ValueError):
            evaluate.decision(outer, dict(updated, holdout={}))
        with self.assertRaises(ValueError):
            evaluate.paired_delta(outer["tuning"], outer["validation"])

    def test_all_real_scored_versions_must_fit(self):
        scores = {"v3": 3.4, "cand20": 4.6}
        self.assertGreater(evaluate.calibration_error(scores, {"v3": 3.4, "cand20": 5.2}), 0.4)
        self.assertLess(evaluate.calibration_error(scores, {"v3": 3.3, "cand20": 4.7}), 0.4)
        self.assertEqual(evaluate.calibration_error(scores, {"v3": 3.4}), float("inf"))

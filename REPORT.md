# Mech Royale evaluation

**Latest real result:** `candB4` scored 3.71. Development is back on `cand11` (`b7bdc6bfb234d08fac7d90b4858fa2fa601f6b26`), the best verified real bot at 3.92. The tables below describe the preceding benchmark and are superseded for new submission decisions. The coordinated-squad recalibration and candidate screen are running.

Each row uses 200 matches per split. Practice columns show the mean followed by the lenient and strict bands.
Free-for-all uses the validation seeds with the same fixed opponent roster for every row.

| Bot | Commit | Practice tuning | Practice validation | Final holdout | FFA validation | Predicted real | Validation act p99 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `v1` | `c0a9f2e31640efbe1fe483dfa3ebb8971ff904d9` | 3.400 (4.25 / 2.55) | 3.390 (4.16 / 2.62) | 3.775 (4.72 / 2.83) | 8.950 | 3.466 | 7.64 ms |
| `v3` | `49501d3408b991ff2f53501e28fc7e4cc6348491` | 3.025 (3.68 / 2.37) | 3.310 (4.16 / 2.46) | 3.350 (4.22 / 2.48) | 9.380 | 3.440 | 7.54 ms |
| `cand1` | `fb04a6eb349752f1e6930da5b8d0239915f0a34d` | 3.560 (4.23 / 2.89) | 3.615 (4.61 / 2.62) | 3.890 (4.84 / 2.94) | 9.550 | 3.540 | 7.39 ms |
| `cand11` | `b7bdc6bfb234d08fac7d90b4858fa2fa601f6b26` | 4.055 (4.89 / 3.22) | 3.950 (5.18 / 2.72) | 4.315 (5.42 / 3.21) | 9.770 | 3.650 | 7.45 ms |
| `cand20` | `fe235ea72c91623e545759413d153ca889134348` | 4.590 (5.16 / 4.02) | 4.455 (5.85 / 3.06) | 4.845 (5.93 / 3.76) | 11.075 | 3.815 | 8.26 ms |
| `candB4` | `653ceb448ad9f261f3c2024cf32159a1e11ebbff` | 4.210 (5.13 / 3.29) | 4.190 (5.44 / 2.94) | 4.410 (5.45 / 3.37) | 9.915 | 3.728 | 7.71 ms |

## Paired checks against the preceding historical bot

These comparisons use only tuning, validation, and validation FFA. Historical commits retain their tags.

| Candidate vs. base | Tuning Δ | Validation Δ | Validation lenient / strict Δ | FFA Δ | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| `v3` vs. `v1` | -0.375 | -0.080 | +0.00 / -0.16 | +0.430 | Fail |
| `cand1` vs. `v3` | +0.535 | +0.305 | +0.45 / +0.16 | +0.170 | Pass |
| `cand11` vs. `cand1` | +0.495 | +0.335 | +0.57 / +0.10 | +0.220 | Pass |
| `cand20` vs. `cand11` | +0.535 | +0.505 | +0.67 / +0.34 | +1.305 | Pass |

## Real-score calibration

Fallback fit: predicted real = 0.3280 × simulated validation + 2.3538.
The map was fitted to the recorded real scores. Errors in the table are fitted residuals.

Raw simulated ordering matches the real ordering: no.

| Bot | Real practice | Raw sim validation | Predicted real | Absolute prediction error |
| --- | ---: | ---: | ---: | ---: |
| `cand1` | 3.54 | 3.615 | 3.540 | 0.000 |
| `cand11` | 3.92 | 3.950 | 3.650 | 0.270 |
| `cand20` | 3.67 | 4.455 | 3.815 | 0.145 |
| `v1` | 3.38 | 3.390 | 3.466 | 0.086 |
| `v3` | 3.40 | 3.310 | 3.440 | 0.040 |

## Deaths for the best real-scored bot, cand11

- easy/gun in 92 validation matches
- easy/laser in 34 validation matches
- medium/gun in 29 validation matches

## Protocol

Tuning uses seeds 1000–1199, validation 1200–1399, and final holdout 1400–1599. Each practice split contains 100 lenient and 100 strict profiles. Only tuning, validation, and validation FFA feed the keep gate.

FFA seats one candidate, one copy each of five fixed historical revisions, the kit starter, and nine independent house mechs. It uses the same ground-only arena approximation as practice.

The old 100-seed results remain in [EXPERIMENTS.md](EXPERIMENTS.md). The profile ranges, score update command, and limits of calibration are in [sim/CALIBRATION.md](sim/CALIBRATION.md).

## What transferred

Healing movement and direct aim when releasing a charged laser raised the actual score through cand11. The projectile-dodge experiment gained 0.93 on the old tuning split and lost 0.25 in real practice. The simulated dodge window is likely more useful than the real one. Cand20 remains excluded based on the measured real loss. No historical midpoint tag exists. CandB4 re-tests exp15 as a single change on top of cand11. Its paired validation gain was +0.240 and its paired validation FFA gain was +0.145. The largest act p99 across the three decision batches was 8.32 ms.

## Next real submissions

1. `candB4` (`653ceb448ad9f261f3c2024cf32159a1e11ebbff`), predicted real 3.728. The fitted gain over cand11 is 0.079, within the observed noise of the real scorer.

One unscored candidate cleared the gates. The best verified real version remains cand11 at 3.92, and the 5.30 real target remains unverified. The simulator still includes its own projectiles in observations, which the real protocol omits. This is a limitation when interpreting projectile-reactive behavior.

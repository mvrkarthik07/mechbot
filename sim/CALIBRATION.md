# Coordinated-squad calibration

The target uses six recorded practice scores and the fixed 200 validation seeds. Differences below 0.25 within the paired real-score groups are treated as potentially noisy.

## Pursuit and warning time

The preceding policy pursued the last sighting and sometimes switched to the player's live location without a new sighting. Hunters generally reserved boosting for zone movement. The current policy shares observed position and velocity. A lead hunter presses while flankers approach from offset routes. After losing contact, they continue searching near the predicted last-known point and rotate sectors. The simulator also omits a bot's own rounds as specified in the protocol. Projectile dodging remains out of the development bot.

On a 24-seed probe at aim scale 0.75, cand11's mean reacquisitions rose from 11.33 to 14.71 per match. Its mean longest contact gap stayed near 32.8 s. CandB4 moved from 0.25 above cand11 to 0.25 below it. Cand20 moved from 0.17 above cand11 to a tie. In a separate probe, shared estimates from noisy sound bearings widened cand20's advantage to 1.33, so that variant was dropped. The probes motivated the full-split tests and do not establish the real cause.

## Full-split fit

| Aim scale / pursuit | Raw rank loss | Raw cand11 | Raw candB4 | Raw cand20 |
| --- | ---: | ---: | ---: | ---: |
| 0.75 / 1 | 0.510 | 6.265 | 6.145 | 6.580 |
| 0.75 / 1.5 | 0.370 | 6.530 | 6.460 | 6.800 |
| 1.05 / 1.5 | 0.685 | 6.635 | 6.520 | 7.040 |

Selected aim scale 0.75, pursuit 1.5, pressure 2, and early laser probability 0.8.
Predicted real = 0.4306 × raw validation + 0.8988.
The exact raw group ordering was not reproduced. The linear fit changes score scale and leaves the order unchanged when the slope is positive.

| Bot | Official | Raw validation | Fitted real | Absolute fit error |
| --- | ---: | ---: | ---: | ---: |
| `v1` | 3.38 | 5.770 | 3.383 | 0.003 |
| `v3` | 3.40 | 5.955 | 3.463 | 0.063 |
| `cand1` | 3.54 | 6.170 | 3.556 | 0.016 |
| `cand11` | 3.92 | 6.530 | 3.711 | 0.209 |
| `cand20` | 3.67 | 6.800 | 3.827 | 0.157 |
| `candB4` | 3.71 | 6.460 | 3.680 | 0.030 |

These are in-sample fitted errors over six versions. They do not measure the uncertainty of a new candidate or a repeat real submission.

Tuning uses seeds 1000–1199 and validation 1200–1399, with 100 lenient and 100 strict profiles per split. Final holdout seeds 1400–1599 appear only in REPORT.md. FFA uses the locked historical roster with independent house actors. Each profile retains the existing randomized lead, reaction, aim noise, schedule, and weapons.

Record a new official result with `python3.13 -B -m sim.evaluate --jobs 9 calibrate --score TAG=POINTS`. Recheck calibration when the fitted error exceeds 0.30 or the observed ordering flips.

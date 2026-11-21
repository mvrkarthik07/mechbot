# Mech Royale coordinated-squad report

**Best verified real version is cand11 at 3.92.** The 5.50 real target has yet to be reached.

## Next submission

**diagC1** — `afe438eaf856a9de94f08f0d8396d497255ab26a`. Release lethal partial laser charges and account for one tick of torso slew. Published for one real diagnostic submission. Main retains cand11. This tests the timing of a hitscan weapon directly, independent of projectile-warning assumptions.
Predicted real 3.758, paired predicted gain +0.047, paired raw validation +0.110, paired FFA +0.050, maximum act p99 9.73 ms.

| Bot | Commit | Tuning | Validation | Final holdout | Validation FFA | Predicted real | Real |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| cand11 | `b7bdc6bfb234d08fac7d90b4858fa2fa601f6b26` | 6.070 (7.04 / 5.10) | 6.530 (7.76 / 5.30) | 6.850 (8.10 / 5.60) | 9.655 | 3.711 | 3.92 |
| diagC1 | `afe438eaf856a9de94f08f0d8396d497255ab26a` | 6.055 (6.70 / 5.41) | 6.640 (7.82 / 5.46) | 6.750 (7.82 / 5.68) | 9.705 | 3.758 | — |

Practice entries show mean and lenient / strict mean. The final holdout ran after the submission was locked.

## Calibration and ranking

Predicted real = 0.4306 × raw validation + 0.8988. All six in-sample fitted errors are within 0.30.
The new model gives cand11 a higher raw score than candB4. It still gives cand20 a higher raw score than cand11. The fitted model preserves this remaining inversion, so a simulated advantage is weaker evidence than a real result. See the [calibration results](sim/CALIBRATION.md).

## Most common deaths for cand11 on practice validation

- easy/gun in 50 of 200 matches
- hard/gun in 38 of 200 matches
- medium/gun in 32 of 200 matches

## What transferred

The early changes through cand11 raised the measured real practice score to 3.92. The real scores for projectile dodging and for seeking cover while healing were lower at 3.67 and 3.71. This round leaves both behaviors out. The pending cand11 repeat will help estimate how much to read into small differences.

The [experiment log](EXPERIMENTS.md) records the paired results and rejection reasons for this round.

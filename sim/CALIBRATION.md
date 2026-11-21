# Randomized practice calibration

The practice benchmark assigns 100 matches to each of two difficulty bands per split. Every seed determines its own profile independently of spawn and bot RNG. Comparing two bots on a seed gives them the same initial layout and opponent profile.

| Draw | Full range | Strict half |
| --- | --- | --- |
| Aim noise multiplier on each difficulty tier | 0.5–1.5 | Lower noise |
| Lead fraction | 0.30–1.00 | More lead |
| Reaction interval | 0.10–1.00 s | Faster reactions |
| Additional hunters per credited kill | 0.25–1.00 | More hunters |
| Remaining squad joins | 240–360 s | Earlier |
| Hard and expert secondary loadout | Match-specific laser/lightning probabilities | Drawn independently of band |

The configuration can scale the center of the aim-noise distribution and skew each continuous draw within its band without crossing its endpoints. FFA starts mechs with guns and supplies secondary weapons through pickups. The FFA squad schedule has no effect because house mechs choose their own opponents.

Record each incoming real practice score with the tagged version or an immutable Git revision.

```sh
python3 -B -m sim.evaluate --jobs 6 calibrate --score cand20=REAL_SCORE
```

The command checks the full 200 randomized validation matches for v3 and every recorded real-scored candidate. It keeps the current distribution when all errors are within ±0.40. Otherwise it screens alternate distributions on 40 validation seeds and confirms promising fits on the full 200. A fit must meet the band for each real score simultaneously. If the bounded search fails, the command retains the current distribution, records the real score and its prediction, and blocks further keep decisions. The final holdout is reserved for the report.

The calibration file records the parameters, measured real scores, and matching simulated validation means. The earlier fixed-opponent calibration and its history are available at commit `7a6410d`. Ground-only motion and the approximate house tactics remain the main limits on competitive prediction.

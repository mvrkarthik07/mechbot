# Mech Royale practice report

## Real-score update

The official scorer's best version is **`cand11`**, commit `b7bdc6bfb234d08fac7d90b4858fa2fa601f6b26`, at **3.92**. The next kept change, projectile dodging in `cand20` (`fe235ea72c91623e545759413d153ca889134348`), scored **3.67**. Exp15 and exp16 were reverted trials and have no historical tags to submit. The randomized calibration completed on all five official scores. The raw model still ranks cand20 above cand11. The linear fallback, residuals, and leave-one-out errors are in [sim/CALIBRATION.md](sim/CALIBRATION.md). The tables below are historical while the new candidate reruns finish.


**Best candidate is `cand20` (`fe235ea`) at 5.53 simulated points.** It gained 2.12 points over v3 on the tuning seeds and 1.60 on untouched seeds. The best simulated mean remains below the new 7–10 point target. The real scorer has yet to evaluate these candidates.

| Bot | Commit | Tuning seeds 0–99 | Untouched seeds 100–199 | Tuning kills | Tuning mean death | Tuning `act()` p99 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| v3 | `49501d3` | 3.41 | 3.37 | 1.81 | 97.45 s | 2.93 ms |
| `cand1` | `fb04a6e` | 4.29 | — | 2.39 | 111.51 s | 2.79 ms |
| `cand11` | `b7bdc6b` | 4.60 | 4.35 | 2.71 | 112.53 s | 2.93 ms |
| `cand20` | `fe235ea` | **5.53** | **4.97** | **3.49** | **123.93 s** | 2.84 ms |

On the untouched seeds, `cand20` beat `cand11` in 40 matches, tied in 33, and lost in 27. The paired gain was 0.62 points. Its held-out mean was 0.56 below the tuning result, so the tuning score is an optimistic estimate of what another seed set may yield.

## Deaths in the best tuning batch

1. Easy house gunfire in 36 matches.
2. Medium house gunfire in 22 matches.
3. Hard house gunfire and the zone tied at 10 matches each.

## Experiments

The log covers 36 trials on 100 paired seeds each. Moving after a recent hit when trying to heal gained 0.88 points. Aiming the charged hitscan laser directly at the target gained 0.31 more. Projecting rounds and steering sideways to clear their path gained the largest increment, 0.93 on the tuning seeds.

A new retreat path helped the earlier laser-aim candidate and regressed after adding projectile dodging. Dodging before the first hit also regressed. Holding a dodge longer gained 0.15, below the keep threshold. Range changes, early zone rotation, more aggressive loot priorities, and changes to healing and upgrades fell short. The [experiment log](EXPERIMENTS.md) lists the paired results.

The [frozen calibration](sim/CALIBRATION.md) scored the v3 reference at 3.41 and the kit starter at 1.44. The best tuning batch averaged 0.73 s per match and peaked at 4.84 s. The official conformance check passed on the host and in the Linux/amd64 Docker image under the match limits. Docker response time was 6.9 ms p99 with zero late responses.

## Real scorer order

1. `cand20` (`fe235ea72c91623e545759413d153ca889134348`), simulated 5.53 on tuning seeds and 4.97 on untouched seeds.
2. `cand11` (`b7bdc6bfb234d08fac7d90b4858fa2fa601f6b26`), simulated 4.60 on tuning seeds and 4.35 on untouched seeds.
3. `cand1` (`fb04a6eb349752f1e6930da5b8d0239915f0a34d`), simulated 4.29 on tuning seeds.

Reopen calibration if a candidate's real score differs from its simulated tuning mean by more than 0.5 points. The simulator uses a ground-only approximation against the house squad. Free-for-all performance remains unmeasured.

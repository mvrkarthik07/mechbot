# Bot experiments

Each row uses the same 100 seeds and the frozen [house calibration](sim/CALIBRATION.md). A change needs at least +0.25 mean points and `act()` p99 below 15 ms. Death time is the mean among matches where the bot died.

| ID | Hypothesis | Change | Mean points | Mean kills | Mean death (s) | p99 (ms) | Result |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| exp1 | Standing still to heal while a hidden hunter is firing costs us early fights. | Roam until 2.5 s have passed since the last hit when no heal loot is available. | 3.41 → 4.29 | 1.81 → 2.39 | 97.45 → 111.51 | 2.79 | Kept |

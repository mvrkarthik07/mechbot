# Practice simulator calibration

The frozen house settings are the defaults in [sim.py](sim.py). The full runs used seeds 0–99, the kit's recorded `hello.config` and arena, the source of `bot.py` at `49501d3`, and the kit's `python/example_bot.py`.

| House settings | v3 points | Starter points |
| --- | ---: | ---: |
| Initial defaults | 5.04 | 2.33 |
| Easy aim noise 1.35°, reaction 0.45 s, 1.00 additional hunters per kill | 2.64 | 1.35 |
| Same aim and reaction, 0.85 additional hunters per kill | **3.41** | **1.44** |
| Real practice reference | 3.40 | 1.15 |

The initial easy gunner had 3.2° aim noise and a 0.55 s reaction interval. It took too long to finish stationary targets, giving the starter more time to earn placement through house deaths. Reducing aim error and reaction time brought its score down. Recruiting a second hunter immediately after the first kill suppressed v3 too much. Using `1 + floor(0.85 × kills)` keeps one hunter through the first kill, then ramps up at subsequent kills. All remaining house mechs join at 240 s. The other difficulty settings, physics, seeds, and game balance stayed fixed for the calibration.

The final v3 run averaged 1.81 kills, died at 97.45 s, and took 1,774 gun damage per match. The starter averaged 0.40 kills and died at 69.94 s. The starter landed near the upper edge of its calibration band. Matching two bots' means leaves uncertainty about later engagements, including how often house bots die to the zone or drones.

On this Mac, v3 averaged 0.55 s per match with a 4.85 s maximum, 2.93 ms `act()` p99, and approximately 56 MiB peak RSS for the benchmark process. Some long matches exceeded the 2 s speed target. The simulator models ground combat and the house squad. It provides no measured free-for-all performance.

Reopen calibration if a submitted bot scores more than 0.5 points away from its simulated mean.

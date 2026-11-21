# Bot experiments

Experiments 1–36 used the same 100 seeds and the earlier fixed [house calibration](sim/CALIBRATION.md). A change needs at least +0.25 mean points and `act()` p99 below 15 ms. Death time is the mean among matches where the bot died. Later keep decisions use the [200-seed evaluation gates](README.md#local-evaluation).

| ID | Hypothesis | Change | Mean points | Mean kills | Mean death (s) | p99 (ms) | Result |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| exp1 | Standing still to heal while a hidden hunter is firing costs us early fights. | Roam until 2.5 s have passed since the last hit when no heal loot is available. | 3.41 → 4.29 | 1.81 → 2.39 | 97.45 → 111.51 | 2.79 | Kept |
| exp2 | More distance will reduce easy gun hits enough to win more early duels. | Increase the preferred gun and laser range from 95 m to 130 m. | 4.29 → 4.13 | 2.39 → 2.29 | 111.51 → 112.26 | 2.93 | Reverted |
| exp3 | Cover chosen against the squad centroid leaves individual hunters a firing line. | Validate hold cover against each nearby mech. | 4.29 → 4.25 | 2.39 → 2.38 | 111.51 → 108.94 | 2.80 | Reverted |
| exp4 | We leave kill cubes behind, missing health, damage, and upgrades before the next hunter arrives. | Favor the remembered drops from kills when picking a safe loot goal. | 4.29 → 4.29 | 2.39 → 2.36 | 111.51 → 112.76 | 2.85 | Reverted |
| exp5 | Longer boost strafes will dodge more rounds in early gun duels. | Lower the fight boost threshold from 55 to 30 energy. | 4.29 → 4.40 | 2.39 → 2.43 | 111.51 → 114.39 | 2.89 | Reverted |
| exp6 | After 60 s silent roaming makes an already-detected mech too slow to escape gunfire. | Walk at full speed while roaming for 2.5 s after taking damage. | 4.29 → 4.31 | 2.39 → 2.42 | 111.51 → 109.92 | 2.83 | Reverted |
| exp7 | The combined strafe and range correction sends us into walls and leaves us exposed. | Fall back to pure strafe when the combined direction crosses a wall. | 4.29 → 4.44 | 2.39 → 2.42 | 111.51 → 114.76 | 2.77 | Reverted |
| exp8 | Waiting for an urgent zone warning during a fight leaves less time to cross cover-heavy terrain. | Start moving toward the next circle while fighting when the existing zone planner calls for it. | 4.29 → 4.19 | 2.39 → 2.34 | 111.51 → 105.89 | 2.85 | Reverted |
| exp9 | When several mechs are tracked, aiming at one behind cover sacrifices shots at exposed hunters. | Penalize targets with a blocked muzzle line when other targets exist. | 4.29 → 4.38 | 2.39 → 2.47 | 111.51 → 112.21 | 2.80 | Reverted |
| exp10 | Retreating below 40% HP leaves too little health to break line of sight after losing a duel. | Raise the losing-fight retreat threshold from 40% to 55% HP. | 4.29 → 4.38 | 2.39 → 2.43 | 111.51 → 111.50 | 2.85 | Reverted |
| exp11 | Projectile lead points a charged hitscan laser ahead of moving targets. | Aim directly at the target while charging the laser. | 4.29 → 4.60 | 2.39 → 2.71 | 111.51 → 112.53 | 2.93 | Kept |
| exp12 | Earlier access to the now-accurate laser will win more duels before the squad ramps up. | Increase the laser pickup preference by reducing its distance score multiplier from 0.80 to 0.45. | 4.60 → 4.51 | 2.71 → 2.66 | 112.53 → 110.42 | 2.95 | Reverted |
| exp13 | Starting the next fight after only a partial heal loses otherwise winnable trades. | Raise the out-of-combat heal threshold from 85% to 98% HP. | 4.60 → 4.60 | 2.71 → 2.59 | 112.53 → 114.32 | 2.61 | Reverted |
| exp14 | Closer fights will improve our gun hit rate and speed up kills enough to pay for the extra risk. | Reduce preferred gun and laser range from 95 m to 65 m. | 4.60 → 4.50 | 2.71 → 2.71 | 112.53 → 112.06 | 2.92 | Reverted |
| exp15 | A retreat toward cover selected from damage bearing will break hidden gunfire sooner than ordinary roaming. | Use the last incoming bearing to choose cover when healing under fire with no loot goal. | 4.60 → 4.64 | 2.71 → 2.73 | 112.53 → 114.05 | 2.92 | Reverted |
| exp16 | Routing through a nearby reachable crate will equip us or earn a cube before the first duels. | When armed only with the starter gun, prefer a reachable crate over aimless roaming. | 4.60 → 4.60 | 2.71 → 2.69 | 112.53 → 115.16 | 2.87 | Reverted |
| exp17 | Mortar aim overrides a usable gun firing line and wastes gun shots. | Reserve mortar aim for blocked lines or when the gun is absent or reloading. | 4.60 → 4.46 | 2.71 → 2.60 | 112.53 → 109.61 | 2.93 | Reverted |
| exp18 | Earlier armor and faster regeneration will survive more gun-heavy engagements than plating-first upgrades. | Lower plating priority below nanites and armor. | 4.60 → 4.60 | 2.71 → 2.70 | 112.53 → 112.96 | 2.90 | Reverted |
| exp19 | Lightning's cone and laser short will win enough close fights to beat laser-first looting. | Rank lightning ahead of laser for pickup and replacement. | 4.60 → 4.27 | 2.71 → 2.41 | 112.53 → 109.21 | 2.72 | Reverted |
| exp20 | Accelerating sideways away from a visible round's projected path will cut gun damage. | Select walkable movement and boost commands by projected lateral miss distance. | 4.60 → 5.53 | 2.71 → 3.49 | 112.53 → 123.93 | 2.84 | Kept |
| exp21 | The gun waits an extra decision after the torso is close enough to finish aligning. | Evaluate first-tick yaw and pitch slew in the gun trigger. | 4.60 → 4.73 | 2.71 → 2.76 | 112.53 → 111.50 | 3.15 | Reverted |
| exp22 | Picking the strafe lane with a useful firing line and cover during reloads will win more early duels. | Score walkable fight lanes for line of sight, range, current velocity, and zone safety. | 4.60 → 4.70 | 2.71 → 2.82 | 112.53 → 113.62 | 2.97 | Reverted |
| exp23 | Retreating in a straight line keeps us in a hunter's firing solution. | Score retreat lanes for cover, transverse movement, and zone safety, and sustain boost farther from the hunter. | 4.60 → 4.90 | 2.71 → 2.96 | 112.53 → 115.82 | 3.12 | Retest on cand20 as exp27 |
| exp24 | Disengaging at 40% HP forfeits winnable duels and draws out lethal retreats. | Lower the losing-fight retreat threshold to 20% HP. | 4.60 → 4.70 | 2.71 → 2.82 | 112.53 → 109.46 | 3.16 | Reverted |
| exp25 | Remembered mechs behind solid cover force premature hold mode. | Count only enemies in range with an unobstructed firing line when entering hold. | 4.60 → 4.62 | 2.71 → 2.74 | 112.53 → 110.08 | 3.08 | Reverted |
| exp26 | Frequent direction changes spend too much of each strafe accelerating. | Lengthen the fight strafe interval from 0.5–1.4 s to 1.3–2.8 s. | 4.60 → 4.80 | 2.71 → 2.81 | 112.53 → 117.05 | 3.09 | Reverted |
| exp27 | Retreat lanes that break line of sight may still add value after projectile dodging. | Retest exp23's retreat movement on cand20. | 5.53 → 5.37 | 3.49 → 3.38 | 123.93 → 123.05 | 2.97 | Reverted |
| exp28 | Dodging visible bullets before the first hit will improve early duels. | Run the dodge planner whenever grounded and the zone permits. | 5.53 → 5.24 | 3.49 → 3.14 | 123.93 → 119.80 | 3.00 | Reverted |
| exp29 | A nearby supply drop can refill HP faster than waiting out the regen timer. | Allow nearby supply drops to be chosen while healing. | 5.53 → 5.52 | 3.49 → 3.49 | 123.93 → 123.84 | 3.10 | Reverted |
| exp30 | A longer duel range will favor the hitscan laser over projectiles after we equip it. | Prefer 135 m when carrying a laser while retaining the normal gun range. | 5.53 → 5.42 | 3.49 → 3.38 | 123.93 → 124.76 | 3.13 | Reverted |
| exp31 | Holding an evasive command briefly should keep the mech from steering back into the shot. | Hold the chosen dodge for up to 0.25 s while the path remains clear. | 5.53 → 5.68 | 3.49 → 3.53 | 123.93 → 129.19 | 3.13 | Reverted |
| exp32 | Beginning a laser charge before rounding cover will shorten exposure before firing. | Charge if the intended movement is expected to open a muzzle line by full charge. | 5.53 → 5.52 | 3.49 → 3.46 | 123.93 → 124.06 | 3.12 | Reverted |
| exp33 | The laser sometimes holds a full charge despite the torso being able to align before the next shot. | Allow release when the next physics tick will align the torso. | 5.53 → 5.55 | 3.49 → 3.51 | 123.93 → 125.71 | 3.11 | Reverted |
| exp34 | Continuing to move after breaking every known firing line gives up opportunities to regenerate. | Stop retreat movement while protected by cover inside the forecast zone. | 5.53 → 5.54 | 3.49 → 3.47 | 123.93 → 121.27 | 3.07 | Reverted |
| exp35 | Keeping gun lead during the first part of a laser charge will add damage before the laser is ready. | Switch from gun lead to direct aim only in the final two decision intervals of the laser charge. | 5.53 → 5.65 | 3.49 → 3.58 | 123.93 → 126.54 | 2.96 | Reverted |
| exp36 | Selecting a walkable direction when stuck will escape exposed wall collisions faster. | Choose a clear escape direction before falling back to the commanded jump and boost. | 5.53 → 5.34 | 3.49 → 3.28 | 123.93 → 119.67 | 3.04 | Reverted |

## Recalibrated trials from cand11

B1–B9 retest the hypotheses from exp12–exp20 individually. The real practice score for the baseline is 3.92.


Scores show the overall mean, paired delta, and paired lenient/strict deltas. FFA shows the mean and the paired delta.

| Trial | Hypothesis | Change | Tuning | Validation | Validation FFA | Predicted real | Max act p99 (ms) | Decision |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| B1 | Earlier access to the now-accurate laser will win more duels before the squad ramps up. | Increase the laser pickup preference | 4.190 (+0.135, +0.08/+0.19) | 3.965 (+0.015, +0.12/-0.09) | — | 3.654 | 8.27 | Reverted |
| B2 | Starting the next fight after only a partial heal loses otherwise winnable trades. | Raise the heal threshold to 98% HP | 4.025 (-0.030, -0.15/+0.09) | — | — | — | 8.50 | Reverted |
| B3 | Closer fights will improve our gun hit rate and speed up kills enough to pay for the extra risk. | Reduce preferred duel range to 65 m | 3.980 (-0.075, +0.13/-0.28) | — | — | — | 8.65 | Reverted |
| B4 | A retreat toward cover selected from damage bearing will break hidden gunfire sooner than ordinary roaming. | Use damage bearing to seek cover while healing | 4.210 (+0.155, +0.24/+0.07) | 4.190 (+0.240, +0.26/+0.22) | 9.915 (+0.145) | 3.728 | 8.32 | Kept as candB4 |
| B5 | Routing through a nearby reachable crate will equip us or earn a cube before the first duels. | Route toward a reachable starter crate | 4.190 (+0.135, +0.15/+0.12) | 4.075 (+0.125, +0.03/+0.22) | — | 3.691 | 8.12 | Reverted |
| B6 | Mortar aim overrides a usable gun firing line and wastes gun shots. | Reserve mortar aim for a blocked line or unavailable gun | 3.980 (-0.075, -0.03/-0.12) | — | — | — | 7.96 | Reverted |
| B7 | Earlier armor and faster regeneration will survive more gun-heavy engagements than plating-first upgrades. | Rank nanites and armor ahead of plating | 4.095 (+0.040, +0.09/-0.01) | 3.930 (-0.020, -0.06/+0.02) | — | 3.643 | 7.91 | Reverted |
| B8 | Lightning's cone and laser short will win enough close fights to beat laser-first looting. | Rank lightning ahead of laser | 3.600 (-0.455, -0.61/-0.30) | — | — | — | 8.03 | Reverted |
| B9 | Accelerating sideways away from a visible round's projected path will cut gun damage. | Dodge projected rounds | 4.590 (+0.535, +0.27/+0.80) | 4.455 (+0.505, +0.67/+0.34) | 11.075 (+1.305) | 3.815 | 8.26 | Reverted, real-score veto |
| B10 | Keeping projectile lead during the first part of the laser charge will let the gun deal more damage before the beam can fire. | Keep gun lead until the last two charging decisions | 3.985 (-0.070, -0.03/-0.11) | — | — | — | 8.05 | Reverted |
| B11 | A remembered mech behind cover can draw aim away from an exposed threat, giving that opponent more free shots. | Prioritize targets with a clear muzzle line | 4.250 (+0.195, +0.33/+0.06) | 4.010 (+0.060, +0.09/+0.03) | — | 3.669 | 7.99 | Reverted |
| B12 | Retreating along a walkable lane that breaks line of sight will stop damage sooner than running straight away from the pursuer. | Choose a walkable escape lane during retreat | 4.200 (+0.145, +0.07/+0.22) | 3.975 (+0.025, -0.02/+0.07) | — | 3.658 | 7.94 | Reverted |

## Coordinated-squad trials from cand11

- C1. Firing a charged laser as soon as the torso will align, or releasing a lethal partial charge, will finish isolated enemies before they can answer.
- C2. Taking a small safe detour to collect kill cubes before re-engaging will turn early kills into health, damage, and upgrades.
- C3. Closing decisively on a wounded isolated mech while our gun or laser is ready will convert more trades into kills.
- C4. Cover that blocks the squad centroid can leave an enemy flank open, so hold positions should block each dangerous line of fire.

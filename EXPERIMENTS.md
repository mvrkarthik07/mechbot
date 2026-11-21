# Bot experiments

Each row uses the same 100 seeds and the frozen [house calibration](sim/CALIBRATION.md). A change needs at least +0.25 mean points and `act()` p99 below 15 ms. Death time is the mean among matches where the bot died.

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

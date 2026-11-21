# kt-mech-v1: Mech Royale bot (mechfight/1)

Python 3.13, standard library only. `bot.py` is the bot; `mechfight.py` is the kit wrapper.

## What it does
- **Map:** rasterises `/arena/v2/world.json` + `terrain.i16` into a 2 m grid (buildings, stadium, bridges, steep slopes) at startup (~0.3 s).
- **Navigation:** weighted A* on the grid (time-capped at 6 ms), path smoothing, and jump+jet when it's stuck.
- **Gun:** solves the intercept for lead, and fires only when the real torso aim is on target and there's a clear line.
- **Laser** (preferred pickup): charges whenever it has a line and releases at full charge on target. Won't charge against lightning holders within 55 m.
- **Lightning / mortar:** fires lightning in its cone; lobs mortar on a ballistic arc (high arc when there's no line).
- **Fight:** strafes perpendicular to the enemy with random switches, holds a preferred range, and dodges a laser charged at it.
- **Retreat:** at <35% HP when losing, breaks line of sight to cover and regenerates. Shoots back if still being hit.
- **Zone:** moves into the next circle early enough not to get caught.
- **Loot:** weapons, cubes, supply drops, farms NPC drones and crates when no enemy is around.
- **Upgrades:** plating/armor/regen first, then weapon upgrades for the weapons it holds.

## Local evaluation

Download and unpack the official [Mech Royale kit](https://www.joinbuilders.org/buildathon/tracks/builders/files/mechfight-kit.tar.gz) here so `mechfight-kit/` sits next to `bot.py`.

```sh
python3 -B sim/sim.py --split tuning
python3 -B sim/sim.py --seed 1000 --verbose
python3 -B sim/sim.py --split validation --ffa
python3 -B -m sim.evaluate --jobs 6 compare --base cand11 --candidate ./bot.py
python3 -B -m sim.evaluate --jobs 6 report
python3 -B -m unittest sim.test_sim sim.test_evaluate
python3 mechfight-kit/check/check.py -- python3 -u bot.py
```

Tuning uses seeds 1000–1199, validation uses 1200–1399, and the final holdout uses 1400–1599. Each split has 100 lenient and 100 strict opponent profiles. The comparison gate screens for a positive tuning gain and requires +0.30 predicted real points from paired validation, no band loss greater than 0.20 on either practice split, and no FFA loss greater than 0.30 on the validation seeds. The candidate's `act()` p99 must stay below 15 ms. The report is the only output that includes final holdout results.

FFA uses the candidate, five pinned historical bot copies, the kit starter, and nine independent house mechs. The simulator uses ground-only motion, the bot's 2 m map, and sampled canopy and shot geometry. For actual scorer feedback, follow the [calibration procedure](sim/CALIBRATION.md).

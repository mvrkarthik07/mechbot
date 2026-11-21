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

## Local practice simulator

Download and unpack the official [Mech Royale kit](https://www.joinbuilders.org/buildathon/tracks/builders/files/mechfight-kit.tar.gz) here so `mechfight-kit/` sits next to `bot.py`.

```sh
python3 -B sim/sim.py --matches 100
python3 -B sim/sim.py --seed 0 --verbose
python3 -B sim/sim.py --bot mechfight-kit/python/example_bot.py --matches 100
python3 -B -m unittest sim.test_sim
python3 mechfight-kit/check/check.py -- python3 -u bot.py
```

The benchmark reads the kit's arena and recorded configuration. A batch uses seeds 0–99 in order, with `--matches` taking a prefix. The simulator reports placement points, kills, cause of death, damage, mode share, and timings as JSON. `--verbose` writes one match timeline to stderr. Stuck time means a movement command above half speed with less than 2 m of displacement over the previous 1–1.2 seconds.

The simulation uses ground-only motion, the bot's 2 m map, sampled canopy and shot geometry, and a modeled house squad. These approximations affect comparisons involving rooftops, jumps, foliage, and cover edges. A* uses a fixed expansion budget in the simulator so runs use the same paths across machines.

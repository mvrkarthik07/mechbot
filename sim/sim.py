#!/usr/bin/env python3
"""Ground-only, in-process practice benchmark for mechfight/1."""
from __future__ import annotations

import argparse
import gzip
import json
import math
import random
import runpy
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from itertools import count
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import mechfight as mf
from bot import Bot, GridMap, Nav, clamp, unit, wrap

KIT = ROOT / "mechfight-kit"
SEEDS = tuple(range(100))
SQUAD = ("easy",) * 4 + ("medium",) * 4 + ("hard",) * 4 + ("expert",) * 3
# House AI parameters, independent of game balance.
HOUSE = {
    # aim error (degrees), lead fraction, reaction (s), preferred gun range
    "easy": (3.2, 0.35, 0.55, 62),
    "medium": (1.8, 0.65, 0.35, 75),
    "hard": (0.9, 0.85, 0.20, 90),
    "expert": (0.5, 1.0, 0.10, 105),
}


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def at_height(pos, height):
    return (pos[0], pos[1], pos[2] + height)


def translate(pos, vector, scale):
    return tuple(p + v * scale for p, v in zip(pos, vector))


def bearing(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def direction(yaw, pitch):
    c = math.cos(pitch)
    return (c * math.cos(yaw), c * math.sin(yaw), math.sin(pitch))


def slew(value, goal, rate):
    return value + clamp(goal - value, -rate, rate)


@dataclass
class Weapon:
    kind: str
    ammo: int = 0
    ready: float = 0.0
    reload_end: float = 0.0
    charge_start: float | None = None
    release: bool = False


@dataclass(eq=False)
class Body:
    id: int
    kind: str
    pos: tuple
    stats: dict
    hp: float
    energy: float = 0.0
    vel: tuple = (0.0, 0.0, 0.0)
    aim: tuple = (0.0, 0.0)
    desired: tuple = (0.0, 0.0)
    cubes: int = 0
    weapons: list = field(default_factory=lambda: [None, None])
    weapon_stats: dict = field(default_factory=dict)
    upgrades: list = field(default_factory=list)
    last_combat: float = -math.inf
    last_spent: float = -math.inf
    next_step: float = 0.0
    short_until: float = 0.0
    action: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    difficulty: str = ""
    nav: Nav | None = None
    next_react: float = 0.0
    strafe: int = 1
    home: tuple | None = None
    target: Body | None = None
    next_shot: float = 0.0
    offer: dict | None = None
    thresholds: int = 0

    @property
    def center(self):
        return at_height(self.pos, self.stats["height"] / 2)

    @property
    def kinds(self):
        return [w.kind for w in self.weapons if w is not None]

    @property
    def charging(self):
        return next((w for w in self.weapons if w and w.charge_start is not None), None)


@dataclass
class Projectile:
    id: int
    owner: Body
    kind: str
    pos: tuple
    vel: tuple
    expires: float
    damage: float
    stats: dict
    radius: float


def cylinder_hit(start, vector, length, body, padding=0):
    """Entry distance for the finite ray and vertical cylinder."""
    x, y, z = start
    bx, by, bz = body.pos
    dx, dy, dz = vector
    x, y = x - bx, y - by
    lo, hi = 0.0, length
    radius = body.stats["radius"] + padding
    a = dx * dx + dy * dy
    c = x * x + y * y - radius * radius
    if a > 1e-12:
        b = x * dx + y * dy
        discriminant = b * b - a * c
        if discriminant < 0:
            return None
        root = math.sqrt(discriminant)
        lo, hi = max(lo, (-b - root) / a), min(hi, (-b + root) / a)
    elif c > 0:
        return None
    bottom, top = bz - padding, bz + body.stats["height"] + padding
    if abs(dz) > 1e-12:
        near, far = (bottom - z) / dz, (top - z) / dz
        lo, hi = max(lo, min(near, far)), min(hi, max(near, far))
    elif not bottom <= z <= top:
        return None
    return lo if lo <= hi else None


class Arena:
    def __init__(self, hello):
        paths = hello["map"]
        cfg = hello["config"]
        self.grid = GridMap(paths["dir"], paths["files"], cfg["mech"]["step_up"], cfg["mech"]["max_slope_deg"])
        if not self.grid.ok:
            raise ValueError("Could not load the official arena")
        self.grid.expansion_limit = 2048  # Stable across machines and repeated A/B runs.
        filename = next(p for p in paths["files"] if p.endswith(".json"))
        world = json.loads((Path(paths["dir"]) / filename).read_text())
        b = world["bounds"]
        self.bounds = b["minX"], b["minY"], b["maxX"], b["maxY"]
        grid = self.grid
        self.roofs = [(*grid.center(i), top) for i, top in enumerate(grid.top)
                      if top > grid.gnd[i] + cfg["mech"]["height"]]
        self.tree_bins = {}
        self.tree_rules = world["rules"]
        data = world["trees"]["data"]
        columns = world["trees"]["fields"]
        step = len(columns)
        for i in range(0, len(data), step):
            tree = dict(zip(columns, data[i:i + step]))
            x, y, r = tree["crownX"], tree["crownY"], tree["crownR"]
            r = max(r + math.hypot(x - tree["x"], y - tree["y"]), tree["trunkR"])
            for ix in range(math.floor((x - r) / 16), math.floor((x + r) / 16) + 1):
                for iy in range(math.floor((y - r) / 16), math.floor((y + r) / 16) + 1):
                    self.tree_bins.setdefault((ix, iy), []).append(tree)

    def position(self, rng, margin=0, circle=None):
        x0, y0, x1, y1 = self.bounds
        for _ in range(2000):
            x, y = rng.uniform(x0 + margin, x1 - margin), rng.uniform(y0 + margin, y1 - margin)
            if circle is not None:
                (cx, cy), r = circle
                angle, offset = rng.uniform(0, math.tau), math.sqrt(rng.random()) * r
                x, y = cx + math.cos(angle) * offset, cy + math.sin(angle) * offset
                if not (x0 + margin <= x <= x1 - margin and y0 + margin <= y <= y1 - margin):
                    continue
            if self.grid.free(x, y):
                return (x, y, self.grid.ground(x, y))
        raise ValueError("No walkable spawn found")

    def solid(self, x, y, z):
        grid = self.grid
        c = grid.cell(x, y)
        if c is None or z <= grid.gnd[c] or grid.base[c] <= z <= grid.top[c]:
            return True
        return any(lo <= z <= hi for lo, hi in grid.elev.get(c, ()))

    def wall_distance(self, start, vector, length):
        # shortcut: ray casts sample the 2 m map, use exact solids for edge-hit parity.
        step = self.grid.C / 2
        x, y, z = start
        dx, dy, dz = vector
        for i in range(1, math.ceil(length / step) + 1):
            d = min(length, i * step)
            if self.solid(x + dx * d, y + dy * d, z + dz * d):
                return d
        return math.inf

    def canopy_clear(self, start, end, dist):
        # shortcut: sample crown and trunk coverage, use exact intersections if vision dominates calibration.
        x, y, z = start
        dx, dy, dz = end[0] - x, end[1] - y, end[2] - z
        samples = int(dist / 4) + 1
        density = 0
        threshold = -math.log(self.tree_rules["canopyBlockT"])
        for i in range(1, samples):
            f = i / samples
            px, py, pz = x + dx * f, y + dy * f, z + dz * f
            for tree in self.tree_bins.get((int(px // 16), int(py // 16)), ()):
                if tree["z"] <= pz <= tree["z"] + tree["height"]:
                    if (px - tree["x"]) ** 2 + (py - tree["y"]) ** 2 < tree["trunkR"] ** 2:
                        return False
                    if pz >= tree["z"] + tree["crownBase"] and (
                            (px - tree["crownX"]) ** 2 + (py - tree["crownY"]) ** 2 < tree["crownR"] ** 2):
                        density += self.tree_rules["canopyDensity"] * dist / samples
                        if density >= threshold:
                            return False
        return True


class Match:
    def __init__(self, hello, arena, bot_type, seed, per_kill, all_after):
        self.start_wall = time.perf_counter()
        self.cfg = hello["config"]
        self.arena = arena
        self.grid = arena.grid
        self.rng = rng = random.Random(seed)
        self.sound_rng = random.Random(seed ^ 0x50A0D)
        self.per_kill, self.all_after = per_kill, all_after
        self.dt = 1 / self.cfg["match"]["tick_hz"]
        self.interval = self.cfg["match"]["decide_every"]
        self.tick = 0
        self.t = 0.0
        self.kills = 0
        self.killer = None
        self.death_time = None
        self.damage = Counter()
        self.modes = Counter()
        self.act_ms = []
        self.stuck = 0
        self.move_history = []
        self.memory = {}
        self.cubes = {}
        self.pickups = {}
        self.crates = {}
        self.sounds = []
        self.beams = []
        self.projectiles = []
        self.ids = {k: count(start) for k, start in (("cube", 5000), ("pickup", 8000), ("projectile", 30000), ("offer", 1))}
        self.upgrades = {u["id"]: u for u in self.cfg["upgrades"]}
        self.zone_index = 0
        zone_cfg = self.cfg["zone"]
        center, radius = zone_cfg["start_center"], zone_cfg["start_radius"]
        self.zones = []
        end = 0
        for phase in zone_cfg["phases"]:
            next_radius = phase["radius"]
            # Sample a contained next circle with a walkable center.
            next_center = list(arena.position(rng, circle=(center, radius - next_radius))[:2])
            start = end + phase["hold_s"]
            end = start + phase["shrink_s"]
            self.zones.append(dict(center=center, radius=radius, next_center=next_center,
                                   next_radius=next_radius, shrink_start=start, shrink_end=end, dps=phase["dps"]))
            center, radius = next_center, next_radius
        self.drops = []
        if cfg_drops := self.cfg.get("drops"):
            for i, called in enumerate(cfg_drops["times"]):
                phase = next((z for z in self.zones if z["shrink_end"] > called), self.zones[-1])
                pos = arena.position(rng, circle=(phase["next_center"], phase["next_radius"] * cfg_drops["spread"]))
                self.drops.append(dict(id=20000 + i, pos=pos, called=called, progress=0, holder=None))
        self.mechs = []
        rules = self.cfg["match"]
        slot = rng.randrange(rules["mechs"])
        difficulties = iter(SQUAD)
        for i in range(rules["mechs"]):
            for _ in range(800):
                pos = arena.position(rng, rules["arena_margin"],
                                     (zone_cfg["start_center"], zone_cfg["start_radius"] * rules["spawn_zone_fraction"]))
                if all(distance(pos, m.pos) >= rules["spawn_min_separation"] for m in self.mechs):
                    break
            else:
                raise ValueError(f"Could not place all mechs for seed {seed}")
            st = self.cfg["mech"].copy()
            m = Body(i, "mech", pos, st, st["hp"], st["energy"], weapon_stats={
                k: v.copy() for k, v in self.cfg["weapons"].items()})
            yaw = rng.uniform(-math.pi, math.pi)
            m.aim = m.desired = (yaw, 0)
            m.weapons[0] = self.new_weapon("gun")
            if i != slot:
                m.difficulty = next(difficulties)
                m.nav = Nav(self.grid)
                m.strafe = rng.choice((-1, 1))
                if m.difficulty in ("hard", "expert"):
                    m.weapons[1] = self.new_weapon(rng.choice(("laser", "lightning")))
            self.mechs.append(m)
        self.player = self.mechs[slot]
        self.house = sorted((m for m in self.mechs if m is not self.player), key=lambda m: SQUAD.index(m.difficulty))
        self.hunters = []
        npc = self.cfg["npc"]
        self.npcs = []
        for i in range(npc["count"]):
            pos = arena.position(rng)
            self.npcs.append(Body(100 + i, "npc", pos, npc, npc["hp"], home=pos))
        crate, loot = self.cfg["crates"], self.cfg["loot"]
        for i in range(crate["count"]):
            pos = self.loot_position(crate["roof_fraction"], i, crate["count"])
            self.crates[1000 + i] = Body(1000 + i, "crate", pos, crate, crate["hp"])
        for i in range(loot["floor_count"]):
            self.add_pickup(self.loot_position(loot["floor_roof_fraction"], i, loot["floor_count"]))
        mf.draw.clear()
        mf.draw.caps = self.cfg["debug"]
        with patch.dict(bot_type.__init__.__globals__, {"GridMap": lambda *args: self.grid}):
            self.bot = bot_type(dict(hello, slot=slot, seed=rng.getrandbits(32)))

    def loot_position(self, roof_fraction, i, total):
        if i < round(total * roof_fraction) and self.arena.roofs:
            return self.rng.choice(self.arena.roofs)
        return self.arena.position(self.rng)

    def new_weapon(self, kind):
        return Weapon(kind, ammo=self.cfg["weapons"][kind].get("mag", 0))

    def add_pickup(self, pos, weapon=None):
        if weapon is None:
            weights = self.cfg["loot"]["weights"]
            weapon = self.new_weapon(self.rng.choices(tuple(weights), weights=tuple(weights.values()))[0])
        self.pickups[next(self.ids["pickup"])] = (pos, weapon)

    def add_cubes(self, pos, amount):
        for i in range(amount):
            # Spread on walkable ground so large stacks remain pickable.
            a = i * 2.399963
            spacing = self.cfg["cubes"]["pickup_radius"] / 2
            x = pos[0] + math.cos(a) * spacing * min(i, 2)
            y = pos[1] + math.sin(a) * spacing * min(i, 2)
            if self.grid.free(x, y) and pos[2] == self.grid.ground(*pos[:2]):
                point = x, y, self.grid.ground(x, y)
            else:
                point = pos
            self.cubes[next(self.ids["cube"])] = point

    def zone(self):
        if self.zone_index < len(self.zones) - 1 and self.t >= self.zones[self.zone_index]["shrink_end"]:
            self.zone_index += 1
        z = self.zones[self.zone_index]
        f = clamp((self.t - z["shrink_start"]) / (z["shrink_end"] - z["shrink_start"]), 0, 1)
        self.zone_center = tuple(a + (b - a) * f for a, b in zip(z["center"], z["next_center"]))
        self.zone_radius = z["radius"] + (z["next_radius"] - z["radius"]) * f
        return z

    def in_zone(self, pos):
        return distance(pos, self.zone_center) <= self.zone_radius

    def visible(self, observer, pos, height=0):
        vision = self.cfg["vision"]
        dist = distance(observer.pos, pos)
        near = dist <= vision["near_range"] + observer.stats["near_range_bonus"]
        if not near and (dist > vision["range"] + observer.stats["vision_bonus"] or
                         abs(wrap(bearing(observer.pos, pos) - observer.aim[0])) > math.radians(vision["fov_deg"] / 2)):
            return False
        eye = at_height(observer.pos, observer.stats["eye_height"])
        for target_height in (height / 2, height) if height else (0,):
            end = at_height(pos, target_height)
            if self.grid.los(*eye, *end) and (near or not vision["canopy_blocks"] or self.arena.canopy_clear(eye, end, dist)):
                return True
        return False

    def sound(self, kind, pos, owner=None):
        p = self.player
        if owner is p:
            return
        st = self.cfg["sound"]
        dist = distance(p.pos, pos)
        if dist <= st["range"][kind]:
            band = "near" if dist < st["near"] else "mid" if dist < st["mid"] else "far"
            yaw = bearing(p.pos, pos)
            noise = self.sound_rng.gauss(0, math.radians(st["bearing_noise_deg"]) * p.stats["hearing"])
            self.sounds.append((self.t, dict(kind=kind, bearing=wrap(yaw + noise), dist=band)))

    def event(self, body, event_type, **values):
        if body is self.player:
            body.events.append(dict(type=event_type, **values))

    def weapon_obs(self, body, w):
        if w is None:
            return None
        st = body.weapon_stats[w.kind]
        obs = dict(kind=w.kind, cooldown=max(0, w.ready - self.t), stats=st.copy())
        if w.kind == "gun":
            obs.update(ammo=w.ammo, reload=max(0, w.reload_end - self.t))
        if w.kind == "laser":
            obs["charge"] = 0 if w.charge_start is None else min(st["charge"], self.t - w.charge_start)
        return obs

    def observation(self, zone):
        p = self.player
        vision = self.cfg["vision"]
        actors = []
        for m in self.mechs + self.npcs:
            if m is p or m.hp <= 0:
                continue
            if self.visible(p, m.pos, m.stats["height"]):
                self.memory[m.id] = self.t + vision["memory_s"]
            elif self.memory.get(m.id, -1) < self.t:
                continue
            actor = dict(id=m.id, kind=m.kind, pos=list(m.pos), aim=list(m.aim), vel=list(m.vel))
            if m.kind == "npc" or vision["show_enemy_hp"]:
                actor.update(hp=m.hp, max_hp=m.stats["hp"])
            if m.kind == "mech":
                actor.update(cubes=m.cubes, weapons=m.kinds, charging=m.charging is not None)
            actors.append(actor)
        drops = []
        if cfg_drops := self.cfg.get("drops"):
            for d in self.drops:
                if d["called"] <= self.t:
                    drops.append(dict(id=d["id"], pos=list(d["pos"]), radius=cfg_drops["radius"],
                                      lands_in=max(0, d["called"] + cfg_drops["fall_s"] - self.t),
                                      capture_s=cfg_drops["capture_s"], progress=d["progress"], holder=d["holder"]))
        own = dict(id=p.id, pos=list(p.pos), vel=list(p.vel), aim=list(p.aim), hp=p.hp, max_hp=p.stats["hp"],
                   energy=p.energy, max_energy=p.stats["energy"], grounded=True, cubes=p.cubes,
                   upgrades=p.upgrades.copy(), weapons=[self.weapon_obs(p, w) for w in p.weapons],
                   in_zone=self.in_zone(p.pos), stats=p.stats.copy())
        obs = {"type": "obs", "tick": self.tick, "t": self.t, "alive": len(self.living), "self": own,
               "zone": zone, "offer": p.offer, "mechs": actors, "drops": drops, "events": p.events,
               "sounds": [dict(d, age=self.t - t) for t, d in self.sounds],
               "beams": [dict(d, age=self.t - t) for t, d in self.beams],
               "crates": [dict(id=m.id, pos=list(m.pos), hp=m.hp) for m in self.crates.values()
                          if self.visible(p, m.pos, m.stats["height"])],
               "cubes": [dict(id=i, pos=list(pos)) for i, pos in self.cubes.items()
                         if self.visible(p, at_height(pos, 0.5))],
               "pickups": [dict(id=i, pos=list(pos), kind=w.kind) for i, (pos, w) in self.pickups.items()
                           if self.visible(p, at_height(pos, 0.5))],
               "projectiles": [dict(id=q.id, kind=q.kind, pos=list(q.pos), vel=list(q.vel))
                               for q in self.projectiles if self.visible(p, q.pos)]}
        p.events, self.sounds, self.beams = [], [], []
        return obs

    def give_cubes(self, body, n):
        cfg = self.cfg["cubes"]
        body.cubes += n
        self.apply_stats(body)
        while self.offer(body):
            if body is self.player:
                break
            self.pick(body, 0)

    def apply_stats(self, body):
        old_hp, old_energy = body.stats["hp"], body.stats["energy"]
        body.stats = self.cfg["mech"].copy()
        body.weapon_stats = {k: v.copy() for k, v in self.cfg["weapons"].items()}
        for upgrade in body.upgrades:
            for effect in self.upgrades[upgrade]["effects"]:
                *prefix, stat = effect["path"].split(".")
                data = body.stats if prefix == ["mech"] else body.weapon_stats[prefix[1]]
                data[stat] = data[stat] * effect.get("mul", 1) + effect.get("add", 0)
        cfg = self.cfg["cubes"]
        body.stats["hp"] *= 1 + cfg["hp_per_cube"] * min(body.cubes, cfg["stat_cap"])
        body.hp += body.stats["hp"] - old_hp
        body.energy += body.stats["energy"] - old_energy
        for key in ("radius", "height", "eye_height", "muzzle_height"):
            body.stats[key] *= 1 + cfg["size_per_cube"] * body.cubes

    def offer(self, body):
        if body.offer is not None:
            return True
        thresholds = self.cfg["cubes"]["upgrade_thresholds"]
        if body.thresholds == len(thresholds) or body.cubes < thresholds[body.thresholds]:
            return False
        body.thresholds += 1
        kinds = body.kinds
        options = [u for u in self.upgrades.values() if ("requires" not in u or u["requires"] in kinds)
                   and body.upgrades.count(u["id"]) < u["max"]]
        if not options:
            return False
        choices = [{k: u[k] for k in ("id", "name", "desc")} for u in self.rng.sample(options, min(3, len(options)))]
        body.offer = dict(id=next(self.ids["offer"]), choices=choices,
                          expires=self.t + self.cfg["bot"]["offer_timeout_s"])
        return True

    def pick(self, body, index):
        choice = body.offer["choices"][index]["id"]
        body.upgrades.append(choice)
        body.offer = None
        self.apply_stats(body)
        self.event(body, "upgrade", id=choice)

    def collect(self):
        cfg = self.cfg["cubes"]
        for key, pos in list(self.cubes.items()):
            candidates = [(distance(m.pos, pos), m.id, m) for m in self.living if m.hp > 0
                          and abs(m.pos[2] - pos[2]) <= 4]
            if candidates and (nearest := min(candidates))[0] <= cfg["pickup_radius"]:
                body = nearest[2]
                del self.cubes[key]
                self.give_cubes(body, 1)
                self.event(body, "pickup", cubes=body.cubes)
        if not self.drops:
            return
        cfg = self.cfg["drops"]
        for d in self.drops[:]:
            remaining = d["called"] + cfg["fall_s"] - self.t
            if remaining > 0:
                continue
            if remaining > -self.dt:
                self.sound("drop", d["pos"])
            inside = [m for m in self.living if m.hp > 0 and distance(m.pos, d["pos"]) <= cfg["radius"]]
            if not inside:
                d.update(holder=None, progress=0)
            elif len(inside) == 1:
                m = inside[0]
                if d["holder"] != m.id:
                    d.update(holder=m.id, progress=0)
                d["progress"] += self.dt
                if d["progress"] + 1e-9 >= cfg["capture_s"]:
                    self.drops.remove(d)
                    self.give_cubes(m, cfg["cubes"])
                    m.hp = min(m.stats["hp"], m.hp + m.stats["hp"] * cfg["repair"])
                    m.energy = m.stats["energy"]
                    self.event(m, "drop", id=d["id"], cubes=m.cubes)

    def equipment(self, m):
        a = m.action
        take, drop = a.get("take"), a.get("drop")
        drop = int(drop) if drop in (0, 1) else None
        if take is None:
            if drop is not None and m.weapons[drop] and m.weapons[drop].charge_start is None:
                self.drop_weapon(m, drop)
            return
        if take not in self.pickups:
            self.event(m, "take_failed", id=take, reason="gone")
            return
        pos, w = self.pickups[take]
        slot = drop if drop is not None else next((i for i, item in enumerate(m.weapons) if item is None), None)
        reason = None
        if distance(m.pos, pos) > self.cfg["loot"]["pickup_radius"] or abs(pos[2] - m.pos[2]) > 4:
            reason = "range"
        elif w.kind in m.kinds:
            reason = "have"
        elif slot is None:
            reason = "full"
        elif m.weapons[slot] and m.weapons[slot].charge_start is not None:
            reason = "busy"
        if reason:
            self.event(m, "take_failed", id=take, reason=reason)
            return
        if m.weapons[slot]:
            self.drop_weapon(m, slot)
        del self.pickups[take]
        m.weapons[slot] = w
        st = m.weapon_stats[w.kind]
        w.ready = max(w.ready, self.t + max(st["cooldown"], self.cfg["loot"]["equip_s"]))
        self.event(m, "took", id=take, kind=w.kind, slot=slot)

    def drop_weapon(self, m, slot):
        w = m.weapons[slot]
        self.add_pickup(m.pos, w)
        key = next(reversed(self.pickups))
        m.weapons[slot] = None
        self.event(m, "dropped", id=key, kind=w.kind, slot=slot)

    def spend(self, m, energy):
        m.energy = max(0, m.energy - energy)
        m.last_spent = self.t

    def move(self, m, vx, vy, acceleration):
        ox, oy, oz = m.pos
        dx, dy = vx - m.vel[0], vy - m.vel[1]
        change = math.hypot(dx, dy)
        factor = min(1, acceleration * self.dt / change) if change else 0
        vx, vy = m.vel[0] + dx * factor, m.vel[1] + dy * factor
        x, y = ox + vx * self.dt, oy + vy * self.dt
        if not self.grid.free(x, y):
            if self.grid.free(x, oy):
                y, vy = oy, 0
            elif self.grid.free(ox, y):
                x, vx = ox, 0
            else:
                x, y, vx, vy = ox, oy, 0, 0
        z = self.grid.ground(x, y)
        m.pos, m.vel = (x, y, z), (vx, vy, (z - oz) / self.dt)

    def move_mech(self, m, zone):
        st = m.stats
        a = m.action
        x, y = a.get("move", (0, 0))
        length = math.hypot(x, y)
        boosting = a.get("boost") and length > 0 and m.energy >= st["boost_drain"] * self.dt
        speed = st["boost_speed"] if boosting else st["walk_speed"]
        yaw, pitch = m.desired
        turning = 1
        if m.charging:
            turning = m.weapon_stats["laser"]["charge_turn_mult"]
            speed *= st["charge_move_mult"]
        yaw = wrap(m.aim[0] + clamp(wrap(yaw - m.aim[0]), -st["turn_rate"] * turning * self.dt,
                                     st["turn_rate"] * turning * self.dt))
        pitch = slew(m.aim[1], clamp(pitch, st["min_pitch"], st["max_pitch"]), st["pitch_rate"] * turning * self.dt)
        m.aim = yaw, pitch
        if length or m.vel[0] or m.vel[1]:
            speed /= max(1, length)
            self.move(m, x * speed, y * speed, st["ground_accel"])
        if boosting:
            self.spend(m, st["boost_drain"] * self.dt)
        if self.t >= m.next_step and math.hypot(*m.vel[:2]) > self.cfg["sound"]["step_speed"]:
            self.sound("boost" if boosting else "step", m.pos, m)
            m.next_step = self.t + self.cfg["sound"]["step_every"]
        if m.energy < st["energy"] and self.t - m.last_spent >= st["energy_regen_delay"]:
            m.energy = min(st["energy"], m.energy + st["energy_regen"] * self.dt)
        if not self.in_zone(m.pos):
            self.hit(None, m, "zone", zone["dps"] * self.dt, None)
        elif m.hp < st["hp"] and self.t - m.last_combat >= st["regen_delay"]:
            m.hp = min(st["hp"], m.hp + st["regen_per_s"] * self.dt)

    def separate_player(self):
        # shortcut: resolve player overlaps, add squad spacing physics if late-game pileups matter.
        p = self.player
        for m in self.hunters:
            dx, dy = p.pos[0] - m.pos[0], p.pos[1] - m.pos[1]
            radius = p.stats["radius"] + m.stats["radius"]
            if dx * dx + dy * dy >= radius * radius:
                continue
            dist = math.hypot(dx, dy)
            ux, uy = (dx / dist, dy / dist) if dist else (1, 0)
            push = (radius - dist) / 2
            for body, sign in ((p, 1), (m, -1)):
                x, y = body.pos[0] + sign * ux * push, body.pos[1] + sign * uy * push
                if self.grid.free(x, y):
                    body.pos = (x, y, self.grid.ground(x, y))

    def can_hit(self, owner, target):
        if target.hp <= 0 or owner is target:
            return False
        return not (owner.difficulty and target.difficulty)

    def hit(self, owner, target, kind, damage, source, effect=None):
        if target.hp <= 0:
            return
        yaw = None if source is None else bearing(target.pos, source)
        rear = False
        if owner is not None:
            owner.last_combat = self.t
        if target.kind == "mech" and kind != "zone":
            rear = abs(wrap(yaw - target.aim[0])) > math.radians(target.stats["front_arc_deg"] / 2)
            damage *= 1 - target.stats["armor"]
            if rear:
                damage *= target.stats["rear_mult"]
        target.hp -= damage
        target.last_combat = self.t
        if target.kind == "npc" and owner is not None and owner.kind == "mech":
            target.target = owner
        if target is self.player:
            self.damage[kind] += damage
            self.event(target, "damaged", amount=damage, weapon=kind, bearing=yaw,
                       by=owner.id if owner else None, rear=rear)
        if owner is not None:
            fields = dict(target=target.id, amount=damage, weapon=kind, rear=rear)
            if effect:
                fields["effect"] = effect
                self.event(target, "effect", effect=effect, by=owner.id)
            self.event(owner, "hit", **fields)
        if target.hp > 0:
            return
        if target is self.player:
            self.death_time = self.t
            self.killer = (owner.difficulty or owner.kind if owner and owner is not target else
                           "self" if owner is target else "zone", kind)
        if target.kind == "mech":
            self.death_ticks[target.id] = self.tick
            self.sound("death", target.pos, target)
            self.add_cubes(target.pos, target.cubes + self.cfg["cubes"]["death_drop_extra"])
            if self.cfg["loot"]["death_drop"]:
                for w in target.weapons:
                    if w and w.kind != "gun":
                        w.charge_start, w.release = None, False
                        self.add_pickup(target.pos, w)
            if owner is self.player and target is not owner:
                self.kills += 1
                self.event(owner, "kill", target=target.id)
        else:
            self.add_cubes(target.pos, target.stats["cubes"])
            if target.kind == "crate":
                del self.crates[target.id]
                self.sound("crate", target.pos)
                if self.rng.random() < self.cfg["loot"]["crate_weapon_chance"]:
                    self.add_pickup(target.pos)

    def targets(self, owner):
        # The squad never damages its own members. Most incoming rounds only need one actor check.
        actors = [self.player] if owner.difficulty else self.living
        return (m for group in (actors, self.npcs, self.crates.values()) for m in group if self.can_hit(owner, m))

    def ray_targets(self, owner, start, vector, length, padding=0):
        x, y, _ = start
        dx, dy, _ = vector
        endx, endy = x + dx * length, y + dy * length
        xmin, xmax = sorted((x, endx))
        ymin, ymax = sorted((y, endy))
        hits = []
        for m in self.targets(owner):
            r = m.stats["radius"] + padding
            tx, ty, _ = m.pos
            if xmin - r <= tx <= xmax + r and ymin - r <= ty <= ymax + r:
                d = cylinder_hit(start, vector, length, m, padding)
                if d is not None:
                    hits.append((d, m.id, m))
        return sorted(hits)

    def muzzle(self, m, kind, vector):
        st = m.stats
        height = st["height"] + 0.5 if kind == "mortar" else st["muzzle_height"]
        start = at_height(m.pos, height)
        offset = st["radius"] + 0.5
        limit = self.arena.wall_distance(start, vector, offset)
        return translate(start, vector, offset if math.isinf(limit) else max(0, limit - self.grid.C / 2))

    def shoot(self, m, w, st, fraction=1):
        kind = w.kind
        scheduled = w.ready if self.t - w.ready < self.dt else self.t
        w.ready = scheduled + st["cooldown"]
        yaw, pitch = m.aim
        if kind == "gun":
            noise = math.radians(st["spread_deg"])
            yaw += self.rng.gauss(0, noise)
            pitch += self.rng.gauss(0, noise)
        vector = direction(yaw, pitch)
        start = self.muzzle(m, kind, vector)
        cube = self.cfg["cubes"]
        damage = st["damage"] * (1 + cube["damage_per_cube"] * min(cube["stat_cap"], m.cubes))
        self.sound(kind, start, m)
        if kind in ("gun", "mortar"):
            duration = st["ttl"] if kind == "mortar" else st["range"] / st["speed"]
            radius = self.cfg["projectile"]["gun_radius"] if kind == "gun" else 0
            self.projectiles.append(Projectile(next(self.ids["projectile"]), m, kind, start,
                                               tuple(c * st["speed"] for c in vector), self.t + duration,
                                               damage, st, radius))
        elif kind == "laser":
            hits = self.ray_targets(m, start, vector, st["range"])
            wall = self.arena.wall_distance(start, vector, st["range"])
            end = translate(start, vector, min(st["range"], wall))
            for d, _, target in hits[:int(st["pierce"]) + 1]:
                if d >= wall:
                    break
                end = translate(start, vector, d)
                cookoff = target.kind == "mech" and "mortar" in target.kinds
                self.hit(m, target, kind, damage * fraction * (1 + st["cookoff"] * cookoff), start,
                         "cookoff" if cookoff else None)
            self.beam(m, kind, [start, end])
        else:
            self.lightning(m, st, start, vector, damage)

    def beam(self, m, kind, path):
        if m is not self.player and any(self.visible(self.player, pos) for pos in path):
            self.beams.append((self.t, dict(by=m.id, kind=kind, path=[list(pos) for pos in path])))

    def lightning(self, m, st, start, vector, damage):
        self.spend(m, st["energy"])
        path = [start]
        origin = m.pos
        struck = set()
        for jump in range(int(st["chain"]) + 1):
            reach = st["chain_range"] if jump else st["range"]
            hits = [(distance(origin, target.pos), target.id, target) for target in self.targets(m)
                    if target not in struck and distance(origin, target.pos) <= reach
                    and (jump or abs(wrap(bearing(origin, target.pos) - m.aim[0])) <= math.radians(st["cone_deg"]))
                    and self.grid.los(*path[-1], *target.center)]
            if not hits:
                if not jump:
                    wall = self.arena.wall_distance(start, vector, reach)
                    path.append(translate(start, vector, min(reach, wall)))
                break
            _, _, target = min(hits)
            path.append(target.center)
            short = target.kind == "mech" and "laser" in target.kinds
            if short:
                target.short_until = self.t + st["short_s"]
                if charging := target.charging:
                    charging.charge_start, charging.release = None, False
            self.hit(m, target, "lightning", damage, path[-2], "short" if short else None)
            struck.add(target)
            origin = target.pos
            damage *= st["chain_falloff"]
        self.beam(m, "lightning", path)

    def triggers(self, m):
        for i, w in enumerate(m.weapons):
            if w is None:
                continue
            st = m.weapon_stats[w.kind]
            fire = m.action.get("fire", ())
            fire = bool(fire[i]) if i < len(fire) else False
            if w.kind == "gun":
                if w.reload_end and self.t + 1e-9 >= w.reload_end:
                    w.ammo, w.reload_end = st["mag"], 0
                if not w.reload_end and (w.ammo == 0 or (m.action.get("reload") and w.ammo < st["mag"])):
                    w.reload_end = self.t + st["reload"]
                    self.sound("reload", m.pos, m)
                if fire and not w.reload_end and self.t + 1e-9 >= w.ready:
                    self.shoot(m, w, st)
                    w.ammo -= 1
            elif w.kind == "laser":
                if w.charge_start is None:
                    if fire and self.t >= max(w.ready, m.short_until):
                        w.charge_start = self.t
                        w.release = False
                        self.sound("laser_charge", m.pos, m)
                else:
                    w.release |= not fire
                    elapsed = self.t - w.charge_start
                    if (w.release and elapsed + 1e-9 >= st["min_charge"]) or elapsed >= st["charge"] + st["hold_s"]:
                        frac = st["min_frac"] + (1 - st["min_frac"]) * min(1, elapsed / st["charge"])
                        self.shoot(m, w, st, frac)
                        w.charge_start, w.release = None, False
            elif fire and self.t + 1e-9 >= w.ready and m.energy >= st.get("energy", 0):
                self.shoot(m, w, st)

    def blast(self, q, pos, direct):
        st = q.stats
        self.sound("explosion", pos, q.owner)
        targets = list(self.targets(q.owner))
        if q.owner.hp > 0:
            targets.append(q.owner)
        if direct:
            self.hit(q.owner, direct, "mortar", q.damage, q.pos)
        for m in targets:
            d = math.dist(pos, m.center)
            if m.hp <= 0 or d > st["splash_radius"] or not self.grid.los(*pos, *m.center):
                continue
            factor = 1 - d / st["splash_radius"] * (1 - st["splash_edge"])
            damage = st["splash"] * q.damage / st["damage"] * factor
            if m is q.owner:
                damage *= m.stats["self_damage_mult"]
            if m.kind == "mech":
                self.spend(m, st["drain"] * factor)
                # shortcut: grounded concussion applies horizontal knock only, add vertical physics if needed.
                ux, uy = unit(m.pos[0] - pos[0], m.pos[1] - pos[1])
                m.vel = (m.vel[0] + ux * st["knock"] * factor, m.vel[1] + uy * st["knock"] * factor, m.vel[2])
            self.hit(q.owner, m, "mortar", damage, pos, "concuss" if m.kind == "mech" else None)

    def fly_projectiles(self):
        remaining = []
        for q in self.projectiles:
            duration = min(self.dt, q.expires - self.t)
            if duration <= 0:
                continue
            vx, vy, vz = q.vel
            g = q.stats["gravity"] if q.kind == "mortar" else 0
            vz -= g * duration / 2
            speed = math.sqrt(vx * vx + vy * vy + vz * vz)
            vector = (vx / speed, vy / speed, vz / speed)
            length = speed * duration
            hits = self.ray_targets(q.owner, q.pos, vector, length, q.radius)
            wall = self.arena.wall_distance(q.pos, vector, length)
            direct = hits[0][2] if hits and hits[0][0] < wall else None
            if direct or wall <= length:
                if q.kind == "mortar":
                    d = hits[0][0] if direct else max(0, wall - self.grid.C / 2)
                    self.blast(q, translate(q.pos, vector, d), direct)
                elif direct:
                    # Travel direction determines which side a projectile hits.
                    source = translate(q.pos, vector, -direct.stats["radius"])
                    self.hit(q.owner, direct, q.kind, q.damage, source)
            elif duration == self.dt:
                q.pos = translate(q.pos, vector, length)
                q.vel = (vx, vy, vz - g * duration / 2)
                remaining.append(q)
        self.projectiles = remaining

    def squad(self):
        p = self.player
        alive = [m for m in self.house if m.hp > 0]
        n = len(alive) if self.t >= self.all_after else 1 + math.floor(self.kills * self.per_kill)
        self.hunters = sorted(alive, key=lambda m: (SQUAD.index(m.difficulty), distance(m.pos, p.pos)))[:n]
        active = set(self.hunters)
        # shortcut: use a shared coarse search fix before contact, replace with patrols if acquisition matters.
        if not hasattr(self, "last_seen") or any(self.visible(m, p.pos, p.stats["height"]) for m in alive):
            self.last_seen = p.pos
        for m in alive:
            mx, my, _ = m.pos
            in_circle = distance(m.pos, self.zone_center) < self.zone_radius - 12
            if m not in active:
                m.action = {}
                if self.tick % (4 * self.interval) == 0:
                    if not in_circle:
                        m.home = self.zone_center
                    elif distance(m.pos, p.pos) < 80:
                        dx, dy = unit(mx - p.pos[0], my - p.pos[1])
                        target = mx + dx * 60, my + dy * 60
                        m.home = target if self.grid.free(*target) else self.zone_center
                    elif m.home is not None and distance(m.pos, m.home) < 12:
                        m.home = None
                if m.home is not None:
                    m.action["move"] = m.nav.dir_to(mx, my, *m.home, self.t)
                continue
            aim_error, lead, reaction, preferred = HOUSE[m.difficulty]
            d = distance(m.pos, p.pos)
            clear = d < m.weapon_stats["laser"]["range"] and self.grid.los(
                *at_height(m.pos, m.stats["muzzle_height"]), *p.center)
            if self.t + 1e-9 >= m.next_react:
                m.next_react = self.t + reaction
                if self.rng.random() < reaction * 0.65:
                    m.strafe *= -1
                gun = m.weapon_stats["gun"]
                laser = m.weapons[1] and m.weapons[1].kind == "laser"
                laser_ready = laser and (m.charging or m.weapons[1].ready <= self.t)
                travel = 0 if laser_ready else min(d, gun["range"]) / gun["speed"] * lead
                target = translate(p.center, p.vel, travel)
                source = at_height(m.pos, m.stats["muzzle_height"])
                sigma = math.radians(aim_error)
                m.desired = (bearing(source, target) + self.rng.gauss(0, sigma),
                             math.atan2(target[2] - source[2], distance(source, target)) + self.rng.gauss(0, sigma))
            if not in_circle:
                move = m.nav.dir_to(mx, my, *self.zone_center, self.t)
            elif clear:
                if m.weapons[1] and m.weapons[1].kind == "lightning":
                    preferred = m.weapon_stats["lightning"]["range"] * 0.8
                rx, ry = unit(p.pos[0] - mx, p.pos[1] - my)
                radial = clamp((d - preferred) / 25, -1, 1)
                sx, sy = -ry * m.strafe, rx * m.strafe
                move = unit(radial * rx + 0.75 * sx, radial * ry + 0.75 * sy)
                if not self.grid.free(mx + move[0] * 4, my + move[1] * 4):
                    m.strafe *= -1
                    move = unit(radial * rx - 0.75 * sx, radial * ry - 0.75 * sy)
                    if not self.grid.free(mx + move[0] * 4, my + move[1] * 4):
                        move = m.nav.dir_to(mx, my, *p.pos[:2], self.t)
            else:
                goal = self.last_seen
                if distance(m.pos, goal) < 12:
                    # A teammate needs to reacquire a moving target beyond the last sighting.
                    goal = p.pos
                move = m.nav.dir_to(mx, my, *goal[:2], self.t)
            aligned = abs(wrap(m.desired[0] - m.aim[0])) < math.radians(8)
            gun_fire = clear and aligned and d < m.weapon_stats["gun"]["range"]
            second = False
            if m.weapons[1] is not None:
                kind = m.weapons[1].kind
                w = m.weapon_stats[kind]
                if kind == "laser" and m.charging:
                    second = clear and self.t - m.charging.charge_start < w["charge"]
                else:
                    second = clear and aligned and d < w["range"]
            m.action = dict(move=move, fire=(gun_fire, second), boost=not in_circle and m.energy > m.stats["energy"] / 3)

    def drones(self):
        for m in self.npcs:
            if m.hp <= 0:
                continue
            st = m.stats
            home_distance = distance(m.pos, m.home)
            p = m.target
            if p and (p.hp <= 0 or distance(m.pos, p.pos) > st["deaggro_range"] or home_distance > st["chase_leash"]):
                m.target = p = None
            if p is None and home_distance <= st["leash"]:
                p = min(self.living, key=lambda b: distance(m.pos, b.pos))
                if distance(m.pos, p.pos) <= st["aggro_range"] and self.grid.los(*m.center, *p.center):
                    m.target = p
                else:
                    p = None
            if p is None:
                if home_distance > st["leash"]:
                    goal = m.home
                elif self.t >= m.next_react:
                    angle = self.rng.uniform(-math.pi, math.pi)
                    m.desired = (angle, 0)
                    m.next_react = self.t + st["leash"] / st["speed"]
                if home_distance <= st["leash"]:
                    goal = translate(m.pos, direction(*m.desired), st["leash"])
            else:
                goal = p.pos
                if self.t >= m.next_shot and self.grid.los(*m.center, *p.center):
                    yaw = bearing(m.pos, p.pos)
                    pitch = math.atan2(p.center[2] - m.center[2], distance(m.pos, p.pos))
                    m.aim = (yaw, pitch)
                    noise = math.radians(st["spread_deg"])
                    vector = direction(yaw + self.rng.gauss(0, noise), pitch + self.rng.gauss(0, noise))
                    vel = tuple(v * st["projectile_speed"] for v in vector)
                    self.projectiles.append(Projectile(next(self.ids["projectile"]), m, "npc", m.center, vel,
                                                       self.t + st["deaggro_range"] / st["projectile_speed"],
                                                       st["damage"], st, self.cfg["projectile"]["npc_radius"]))
                    self.sound("npc_gun", m.pos, m)
                    m.next_shot = self.t + st["cooldown"]
            dx, dy = unit(goal[0] - m.pos[0], goal[1] - m.pos[1])
            self.move(m, dx * st["speed"], dy * st["speed"], self.cfg["mech"]["ground_accel"])

    def player_decision(self, obs):
        start = time.perf_counter_ns()
        action = self.bot.act(obs)
        elapsed = (time.perf_counter_ns() - start) / 1e6
        self.act_ms.append(elapsed)
        label = (mf.draw.take() or {}).get("label", "").split()
        mode = label[0].rstrip("!") if label else ""
        if mode in {"get", "cube", "drop", "drone"}:
            mode = "loot"
        elif mode not in {"fight", "hold", "retreat", "heal", "roam", "zone"}:
            mode = "unlabeled"
        self.modes[mode] += 1
        self.mode = mode
        player = self.player
        if elapsed > self.cfg["bot"]["tick_budget_ms"]:
            # Match transport would drop a late action and clear its triggers.
            coast = self.cfg["bot"]["coast_s"]
            action = {k: player.action[k] for k in ("move", "boost", "aim") if k in player.action} if (
                self.t - self.last_action <= coast) else {}
        else:
            self.last_action = self.t
        player.action = action
        if "aim" in action:
            player.desired = action["aim"]
        self.equipment(player)
        if self.offer(player):
            pick = action.get("pick")
            if isinstance(pick, (int, float)) and 0 <= pick < len(player.offer["choices"]) and pick == int(pick):
                self.pick(player, int(pick))
                self.offer(player)
        self.move_history.append((self.t, player.pos))
        while self.t - self.move_history[0][0] > 1.2:
            self.move_history.pop(0)
        old_t, old_pos = self.move_history[0]
        if self.t - old_t >= 1 and math.hypot(*action.get("move", (0, 0))) > 0.5 and distance(old_pos, player.pos) < 2:
            self.stuck += 1

    def timeline(self):
        p = self.player
        hunters = ", ".join(f"{m.id}/{m.difficulty}:{distance(m.pos, p.pos):.0f}m" for m in self.hunters if m.hp > 0)
        print(f"{self.t:6.1f}s {self.mode:8} hp={p.hp:6.0f} energy={p.energy:5.1f} "
              f"pos=({p.pos[0]:.0f},{p.pos[1]:.0f}) kills={self.kills} cubes={p.cubes} "
              f"weapons={','.join(p.kinds)} hunters=[{hunters}]", file=sys.stderr)

    def run(self, verbose=False):
        p = self.player
        self.living = self.mechs.copy()
        self.death_ticks = {}
        self.last_action = -math.inf
        ticks = round(self.cfg["match"]["duration_s"] / self.dt)
        trace_ticks = round(5 / self.dt)
        for self.tick in range(ticks):
            self.t = self.tick * self.dt
            zone = self.zone()
            if self.tick % self.interval == 0:
                self.player_decision(self.observation(zone))
                self.squad()
                if verbose and self.tick % trace_ticks == 0:
                    self.timeline()
            if p.offer is not None and self.t >= p.offer["expires"]:
                self.pick(p, 0)
                self.offer(p)
            for m in self.living:
                self.move_mech(m, zone)
            self.separate_player()
            for m in self.living:
                if m.hp > 0 and (m is p or m in self.hunters):
                    self.triggers(m)
            self.drones()
            self.fly_projectiles()
            if self.cubes or self.drops:
                self.collect()
            if self.death_ticks:
                self.living = [m for m in self.living if m.hp > 0]
            if p.hp <= 0 or len(self.living) == 1:
                break
        if p.hp <= 0:
            points = sum(tick < self.death_ticks[p.id] for tick in self.death_ticks.values())
        else:
            points = len(self.mechs) - 1 - sum(m.hp > p.hp for m in self.living)
        if verbose:
            self.timeline()
            print(f"finish {self.t:.2f}s points={points} killer={self.killer} damage={dict(self.damage)}", file=sys.stderr)
        return dict(points=points, kills=self.kills, death_time=self.death_time, killer=self.killer,
                    damage=self.damage, modes=self.modes, stuck=self.stuck, act_ms=self.act_ms,
                    wall_s=time.perf_counter() - self.start_wall)


def load_hello(kit):
    with gzip.open(kit / "check" / "stream.jsonl.gz", "rt") as stream:
        hello = json.loads(next(stream))
    hello["map"]["dir"] = str((kit / "arena").resolve())
    return hello


def load_bot(path):
    if path is None:
        return Bot
    # The starter calls mf.run at import time. Capture its class without starting the transport.
    with patch.object(mf, "run"):
        return runpy.run_path(str(path))["Bot"]


def summarize(results):
    samples = sorted(elapsed for r in results for elapsed in r["act_ms"])
    total = len(samples)
    deaths = [r["death_time"] for r in results if r["death_time"] is not None]
    damage = Counter()
    modes = Counter()
    killers = Counter()
    for r in results:
        damage.update(r["damage"])
        modes.update(r["modes"])
        if r["killer"]:
            killers["/".join(r["killer"])] += 1
    return dict(matches=len(results), mean_points=statistics.mean(r["points"] for r in results),
                mean_kills=statistics.mean(r["kills"] for r in results),
                mean_death_s=statistics.mean(deaths) if deaths else None,
                deaths=len(deaths), killed_by=dict(killers.most_common()),
                damage_taken_per_match={k: round(v / len(results), 1) for k, v in damage.most_common()},
                mode_pct={k: round(n / total * 100, 2) for k, n in modes.most_common()},
                stuck_pct=round(sum(r["stuck"] for r in results) / total * 100, 2),
                act_p50_ms=round(statistics.median(samples), 3),
                act_p99_ms=round(samples[math.ceil(0.99 * total) - 1], 3),
                act_max_ms=round(samples[-1], 3),
                mean_wall_s=round(statistics.mean(r["wall_s"] for r in results), 3),
                max_wall_s=round(max(r["wall_s"] for r in results), 3),
                points_by_seed=[r["points"] for r in results])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, default=KIT)
    parser.add_argument("--bot", type=Path, help="alternate Python bot with a Bot class")
    parser.add_argument("--matches", type=int, default=len(SEEDS), choices=range(1, len(SEEDS) + 1),
                        metavar="1–100", help="run the first N fixed seeds")
    parser.add_argument("--seed", type=int, help="run one match with this seed")
    parser.add_argument("--per-kill", type=float, default=0.65, help="additional hunters per credited kill")
    parser.add_argument("--all-after", type=float, default=240, help="send all surviving hunters at this match time")
    parser.add_argument("--verbose", action="store_true", help="print the first match as a five-second timeline")
    args = parser.parse_args()
    if not all(math.isfinite(v) and v >= 0 for v in (args.per_kill, args.all_after)):
        parser.error("hunter settings must be finite and nonnegative")
    hello = load_hello(args.kit)
    arena = Arena(hello)
    bot_type = load_bot(args.bot)
    seeds = (args.seed,) if args.seed is not None else SEEDS[:args.matches]
    results = []
    for seed in seeds:
        match = Match(hello, arena, bot_type, seed, args.per_kill, args.all_after)
        results.append(match.run(args.verbose and not results))
    print(json.dumps(dict(seeds=list(seeds), **summarize(results)), indent=2))


if __name__ == "__main__":
    main()

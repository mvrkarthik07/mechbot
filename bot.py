"""Mech Royale bot v1 (mechfight/1).

Plan, per decision (10 Hz):
  1. Read the world: our state, visible mechs/NPCs, loot, zone, events.
  2. Pick a mode: ZONE (get inside), FIGHT, RETREAT (break line of sight and regen),
     LOOT (weapons, cubes, drones, crates, supply drops), ROAM.
  3. Legs and torso are independent: movement comes from the mode, aim always tracks
     the most useful target (enemy > drone > crate), with lead for the gun.

Placement is what scores, so the bot fights only good trades, disengages to regen,
and never loses to the zone.
"""
import heapq
import math
import os
import random
import sys
import time
from array import array

import mechfight as mf

TAU = 2 * math.pi

# ---- experiment knobs (change one per submission) ----
VERSION = "v3"
WEAPON_RANK = {"laser": 3, "lightning": 2, "mortar": 1, "gun": 0}
RETREAT_HP = 0.40        # disengage below this HP fraction when losing
BOOST_STRAFE = True      # burst-boost sideways in fights to dodge bullets
SILENT_ROAM = True       # walk under 5 m/s (no footstep sound) when idle after the first minute
HEAL_HP = 0.85           # below this with no enemy in sight: stop farming so out-of-combat regen kicks in
EARLY_LOOT_RANGE = 300.0 # how far to go for a first weapon early on
HOLD_WHEN_OUTNUMBERED = True  # 2+ enemies close: fight from cover so they come one at a time
FIGHT_RANGE = 95.0       # preferred range with gun/laser
UPGRADE_SCORE = {"plating": 12, "nanites": 10, "armor": 9, "laser_damage": 8, "laser_charge": 8,
                 "gun_rate": 7, "gun_damage": 7, "lightning_efficiency": 7, "gyros": 6,
                 "lightning_range": 6, "gun_mag": 6, "reactor": 5, "sensors": 5, "gun_velocity": 5,
                 "mortar_reload": 5, "lightning_chain": 4, "capacitor": 4, "servos": 4,
                 "mortar_splash": 4, "jets": 3, "mortar_velocity": 3, "laser_pierce": 3}


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def unit(dx, dy):
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d > 1e-6 else (0.0, 0.0)


# --------------------------------------------------------------------------- map
class GridMap:
    """2 m grid over the arena: ground height, building/stadium/bridge solids, walkability."""

    C = 2.0
    expansion_limit = None

    def __init__(self, mdir, files, step_up=1.2, max_slope_deg=50.0):
        self.ok = False
        t0 = time.time()
        try:
            self._load(mdir, files, step_up, max_slope_deg)
            self.ok = True
            mf.log(f"map ok {self.W}x{self.H} in {time.time() - t0:.2f}s")
        except Exception as e:  # play without a map rather than not at all
            mf.log(f"map load failed: {e!r}")

    def _load(self, mdir, files, step_up, max_slope_deg):
        import json

        wpath = os.path.join(mdir, next((f for f in files if f.endswith(".json")), "v2/world.json"))
        with open(wpath) as f:
            w = json.load(f)
        ter = w["terrain"]
        tpath = os.path.join(os.path.dirname(wpath), ter.get("file", "terrain.i16"))
        th = array("h")
        with open(tpath, "rb") as f:
            th.frombytes(f.read())
        if sys.byteorder == "big":
            th.byteswap()
        tnx, tny = int(ter["nx"]), int(ter["ny"])
        tminx, tminy, tstep = float(ter["minX"]), float(ter["minY"]), float(ter.get("step", 1.0))
        scale = float(ter.get("scale", 0.01))
        C = self.C
        self.ox, self.oy = tminx, tminy
        W = self.W = int((tnx - 1) * tstep / C)
        H = self.H = int((tny - 1) * tstep / C)
        N = W * H

        # ground height (cell center) and steepness from the 1 m terrain grid
        gnd = array("f", bytes(4 * N))
        steep = bytearray(N)
        lim = math.tan(math.radians(max_slope_deg)) * tstep / scale * 0.98  # in raw units per sample
        r = int(round(C / tstep))
        for j in range(H):
            tj = j * r
            for i in range(W):
                ti = i * r
                k = tj * tnx + ti
                gnd[j * W + i] = th[k + (r // 2) * tnx + r // 2] * scale
                mx = 0
                for dj in range(r):
                    base = k + dj * tnx
                    for di in range(r):
                        a = th[base + di]
                        d1 = abs(th[base + di + 1] - a)
                        d2 = abs(th[base + di + tnx] - a)
                        if d1 > mx:
                            mx = d1
                        if d2 > mx:
                            mx = d2
                if mx > lim:
                    steep[j * W + i] = 1
        self.gnd = gnd

        # solids: per cell lowest base / highest top (LOS), plus elevated pieces kept apart
        base = array("f", [1e9]) * N
        top = array("f", [-1e9]) * N
        elev = {}
        block = bytearray(N)
        for p in w.get("prisms", []):
            rings = [p["ring"]]
            holes = p.get("holes") or []
            if holes and isinstance(holes[0], (int, float)):
                holes = [holes]
            rings += [h for h in holes if len(h) >= 6]
            pb, pt, kind = float(p["base"]), float(p["top"]), p.get("kind", "building")
            for c in self._cells(rings):
                g = gnd[c]
                if pb - g > 3.0:  # elevated deck (bridge over a road): blocks sight/shots at its height only
                    elev.setdefault(c, []).append((pb, pt))
                    if pb - g < 9.0 and kind != "bridge":
                        block[c] = 1
                    continue
                if pb < base[c]:
                    base[c] = pb
                if pt > top[c]:
                    top[c] = pt
                if kind != "bridge" and pt - g > step_up:
                    block[c] = 1
        self.base, self.top, self.elev = base, top, elev
        for c in range(N):
            if steep[c]:
                block[c] = 1
        self.block = block
        # inflate by one cell for planning (mech radius 2.5 m)
        inf = bytearray(block)
        for c in range(N):
            if block[c]:
                i, j = c % W, c // W
                for dj in (-1, 0, 1):
                    jj = j + dj
                    if 0 <= jj < H:
                        row = jj * W
                        for di in (-1, 0, 1):
                            ii = i + di
                            if 0 <= ii < W:
                                inf[row + ii] = 1
        # map edge is a wall
        for i in range(W):
            inf[i] = inf[(H - 1) * W + i] = 1
        for j in range(H):
            inf[j * W] = inf[j * W + W - 1] = 1
        self.inf = inf

    def _cells(self, rings):
        """Scanline fill (even-odd over ring + holes) of cell centers, plus every vertex cell."""
        C, W, H, ox, oy = self.C, self.W, self.H, self.ox, self.oy
        edges = []
        ymin, ymax = 1e18, -1e18
        out = set()
        for rg in rings:
            n = len(rg) // 2
            for k in range(n):
                x0, y0 = rg[2 * k], rg[2 * k + 1]
                k2 = (k + 1) % n
                x1, y1 = rg[2 * k2], rg[2 * k2 + 1]
                if y0 != y1:
                    edges.append((x0, y0, x1, y1))
                ymin, ymax = min(ymin, y0), max(ymax, y0)
        for k in range(0, len(rings[0]) - 1, 2):
            i, j = int((rings[0][k] - ox) / C), int((rings[0][k + 1] - oy) / C)
            if 0 <= i < W and 0 <= j < H:
                out.add(j * W + i)
        j0 = max(0, int(math.ceil((ymin - oy) / C - 0.5)))
        j1 = min(H - 1, int(math.floor((ymax - oy) / C - 0.5)))
        for j in range(j0, j1 + 1):
            yc = oy + (j + 0.5) * C
            xs = []
            for x0, y0, x1, y1 in edges:
                if (y0 <= yc < y1) or (y1 <= yc < y0):
                    xs.append(x0 + (yc - y0) * (x1 - x0) / (y1 - y0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                i0 = max(0, int(math.ceil((xs[k] - ox) / C - 0.5)))
                i1 = min(W - 1, int(math.floor((xs[k + 1] - ox) / C - 0.5)))
                row = j * W
                for i in range(i0, i1 + 1):
                    out.add(row + i)
        return out

    # -- queries
    def cell(self, x, y):
        i, j = int((x - self.ox) / self.C), int((y - self.oy) / self.C)
        if 0 <= i < self.W and 0 <= j < self.H:
            return j * self.W + i
        return None

    def center(self, c):
        return self.ox + (c % self.W + 0.5) * self.C, self.oy + (c // self.W + 0.5) * self.C

    def ground(self, x, y):
        c = self.cell(x, y) if self.ok else None
        return self.gnd[c] if c is not None else 0.0

    def free(self, x, y):
        if not self.ok:
            return True
        c = self.cell(x, y)
        return c is not None and not self.inf[c]

    def los(self, ax, ay, az, bx, by, bz, step=1.5):
        """Straight line clear of terrain and solids (trees ignored: they never stop shots)."""
        if not self.ok:
            return True
        dx, dy, dz = bx - ax, by - ay, bz - az
        n = int(math.sqrt(dx * dx + dy * dy + dz * dz) / step) + 1
        C, W, H, ox, oy = self.C, self.W, self.H, self.ox, self.oy
        gnd, base, top, elev = self.gnd, self.base, self.top, self.elev
        for k in range(1, n):
            f = k / n
            px, py, pz = ax + dx * f, ay + dy * f, az + dz * f
            i, j = int((px - ox) / C), int((py - oy) / C)
            if not (0 <= i < W and 0 <= j < H):
                return False
            c = j * W + i
            if pz < gnd[c] - 0.3 or base[c] <= pz <= top[c]:
                return False
            if elev:
                e = elev.get(c)
                if e:
                    for b, t in e:
                        if b <= pz <= t:
                            return False
        return True

    def walk_clear(self, ax, ay, bx, by, step=1.5):
        if not self.ok:
            return True
        dx, dy = bx - ax, by - ay
        n = int(math.hypot(dx, dy) / step) + 1
        inf = self.inf
        start = self.cell(ax, ay)
        for k in range(1, n + 1):
            c = self.cell(ax + dx * k / n, ay + dy * k / n)
            if c is None:
                return False
            if inf[c] and c != start:
                return False
        return True

    def nearest_free(self, c, rad=6):
        if not self.inf[c]:
            return c
        W, H = self.W, self.H
        i, j = c % W, c // W
        for r in range(1, rad + 1):
            for dj in range(-r, r + 1):
                for di in (-r, r) if abs(dj) != r else range(-r, r + 1):
                    ii, jj = i + di, j + dj
                    if 0 <= ii < W and 0 <= jj < H and not self.inf[jj * W + ii]:
                        return jj * W + ii
        return None

    def astar(self, sx, sy, gx, gy, budget_s=0.006):
        """A* on the inflated grid; returns world waypoints, or a partial path toward the goal."""
        s, g = self.cell(sx, sy), self.cell(gx, gy)
        if s is None or g is None:
            return None
        g = self.nearest_free(g) or g
        W, H, inf = self.W, self.H, self.inf
        if not hasattr(self, "_gs"):
            N = W * H
            self._gs = array("d", bytes(8 * N))
            self._came = array("i", bytes(4 * N))
            self._stamp = array("i", bytes(4 * N))
            self._run = 0
        self._run += 1
        run, gs, came, stamp = self._run, self._gs, self._came, self._stamp
        gi, gj = g % W, g // W
        SQ2, K = 1.4142, 1.4142 - 2
        nb = ((1, 1.0, 0, 0), (-1, 1.0, 0, 0), (W, 1.0, 0, 0), (-W, 1.0, 0, 0),
              (W + 1, SQ2, W, 1), (W - 1, SQ2, W, -1), (-W + 1, SQ2, -W, 1), (-W - 1, SQ2, -W, -1))
        NN = W * H
        di0, dj0 = abs(s % W - gi), abs(s // W - gj)
        h0 = di0 + dj0 + K * (di0 if di0 < dj0 else dj0)
        stamp[s] = run
        gs[s] = 0.0
        came[s] = -1
        openh = [(h0, 0.0, s)]
        best, besth = s, h0
        t0 = time.perf_counter()
        n = 0
        expansion_limit = self.expansion_limit
        pop, push, pc = heapq.heappop, heapq.heappush, time.perf_counter
        while openh:
            _, gc, c = pop(openh)
            if gc > gs[c]:
                continue
            if c == g:
                best = c
                break
            n += 1
            if expansion_limit is not None:
                if n >= expansion_limit:
                    break
            elif (n & 127) == 0 and pc() - t0 > budget_s:
                break
            ci = c % W
            for off, cost, o1, o2 in nb:
                nc = c + off
                if nc < 0 or nc >= NN:
                    continue
                ni = nc % W
                if ni - ci > 1 or ci - ni > 1 or inf[nc]:
                    continue
                if o1 and (inf[c + o1] or inf[c + o2]):
                    continue  # no corner cutting
                ng = gc + cost
                if stamp[nc] != run or ng < gs[nc]:
                    stamp[nc] = run
                    gs[nc] = ng
                    came[nc] = c
                    a, b = abs(ni - gi), abs(nc // W - gj)
                    hn = a + b + K * (a if a < b else b)
                    push(openh, (ng + 1.5 * hn, ng, nc))
                    if hn < besth:
                        besth, best = hn, nc
        path = []
        c = best
        while c != -1:
            path.append(self.center(c))
            c = came[c]
        path.reverse()
        return path


class Nav:
    """Follows A* paths with line-of-walk smoothing; straight line when it's clear."""

    def __init__(self, m):
        self.m = m
        self.path = None
        self.goal = None
        self.plan_t = -99.0
        self.ptr = 0

    def reset(self):
        self.path = None

    def dir_to(self, x, y, gx, gy, t):
        dx, dy = gx - x, gy - y
        d = math.hypot(dx, dy)
        if d < 1.0:
            return 0.0, 0.0
        m = self.m
        if not m.ok or (d < 80 and m.walk_clear(x, y, gx, gy)):
            self.path = None
            return dx / d, dy / d
        moved = self.goal is None or math.hypot(self.goal[0] - gx, self.goal[1] - gy) > 10
        stale = self.path is None or (moved and t - self.plan_t > 1.0) or t - self.plan_t > 4.0
        if stale:
            self.path = m.astar(x, y, gx, gy)
            self.goal, self.plan_t, self.ptr = (gx, gy), t, 0
        p = self.path
        if not p or len(p) < 2:
            return dx / d, dy / d
        # snap pointer to the nearest waypoint ahead
        best, bi = 1e18, self.ptr
        for k in range(self.ptr, min(len(p), self.ptr + 12)):
            dd = math.hypot(p[k][0] - x, p[k][1] - y)
            if dd < best:
                best, bi = dd, k
        self.ptr = bi
        tx, ty = p[min(bi + 1, len(p) - 1)]
        for k in range(min(len(p) - 1, bi + 8), bi, -1):
            if m.walk_clear(x, y, p[k][0], p[k][1]):
                tx, ty = p[k]
                break
        return unit(tx - x, ty - y)


# --------------------------------------------------------------------------- bot
class Bot:
    name = "kt-mech-" + VERSION

    def __init__(self, hello):
        cfg = hello.get("config", {})
        self.cfg = cfg
        random.seed(hello.get("seed", 0))
        mech = cfg.get("mech", {})
        mp = hello.get("map", {})
        self.map = GridMap(mp.get("dir", "/arena"), mp.get("files", ["v2/world.json"]),
                           mech.get("step_up", 1.2), mech.get("max_slope_deg", 50))
        self.nav = Nav(self.map)
        self.reach = cfg.get("loot", {}).get("pickup_radius", 4.0)
        self.cube_r = cfg.get("cubes", {}).get("pickup_radius", 3.5)
        self.vision_near = cfg.get("vision", {}).get("near_range", 45)
        self.mortar_g = cfg.get("weapons", {}).get("mortar", {}).get("gravity", 22)
        self.upgrades = {u["id"]: u for u in cfg.get("upgrades", [])}
        self.last_damaged = -99.0
        self.last_dealt = -99.0
        self.last_attacker = None
        self.dmg_bearing = None
        self.sound_bearing = None
        self.sound_t = -99.0
        self.strafe = 1
        self.strafe_until = 0.0
        self.mode = "roam"
        self.retreat_until = -1.0
        self.cover = None
        self.cover_t = -99.0
        self.hist = []  # (t, x, y) for stuck detection
        self.unstick_until = -1.0
        self.unstick_dir = (0.0, 0.0)
        self.picked_offer = None
        self.bad_pickups = set()
        self.roam_goal = None
        self.scan_phase = 0.0
        self.seen = {}  # enemy id -> (t, mech dict)
        self.known_pickups = {}  # id -> (kind, pos, expires)
        self.known_cubes = {}    # id -> (pos, expires)

    # ------------------------------------------------------------- helpers
    def zone_now(self, z, t):
        if t < z["shrink_start"]:
            return z["center"], z["radius"]
        f = clamp((t - z["shrink_start"]) / max(1e-6, z["shrink_end"] - z["shrink_start"]), 0, 1)
        cx = z["center"][0] + (z["next_center"][0] - z["center"][0]) * f
        cy = z["center"][1] + (z["next_center"][1] - z["center"][1]) * f
        return (cx, cy), z["radius"] + (z["next_radius"] - z["radius"]) * f

    def point_safe(self, px, py, z, t, margin=10.0):
        """Will (px, py) still be inside the zone a little after we could get there?"""
        (cx, cy), r = self.zone_now(z, t + 15)
        return math.hypot(px - cx, py - cy) < r - margin

    def zone_goal(self, x, y, z, t, speed):
        """Where to stand to stay ahead of the zone, or None if we're fine."""
        nc, nr = z["next_center"], z["next_radius"]
        dn = math.hypot(x - nc[0], y - nc[1])
        (cx, cy), r = self.zone_now(z, t)
        dc = math.hypot(x - cx, y - cy)
        want = max(0.0, nr * 0.6)
        travel = max(0.0, dn - want) / max(1.0, speed)
        urgent = dc > r - 8
        soon = t + travel + 20 > z["shrink_start"]
        if urgent or (soon and dn > nr * 0.85):
            ux, uy = unit(x - nc[0], y - nc[1])
            return (nc[0] + ux * want, nc[1] + uy * want), urgent
        return None, False

    def lead(self, ox, oy, oz, tx, ty, tz, vx, vy, vz, speed):
        px, py, pz = tx - ox, ty - oy, tz - oz
        a = vx * vx + vy * vy + vz * vz - speed * speed
        b = 2 * (px * vx + py * vy + pz * vz)
        c = px * px + py * py + pz * pz
        tt = None
        if abs(a) < 1e-6:
            if b < 0:
                tt = -c / b
        else:
            disc = b * b - 4 * a * c
            if disc >= 0:
                sq = math.sqrt(disc)
                cands = [r for r in ((-b - sq) / (2 * a), (-b + sq) / (2 * a)) if r > 0]
                tt = min(cands) if cands else None
        if tt is None:
            tt = math.sqrt(c) / speed
        tt += 0.05  # decision latency
        return tx + vx * tt, ty + vy * tt, tz + vz * tt * 0.5

    @staticmethod
    def aim_at(ox, oy, oz, tx, ty, tz):
        dx, dy = tx - ox, ty - oy
        return math.atan2(dy, dx), math.atan2(tz - oz, math.hypot(dx, dy))

    def mortar_pitch(self, d, dz, v, high):
        g = self.mortar_g
        if d < 1:
            return None
        k = g * d * d / (2 * v * v)
        disc = d * d - 4 * k * (dz + k)
        if disc < 0:
            return None
        sq = math.sqrt(disc)
        u = (d + sq) / (2 * k) if high else (d - sq) / (2 * k)
        return math.atan(u)

    def pick_upgrade(self, offer, have):
        def score(ch):
            cid = ch["id"]
            s = UPGRADE_SCORE.get(cid, 3)
            req = self.upgrades.get(cid, {}).get("requires")
            if req and req not in have:
                s -= 5
            return s
        ch = offer.get("choices", [])
        return max(range(len(ch)), key=lambda i: score(ch[i])) if ch else 0

    # ------------------------------------------------------------- main
    def act(self, obs):
        t = obs["t"]
        me = obs["self"]
        x, y, z = me["pos"]
        hp, mhp = me["hp"], me["max_hp"]
        hpf = hp / max(1.0, mhp)
        energy = me.get("energy", 0)
        st = me.get("stats", {})
        walk = st.get("walk_speed", 11.7)
        muz_z = z + st.get("muzzle_height", 7.0)
        eye_z = z + st.get("eye_height", 8.0)
        cur_yaw, cur_pitch = me["aim"]
        weapons = me.get("weapons") or []
        kinds = {w["kind"]: i for i, w in enumerate(weapons) if w}
        zone = obs["zone"]
        act = {}
        label = ""

        # events
        for e in obs.get("events", []):
            et = e.get("type")
            if et == "damaged" and e.get("weapon") != "zone":
                self.last_damaged = t
                self.last_attacker = e.get("by")
                self.dmg_bearing = e.get("bearing")
            elif et == "hit":
                self.last_dealt = t
            elif et == "take_failed":
                if e.get("reason") == "gone":
                    self.known_pickups.pop(e.get("id"), None)
                else:
                    self.bad_pickups.add(e.get("id"))
            elif et == "took":
                self.known_pickups.pop(e.get("id"), None)
            elif et == "kill":
                s = self.seen.get(e.get("target"))
                if s:
                    self.known_cubes[("kill", e.get("target"))] = (s[1]["pos"], t + 25)
        for s in obs.get("sounds", []):
            if s.get("kind") in ("gun", "laser", "laser_charge", "lightning", "mortar", "step", "boost", "jet") \
                    and s.get("dist") in ("near", "mid"):
                self.sound_bearing, self.sound_t = s["bearing"], t

        # upgrade offer
        off = obs.get("offer")
        if off and off.get("id") != self.picked_offer:
            act["pick"] = self.pick_upgrade(off, kinds)
            self.picked_offer = off.get("id")

        mechs = [m for m in obs.get("mechs", []) if m.get("kind") == "mech" and m.get("id") != me.get("id")]
        for m in mechs:
            self.seen[m["id"]] = (t, m)
        self.update_memory(obs, x, y, eye_z, t)

        def dist(p):
            return math.hypot(p[0] - x, p[1] - y)

        # ---------------- target selection (enemy mechs)
        target = None
        if mechs:
            def tscore(m):
                d = dist(m["pos"])
                s = d / 60.0 + 2.0 * m.get("hp", 1400) / max(1, m.get("max_hp", 1400))
                if m["id"] == self.last_attacker and t - self.last_damaged < 3:
                    s -= 1.0
                return s
            target = min(mechs, key=tscore)
        tdist = dist(target["pos"]) if target else 1e9
        t_hpf = target.get("hp", 1400) / max(1, target.get("max_hp", 1400)) if target else 1.0
        t_light = target is not None and "lightning" in (target.get("weapons") or [])

        # ---------------- mode decision
        zgoal, zurgent = self.zone_goal(x, y, zone, t, walk)
        close_threats = [m for m in mechs if dist(m["pos"]) < 160]
        outnumbered = len(close_threats) >= 2
        if self.mode == "retreat":
            done = hpf > 0.85 or (not mechs and t - self.last_damaged > 8)
            if done or t > self.retreat_until:
                self.mode = "roam"
        if self.mode != "retreat" and target is not None:
            losing = hpf < RETREAT_HP and (t_hpf > hpf + 0.1 or outnumbered)
            if losing and t_hpf > 0.2:
                self.mode = "retreat"
                self.retreat_until = t + 12
                self.cover = None
        if self.mode != "retreat":
            if target is None:
                self.mode = "roam"
            elif HOLD_WHEN_OUTNUMBERED and outnumbered and not (len(close_threats) == 2 and min(
                    m.get("hp", 1400) / max(1, m.get("max_hp", 1400)) for m in close_threats) < 0.2):
                self.mode = "hold"
            else:
                self.mode = "fight"
        # regen needs 5 s without dealing OR taking damage: if we're being hit anyway, shooting back is free
        cornered = self.mode == "retreat" and target is not None and (tdist < 35 or t - self.last_damaged < 2.5)
        healing = self.mode == "roam" and hpf < HEAL_HP

        # ---------------- movement
        move = (0.0, 0.0)
        boost = False
        jump = False
        if self.mode == "fight":
            want = 30.0 if "lightning" in kinds else FIGHT_RANGE
            if t_light:
                want = max(want, 60.0)
            if t_hpf < 0.25:
                want = min(want, 60.0)  # press a weak target
            ex, ey = target["pos"][0], target["pos"][1]
            rx, ry = unit(ex - x, ey - y)
            has_los = self.map.los(x, y, eye_z, ex, ey, target["pos"][2] + 4.5)
            if t >= self.strafe_until:
                self.strafe = -self.strafe if random.random() < 0.7 else self.strafe
                self.strafe_until = t + random.uniform(0.5, 1.4)
            tx_, ty_ = -ry * self.strafe, rx * self.strafe
            if not self.map.free(x + tx_ * 6, y + ty_ * 6):
                self.strafe = -self.strafe
                tx_, ty_ = -tx_, -ty_
            if has_los:
                radial = clamp((tdist - want) / 25.0, -1.0, 1.0)
                mx, my = rx * radial * 0.8 + tx_, ry * radial * 0.8 + ty_
                move = unit(mx, my)
                if BOOST_STRAFE and "lightning" not in kinds and energy > 55 and tdist > 40:
                    boost = True
            else:
                # no line: close in along a path if healthy, else hold and wait at cover
                if hpf > 0.6:
                    move = self.nav.dir_to(x, y, ex, ey, t)
            # dodge a laser that is pointed at us
            if target.get("charging"):
                ay = target.get("aim", [0, 0])[0]
                if abs(wrap(ay - math.atan2(y - ey, x - ex))) < 0.2 and energy > 25:
                    move = (tx_, ty_)
                    boost = True
            label = f"fight {target['id']} d{tdist:.0f}"
        elif self.mode == "hold":
            cxs = sum(m["pos"][0] for m in close_threats) / len(close_threats)
            cys = sum(m["pos"][1] for m in close_threats) / len(close_threats)
            czs = max(m["pos"][2] for m in close_threats)
            stale = self.cover is None or t - self.cover_t > 1.0
            if not stale and self.map.los(cxs, cys, czs + 8, self.cover[0], self.cover[1],
                                         self.map.ground(*self.cover) + 5.0):
                stale = True
            if stale:
                c = self.find_cover(x, y, cxs, cys, czs + 8, zone, t)
                if c is not None or self.cover is None:
                    self.cover = c
                self.cover_t = t
            if self.cover and math.hypot(self.cover[0] - x, self.cover[1] - y) > 3:
                move = self.nav.dir_to(x, y, self.cover[0], self.cover[1], t)
            elif self.cover is None:
                # no cover nearby: strafe around the group, backing off if they're close
                if t >= self.strafe_until:
                    self.strafe = -self.strafe if random.random() < 0.7 else self.strafe
                    self.strafe_until = t + random.uniform(0.5, 1.4)
                bx, by = unit(x - cxs, y - cys)
                sx_, sy_ = -by * self.strafe, bx * self.strafe
                back = 0.8 if tdist < 70 else 0.0
                move = unit(sx_ + bx * back, sy_ + by * back)
                boost = BOOST_STRAFE and energy > 55 and "lightning" not in kinds
            else:
                move = (0.0, 0.0)  # in cover: let them come around the corner one at a time
            label = f"hold x{len(close_threats)}"
        elif self.mode == "retreat":
            ref = target or (self.seen.get(self.last_attacker, (0, None))[1])
            if ref is not None:
                ex, ey, ez = ref["pos"]
                if self.cover is None or t - self.cover_t > 1.0:
                    self.cover = self.find_cover(x, y, ex, ey, ez + 8, zone, t)
                    self.cover_t = t
                if self.cover:
                    move = self.nav.dir_to(x, y, self.cover[0], self.cover[1], t)
                else:
                    move = unit(x - ex, y - ey)
                boost = energy > 35 and tdist < 120
            label = "retreat"
        else:
            goal, why = self.loot_goal(obs, x, y, z, kinds, zone, t, max_d=50.0 if healing else None)
            if goal is None and healing and t - self.last_damaged >= 2.5:
                goal, why = (x, y), "heal"
            if goal is None:
                goal, why = self.roam(x, y, zone, t), "roam"
            move = self.nav.dir_to(x, y, goal[0], goal[1], t)
            if SILENT_ROAM and why == "roam" and t > 60 and zgoal is None:
                sp = 4.6 / max(1.0, walk)  # just under the 5 m/s step-sound threshold
                move = (move[0] * sp, move[1] * sp)
            label = why

        # the zone overrides everything except a point-blank fight
        if zgoal is not None and not (self.mode == "fight" and tdist < 50 and not zurgent):
            if zurgent or self.mode == "roam":
                move = self.nav.dir_to(x, y, zgoal[0], zgoal[1], t)
                boost = boost or (zurgent and energy > 20)
                label = "zone" + ("!" if zurgent else "")

        # stuck: jump and jet over whatever is in the way, then sidestep
        self.hist.append((t, x, y))
        while self.hist and t - self.hist[0][0] > 1.2:
            self.hist.pop(0)
        if t < self.unstick_until:
            move = self.unstick_dir
            jump, boost = True, energy > 10
        elif math.hypot(*move) > 0.5 and len(self.hist) > 8:
            t0, x0, y0 = self.hist[0]
            if t - t0 > 1.0 and math.hypot(x - x0, y - y0) < 2.0:
                ang = math.atan2(move[1], move[0]) + random.choice((-1, 1)) * random.uniform(0.6, 1.6)
                self.unstick_dir = (math.cos(ang), math.sin(ang)) if random.random() < 0.5 else move
                self.unstick_until = t + 1.0
                self.nav.reset()
                self.hist.clear()

        # ---------------- aim and fire
        fire = [False, False]
        aim = None
        gi = kinds.get("gun")
        gun = weapons[gi] if gi is not None else None
        shoot_target = target
        if shoot_target is None or (self.mode == "retreat" and not cornered and t_hpf > 0.2):
            shoot_target = None
        aim_obj = target  # what the torso faces (front armor)
        if shoot_target is None and self.mode != "retreat" and not healing:
            aim_obj = self.farm_target(obs, x, y, eye_z, need_weapon=len(kinds) < 2)
        if aim_obj is not None:
            tp = aim_obj["pos"]
            is_mech = aim_obj.get("kind") == "mech"
            is_npc = aim_obj.get("kind") == "npc"
            cz = tp[2] + (4.5 if is_mech else 1.75 if is_npc else 1.2)
            vel = aim_obj.get("vel", [0, 0, 0])
            gspeed = gun["stats"].get("speed", 252) if gun else 252
            li = kinds.get("laser")
            if li is not None and weapons[li].get("charge", 0) > 0:
                lx, ly, lz = tp[0], tp[1], cz
            else:
                lx, ly, lz = self.lead(x, y, muz_z, tp[0], tp[1], cz, vel[0], vel[1], vel[2], gspeed)
            aim = list(self.aim_at(x, y, muz_z, lx, ly, lz))
            d = math.hypot(tp[0] - x, tp[1] - y)
            yaw_err = abs(wrap(cur_yaw - aim[0]))
            pitch_err = abs(cur_pitch - aim[1])
            rad = 2.5 if is_mech else 1.8 if is_npc else 1.4
            tol = max(0.012, math.atan2(rad * 0.8, max(d, 1.0)))
            clear = self.map.los(x, y, muz_z, tp[0], tp[1], cz)
            allowed = shoot_target is not None or aim_obj is not target
            if allowed and clear and yaw_err < tol * 1.5 and pitch_err < tol * 2:
                # gun
                if gun and gun.get("reload", 0) == 0 and gun.get("ammo", 1) > 0 \
                        and d < gun["stats"].get("range", 230):
                    fire[gi] = True
            # laser: charge while we have a line, release at full charge when on target
            if li is not None and allowed:
                lw = weapons[li]
                full = lw["stats"].get("charge", 0.75)
                ch = lw.get("charge", 0) or 0
                if ch > 0:
                    ready = ch >= full * 0.97 and yaw_err < tol and pitch_err < tol * 2 and clear
                    fire[li] = not ready  # keep holding until ready, then let go
                elif lw.get("cooldown", 0) <= 0.05 and clear and d < lw["stats"].get("range", 280) - 10 \
                        and not (is_mech and t_light and d < 55):
                    fire[li] = True
            # lightning: auto-targets in its cone
            ki = kinds.get("lightning")
            if ki is not None and allowed:
                kw = weapons[ki]["stats"]
                if d < kw.get("range", 45) - 2 and yaw_err < math.radians(kw.get("cone_deg", 30)) * 0.8 \
                        and energy > kw.get("energy", 3) + 8 and clear:
                    fire[ki] = True
            # mortar: lob, high arc if no line
            mi = kinds.get("mortar")
            if mi is not None and allowed and (is_mech or is_npc) and 30 < d < 220:
                mw = weapons[mi]
                v = mw["stats"].get("speed", 72)
                pch = self.mortar_pitch(d, cz - 1.5 - (z + st.get("height", 9) + 0.5), v, high=not clear)
                if pch is not None and mw.get("cooldown", 0) <= 0.05:
                    if clear or is_mech:
                        if aim_obj is target:
                            aim = [aim[0], clamp(pch, -0.7, 1.3)]
                            if abs(cur_pitch - aim[1]) < 0.05 and yaw_err < tol * 2:
                                fire[mi] = True
            if gun and gun.get("reload", 0) == 0 and (gun.get("ammo", 1) == 0 or (
                    not clear and gun.get("ammo", 12) < gun["stats"].get("mag", 12) * 0.5)):
                act["reload"] = True
        else:
            # nothing to shoot: look where trouble came from, else sweep
            if gun and gun.get("ammo", 12) < gun["stats"].get("mag", 12) * 0.6 and gun.get("reload", 0) == 0:
                act["reload"] = True
            if t - self.last_damaged < 4 and self.dmg_bearing is not None:
                yaw = self.dmg_bearing
            elif t - self.sound_t < 3 and self.sound_bearing is not None:
                yaw = self.sound_bearing
            else:
                self.scan_phase += 0.1
                base = math.atan2(move[1], move[0]) if math.hypot(*move) > 0.3 else cur_yaw
                yaw = base + 1.4 * math.sin(self.scan_phase * 0.9)
            aim = [wrap(yaw), 0.0]

        # weapon pickups / swaps when standing on them
        tk = self.take_choice(obs, x, y, z, weapons, kinds)
        if tk is not None:
            act["take"], dslot = tk
            if dslot is not None:
                act["drop"] = dslot

        act["move"] = [round(move[0], 3), round(move[1], 3)]
        act["boost"] = bool(boost)
        act["jump"] = bool(jump)
        if aim is not None:
            act["aim"] = [round(wrap(aim[0]), 4), round(clamp(aim[1], -0.7, 1.3), 4)]
        act["fire"] = fire
        mf.draw.label(f"{label} hp{hp:.0f}")
        return act

    # ------------------------------------------------------------- sub-behaviours
    def find_cover(self, x, y, ex, ey, ez, zone, t):
        """Nearby walkable point the enemy can't see, preferring away from them."""
        best, bs = None, 1e18
        away = math.atan2(y - ey, x - ex)
        for r in (14, 24, 36, 50):
            for k in range(10):
                a = away + (k - 4.5) * 0.35
                px, py = x + math.cos(a) * r, y + math.sin(a) * r
                if not self.map.free(px, py) or not self.point_safe(px, py, zone, t, 5):
                    continue
                gz = self.map.ground(px, py)
                if self.map.los(ex, ey, ez, px, py, gz + 5.0):
                    continue
                s = r + 0.5 * math.hypot(px - ex, py - ey) * -0.3
                if s < bs:
                    bs, best = s, (px, py)
            if best:
                return best
        return None

    def take_choice(self, obs, x, y, z, weapons, kinds):
        slot1 = weapons[1] if len(weapons) > 1 else None
        cur = WEAPON_RANK.get(slot1["kind"], 0) if slot1 else -1
        for p in obs.get("pickups", []):
            if p["id"] in self.bad_pickups or p["kind"] == "gun" or p["kind"] in kinds:
                continue
            if math.hypot(p["pos"][0] - x, p["pos"][1] - y) > self.reach - 0.3 or abs(p["pos"][2] - z) > 3.8:
                continue
            r = WEAPON_RANK.get(p["kind"], 0)
            if slot1 is None:
                return p["id"], None
            if r > cur and not (slot1["kind"] == "laser" and (slot1.get("charge") or 0) > 0):
                return p["id"], 1
        return None

    def farm_target(self, obs, x, y, eye_z, need_weapon=False):
        """Something to shoot when no mech is around: NPC drones, then crates."""
        best, bs = None, 1e18
        if need_weapon:
            for c in obs.get("crates", []):
                d = math.hypot(c["pos"][0] - x, c["pos"][1] - y)
                if d < 140 and d < bs and self.map.los(x, y, eye_z, c["pos"][0], c["pos"][1], c["pos"][2] + 1.2):
                    best, bs = dict(c, kind="crate"), d
            if best:
                return best
        for n in obs.get("mechs", []):
            if n.get("kind") != "npc":
                continue
            d = math.hypot(n["pos"][0] - x, n["pos"][1] - y)
            if d < 150 and d < bs:
                best, bs = n, d
        if best:
            return best
        for c in obs.get("crates", []):
            d = math.hypot(c["pos"][0] - x, c["pos"][1] - y)
            if d < 110 and d < bs and self.map.los(x, y, eye_z, c["pos"][0], c["pos"][1], c["pos"][2] + 1.2):
                best, bs = dict(c, kind="crate"), d
        return best

    def update_memory(self, obs, x, y, eye_z, t):
        vis_p = {p["id"] for p in obs.get("pickups", [])}
        vis_c = {c["id"] for c in obs.get("cubes", [])}
        for p in obs.get("pickups", []):
            self.known_pickups[p["id"]] = (p["kind"], p["pos"], t + 150)
        for c in obs.get("cubes", []):
            self.known_cubes[c["id"]] = (c["pos"], t + 60)
        near = self.vision_near - 8
        for pid, (k, pos, exp) in list(self.known_pickups.items()):
            d = math.hypot(pos[0] - x, pos[1] - y)
            if t > exp or (pid not in vis_p and d < near and self.map.los(x, y, eye_z, pos[0], pos[1], pos[2] + 0.5)):
                del self.known_pickups[pid]
        for cid, (pos, exp) in list(self.known_cubes.items()):
            d = math.hypot(pos[0] - x, pos[1] - y)
            fake = isinstance(cid, tuple)
            if t > exp or (fake and d < 6) or (not fake and cid not in vis_c and d < near
                                                 and self.map.los(x, y, eye_z, pos[0], pos[1], pos[2] + 0.5)):
                del self.known_cubes[cid]

    def loot_goal(self, obs, x, y, z, kinds, zone, t, max_d=None):
        best, bs, why = None, 1e18, ""
        slot_rank = max([WEAPON_RANK[k] for k in kinds if k != "gun"], default=-1)
        wrange = EARLY_LOOT_RANGE if (slot_rank < 0 and t < 120) else 160.0
        if max_d is not None:
            wrange = min(wrange, max_d)
        for pid, (kind, pos, _) in self.known_pickups.items():
            if pid in self.bad_pickups or kind == "gun" or kind in kinds:
                continue
            r = WEAPON_RANK.get(kind, 0)
            if r <= slot_rank:
                continue
            if pos[2] - self.map.ground(pos[0], pos[1]) > 3:
                continue  # rooftop loot: skip
            d = math.hypot(pos[0] - x, pos[1] - y)
            s = d * (0.25 if slot_rank < 0 else 0.5) * (0.8 if r >= 3 else 1.0)
            if d < wrange and s < bs and self.point_safe(pos[0], pos[1], zone, t):
                best, bs, why = pos, s, f"get {kind}"
        crange = 120.0 if max_d is None else max_d
        for cid, (pos, _) in self.known_cubes.items():
            d = math.hypot(pos[0] - x, pos[1] - y)
            if d < crange and d * 0.5 < bs and self.point_safe(pos[0], pos[1], zone, t):
                best, bs, why = pos, d * 0.5, "cube"
        if max_d is None:
            for dr in obs.get("drops", []):
                d = math.hypot(dr["pos"][0] - x, dr["pos"][1] - y)
                eta = d / 11.0
                if d < 260 and eta + 3 > dr.get("lands_in", 0) and (dr.get("holder") is None or d < 30):
                    s = d * 0.7
                    if s < bs:
                        best, bs, why = dr["pos"], s, "drop"
            # chase a drone into gun range (we stay ~60 m out)
            if best is None:
                for n in obs.get("mechs", []):
                    if n.get("kind") == "npc":
                        d = math.hypot(n["pos"][0] - x, n["pos"][1] - y)
                        if 90 < d < 200 and d < bs:
                            best, bs, why = n["pos"], d, "drone"
        return (best[:2] if best else None), why

    def roam(self, x, y, zone, t):
        nc, nr = zone["next_center"], zone["next_radius"]
        g = self.roam_goal
        if g is None or math.hypot(g[0] - x, g[1] - y) < 15 or not self.point_safe(g[0], g[1], zone, t):
            for _ in range(20):
                a = random.uniform(0, TAU)
                r = random.uniform(0, max(10.0, nr * 0.6))
                px, py = nc[0] + math.cos(a) * r, nc[1] + math.sin(a) * r
                if self.map.free(px, py):
                    g = (px, py)
                    break
            else:
                g = tuple(nc)
            self.roam_goal = g
        return g


if __name__ == "__main__":
    mf.run(Bot)
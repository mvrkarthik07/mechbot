"""Run with python3 -B -m unittest sim.test_sim."""
import math
import runpy
import unittest
from unittest.mock import patch

from sim.sim import Arena, Body, Bot, KIT, Match, cylinder_hit, load_hello


class SimulatorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hello = load_hello(KIT)
        cls.arena = Arena(cls.hello)

    def match(self):
        return Match(self.hello, self.arena, Bot, 0, 0.65, 240)

    def test_cylinder_intersection(self):
        body = Body(1, "mech", (5, 0, 1), {"height": 4, "radius": 2}, 10)
        self.assertEqual(cylinder_hit((0, 0, 3), (1, 0, 0), 10, body), 3)
        self.assertEqual(cylinder_hit((5, 0, 8), (0, 0, -1), 10, body), 3)
        self.assertIsNone(cylinder_hit((0, 0, 0), (1, 0, 0), 10, body))
        self.assertIsNone(cylinder_hit((0, 0, 3), (1, 0, 0), 2, body))

    def test_rear_damage_and_cube_offer(self):
        match = self.match()
        p = match.player
        p.aim = (0, 0)
        attacker = match.house[0]
        gun = match.cfg["weapons"]["gun"]
        hit = gun["damage"]
        match.hit(attacker, p, "gun", hit, (p.pos[0] - 1, p.pos[1], p.pos[2]))
        self.assertEqual(p.hp, p.stats["hp"] - hit * p.stats["rear_mult"])
        self.assertTrue(p.events[-1]["rear"])
        self.assertEqual(p.last_combat, match.t)
        match.give_cubes(p, match.cfg["cubes"]["upgrade_thresholds"][0])
        self.assertIsNotNone(p.offer)
        saved = p.offer["choices"][0]["id"]
        match.pick(p, 0)
        self.assertEqual(p.upgrades, [saved])
        self.assertGreater(p.stats["radius"], match.cfg["mech"]["radius"])

    def test_laser_release_and_gun_reload(self):
        match = self.match()
        p = match.player
        laser = p.weapons[1] = match.new_weapon("laser")
        gun = p.weapons[0]
        gun.ammo = 0
        p.action = {"fire": [False, True]}
        match.triggers(p)
        self.assertEqual(laser.charge_start, 0)
        self.assertGreater(gun.reload_end, 0)
        p.action = {}
        match.t = match.dt
        with patch.object(match, "shoot") as shoot:
            match.triggers(p)
            shoot.assert_not_called()
            match.t = p.weapon_stats["laser"]["min_charge"]
            match.triggers(p)
            self.assertEqual(shoot.call_args.args[:3], (p, laser, p.weapon_stats["laser"]))
            self.assertIsNone(laser.charge_start)
        match.t = gun.reload_end
        match.triggers(p)
        self.assertEqual(gun.ammo, p.weapon_stats["gun"]["mag"])

    def test_bot_aims_charged_laser_without_projectile_lead(self):
        match = self.match()
        p = match.player
        match.living = match.mechs.copy()
        zone = match.zone()
        laser = p.weapons[1] = match.new_weapon("laser")
        x, y, z = p.pos
        target = dict(id=match.house[0].id, kind="mech", pos=[x + 90, y, z],
                      vel=[0, 10, 0], aim=[0, 0], hp=p.hp, max_hp=p.hp, weapons=["gun"])
        with patch.object(match.grid, "los", return_value=True):
            obs = match.observation(zone)
            obs["mechs"] = [target]
            self.assertGreater(match.bot.act(obs)["aim"][0], 0.01)
            match.t = match.dt
            laser.charge_start = 0
            obs["self"]["weapons"][1] = match.weapon_obs(p, laser)
            self.assertAlmostEqual(match.bot.act(obs)["aim"][0], 0)

    def test_lightning_cancels_laser_charge(self):
        match = self.match()
        p = match.player
        opponent = match.house[0]
        opponent.weapons[1] = laser = match.new_weapon("laser")
        laser.charge_start = 0
        opponent.pos = (p.pos[0] + 10, *p.pos[1:])
        p.aim = (0, 0)
        config = p.weapon_stats["lightning"]
        with patch.object(match, "targets", side_effect=lambda owner: iter([opponent])):
            with patch.object(match.grid, "los", return_value=True):
                match.lightning(p, config, p.center, (1, 0, 0), config["damage"])
        self.assertIsNone(laser.charge_start)
        self.assertEqual(opponent.short_until, config["short_s"])

    def test_visibility_memory(self):
        match = self.match()
        match.living = match.mechs.copy()
        opponent = match.house[0]
        zone = match.zone()
        with patch.object(match, "visible", side_effect=lambda observer, pos, height=0: pos is opponent.pos):
            first = match.observation(zone)
        self.assertIn(opponent.id, [m["id"] for m in first["mechs"]])
        opponent.pos = (opponent.pos[0] + 1, *opponent.pos[1:])
        with patch.object(match, "visible", return_value=False):
            match.t = match.cfg["vision"]["memory_s"]
            remembered = match.observation(zone)["mechs"]
            self.assertEqual(remembered[0]["pos"], list(opponent.pos))
            match.t = math.nextafter(match.t, math.inf)
            self.assertEqual(match.observation(zone)["mechs"], [])

    def test_schema_and_paired_seed(self):
        schema_cls = runpy.run_path(str(KIT / "check" / "check.py"))["Schema"]
        schema = schema_cls(str(KIT / "mechfight.schema.json"))
        match = self.match()
        make_obs = match.observation
        checked = 0

        def check_observation(zone):
            nonlocal checked
            obs = make_obs(zone)
            if checked % 17 == 0:
                self.assertEqual(schema.errors(obs, "Observation"), [])
            checked += 1
            return obs

        with patch.object(match, "observation", side_effect=check_observation):
            first = match.run()
        second = self.match().run()
        for key in ("points", "kills", "death_time", "killer", "damage", "modes", "stuck"):
            self.assertEqual(first[key], second[key], key)
        self.assertGreater(checked, 100)

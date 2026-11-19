import unittest
from types import SimpleNamespace

from panda3d.bullet import BulletWorld
from panda3d.core import NodePath, Vec3

from game.core.events import EventBus
from game.entities.weapons import WEAPON_SPECS, WeaponSystem


class _Target:
    person = object()

    def raycast(self, origin, direction, max_distance):
        if max_distance < 5:
            return None
        return SimpleNamespace(position=origin + direction * 5, normal=-direction,
                               distance=5, person=self.person, headshot=False)


class WeaponTests(unittest.TestCase):
    def setUp(self):
        self.events = EventBus()
        self.weapons = WeaponSystem(NodePath("weapon fixture"), BulletWorld(), self.events)
        self.addCleanup(self.weapons.close)
        self.origin = Vec3(0, 0, 1.3)
        self.forward = Vec3(0, 1, 0)

    def select(self, weapon_id):
        self.assertTrue(self.weapons.grant_weapon(weapon_id))
        self.assertTrue(self.weapons.select(WEAPON_SPECS[weapon_id].slot))

    def test_burst_keeps_firing_after_release_and_respects_cadence(self):
        self.select("burst")
        fired = []
        self.events.subscribe("gunshot", lambda **event: fired.append(event["weapon"]))
        self.assertIsNotNone(self.weapons.fire(self.origin, self.forward, pressed=True))
        self.assertTrue(self.weapons.burst_pending)
        for _ in range(2):
            self.weapons.update(.04)
            self.assertIsNone(self.weapons.fire(self.origin, self.forward))
            self.weapons.update(.05)
            self.assertIsNotNone(self.weapons.fire(self.origin, self.forward))
        self.assertFalse(self.weapons.burst_pending)
        self.assertEqual(self.weapons.ammo, (15, 54))
        self.weapons.update(1)
        self.assertIsNone(self.weapons.fire(self.origin, self.forward))
        self.assertEqual(fired, ["burst"] * 3)

    def test_partial_burst_and_equip_cancel(self):
        self.weapons.restore({"selected": "burst", "inventory": {"burst": {"magazine": 2, "reserve": 8}}})
        self.assertIsNotNone(self.weapons.fire(self.origin, self.forward, pressed=True))
        self.weapons.update(.09)
        self.assertIsNotNone(self.weapons.fire(self.origin, self.forward))
        self.assertFalse(self.weapons.burst_pending)
        self.assertEqual(self.weapons.ammo, (0, 8))
        self.assertTrue(self.weapons.reload())
        self.weapons.update(2)
        self.assertIsNotNone(self.weapons.fire(self.origin, self.forward, pressed=True))
        self.assertTrue(self.weapons.burst_pending)
        self.assertTrue(self.weapons.select(1))
        self.assertFalse(self.weapons.burst_pending)
        self.assertTrue(self.weapons.select(8))
        self.assertFalse(self.weapons.burst_pending)
        self.weapons.update(.09)
        self.assertIsNotNone(self.weapons.fire(self.origin, self.forward, pressed=True))
        self.assertTrue(self.weapons.burst_pending)
        self.assertEqual(self.weapons.add_ammo("burst", 6), 6)
        self.assertTrue(self.weapons.reload())
        self.assertFalse(self.weapons.burst_pending)

    def test_automatic_scatter_uses_one_shell_and_combines_hits(self):
        self.select("drum")
        hits = []
        self.events.subscribe("weapon_hit", lambda **event: hits.append(event["amount"]))
        result = self.weapons.fire(self.origin, self.forward, people=_Target())
        self.assertTrue(result.hit)
        self.assertEqual(hits, [48])
        self.assertEqual(self.weapons.ammo, (9, 30))
        self.assertIsNone(self.weapons.fire(self.origin, self.forward, people=_Target()))

    def test_marksman_aim_compacts_spread_and_revolver_has_recovery(self):
        self.select("marksman")
        spec = self.weapons.selected
        state = self.weapons._random.getstate()
        hip = next(self.weapons._directions(self.forward, False, spec))
        self.weapons._random.setstate(state)
        aimed = next(self.weapons._directions(self.forward, True, spec))
        self.assertLess((aimed - self.forward).length(), (hip - self.forward).length() * .08)
        self.assertEqual(spec.aim_fov, 45)
        self.select("revolver")
        result = self.weapons.fire(self.origin, self.forward, pressed=True, people=_Target())
        self.assertTrue(result.hit)
        self.assertGreater(result.recoil, WEAPON_SPECS["pistol"].recoil_degrees)
        self.weapons.update(.4)
        self.assertIsNone(self.weapons.fire(self.origin, self.forward, pressed=True))

    def test_legacy_slots_and_new_inventory_round_trip(self):
        originals = ["pistol", "smg", "shotgun", "rifle", "melee", "grenade", "rocket"]
        self.assertEqual([WEAPON_SPECS[name].slot for name in originals], list(range(1, 8)))
        self.weapons.restore({"selected": "rifle", "inventory": {"rifle": {"magazine": 17, "reserve": 63}}})
        self.assertEqual(self.weapons.selected.id, "rifle")
        self.assertEqual(self.weapons.ammo, (17, 63))
        for weapon_id in ("burst", "revolver", "drum", "marksman"):
            self.assertFalse(self.weapons.owns(weapon_id))
            self.select(weapon_id)
        self.assertIsNotNone(self.weapons.fire(self.origin, self.forward, pressed=True))
        snapshot = self.weapons.snapshot()
        self.weapons.restore(None)
        self.weapons.restore(snapshot)
        self.assertEqual(self.weapons.selected.id, "marksman")
        self.assertEqual(self.weapons.ammo, (4, 20))
        self.assertEqual(self.weapons.snapshot(), snapshot)

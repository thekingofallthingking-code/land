"""State transitions and navigation for the three city activities."""

import unittest
from types import SimpleNamespace

from panda3d.core import NodePath, Vec3

from game.core.events import EventBus
from game.missions.activities import Activities, road_gps
from game.world.roads import RoadGraph


class FakePedestrians:
    def __init__(self):
        self.people = []

    def spawn_at(self, position, archetype, *, heading, pinned, priority):
        target = SimpleNamespace(
            position=position, archetype=archetype, display_name="Generic gang member",
            health=95, pinned=pinned, heading=heading, priority=priority,
        )
        self.people.append(target)
        return target


class ActivityTests(unittest.TestCase):
    def setUp(self):
        self.events = EventBus()
        self.city = SimpleNamespace(graph=RoadGraph(), is_loaded=lambda x, y: True)
        self.peds = FakePedestrians()
        self.player = SimpleNamespace(position=Vec3(), health=100, money=0)
        self.car = SimpleNamespace(position=Vec3(), speed_kph=0., health=100)
        self.activities = Activities(NodePath("test activities"), self.city,
                                     self.events, self.peds, self.player)
        self.addCleanup(self.activities.close)
        self.completed = []
        self.failed = []
        self.events.subscribe("mission_completed", lambda **row: self.completed.append(row))
        self.events.subscribe("mission_failed", lambda **row: self.failed.append(row))

    def test_getaway_requires_chase_then_quiet_slow_finish(self):
        missions = self.activities
        spec = missions.missions["slipway_escape"]
        self.assertEqual(missions.offered_at(Vec3(*spec.start)), spec)
        self.assertTrue(missions.accept(spec.id))
        self.assertFalse(missions.accept("exchange_sprint"))
        self.car.position = Vec3(*spec.destination)
        missions.update(.02, self.car, 0)
        self.assertEqual(missions.phase, "seek")
        missions.update(.02, None, 2)
        self.assertEqual(missions.phase, "seek")
        missions.update(.02, self.car, 2)
        self.assertEqual(missions.phase, "chase")
        self.assertIsNone(missions.waypoint())

        saved = missions.snapshot()
        missions.restore(saved)
        self.assertEqual(missions.phase, "seek")
        missions.restore(saved, wanted_stars=2)
        self.assertEqual(missions.phase, "chase")
        self.car.speed_kph = 23
        missions.update(.02, self.car, 0)
        self.assertEqual(missions.phase, "drop")
        self.assertEqual(missions.waypoint(), Vec3(*spec.destination))
        self.car.speed_kph = 12
        missions.update(.02, self.car, 1)
        self.assertEqual(self.player.money, 0)
        missions.update(.02, self.car, 0)
        self.assertIsNone(missions.active)
        self.assertEqual(self.player.money, spec.reward)
        self.assertFalse(missions.accept(spec.id))
        self.assertEqual(self.completed, [{"title": spec.title, "reward": spec.reward}])

    def test_target_spawns_near_player_and_health_survives_reload(self):
        missions = self.activities
        spec = missions.missions["breakwater_bounty"]
        self.assertTrue(missions.accept(spec.id))
        missions.update(.02, None, 0)
        self.assertIsNone(missions.target)
        self.player.position = Vec3(*spec.destination) + Vec3(12, 0, 0)
        missions.update(.02, None, 0)
        self.assertEqual(missions.target.display_name, spec.destination_name)
        self.assertTrue(missions.target.pinned)
        missions.target.health = 38
        self.peds.people.remove(missions.target)
        self.player.position = Vec3(*spec.start)
        missions.update(.02, None, 0)
        self.assertIsNone(missions.target)
        self.assertEqual(missions.snapshot()["target_health"], 38)
        missions.restore(missions.snapshot())

        self.player.position = Vec3(*spec.destination) + Vec3(12, 0, 0)
        missions.update(.02, None, 0)
        victim = missions.target
        self.assertEqual(victim.health, 38)
        self.events.publish("pedestrian_death", person=victim, source=self.player)
        self.assertEqual(self.player.money, spec.reward)
        self.assertFalse(victim.pinned)
        self.assertIn(spec.id, missions.completed)

    def test_target_killed_by_another_actor_can_be_retried(self):
        missions = self.activities
        spec = missions.missions["breakwater_bounty"]
        self.assertTrue(missions.accept(spec.id))
        self.player.position = Vec3(*spec.destination)
        missions.update(.02, None, 0)
        self.events.publish("pedestrian_death", person=missions.target, source=object())
        self.assertEqual(self.player.money, 0)
        self.assertEqual(len(self.failed), 1)
        self.assertTrue(missions.accept(spec.id))

    def test_race_requires_ordered_vehicle_gates_and_resumes_timer(self):
        missions = self.activities
        spec = missions.missions["exchange_sprint"]
        self.assertTrue(missions.accept(spec.id))
        self.car.position = Vec3(*spec.checkpoints[1])
        missions.update(15, self.car, 0)
        self.assertEqual(missions.remaining, spec.time_limit)
        self.assertEqual(missions.checkpoint, 0)
        self.car.position = Vec3(*spec.checkpoints[0])
        missions.update(1, None, 0)
        self.assertEqual(missions.phase, "lineup")
        missions.update(1, self.car, 0)
        self.assertEqual(missions.phase, "race")
        self.assertEqual(missions.checkpoint, 1)
        missions.update(10, self.car, 0)

        state = missions.snapshot()
        missions.restore(state)
        self.assertEqual(missions.remaining, spec.time_limit - 10)
        self.assertEqual(missions.checkpoint, 1)
        for gate in spec.checkpoints[1:]:
            self.car.position = Vec3(*gate)
            missions.update(.02, self.car, 0)
        self.assertEqual(self.player.money, spec.reward)
        missions.restore(missions.snapshot())
        self.assertFalse(missions.accept(spec.id))

    def test_race_timeout_and_invalid_saved_progress(self):
        missions = self.activities
        spec = missions.missions["exchange_sprint"]
        self.assertTrue(missions.accept(spec.id))
        self.car.position = Vec3(*spec.checkpoints[0])
        missions.update(.02, self.car, 0)
        state = missions.snapshot()
        missions.restore({**state, "checkpoint": 90, "remaining": float("nan"),
                          "completed": [None, [], "not_a_mission"]})
        self.assertEqual(missions.phase, "lineup")
        self.assertEqual(missions.checkpoint, 0)
        missions.update(.02, self.car, 0)
        missions.update(spec.time_limit + 1, self.car, 0)
        self.assertIsNone(missions.active)
        self.assertEqual(self.failed, [{"title": spec.title, "reason": "Time expired"}])
        self.assertTrue(missions.accept(spec.id))

    def test_gps_joins_real_intersections_without_backtracking(self):
        graph = self.city.graph
        self.assertEqual(road_gps(graph, (3.4, 28), (3.4, 100)),
                         ((3.4, 28.), (0, 28.), (0, 100.), (3.4, 100.)))
        self.assertEqual(road_gps(graph, (11.1, 73), (106, 140.6)),
                         ((11.1, 73.), (0, 73.), (0, 144), (106., 144), (106., 140.6)))
        self.assertTrue(self.activities.accept("exchange_sprint"))
        route = self.activities.route(Vec3(11.1, -63, .19))
        self.assertEqual(route[-1], tuple(self.activities.waypoint())[:2])


if __name__ == "__main__":
    unittest.main()

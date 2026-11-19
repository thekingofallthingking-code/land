import unittest

from game.core.events import EventBus
from game.core.rules import apply_damage, damage_falloff, warranted_stars


class RulesTests(unittest.TestCase):
    def test_damage_falloff_and_armor(self):
        self.assertEqual(damage_falloff(100, 5, 20), 75)
        self.assertEqual(damage_falloff(100, 20, 20), 0)
        self.assertEqual(damage_falloff(100, float("nan"), 20), 0)
        self.assertEqual(apply_damage(100, 20, 75), (45, 0))
        self.assertEqual(apply_damage(4, 0, 10), (0, 0))

    def test_wanted_requires_witness(self):
        self.assertEqual(warranted_stars(1, 2, False), 1)
        self.assertEqual(warranted_stars(1, 2, True), 3)
        self.assertEqual(warranted_stars(4, 2, True), 5)

    def test_event_order_and_unsubscribe(self):
        seen = []
        bus = EventBus()

        def first(amount):
            seen.append(("first", amount))
            bus.unsubscribe("damage", first)

        def second(amount):
            seen.append(("second", amount))

        bus.subscribe("damage", first)
        bus.subscribe("damage", second)
        bus.publish("damage", amount=2)
        bus.publish("damage", amount=4)
        self.assertEqual(seen, [("first", 2), ("second", 2), ("second", 4)])

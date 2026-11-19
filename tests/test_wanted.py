import unittest

from game.core.wanted import RULES, Wanted


class WantedTests(unittest.TestCase):
    def setUp(self):
        self.wanted = Wanted()
        self.where = (22, 4, 1)
        self.witness = (object(),)

    def test_crime_requires_witness_and_escalates(self):
        self.assertFalse(self.wanted.report("shooting", self.where, (), 0))
        self.assertEqual(self.wanted.stars, 0)
        self.wanted.report("shooting", self.where, self.witness, 1)
        self.assertEqual(self.wanted.stars, 1)
        self.assertFalse(self.wanted.report("shooting", self.where, self.witness, 1.1))
        self.wanted.report("car_theft", self.where, self.witness, 2)
        self.assertEqual(self.wanted.stars, 2)
        self.wanted.report("explosion", self.where, self.witness, 3)
        self.assertEqual(self.wanted.stars, 3)
        self.assertEqual(self.wanted.mode, "pursuit")

    def test_search_cooldown_and_reacquisition(self):
        self.wanted.report("explosion", self.where, self.witness, 0)
        grace = RULES["loss_grace"]
        search = RULES["search_seconds"]
        cooldown = RULES["cooldown_seconds"]
        self.wanted.update(grace)
        self.assertEqual(self.wanted.mode, "search")
        self.wanted.update(grace + 1, (40, 6, 1))
        self.assertEqual(self.wanted.last_seen, (40, 6, 1))
        self.assertEqual(self.wanted.mode, "pursuit")
        start = 2 * grace + search + 2
        self.wanted.update(start)
        self.assertEqual(self.wanted.mode, "cooldown")
        self.wanted.update(start + cooldown)
        self.assertEqual(self.wanted.stars, 1)
        self.wanted.update(start + 2 * cooldown)
        self.assertEqual(self.wanted.mode, "clear")

    def test_round_trip_carries_stars_and_last_seen(self):
        self.wanted.report("car_theft", self.where, self.witness, 30)
        restored = Wanted()
        restored.restore(self.wanted.snapshot(33), 100)
        self.assertEqual(restored.stars, 1)
        self.assertEqual(restored.last_seen, self.where)
        self.assertEqual(restored.last_seen_time, 97)

    def test_high_alert_and_shelter(self):
        for elapsed in range(5):
            self.wanted.report("explosion", self.where, self.witness, elapsed)
        self.assertEqual(self.wanted.stars, 5)
        self.assertFalse(self.wanted.take_cover(4))
        self.wanted.update(10)
        self.assertTrue(self.wanted.take_cover(10))
        self.wanted.update(12)
        self.assertEqual(self.wanted.stars, 4)
        self.wanted.update(12.5, self.where)
        self.assertEqual(self.wanted.mode, "pursuit")
        self.assertEqual(self.wanted.cooldown_interval, RULES["cooldown_seconds"])

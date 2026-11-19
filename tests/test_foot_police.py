import unittest

from game.ai.foot_police import arrest_progress


class ArrestProgressTests(unittest.TestCase):
    def test_capture_requires_uninterrupted_close_contact(self):
        condition = dict(distance=1.4, speed=.8, visible=True, on_foot=True)
        held = arrest_progress(0., .6, **condition)
        self.assertAlmostEqual(held, .6)
        self.assertAlmostEqual(arrest_progress(held, 1., **condition), 1.12)
        for broken in (dict(distance=2.2), dict(speed=4.1), dict(visible=False), dict(on_foot=False)):
            self.assertEqual(arrest_progress(held, .12, **(condition | broken)), 0.)

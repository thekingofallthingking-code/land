import unittest

from game.world.roads import RoadGraph


class RoadGraphTests(unittest.TestCase):
    def test_astar_shortest_and_connected(self):
        graph = RoadGraph()
        path = graph.path((-8, -8), (8, 8))
        self.assertEqual(path[0], (-8, -8))
        self.assertEqual(path[-1], (8, 8))
        self.assertEqual(len(path), 33)
        for start, end in zip(path, path[1:]):
            self.assertEqual(abs(end[0] - start[0]) + abs(end[1] - start[1]), 1)

    def test_world_route_coordinates(self):
        graph = RoadGraph()
        route = graph.route((4, 3), (145, 289))
        self.assertEqual(route[0], (0, 0))
        self.assertEqual(route[-1], (144, 288))

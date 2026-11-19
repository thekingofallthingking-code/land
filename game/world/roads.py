"""Shared road, lane and footway topology for Harbor City."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from math import hypot
from typing import Callable, TypeVar


CHUNK_SIZE = 144
CHUNK_MIN = -8
CHUNK_MAX = 7
CITY_MIN = CHUNK_MIN * CHUNK_SIZE
CITY_MAX = (CHUNK_MAX + 1) * CHUNK_SIZE
ROAD_HALF_WIDTH = 8.5
LANE_OFFSET = 3.4
SIDEWALK_OFFSET = 11.1
STOP_LINE_OFFSET = 13.25
DISTRICT_NAMES = {
    "downtown": "Exchange Quarter",
    "residential": "Westbank",
    "harbor": "Foundry Docks",
    "park": "Juniper Park",
    "beachfront": "South Strand",
}

Point = tuple[float, float]
Intersection = tuple[int, int]
SidewalkNode = tuple[int, int, int, int]
Node = TypeVar("Node", bound=tuple)


def district_at(ix: int, iy: int) -> str:
    if iy <= -6:
        return "beachfront"
    if ix >= 4 and iy <= 3:
        return "harbor"
    if ix <= -3 and iy >= 3:
        return "park"
    if -3 <= ix <= 2 and -3 <= iy <= 3:
        return "downtown"
    return "residential"


@dataclass(frozen=True, slots=True)
class Lane:
    origin: Intersection
    destination: Intersection
    start: Point
    stop: Point
    end: Point
    axis: str
    speed_limit: float


@dataclass(frozen=True, slots=True)
class Crosswalk:
    intersection: Intersection
    origin: SidewalkNode
    destination: SidewalkNode
    start: Point
    end: Point
    axis: str


def _astar(
    start: Node,
    goal: Node,
    neighbors: Callable[[Node], tuple[Node, ...]],
    position: Callable[[Node], Point],
) -> list[Node]:
    goal_x, goal_y = position(goal)
    frontier = [(0.0, 0.0, start)]
    distance = {start: 0.0}
    previous: dict[Node, Node] = {}
    while frontier:
        _, travelled, node = heappop(frontier)
        if travelled != distance[node]:
            continue
        if node == goal:
            path = [node]
            while node != start:
                node = previous[node]
                path.append(node)
            return path[::-1]
        x, y = position(node)
        for neighbor in neighbors(node):
            neighbor_x, neighbor_y = position(neighbor)
            candidate = travelled + hypot(neighbor_x - x, neighbor_y - y)
            if candidate < distance.get(neighbor, float("inf")):
                distance[neighbor] = candidate
                previous[neighbor] = node
                estimate = hypot(neighbor_x - goal_x, neighbor_y - goal_y)
                heappush(frontier, (candidate + estimate, candidate, neighbor))
    return []


class RoadGraph:
    """A grid of intersections with directed lanes and connected sidewalk corners.

    Intersection identifiers are integer grid coordinates. Positions are metre
    coordinates with east as positive x and north as positive y.
    """

    def __init__(self) -> None:
        coordinate_range = range(CHUNK_MIN, CHUNK_MAX + 2)
        self.intersections = tuple((x, y) for x in coordinate_range for y in coordinate_range)
        node_set = frozenset(self.intersections)
        self._neighbors = {
            (x, y): tuple(
                candidate for candidate in ((x - 1, y), (x, y - 1), (x, y + 1), (x + 1, y))
                if candidate in node_set
            )
            for x, y in self.intersections
        }
        self.segments = tuple(
            (origin, destination)
            for origin, neighbors in self._neighbors.items()
            for destination in neighbors
            if origin < destination
        )
        self._sidewalk_nodes = frozenset(
            (x, y, sx, sy)
            for x, y in self.intersections
            for sx in (-1, 1)
            for sy in (-1, 1)
            if self._corner_in_city(x, y, sx, sy)
        )
        self.lanes = {
            (origin, destination): self._make_lane(origin, destination)
            for origin, neighbors in self._neighbors.items()
            for destination in neighbors
        }

    @staticmethod
    def position(node: Intersection) -> Point:
        return node[0] * CHUNK_SIZE, node[1] * CHUNK_SIZE

    def neighbors(self, node: Intersection) -> tuple[Intersection, ...]:
        return self._neighbors.get(node, ())

    @staticmethod
    def nearest_intersection(x: float, y: float) -> Intersection:
        return (
            min(CHUNK_MAX + 1, max(CHUNK_MIN, round(x / CHUNK_SIZE))),
            min(CHUNK_MAX + 1, max(CHUNK_MIN, round(y / CHUNK_SIZE))),
        )

    def path(self, start: Intersection, goal: Intersection) -> list[Intersection]:
        if start not in self._neighbors or goal not in self._neighbors:
            return []
        return _astar(start, goal, self.neighbors, self.position)

    def route(self, start: Point, goal: Point) -> list[Point]:
        return [
            self.position(node)
            for node in self.path(self.nearest_intersection(*start), self.nearest_intersection(*goal))
        ]

    @staticmethod
    def _corner_in_city(x: int, y: int, sx: int, sy: int) -> bool:
        return (
            CHUNK_MIN <= x + min(sx, 0) <= CHUNK_MAX
            and CHUNK_MIN <= y + min(sy, 0) <= CHUNK_MAX
        )

    @staticmethod
    def sidewalk_position(node: SidewalkNode) -> Point:
        x, y, sx, sy = node
        return x * CHUNK_SIZE + sx * SIDEWALK_OFFSET, y * CHUNK_SIZE + sy * SIDEWALK_OFFSET

    def nearest_sidewalk(self, x: float, y: float) -> SidewalkNode:
        ix, iy = self.nearest_intersection(x, y)
        candidates = (
            (ix, iy, sx, sy) for sx in (-1, 1) for sy in (-1, 1)
            if (ix, iy, sx, sy) in self._sidewalk_nodes
        )

        def distance(node: SidewalkNode) -> float:
            corner_x, corner_y = self.sidewalk_position(node)
            return hypot(x - corner_x, y - corner_y)

        return min(candidates, key=distance)

    def sidewalk_neighbors(self, node: SidewalkNode) -> tuple[SidewalkNode, ...]:
        x, y, sx, sy = node
        corners = ((x, y, -sx, sy), (x, y, sx, -sy), (x + sx, y, -sx, sy), (x, y + sy, sx, -sy))
        return tuple(corner for corner in corners if corner in self._sidewalk_nodes)

    def sidewalk_path(self, start: SidewalkNode, goal: SidewalkNode) -> list[SidewalkNode]:
        if start not in self._sidewalk_nodes or goal not in self._sidewalk_nodes:
            return []
        return _astar(start, goal, self.sidewalk_neighbors, self.sidewalk_position)

    def _make_lane(self, origin: Intersection, destination: Intersection) -> Lane:
        origin_x, origin_y = self.position(origin)
        end_x, end_y = self.position(destination)
        dx, dy = destination[0] - origin[0], destination[1] - origin[1]
        offset_x, offset_y = dy * LANE_OFFSET, -dx * LANE_OFFSET
        axis = "east_west" if dx else "north_south"
        speed_limit = 17.0 if ((dx and origin[1] % 4 == 0) or (dy and origin[0] % 4 == 0)) else 12.0
        return Lane(
            origin,
            destination,
            (origin_x + offset_x, origin_y + offset_y),
            (end_x + offset_x - dx * STOP_LINE_OFFSET, end_y + offset_y - dy * STOP_LINE_OFFSET),
            (end_x + offset_x, end_y + offset_y),
            axis,
            speed_limit,
        )

    def lane(self, origin: Intersection, destination: Intersection) -> Lane:
        return self.lanes[origin, destination]

    def crosswalks(self, node: Intersection) -> tuple[Crosswalk, ...]:
        x, y = node
        crossings = []
        for side in (-1, 1):
            for origin, destination, axis in (
                ((x, y, -1, side), (x, y, 1, side), "east_west"),
                ((x, y, side, -1), (x, y, side, 1), "north_south"),
            ):
                if origin in self._sidewalk_nodes and destination in self._sidewalk_nodes:
                    crossings.append(Crosswalk(
                        node, origin, destination, self.sidewalk_position(origin),
                        self.sidewalk_position(destination), axis,
                    ))
        return tuple(crossings)

    @staticmethod
    def signal(node: Intersection, elapsed: float, axis: str) -> str:
        """Sample one vehicle axis of a staggered, four-way signal cycle."""
        if axis not in ("east_west", "north_south"):
            raise ValueError(f"unknown road axis {axis!r}")
        offset = (node[0] * 7 + node[1] * 11) % 28
        phase = (elapsed + offset + (14 if axis == "east_west" else 0)) % 28
        if phase < 10:
            return "green"
        if phase < 13:
            return "yellow"
        return "red"

    def pedestrian_signal(self, crossing: Crosswalk, elapsed: float) -> str:
        return "walk" if self.signal(crossing.intersection, elapsed, crossing.axis) == "green" else "wait"

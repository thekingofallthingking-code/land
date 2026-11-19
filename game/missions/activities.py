"""Data-driven getaway, bounty and race activities in the shared city."""

from dataclasses import dataclass
from functools import lru_cache
from math import ceil, hypot

from panda3d.core import Vec3

from game.core.config import ROOT, read_json
from game.missions.delivery import _marker


@dataclass(frozen=True, slots=True)
class MissionSpec:
    id: str
    kind: str
    title: str
    start: tuple
    reward: int
    radius: float
    color: tuple
    destination: tuple = ()
    destination_name: str = ""
    maximum_finish_kph: float = 0
    minimum_stars: int = 1
    target_archetype: str = ""
    checkpoints: tuple = ()
    time_limit: float = 0

    @classmethod
    def from_record(cls, row):
        return cls(
            id=row["id"], kind=row["kind"], title=row["title"],
            start=tuple(row["start"]), reward=row["reward"],
            radius=row["arrival_radius"], color=tuple(row["color"]),
            destination=tuple(row.get("destination", ())),
            destination_name=row.get("destination_name", ""),
            maximum_finish_kph=row.get("maximum_finish_kph", 0),
            minimum_stars=row.get("minimum_stars", 1),
            target_archetype=row.get("target_archetype", ""),
            checkpoints=tuple(tuple(gate) for gate in row.get("checkpoints", ())),
            time_limit=row.get("time_limit", 0),
        )


INITIAL_PHASE = {"getaway": "seek", "target": "target", "race": "lineup"}
TARGET_SPAWN_RADIUS = 112.
OFFER_RADIUS = 3.15


def _xy_distance(first, second):
    return hypot(first[0] - second[0], first[1] - second[1])


def _road_edge(graph, point):
    """Project onto the closest road centerline and find the containing edge."""
    x, y = point
    intersection = graph.nearest_intersection(x, y)
    center_x, center_y = graph.position(intersection)
    ix, iy = intersection
    if abs(x - center_x) < abs(y - center_y):
        projection = (center_x, y)
        far = (ix, iy + (1 if y > center_y else -1))
    else:
        projection = (x, center_y)
        far = (ix + (1 if x > center_x else -1), iy)
    if projection == (center_x, center_y) or far not in graph.neighbors(intersection):
        return (center_x, center_y), (intersection,)
    return projection, (intersection, far)


def road_gps(graph, begin, end, find_path=None):
    """Connect positions via their road segments and a shortest graph path."""
    start = (float(begin[0]), float(begin[1]))
    destination = (float(end[0]), float(end[1]))
    entry, origins = _road_edge(graph, start)
    exit_point, goals = _road_edge(graph, destination)
    if set(origins) == set(goals):
        through = ()
    else:
        shortest = float("inf")
        through = ()
        pathfinder = graph.path if find_path is None else find_path
        for origin in origins:
            for goal in goals:
                nodes = pathfinder(origin, goal)
                if not nodes:
                    continue
                candidate = tuple(graph.position(node) for node in nodes)
                cost = _xy_distance(entry, candidate[0]) + _xy_distance(candidate[-1], exit_point)
                cost += sum(_xy_distance(a, b) for a, b in zip(candidate, candidate[1:]))
                if cost < shortest:
                    shortest, through = cost, candidate
    points = []
    for point in (start, entry, *through, exit_point, destination):
        if not points or _xy_distance(points[-1], point) >= .03:
            points.append(point)
    return tuple(points)


class Activities:
    """One active activity at a time with streamed markers and saveable progress."""

    def __init__(self, render, city, events, peds, player):
        self.city = city
        self.events = events
        self.peds = peds
        self.player = player
        rows = read_json(ROOT / "game/data/missions.json")["missions"]
        self.missions = {
            row["id"]: MissionSpec.from_record(row)
            for row in rows if row.get("kind") in INITIAL_PHASE
        }
        self.root = render.attach_new_node("city activities")
        self.contacts = {}
        self.goals = {}
        for mission in self.missions.values():
            self.contacts[mission.id] = _marker(self.root, Vec3(*mission.start), .85, mission.color)
            goal = mission.destination or mission.checkpoints[0]
            self.goals[mission.id] = _marker(self.root, Vec3(*goal), mission.radius, mission.color)
        self.completed: set[str] = set()
        self.active: MissionSpec | None = None
        self.phase = ""
        self.checkpoint = 0
        self.remaining = 0.
        self.target = None
        self.target_health = None
        self._previous_target_name = ""
        self._occupied = None
        self._stars = 0
        self._find_path = lru_cache(maxsize=64)(self.city.graph.path)
        self.events.subscribe("pedestrian_death", self._on_target_death)
        self._sync_markers()

    def offered_at(self, position):
        if self.active is not None:
            return None
        for mission in self.missions.values():
            if (mission.id not in self.completed
                    and (position - Vec3(*mission.start)).length_squared() <= OFFER_RADIUS ** 2):
                return mission
        return None

    def accept(self, mission_id):
        mission = self.missions.get(mission_id)
        if self.active is not None or mission is None or mission_id in self.completed:
            return False
        self.active = mission
        self.phase = INITIAL_PHASE[mission.kind]
        self.remaining = mission.time_limit
        self._sync_markers()
        return True

    def _release_target(self):
        if self.target is not None:
            self.target.pinned = False
            self.target.display_name = self._previous_target_name
            self.target = None
        self.target_health = None
        self._previous_target_name = ""

    def _reset(self):
        self._release_target()
        self.active = None
        self.phase = ""
        self.checkpoint = 0
        self.remaining = 0.

    def cancel(self, reason="Abandoned"):
        if self.active is None:
            return
        mission = self.active
        self._reset()
        self._sync_markers()
        self.events.publish("mission_failed", title=mission.title, reason=reason)

    def _finish(self):
        mission = self.active
        self.completed.add(mission.id)
        self.player.money += mission.reward
        self._reset()
        self._sync_markers()
        self.events.publish("mission_completed", title=mission.title, reward=mission.reward)

    def _on_target_death(self, person, source=None, **_):
        if self.active is None or self.target is None or person is not self.target:
            return
        if self.player.health > 0 and (source is self.player
                                       or (source is not None and source is self._occupied)):
            self._finish()
        else:
            self.cancel("Another actor took down the target")

    def _update_target(self, focus):
        if self.target is not None and self.target not in self.peds.people:
            retained_health = self.target.health
            self._release_target()
            self.target_health = retained_health
        if self.target is not None:
            return
        mission = self.active
        x, y, z = mission.destination
        if _xy_distance(focus, mission.destination) > TARGET_SPAWN_RADIUS or not self.city.is_loaded(x, y):
            return
        target = self.peds.spawn_at(Vec3(x, y, z), mission.target_archetype,
                                    pinned=True, priority=True, heading=90.)
        if target is not None:
            self._previous_target_name = target.display_name
            target.display_name = mission.destination_name
            if self.target_health is not None:
                target.health = min(self.target_health, target.health)
            self.target = target

    def _update_getaway(self, occupied, stars):
        mission = self.active
        if self.phase == "seek" and occupied is not None and stars >= mission.minimum_stars:
            self.phase = "chase"
        if self.phase == "chase" and stars == 0:
            self.phase = "drop"
        if (self.phase == "drop" and stars == 0 and occupied is not None
                and abs(occupied.speed_kph) <= mission.maximum_finish_kph
                and self._at(occupied.position, mission.destination)):
            self._finish()

    def _at(self, position, destination):
        return (abs(position.z - destination[2]) < 3.0
                and _xy_distance(position, destination) < self.active.radius)

    def _update_race(self, dt, occupied):
        mission = self.active
        if self.phase == "race":
            self.remaining = max(0., self.remaining - dt)
            if self.remaining == 0:
                self.cancel("Time expired")
                return
        if occupied is None or not self._at(occupied.position, mission.checkpoints[self.checkpoint]):
            return
        self.checkpoint += 1
        if self.checkpoint == len(mission.checkpoints):
            self._finish()
        else:
            self.phase = "race"

    def update(self, dt, occupied, stars):
        if occupied is not None and occupied.health <= 0:
            occupied = None
        self._occupied = occupied
        self._stars = stars
        if self.active is not None and self.player.health > 0:
            focus = occupied.position if occupied is not None else self.player.position
            kind = self.active.kind
            if kind == "getaway":
                self._update_getaway(occupied, stars)
            elif kind == "target":
                self._update_target(focus)
            else:
                self._update_race(dt, occupied)
        self._sync_markers()

    def objective(self, position):
        mission = self.active
        if mission is None:
            return ""
        if mission.kind == "getaway":
            if self.phase == "seek":
                task = "Get a wanted star while driving"
            elif self.phase == "chase" or self._stars:
                task = "Lose the police"
            else:
                distance = _xy_distance(position, mission.destination)
                task = f"Park at {mission.destination_name}   {distance:.0f} m"
        elif mission.kind == "target":
            distance = _xy_distance(position, self.waypoint())
            task = f"Take down {mission.destination_name}   {distance:.0f} m"
        elif self.phase == "lineup":
            task = "Drive through the starting gate"
        else:
            minutes, seconds = divmod(ceil(self.remaining), 60)
            task = f"Gate {self.checkpoint}/{len(mission.checkpoints) - 1}   {minutes}:{seconds:02d}"
        return f"{mission.title}  /  {task}"

    def waypoint(self, position=None):
        mission = self.active
        if mission is None:
            focus = self.player.position if position is None else position
            options = (item for item in self.missions.values() if item.id not in self.completed)
            closest = min(options, key=lambda item: _xy_distance(item.start, focus), default=None)
            return Vec3(*closest.start) if closest is not None else None
        if mission.kind == "getaway":
            return Vec3(*mission.destination) if self.phase == "drop" and self._stars == 0 else None
        if mission.kind == "target":
            return self.target.position if self.target is not None else Vec3(*mission.destination)
        return Vec3(*mission.checkpoints[self.checkpoint])

    def route(self, position):
        waypoint = self.waypoint(position)
        if waypoint is None:
            return ()
        return road_gps(self.city.graph, position, waypoint, self._find_path)

    def _sync_markers(self):
        active = self.active
        waypoint = self.waypoint() if active is not None else None
        for mission in self.missions.values():
            contact = self.contacts[mission.id]
            if (active is None and mission.id not in self.completed
                    and self.city.is_loaded(*mission.start[:2])):
                contact.show()
            else:
                contact.hide()
            goal = self.goals[mission.id]
            if active is mission and waypoint is not None and self.city.is_loaded(waypoint.x, waypoint.y):
                goal.set_pos(waypoint + Vec3(0, 0, .035))
                goal.show()
            else:
                goal.hide()

    def snapshot(self):
        health = self.target.health if self.target is not None else self.target_health
        return {
            "schema": 1,
            "completed": sorted(self.completed),
            "active": self.active.id if self.active is not None else None,
            "phase": self.phase,
            "checkpoint": self.checkpoint,
            "remaining": self.remaining,
            "target_health": health,
        }

    def restore(self, data, *, wanted_stars=0):
        self._reset()
        self._stars = wanted_stars
        self._occupied = None
        self.completed.clear()
        if isinstance(data, dict) and data.get("schema") == 1:
            completed = data.get("completed")
            if isinstance(completed, list):
                self.completed.update(item for item in completed
                                      if isinstance(item, str) and item in self.missions)
            active = data.get("active")
            if isinstance(active, str) and self.accept(active):
                self._restore_phase(data)
        self._sync_markers()

    def _restore_phase(self, data):
        mission = self.active
        phase = data.get("phase")
        if mission.kind == "getaway":
            if phase == "drop" or (phase == "chase" and self._stars > 0):
                self.phase = phase
        elif mission.kind == "target":
            health = data.get("target_health")
            if type(health) in (int, float) and 0 < health <= 1000:
                self.target_health = health
        elif phase == "race":
            checkpoint = data.get("checkpoint")
            remaining = data.get("remaining")
            if (type(checkpoint) is int and 0 < checkpoint < len(mission.checkpoints)
                    and type(remaining) in (int, float) and 0 < remaining <= mission.time_limit):
                self.phase = phase
                self.checkpoint = checkpoint
                self.remaining = remaining

    def close(self):
        self.events.unsubscribe("pedestrian_death", self._on_target_death)
        self._reset()
        self.root.remove_node()

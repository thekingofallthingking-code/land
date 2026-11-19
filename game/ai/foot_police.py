"""Arcade foot officers dispatched into the streamed city."""

from __future__ import annotations

import math
import random

from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import BitMask32, Point3, Vec3

from game.ai.pedestrians import PedestrianHit, _CitizenArt, _angle, _flat_distance, _grade, _make_model
from game.entities.player import _Part
from game.world.roads import CHUNK_SIZE, SIDEWALK_OFFSET

_UP = Vec3(0, 0, 1)
_MASK = BitMask32.bit(0)
_ARREST_TIME = 1.12
_UNIFORM = {
    "styles": [["#233a54", "#52657d"], ["#273e57", "#53657c"]],
    "hat": "cap",
    "weapon": "pistol",
}


def arrest_progress(held, dt, *, distance, speed, visible, on_foot):
    """Return consecutive contact time for the nonlethal capture animation."""
    if not on_foot or not visible or distance > 1.95 or speed > 2.5:
        return 0.
    return min(_ARREST_TIME, held + max(0., dt))


class FootOfficer:
    is_police = True
    is_shopkeeper = False
    display_name = "Harbor City officer"

    def __init__(self, manager, number, position, heading):
        self.manager = manager
        self.number = number
        self.node = manager.root.attach_new_node(f"officer {number}")
        self.node.set_pos(position)
        self.node.set_h(heading)
        self.health = 100.
        self.state = "chase"
        self.height = manager.rng.uniform(1.0, 1.09)
        template = manager.uniforms[number % len(manager.uniforms)]
        self.art = _CitizenArt(template, self.node, self.height, manager.rng.uniform(0., math.tau))
        self.goal = Vec3(position)
        self.route = []
        self.route_target = None
        self.velocity = Vec3()
        self.next_think = 0.
        self.next_fire = manager.elapsed + manager.rng.uniform(.65, 1.30)
        self.next_animation = 0.
        self.stagger_until = 0.
        self.depart_at = 0.
        self.dead_at = 0.
        self.search_angle = manager.rng.uniform(0., math.tau)
        self.search_anchor = None
        self.search_goal = None
        self.next_search_point = 0.

    @property
    def position(self):
        return self.node.get_pos(self.manager.render)

    @property
    def alive(self):
        return self.health > 0

    def take_damage(self, amount, *, source=None, direction=None, headshot=False, kind="gunshot", **_):
        if not self.alive or amount <= 0 or not math.isfinite(amount):
            return False
        self.health = max(0., self.health - amount)
        if direction is not None and Vec3(direction).length_squared() > .01:
            self.node.set_h(_angle(-Vec3(direction)))
        self.velocity = Vec3()
        if not self.alive:
            self.state = "dead"
            self.dead_at = self.manager.elapsed
            self.manager.events.publish("police_officer_down", officer=self, source=source,
                                        position=self.position, kind=kind)
        elif headshot or kind == "melee" or amount >= 37:
            self.state = "knocked_down"
            self.stagger_until = self.manager.elapsed + (.65 if kind == "melee" else 1.1)
        return True


class FootPolice:
    """A bounded local group of officers, using the same footway graph as civilians."""

    def __init__(self, render, physics, city, events, *, cap=5, seed=32954):
        self.render = render
        self.physics = physics
        self.city = city
        self.graph = city.graph
        self.events = events
        self.cap = max(1, min(7, int(cap)))
        self.root = render.attach_new_node("Foot patrol")
        self.rng = random.Random(seed)
        self.officers = []
        self.uniforms = [_make_model("Harbor City officer", _UNIFORM, index) for index in (0, 1)]
        for template in self.uniforms:
            insignia = _Part(template.find("torso"), "Officer badge")
            insignia.box((.083, .124, .391), (.035, .018, .047), (.90, .69, .28, 1))
            insignia.box((-.079, -.124, .413), (.22, .023, .035), (.64, .72, .78, 1))
            insignia.finish()
        self.elapsed = 0.
        self._serial = 0
        self._next_spawn = 0.
        self._focus = Vec3(city.spawn)
        self._player = None
        self._occupied = None
        self._previous_player = None
        self._player_speed = 0.
        self._arresting = None
        self._arrest_time = 0.
        self._arrest_sent = False
        self.events.subscribe("police_deploy_foot", self._deploy)
        self.events.subscribe("damage", self._damage)

    @property
    def arrest_fraction(self):
        return self._arrest_time / _ARREST_TIME

    def _remove(self, officer):
        self.officers.remove(officer)
        officer.node.remove_node()
        if self._arresting is officer:
            self._arresting = None
            self._arrest_time = 0.

    def _damage(self, target, amount, **data):
        if isinstance(target, FootOfficer) and target.manager is self:
            target.take_damage(amount, **data)

    def _first_blocker(self, origin, destination, *, ignore=()):
        if (destination - origin).length_squared() < .0004:
            return None
        start, end = Point3(origin), Point3(destination)
        closest = self.physics.ray_test_closest(start, end, _MASK)
        if not closest.has_hit():
            return None
        if closest.get_node() not in ignore:
            return Vec3(closest.get_hit_pos())
        ray = self.physics.ray_test_all(start, end, _MASK)
        blockers = [hit for hit in ray.get_hits() if hit.get_node() not in ignore]
        if blockers:
            return Vec3(min(blockers, key=lambda hit: hit.get_hit_fraction()).get_hit_pos())
        return None

    def _ignored_target(self):
        player = self._player.controller if self._player is not None else None
        car = self._occupied.body if self._occupied is not None else None
        return player, car

    def has_line_of_sight(self, position, max_distance=62.):
        position = Vec3(position)
        for officer in self.officers:
            if (officer.alive and officer.state not in ("depart", "knocked_down")
                    and self._can_see(officer, position, max_distance)):
                return True
        return False

    def _can_see(self, officer, position, max_distance):
        origin = officer.position
        direction = position - origin
        distance = _flat_distance(origin, position)
        if distance > max_distance or abs(direction.z) > 13:
            return False
        direction.z = 0.
        if distance > 4.8 and direction.dot(officer.node.get_quat().get_forward()) < distance * .22:
            return False
        return self._first_blocker(origin + _UP * 1.48, position + _UP * 1.05,
                                   ignore=self._ignored_target()) is None

    def _ground(self, point):
        point = Vec3(point)
        high = max(1.45, point.z + .85)
        top = Point3(point.x, point.y, high)
        ray = self.physics.ray_test_all(top, Point3(point.x, point.y, high - 3.7), _MASK)
        floor = [
            hit for hit in ray.get_hits()
            if isinstance(hit.get_node(), BulletRigidBodyNode) and hit.get_node().get_mass() == 0
            and hit.get_hit_normal().z > .57
        ]
        return Vec3(min(floor, key=lambda hit: hit.get_hit_fraction()).get_hit_pos()) if floor else None

    def spawn_at(self, position, heading=0.):
        position = Vec3(*position)
        if len(self.officers) >= self.cap or not self.city.is_loaded(position.x, position.y):
            return None
        point = self._ground(position)
        if point is None:
            return None
        if any(_flat_distance(point, unit.position) < 1.05 for unit in self.officers if unit.alive):
            return None
        self._serial += 1
        officer = FootOfficer(self, self._serial, point + _UP * .012, heading)
        self.officers.append(officer)
        return officer

    def _deploy(self, position, heading=0., vehicle=None, **_):
        origin = Vec3(position)
        radians = math.radians(heading)
        right = Vec3(math.cos(radians), math.sin(radians), 0)
        alternatives = (origin, origin + right, origin - right)
        for point in alternatives:
            if vehicle is not None and _flat_distance(point, vehicle.position) < 1.3:
                continue
            if self.spawn_at(point, heading) is not None:
                break

    def _spawn_near(self, target):
        for _ in range(14):
            angle = self.rng.uniform(0, math.tau)
            radius = self.rng.uniform(32., 62.)
            sample = target + Vec3(math.cos(angle) * radius, math.sin(angle) * radius, 0.)
            sample.z = .19
            horizontal = round(sample.y / CHUNK_SIZE) * CHUNK_SIZE
            vertical = round(sample.x / CHUNK_SIZE) * CHUNK_SIZE
            if abs(sample.x - vertical) < abs(sample.y - horizontal):
                sample.x = vertical + math.copysign(SIDEWALK_OFFSET, sample.x - vertical)
            else:
                sample.y = horizontal + math.copysign(SIDEWALK_OFFSET, sample.y - horizontal)
            if not (25 < _flat_distance(sample, target) < 68) or not self.city.is_loaded(sample.x, sample.y):
                continue
            if self._first_blocker(sample + _UP * .72, sample + Vec3(.44, .32, .72)) is not None:
                continue
            if self.spawn_at(sample, _angle(target - sample)) is not None:
                return

    def _choose_route(self, officer, goal):
        position = officer.position
        endpoint = self.graph.nearest_sidewalk(goal.x, goal.y)
        if endpoint != officer.route_target or not officer.route:
            start = self.graph.nearest_sidewalk(position.x, position.y)
            nodes = self.graph.sidewalk_path(start, endpoint)
            officer.route = [Vec3(*self.graph.sidewalk_position(node), .18) for node in nodes]
            officer.route_target = endpoint
        while officer.route and _flat_distance(officer.route[0], position) < 1.25:
            officer.route.pop(0)
        return officer.route[0] if officer.route else goal

    def _direct_or_route(self, officer, target):
        position = officer.position
        start = position + _UP * .79
        end = Vec3(target.x, target.y, position.z + .79)
        if self._first_blocker(start, end, ignore=self._ignored_target()) is None:
            return target
        return self._choose_route(officer, target)

    def _movable(self, position, direction, distance):
        forward = position + direction * distance
        return self._first_blocker(position + _UP * .61, forward + _UP * .61,
                                   ignore=self._ignored_target()) is None

    def _move(self, officer, dt, speed):
        position = officer.position
        delta = officer.goal - position
        delta.z = 0.
        gap = delta.length()
        officer.velocity = Vec3()
        if gap < .08:
            return
        direction = delta / gap
        for other in self.officers:
            if other is officer or not other.alive:
                continue
            offset = position - other.position
            offset.z = 0.
            if .05 < offset.length_squared() < 1.1:
                direction += offset * .34
        direction.normalize()
        distance = min(gap, speed * dt)
        if not self._movable(position, direction, distance + .35):
            side = Vec3(direction.y, -direction.x, 0.)
            options = (side, -side) if officer.number % 2 else (-side, side)
            direction = next((step for step in options if self._movable(position, step, distance + .45)), Vec3())
        if direction.length_squared() < .02:
            return
        point = position + direction * distance
        if not self.city.is_loaded(point.x, point.y):
            return
        point.z += (_grade(point.x, point.y) - position.z) * min(1., dt * 12)
        officer.node.set_pos(self.render, point)
        current = officer.node.get_h()
        officer.node.set_h(current + ((_angle(direction) - current + 180) % 360 - 180) * min(1., dt * 13))
        officer.velocity = direction * speed

    def _fire(self, officer, target_position, player, occupied):
        position = officer.position
        direction = Vec3(target_position) - position
        direction.z = 0.
        direction.normalize()
        origin = position + _UP * (1.28 * officer.height) + direction * .38
        end = Vec3(target_position) + _UP * (1.04 if occupied is not None else 1.2)
        if self._first_blocker(origin, end, ignore=self._ignored_target()) is not None:
            return
        distance = _flat_distance(position, target_position)
        chance = max(.32, .86 - distance * .023 - min(6., self._player_speed) * .025)
        hit = self.rng.random() < chance
        if not hit:
            end += Vec3(-direction.y, direction.x, 0.) * self.rng.choice((-1.8, 1.8))
        self.events.publish("npc_shot", origin=origin, end=end, blocked=False, officer=officer)
        self.events.publish("gunshot", position=origin, direction=(end - origin).normalized(),
                            weapon="pistol", owner=officer)
        if hit:
            self.events.publish("damage", target=occupied if occupied is not None else player,
                                amount=10., source=officer, kind="police_gunshot", direction=direction)

    def _think(self, officer, target, last_seen, search_radius, stars, mode, player, occupied):
        position = officer.position
        officer.velocity = Vec3()
        pursuit = mode == "pursuit" and (player.active or occupied is not None)
        if not stars:
            if officer.state != "depart":
                officer.state = "depart"
                officer.depart_at = self.elapsed + 4.8
                officer.goal = position + (position - self._focus).normalized() * 12
            return
        if pursuit:
            officer.search_anchor = None
            distance = _flat_distance(position, target)
            combat = stars >= 2 and 2.1 < distance < (16. if occupied is None else 20.)
            if combat and self._can_see(officer, target, 21.):
                officer.state = "shoot"
                officer.node.set_h(_angle(target - position))
                if self.elapsed >= officer.next_fire:
                    officer.next_fire = self.elapsed + self.rng.uniform(.83, 1.46)
                    self._fire(officer, target, player, occupied)
                return
            officer.state = "chase"
            if occupied is None and distance < 4. and self._can_see(officer, target, 5.):
                approach = target - position
                approach.z = 0.
                officer.goal = position + approach * max(0., (distance - 1.35) / max(distance, .01))
            else:
                officer.goal = self._direct_or_route(officer, target)
            return
        officer.state = "search"
        if officer.search_anchor is None or _flat_distance(officer.search_anchor, last_seen) > 5.:
            officer.search_anchor = Vec3(last_seen)
            officer.search_goal = Vec3(last_seen)
            officer.next_search_point = self.elapsed + max(4., min(15., _flat_distance(position, last_seen) * .44))
        if self.elapsed >= officer.next_search_point or _flat_distance(position, officer.search_goal) < 1.6:
            officer.search_angle = (officer.search_angle + 1.83) % math.tau
            step = max(3., min(22., search_radius * .44))
            offset = Vec3(math.cos(officer.search_angle), math.sin(officer.search_angle), 0.) * step
            candidate = officer.search_anchor + offset
            officer.search_goal = candidate if self.city.is_loaded(candidate.x, candidate.y) else officer.search_anchor
            officer.next_search_point = self.elapsed + self.rng.uniform(5.1, 8.5)
        officer.goal = self._direct_or_route(officer, officer.search_goal)

    def _track_arrest(self, dt, target, player, occupied, active):
        if not active or not player.active or occupied is not None or self._arrest_sent:
            self._arresting, self._arrest_time = None, 0.
            return
        candidates = [
            officer for officer in self.officers
            if officer.alive and officer.state not in ("knocked_down", "depart")
            and abs(officer.position.z - target.z) < .8
            and _flat_distance(officer.position, target) <= 1.95
            and self._can_see(officer, target, 4.)
        ]
        closest = self._arresting if self._arresting in candidates else min(
            candidates, key=lambda officer: _flat_distance(officer.position, target), default=None)
        if closest is not self._arresting:
            self._arrest_time = 0.
            self._arresting = closest
        if closest is None:
            return
        self._arrest_time = arrest_progress(self._arrest_time, dt, distance=_flat_distance(closest.position, target),
                                            speed=self._player_speed, visible=True, on_foot=True)
        if self._arrest_time >= _ARREST_TIME:
            self._arrest_sent = True
            self.events.publish("police_arrest", officer=closest, position=Vec3(target))

    def update(self, dt, elapsed, player, occupied, wanted):
        self.elapsed = elapsed
        self._player, self._occupied = player, occupied
        self._focus = Vec3(occupied.position if occupied is not None else player.position)
        target = self._focus
        mode, stars = wanted.mode, wanted.stars
        raw_last_seen = wanted.last_seen
        last_seen = Vec3(*raw_last_seen) if raw_last_seen is not None else Vec3(target)
        search_radius = max(0., wanted.search_radius)
        if self._previous_player is not None and occupied is None and dt > 0:
            speed = min(22., _flat_distance(player.position, self._previous_player) / dt)
            self._player_speed += (speed - self._player_speed) * min(1., dt * 16.)
        else:
            self._player_speed = 0.
        self._previous_player = Vec3(player.position)
        if not stars:
            self._arrest_sent = False
        for officer in self.officers[:]:
            distance = _flat_distance(officer.position, target)
            if ((not officer.alive and elapsed - officer.dead_at > 11.) or distance > 156
                    or (officer.state == "depart" and elapsed >= officer.depart_at)
                    or not self.city.is_loaded(officer.position.x, officer.position.y)):
                self._remove(officer)
                continue
            if officer.alive and elapsed >= officer.stagger_until:
                if elapsed >= officer.next_think:
                    self._think(officer, target, last_seen, search_radius, stars, mode, player, occupied)
                    officer.next_think = elapsed + (.13 if distance < 25. else .30)
                if officer.state in ("chase", "search", "depart"):
                    speed = (5.4 if occupied is None else 4.8) if officer.state == "chase" else 2.25
                    self._move(officer, dt, speed)
            if elapsed >= officer.next_animation:
                interval = dt if distance < 31 else .082 if distance < 76 else .16
                pose = "fight" if officer.state == "shoot" else officer.state
                officer.art.update(interval, pose, officer.velocity.length())
                officer.next_animation = elapsed + interval
        if (mode == "pursuit" and stars > 0 and len(self.officers) < self.cap
                and sum(officer.alive for officer in self.officers) < min(self.cap, stars + int(stars >= 3))
                and elapsed >= self._next_spawn):
            self._spawn_near(last_seen)
            self._next_spawn = elapsed + (3.7 if stars == 1 else 2.35)
        self._track_arrest(dt, target, player, occupied, stars > 0 and mode == "pursuit")

    def _raycast(self, origin, direction, max_distance, extra_radius):
        origin, direction = Vec3(origin), Vec3(direction)
        if not direction.normalize():
            return None
        best = None
        for officer in self.officers:
            position = officer.position
            if not officer.alive or _flat_distance(origin, position) > max_distance + 1.5:
                continue
            if officer.state == "knocked_down":
                forward = officer.node.get_quat().get_forward()
                volumes = ((position - forward * .81 + _UP * .25, .43, False),)
            else:
                scale = officer.height
                volumes = tuple((position + _UP * (height * scale), radius * scale, headshot)
                                for height, radius, headshot in ((1.64, .17, True), (1.16, .29, False),
                                                                  (.71, .25, False), (.35, .19, False)))
            for center, radius, headshot in volumes:
                gap = center - origin
                projection = gap.dot(direction)
                area = (radius + extra_radius) ** 2 - (gap.length_squared() - projection * projection)
                if area < 0.:
                    continue
                root = math.sqrt(area)
                distance = max(0., projection - root)
                if projection + root < 0. or distance > max_distance:
                    continue
                impact = origin + direction * distance
                best = PedestrianHit(officer, distance, impact, (impact - center).normalized(), headshot)
                max_distance = distance
        return best

    def raycast(self, origin, direction, max_distance):
        return self._raycast(origin, direction, max_distance, 0.)

    def melee_target(self, origin, direction, max_distance):
        return self._raycast(origin, direction, max_distance, .25)

    def clear(self):
        for officer in self.officers[:]:
            self._remove(officer)
        self._arresting, self._arrest_time = None, 0.
        self._arrest_sent = False
        self._next_spawn = self.elapsed + 1.5

    def close(self):
        self.events.unsubscribe("police_deploy_foot", self._deploy)
        self.events.unsubscribe("damage", self._damage)
        self.clear()
        self.root.remove_node()
        for template in self.uniforms:
            template.remove_node()

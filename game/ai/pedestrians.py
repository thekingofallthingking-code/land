"""Streamed sidewalk pedestrians and their encounter state."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import random

from panda3d.core import BitMask32, NodePath, Point3, Vec3

from game.core.config import ROOT
from game.entities.player import _Part
from game.world.roads import CHUNK_SIZE, ROAD_HALF_WIDTH, district_at

_ROAD_MASK = BitMask32.bit(0)
_UP = Vec3(0, 0, 1)
_GROUND = .185
_STREET = .008
_SKINS = ("#8b5d47", "#b98364", "#644439", "#cc9979", "#b7895b")
_HAIRS = ("#272729", "#513b32", "#3b2928", "#605852", "#32262b")


def _tint(code):
    return tuple(int(code[index:index + 2], 16) / 255 for index in (1, 3, 5)) + (1.,)


def _read_data(name):
    return json.loads((ROOT / "game" / "data" / name).read_text(encoding="utf-8"))


def _flat_distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def _grade(x, y):
    street_gap = min(abs(value - round(value / CHUNK_SIZE) * CHUNK_SIZE) for value in (x, y))
    return _GROUND if street_gap > ROAD_HALF_WIDTH else _STREET


def _angle(vector):
    return math.degrees(math.atan2(-vector.x, vector.y))


def _make_model(title, spec, variation):
    root = NodePath(title)
    colors = spec["styles"][variation % len(spec["styles"])]
    coat, accent = map(_tint, colors)
    skin = _tint(_SKINS[variation % len(_SKINS)])
    hair = _tint(_HAIRS[variation % len(_HAIRS)])
    dark = _tint(("#303c49", "#423f43", "#4b4940")[variation % 3])
    sole = _tint("#88877a")

    torso = root.attach_new_node("torso")
    torso.set_z(.91)
    body = _Part(torso, "coat")
    body.rings(0, 0, ((-.065, .174, .114, 0), (.06, .188, .121, 0),
                      (.32, .202, .121, .003), (.48, .211, .114, 0),
                      (.525, .115, .085, 0)), coat)
    body.rings(0, 0, ((.52, .066, .06, 0), (.64, .064, .058, 0)), skin)
    body.box((0, .122, .286), (.022, .018, .321), accent)
    body.box((-.102, .114, .37), (.080, .012, .044), accent)
    body.box((0, -.119, .38), (.23, .016, .031), accent)
    if spec.get("shopkeeper"):
        body.box((0, .119, .238), (.263, .037, .406), accent)
        body.box((0, .143, .14), (.192, .012, .071), coat)
    body.finish()

    head = torso.attach_new_node("head")
    head.set_z(.595)
    face = _Part(head, "face")
    face.rings(0, 0, ((.022, .058, .060, .009), (.063, .081, .079, .011),
                      (.109, .092, .086, .011), (.169, .09, .082, .006),
                      (.207, .072, .068, 0)), skin)
    face.rings(0, -.006, ((.155, .096, .092, 0), (.211, .089, .084, 0),
                           (.24, .053, .055, 0)), hair)
    face.box((0, .101, .110), (.019, .021, .028), skin)
    for side in (-1, 1):
        face.box((side * .038, .092, .124), (.025, .012, .010), hair)
    if spec.get("hat"):
        face.rings(0, -.002, ((.161, .103, .098, 0), (.203, .106, .09, 0),
                              (.25, .070, .068, 0)), accent)
        if spec["hat"] == "cap":
            face.box((0, .095, .172), (.148, .115, .019), accent)
    face.finish()

    for side, name in ((-1, "left"), (1, "right")):
        upper = torso.attach_new_node(f"arm-{name}")
        upper.set_pos(side * .221, 0, .449)
        sleeve = _Part(upper, "upper sleeve")
        sleeve.rings(0, 0, ((-.262, .057, .055, 0), (-.111, .07, .070, 0),
                            (.028, .076, .071, 0)), coat)
        sleeve.finish()
        lower = upper.attach_new_node(f"forearm-{name}")
        lower.set_z(-.258)
        cuff = _Part(lower, "forearm")
        cuff.rings(0, 0, ((-.199, .043, .046, 0), (-.032, .063, .058, 0),
                           (.017, .059, .057, 0)), coat)
        cuff.rings(0, 0, ((-.266, .029, .038, .005), (-.214, .041, .043, .006),
                           (-.183, .039, .037, 0)), skin)
        cuff.finish()
        if side > 0 and spec.get("weapon"):
            socket = lower.attach_new_node("sidearm mount")
            socket.set_pos(0, .006, -.242)
            socket.set_p(-84)
            prop = _Part(socket, "sidearm")
            prop.box((0, .060, .014), (.054, .194, .049), dark)
            prop.box((0, .002, -.023), (.044, .059, .096), dark)
            prop.finish().hide()

        leg = root.attach_new_node(f"leg-{name}")
        leg.set_pos(side * .094, 0, .909)
        thigh = _Part(leg, "upper trouser")
        thigh.rings(0, 0, ((-.425, .068, .069, 0), (-.176, .086, .097, 0),
                           (.062, .099, .107, 0)), dark)
        thigh.finish()
        shin = leg.attach_new_node(f"shin-{name}")
        shin.set_z(-.417)
        shoe = _Part(shin, "lower trouser and shoe")
        shoe.rings(0, 0, ((-.408, .053, .055, 0), (-.204, .066, .064, 0),
                          (.019, .067, .065, 0)), dark)
        shoe.rings(0, 0, ((-.484, .066, .116, .049), (-.451, .066, .116, .049)), sole, 8)
        shoe.rings(0, 0, ((-.455, .069, .119, .051), (-.415, .066, .116, .045),
                          (-.368, .052, .064, .005)), hair, 8)
        shoe.finish()
    return root


class _CitizenArt:
    def __init__(self, template, parent, height, phase):
        self.model = template.copy_to(parent)
        self.model.set_scale(height)
        self.torso = self.model.find("torso")
        self.joints = [tuple(self.model.find(f"**/{joint}-{side}")
                             for joint in ("arm", "forearm", "leg", "shin"))
                       for side in ("left", "right")]
        self.sidearm = self.model.find("**/sidearm")
        self.phase = phase
        self.fall = 0.
        self.armed = False

    def update(self, dt, state, speed):
        falling = state in ("knocked_down", "dead")
        cowering = state == "panic"
        target = 1. if falling else 0.
        self.fall += (target - self.fall) * min(1., dt * (13 if falling else 5))
        self.model.set_p(86 * self.fall)
        self.model.set_z(.21 * self.fall)
        draw = state == "fight"
        if not self.sidearm.is_empty() and draw != self.armed:
            self.armed = draw
            if draw:
                self.sidearm.show()
            else:
                self.sidearm.hide()
        gait = min(1., speed / 1.35)
        self.phase += dt * (3.4 + speed * 2.5) if gait > .015 else 0.
        running = max(0., min(1., (speed - 1.55) / 1.65))
        self.torso.set_z(.85 if cowering else .91 + gait * abs(math.sin(self.phase)) * (.014 + .019 * running))
        self.torso.set_p(-16 if cowering else -9. * running)
        for index, (arm, forearm, leg, shin) in enumerate(self.joints):
            phase = self.phase + index * math.pi
            stride = math.sin(phase) * gait
            lift = max(0., math.cos(phase)) * gait
            leg.set_p(stride * (24 + 11 * running) + 28 * self.fall)
            shin.set_p(-lift * (19 + 23 * running) - (12 + index * 10) * self.fall)
            arm_pitch = -stride * (23 + 13 * running) + 16 * self.fall
            arm.set_p(66 if draw else 37 if cowering else arm_pitch)
            arm.set_r((-1 if index == 0 else 1) * (10 + 11 * self.fall))
            forearm.set_p(18 if draw else 69 if cowering else 8 + gait * (12 + 35 * running))


@dataclass(frozen=True)
class PedestrianHit:
    person: Pedestrian
    distance: float
    position: Vec3
    normal: Vec3
    headshot: bool


class Pedestrian:
    def __init__(self, manager, number, position, spec, variation, heading, pinned):
        self.manager = manager
        self.number = number
        self.spec = spec
        self.archetype_id = spec["id"]
        self.display_name = manager.rng.choice(spec["names"])
        self.is_shopkeeper = spec.get("shopkeeper", False)
        self.pinned = pinned
        self.health = float(spec["health"])
        self.state = "idle"
        self.hostility = 0.
        self.node = manager.root.attach_new_node(f"{self.archetype_id}-{number}")
        self.node.set_pos(position)
        self.node.set_h(heading)
        self.height = manager.rng.uniform(.91, 1.08)
        self.art = _CitizenArt(manager.template(spec, variation), self.node, self.height,
                               manager.rng.uniform(0, math.tau))
        self.route_from = None
        self.route_to = None
        self.route_entry = None
        self.crossing = False
        self.velocity = Vec3()
        self.threat = Vec3(position)
        self.speed_scale = manager.rng.uniform(.9, 1.12)
        self.decision_at = 0.
        self.animation_at = 0.
        self.rest_until = manager.elapsed + manager.rng.uniform(0, 1.3)
        self.state_until = 0.
        self.dead_at = 0.
        self.safe_until = 0.
        self.bump_ready = 0.
        self.last_talk = -10.
        self.last_line = None
        self.attack_at = 0.
        self.approach_until = 0.
        self.reaction = "flee"
        self.escape_until = 0.
        self.drag = None

    @property
    def position(self):
        return self.node.get_pos(self.manager.render)

    @property
    def alive(self):
        return self.health > 0

    @property
    def mood(self):
        if self.state in ("panic", "flee", "knocked_down"):
            return "afraid"
        if self.hostility >= 42:
            return "angry"
        if self.hostility >= 12:
            return "annoyed"
        return "calm"

    def take_damage(self, amount, *, source=None, direction=None, headshot=False, kind="gunshot"):
        return self.manager.damage(self, amount, source=source, direction=direction,
                                   headshot=headshot, kind=kind)


class PedestrianManager:
    """An active, capped population around the player's streamed city position."""

    def __init__(self, render, physics, city, events, *, limit=32, seed=81732):
        self.render = render
        self.physics = physics
        self.city = city
        self.graph = city.graph
        self.events = events
        self.root = render.attach_new_node("Sidewalk population")
        self.rng = random.Random(seed)
        self.limit = max(1, min(40, int(limit)))
        self.people = []
        self.archetypes = {spec["id"]: spec for spec in _read_data("npcs.json")["archetypes"]}
        self.lines = _read_data("dialogue.json")["lines"]
        self._templates = {}
        self._crosswalks = {}
        for intersection in self.graph.intersections:
            for crossing in self.graph.crosswalks(intersection):
                self._crosswalks[crossing.origin, crossing.destination] = crossing
                self._crosswalks[crossing.destination, crossing.origin] = crossing
        self.elapsed = 0.
        self._spawn_at = 0.
        self._numbers = 0
        self._focus = Vec3(city.spawn)
        self._player = None
        self._car_samples = []
        self._next_car_sample = 0.
        self._shop = Vec3(getattr(city, "shop", Vec3(15.6, 46, .19)))
        self.shopkeeper = None
        self.events.subscribe("gunshot", self._gunshot)
        self.events.subscribe("explosion", self._explosion)
        self.events.subscribe("damage", self._damage_event)

    def template(self, spec, variation):
        key = spec["id"], variation
        if key not in self._templates:
            self._templates[key] = _make_model(spec["id"], spec, variation)
        return self._templates[key]

    def _links(self, position):
        ix, iy = self.graph.nearest_intersection(position.x, position.y)
        for x in range(ix - 1, ix + 2):
            for y in range(iy - 1, iy + 2):
                for sx, sy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    origin = x, y, sx, sy
                    for destination in self.graph.sidewalk_neighbors(origin):
                        if origin < destination and origin[:2] != destination[:2]:
                            yield origin, destination

    def _route_at(self, position):
        best = math.inf
        route = None
        entry = None
        for origin, destination in self._links(position):
            ax, ay = self.graph.sidewalk_position(origin)
            bx, by = self.graph.sidewalk_position(destination)
            dx, dy = bx - ax, by - ay
            progress = min(1., max(0., ((position.x - ax) * dx + (position.y - ay) * dy)
                                      / (dx * dx + dy * dy)))
            nearest = Vec3(ax + dx * progress, ay + dy * progress, position.z)
            distance = _flat_distance(position, nearest)
            if distance < best:
                best, route, entry = distance, (origin, destination), nearest
        if route and self.rng.random() < .5:
            route = route[::-1]
        return route, entry if best > .23 else None

    def _spawn(self, position, archetype_id, route, heading, pinned):
        self._numbers += 1
        spec = self.archetypes[archetype_id]
        variation = self.rng.randrange(6)
        person = Pedestrian(self, self._numbers, position, spec, variation, heading, pinned)
        if route:
            person.route_from, person.route_to = route
        self.people.append(person)
        return person

    def spawn_at(self, position, archetype_id="local", *, heading=0., pinned=False, priority=False):
        if len(self.people) >= self.limit:
            candidates = (p for p in self.people if not p.pinned)
            replacement = max(candidates, key=lambda p: _flat_distance(p.position, self._focus), default=None)
            if replacement is None or (not priority and _flat_distance(replacement.position, self._focus) <= 25):
                return None
            self._remove(replacement)
        position = Vec3(position)
        route, entry = (None, None) if pinned else self._route_at(position)
        person = self._spawn(position, archetype_id, route, heading, pinned)
        person.route_entry = entry
        return person

    def _remove(self, person):
        self.people.remove(person)
        person.node.remove_node()
        if person is self.shopkeeper:
            self.shopkeeper = None

    def _stream(self, focus):
        first = self._spawn_at == 0.
        self._spawn_at = self.elapsed + .40
        for person in self.people[:]:
            distance = _flat_distance(person.position, focus)
            if person.pinned:
                if distance > 140 or not self.city.is_loaded(person.position.x, person.position.y):
                    self._remove(person)
            elif (distance > 147 or not self.city.is_loaded(person.position.x, person.position.y)
                  or (not person.alive and self.elapsed - person.dead_at > 18)):
                self._remove(person)
        if (self.shopkeeper is None and _flat_distance(self._shop, focus) < 105
                and self.city.is_loaded(self._shop.x, self._shop.y)):
            self.shopkeeper = self.spawn_at(self._shop, "shopkeeper", heading=90, pinned=True)

        available = min(9 if first else 3, max(0, self.limit - 2 - len(self.people)))
        if not available:
            return
        links = list(self._links(focus))
        if not links:
            return
        for _ in range(available * 13):
            origin, destination = self.rng.choice(links)
            ax, ay = self.graph.sidewalk_position(origin)
            bx, by = self.graph.sidewalk_position(destination)
            progress = self.rng.uniform(.035, .965)
            position = Vec3(ax + (bx - ax) * progress, ay + (by - ay) * progress, _GROUND)
            distance = _flat_distance(position, focus)
            if not (9 if first else 20) < distance < 112:
                continue
            if not self.city.is_loaded(position.x, position.y):
                continue
            if any(_flat_distance(position, p.position) < 2.9 for p in self.people):
                continue
            district = district_at(math.floor(position.x / CHUNK_SIZE), math.floor(position.y / CHUNK_SIZE))
            specs = [p for p in self.archetypes.values() if not p.get("shopkeeper")]
            weights = [p.get("districts", {}).get(district, 0) + .24 for p in specs]
            spec = self.rng.choices(specs, weights)[0]
            if self.rng.random() < .5:
                origin, destination = destination, origin
            tx, ty = self.graph.sidewalk_position(destination)
            self._spawn(position, spec["id"], (origin, destination),
                        _angle(Vec3(tx - position.x, ty - position.y, 0)), False)
            available -= 1
            if available == 0:
                break

    def _line(self, person, mood):
        lines = self.lines[person.archetype_id][mood]
        choices = [line for line in lines if line != person.last_line]
        person.last_line = self.rng.choice(choices or lines)
        return person.last_line

    def nearby(self, position, radius=3.1):
        visible = [
            (_flat_distance(position, p.position), p)
            for p in self.people
            if p.alive and p.state != "knocked_down" and abs(position.z - p.position.z) < 1.3
        ]
        for distance, person in sorted(visible, key=lambda item: item[0]):
            if distance > radius:
                return None
            if self._blocked(Vec3(position) + _UP * 1.27, person.position + _UP * 1.18) is None:
                return person
        return None

    def talk(self, person, player_position=None):
        if not person.alive:
            return ""
        if self.elapsed - person.last_talk < 1.4:
            person.hostility = min(100., person.hostility + 15.)
        person.last_talk = self.elapsed
        if person.state in ("idle", "walk", "wait") and player_position is not None:
            person.node.set_h(_angle(Vec3(player_position) - person.position))
            person.rest_until = max(person.rest_until, self.elapsed + 2.0)
        return self._line(person, person.mood)

    def _blocked(self, start, end, vehicle=None):
        player_node = self._player.controller if self._player is not None else None
        ignored = (player_node, vehicle.body if vehicle is not None else None)
        hit = self.physics.ray_test_closest(Point3(start), Point3(end), _ROAD_MASK)
        if not hit.has_hit():
            return None
        if hit.get_node() not in ignored:
            return Vec3(hit.get_hit_pos())
        ray = self.physics.ray_test_all(Point3(start), Point3(end), _ROAD_MASK)
        other = [item for item in ray.get_hits() if item.get_node() not in ignored]
        return Vec3(min(other, key=lambda item: item.get_hit_fraction()).get_hit_pos()) if other else None

    def _damage_event(self, target, amount, **payload):
        if isinstance(target, Pedestrian) and target.manager is self:
            self.damage(target, amount, **payload)

    def damage(self, person, amount, *, source=None, direction=None, headshot=False, kind="gunshot", **_):
        if not person.alive or amount <= 0 or not math.isfinite(amount):
            return False
        person.health = max(0., person.health - amount)
        person.hostility = min(100., person.hostility + max(52., amount * 1.65))
        if direction is not None:
            incoming = Vec3(direction)
            incoming.z = 0.
            incoming.normalize()
            person.threat = person.position - incoming * 3
        else:
            person.threat = Vec3(getattr(source, "position", self._focus))
        person.escape_until = self.elapsed + self.rng.uniform(7., 13.)
        if not person.alive:
            person.state = "dead"
            person.dead_at = self.elapsed
            person.velocity = Vec3()
            low, high = person.spec["cash"]
            position = person.position
            self.events.publish("cash_drop", position=position, amount=self.rng.randint(low, high))
            if weapon_id := person.spec.get("weapon"):
                self.events.publish("weapon_drop", position=position + Vec3(.55, .1, 0),
                                    weapon_id=weapon_id, rounds=person.spec["rounds"])
            self.events.publish("pedestrian_death", person=person, source=source, kind=kind, position=position)
            return True

        person.reaction = "fight" if person.spec.get("weapon") and kind != "vehicle" else "flee"
        if (kind in ("vehicle", "melee") or headshot or amount >= 39) and person.state != "knocked_down":
            self._knock_down(person)
        elif person.state != "knocked_down":
            if person.reaction == "fight":
                self._start_fight(person)
            else:
                self._frighten(person, person.threat)
        return True

    def _knock_down(self, person):
        person.state = "knocked_down"
        person.velocity = Vec3()
        person.state_until = self.elapsed + self.rng.uniform(1.25, 1.8)
        if _flat_distance(person.threat, person.position) > .3:
            person.node.set_h(_angle(person.threat - person.position))

    def _start_fight(self, person):
        person.state = "fight"
        person.attack_at = max(person.attack_at, self.elapsed + self.rng.uniform(.4, .85))
        person.approach_until = self.elapsed
        person.escape_until = self.elapsed + 16.

    def displaced_driver(self, person, player_position, *, hostile=False, from_position=None):
        if person is None or not person.alive:
            return
        person.hostility = 78.
        person.threat = Vec3(player_position)
        person.escape_until = self.elapsed + 13.
        person.reaction = "fight" if hostile and person.spec.get("weapon") else "flee"
        self._knock_down(person)
        if from_position is not None:
            destination, origin = person.position, Vec3(from_position)
            origin.z = max(destination.z, origin.z - .22)
            person.drag = self.elapsed, origin, Vec3(destination)
            person.node.set_h(_angle(origin - destination))
            person.node.set_pos(self.render, origin)

    def _frighten(self, person, position):
        if not person.alive or person.state in ("dead", "knocked_down", "fight"):
            return
        person.threat = Vec3(position)
        person.escape_until = max(person.escape_until, self.elapsed + self.rng.uniform(6.0, 10.0)
                                  - person.spec["courage"] * 2.)
        if person.state in ("panic", "flee"):
            return
        person.state = "panic"
        person.state_until = person.escape_until if person.pinned else self.elapsed + self.rng.uniform(.11, .42)

    def _gunshot(self, position=None, owner=None, origin=None, **_):
        point = position if position is not None else origin
        if point is not None:
            for person in self.people:
                if person is not owner and _flat_distance(person.position, point) < 39:
                    self._frighten(person, point)

    def _explosion(self, position=None, radius=10., **_):
        if position is not None:
            for person in self.people:
                if _flat_distance(person.position, position) < max(26., float(radius) * 2.5):
                    self._frighten(person, position)

    def _sample_cars(self, vehicles, occupied):
        self._car_samples.clear()
        for car in vehicles:
            if not car.physics_active:
                continue
            point = Vec3(car.position)
            if _flat_distance(point, self._focus) > 153:
                continue
            velocity = Vec3(car.body.get_linear_velocity())
            velocity.z = 0.
            speed = velocity.length()
            if speed < 3.3:
                continue
            forward = car.node.get_quat().get_forward()
            forward.z = 0.
            if not forward.normalize():
                forward = velocity / speed
            self._car_samples.append((car, car is occupied, point, forward, velocity / speed, speed))

    def _vehicle_reaction(self, person):
        position = person.position
        for car, controlled, point, forward, travel, speed in self._car_samples:
            difference = position - point
            if abs(difference.z) > 1.45 or abs(difference.x) > 14 or abs(difference.y) > 14:
                continue
            difference.z = 0.
            along = difference.dot(forward)
            lateral = abs(difference.x * forward.y - difference.y * forward.x)
            half_width = car.spec["width"] * .5
            half_length = car.spec["length"] * .5
            if (lateral < half_width + .25 and abs(along) < half_length + .23
                    and (person.state != "knocked_down" or speed > 7)
                    and self.elapsed >= person.safe_until):
                person.safe_until = self.elapsed + 1.25
                self.events.publish("damage", target=person, amount=min(105., 12. + speed * 2.9),
                                    source=car, direction=travel, kind="vehicle")
                if controlled:
                    self.events.publish("hit_and_run", person=person, vehicle=car, position=position)
                return
            travel_offset = difference.dot(travel)
            travel_side = abs(difference.x * travel.y - difference.y * travel.x)
            if 0.2 < travel_offset < min(13, 1.4 + speed * .54) and travel_side < half_width + .56:
                self._frighten(person, point)

    def _select_route(self, person, intersection):
        neighbors = self.graph.sidewalk_neighbors(intersection)
        options = [node for node in neighbors if node != person.route_from] or list(neighbors)
        if not options:
            return
        if person.state == "flee":
            # Let the sidewalk split direct a fleeing citizen away from the danger.
            options = list(neighbors)
            choice = max(options, key=lambda n: _flat_distance(
                Vec3(*self.graph.sidewalk_position(n), 0), person.threat) + self.rng.uniform(0, 12))
        else:
            choice = self.rng.choice(options)
        person.route_from, person.route_to = intersection, choice
        person.crossing = False

    def _walk(self, person, dt):
        if not person.route_to:
            route, person.route_entry = self._route_at(person.position)
            if not route:
                return
            person.route_from, person.route_to = route
        crossing = None if person.route_entry is not None else self._crosswalks.get(
            (person.route_from, person.route_to))
        is_fleeing = person.state == "flee"
        if crossing is not None and not person.crossing:
            if self.graph.pedestrian_signal(crossing, self.elapsed) != "walk" and not is_fleeing:
                person.state = "wait"
                person.velocity = Vec3()
                return
            person.crossing = True

        goal = person.route_entry
        if goal is None:
            goal = Vec3(*self.graph.sidewalk_position(person.route_to), 0)
        position = person.position
        delta = goal - position
        delta.z = 0.
        distance = delta.length()
        speed = person.spec["run_mps" if is_fleeing else "walk_mps"] * person.speed_scale
        if crossing is not None and not is_fleeing:
            speed = max(speed, 1.75)
        if distance < max(.075, speed * dt):
            self._shift(person, Vec3(goal.x, goal.y, position.z), delta, speed, dt)
            if person.route_entry is not None:
                person.route_entry = None
                return
            previous_crossing = person.crossing
            self._select_route(person, person.route_to)
            if not is_fleeing and not previous_crossing and self.rng.random() < .24:
                person.rest_until = self.elapsed + self.rng.uniform(.65, 2.3)
            return
        direction = delta / distance
        self._shift(person, position + direction * speed * dt, direction, speed, dt)
        if not is_fleeing:
            person.state = "walk"

    def _shift(self, person, position, direction, speed, dt):
        if not self.city.is_loaded(position.x, position.y):
            person.velocity = Vec3()
            return
        position.z += (_grade(position.x, position.y) - position.z) * min(1., dt * 16)
        person.node.set_pos(self.render, position)
        if direction.length_squared() > .0001:
            direction = direction.normalized()
            target_h = _angle(direction)
            current_h = person.node.get_h()
            difference = (target_h - current_h + 180) % 360 - 180
            person.node.set_h(current_h + difference * min(1., dt * 14.))
            person.velocity = direction * speed

    def _fight(self, person, player, occupied):
        if not player.active and occupied is None:
            return
        target_position = Vec3(occupied.position if occupied is not None else player.position)
        delta = target_position - person.position
        delta.z = 0.
        distance = delta.length()
        if distance > 30 or self.elapsed > person.escape_until:
            person.state = "flee"
            person.escape_until = self.elapsed + 3.0
            return
        person.velocity = Vec3()
        person.node.set_h(_angle(delta))
        if person.decision_at > self.elapsed or person.attack_at > self.elapsed:
            return
        person.attack_at = self.elapsed + self.rng.uniform(.72, 1.45)
        direction = delta / max(.1, distance)
        origin = person.position + _UP * (1.25 * person.height) + direction * .38
        target = target_position + _UP * (.85 if occupied is not None else 1.23)
        if distance > 21 or self._blocked(origin, target, occupied) is not None:
            if distance > 4 and self._blocked(person.position + _UP * .8,
                                              person.position + direction * 1.05 + _UP * .8,
                                              occupied) is None:
                person.approach_until = self.elapsed + .44
            return
        chance = max(.31, .89 - distance * .021)
        hit = self.rng.random() < chance
        if not hit:
            target += Vec3(-direction.y, direction.x, 0) * self.rng.choice((-1.25, 1.25))
        self.events.publish("npc_shot", origin=origin, end=target, blocked=False, person=person)
        self.events.publish("gunshot", position=origin, direction=(target - origin).normalized(),
                            weapon=person.spec["weapon"], owner=person)
        if hit:
            victim = occupied if occupied is not None else player
            self.events.publish("damage", target=victim, amount=person.spec["attack_damage"],
                                source=person, kind="npc_gunshot", direction=direction)

    def _bump(self, person, player):
        if (not player.active or self.elapsed < person.bump_ready or not person.alive
                or person.state not in ("idle", "walk", "wait")
                or _flat_distance(player.position, person.position) > .63
                or abs(player.position.z - person.position.z) > .7):
            return
        person.bump_ready = self.elapsed + 3.4
        person.hostility = min(100., person.hostility + 23.)
        person.rest_until = max(person.rest_until, self.elapsed + .48)
        separation = person.position - player.position
        separation.z = 0.
        if separation.length_squared() > .005:
            person.node.set_h(_angle(-separation))
            step = Vec3(separation.y, -separation.x, 0).normalized() * .34
            here = person.position
            if not person.pinned and self._blocked(here + _UP * .8, here + step + _UP * .8) is None:
                person.node.set_pos(self.render, here + step)
        self.events.publish("pedestrian_bump", person=person, message=self._line(person, person.mood),
                            position=person.position)

    def _update_person(self, person, dt, player, distance, occupied):
        if not person.alive:
            return
        decay = 2.2 if person.state in ("idle", "walk", "wait") else .62
        person.hostility = max(0., person.hostility - decay * dt)
        if person.decision_at <= self.elapsed:
            if distance < 100:
                self._vehicle_reaction(person)
                if not person.alive:
                    return
            self._bump(person, player)
            if person.state == "fight":
                self._fight(person, player, occupied)
            person.decision_at = self.elapsed + (.10 if distance < 35 else .26) + self.rng.random() * .033

        if person.state == "knocked_down":
            if person.drag is not None:
                started, origin, destination = person.drag
                fraction = min(1., (self.elapsed - started) / .36)
                blend = fraction * fraction * (3. - fraction * 2.)
                person.node.set_pos(self.render, origin + (destination - origin) * blend)
                if fraction == 1.:
                    person.drag = None
            if self.elapsed >= person.state_until:
                if person.reaction == "fight":
                    self._start_fight(person)
                else:
                    person.state = "flee"
            return
        if person.state == "fight":
            if self.elapsed < person.approach_until:
                target = occupied.position if occupied is not None else player.position
                direction = Vec3(target) - person.position
                direction.z = 0.
                direction.normalize()
                speed = person.spec["walk_mps"]
                self._shift(person, person.position + direction * speed * dt, direction, speed, dt)
            return
        if person.state == "panic":
            person.velocity = Vec3()
            if self.elapsed < person.state_until:
                return
            if person.pinned:
                person.state = "idle"
                person.rest_until = person.escape_until
                return
            person.state = "flee"
            if not person.crossing and person.route_from is not None and person.route_to is not None:
                prior = Vec3(*self.graph.sidewalk_position(person.route_from), 0)
                ahead = Vec3(*self.graph.sidewalk_position(person.route_to), 0)
                if _flat_distance(prior, person.threat) > _flat_distance(ahead, person.threat):
                    person.route_from, person.route_to = person.route_to, person.route_from
        if person.state == "flee" and (self.elapsed >= person.escape_until or person.pinned):
            person.state = "idle"
            person.rest_until = self.elapsed + .3
        if person.pinned or (self.elapsed < person.rest_until and person.state != "flee"):
            if person.pinned and self.elapsed < person.escape_until:
                person.state = "panic"
                person.state_until = person.escape_until
            else:
                person.state = "idle"
            person.velocity = Vec3()
            return
        self._walk(person, dt)

    def update(self, dt, elapsed, focus, player, vehicles=(), occupied=None):
        self.elapsed = elapsed
        self._focus = Vec3(focus)
        self._player = player
        if elapsed >= self._spawn_at:
            self._stream(focus)
        if elapsed >= self._next_car_sample:
            self._sample_cars(vehicles, occupied)
            self._next_car_sample = elapsed + .065
        for person in self.people:
            distance = _flat_distance(person.position, focus)
            self._update_person(person, dt, player, distance, occupied)
            if elapsed >= person.animation_at:
                period = dt if distance < 34 else .083 if distance < 70 else .18
                person.art.update(period, person.state, person.velocity.length())
                person.animation_at = elapsed + period

    def _raycast_person(self, person, origin, direction, max_distance, width=0.):
        if not person.alive:
            return None
        position = person.position
        scale = person.height
        if person.state == "knocked_down":
            forward = person.node.get_quat(self.render).get_forward()
            spheres = ((position - forward * .84 + _UP * .24, .42, False),)
        else:
            spheres = tuple((position + _UP * (z * scale), (radius + width) * scale, head)
                            for z, radius, head in ((1.64, .171, True), (1.18, .287, False),
                                                     (.76, .265, False), (.37, .19, False)))
        best = None
        for center, radius, head in spheres:
            gap = center - origin
            projection = gap.dot(direction)
            discriminant = radius * radius - (gap.length_squared() - projection * projection)
            if discriminant < 0.:
                continue
            distance = max(0., projection - math.sqrt(discriminant))
            if projection + math.sqrt(discriminant) < 0. or distance > max_distance:
                continue
            hit = origin + direction * distance
            normal = (hit - center).normalized()
            best = PedestrianHit(person, distance, hit, normal, head)
            max_distance = distance
        return best

    def raycast(self, origin, direction, max_distance):
        return self._raycast(origin, direction, max_distance, 0.)

    def melee_target(self, origin, direction, max_distance):
        return self._raycast(origin, direction, max_distance, .25)

    def _raycast(self, origin, direction, max_distance, width):
        closest = None
        origin, direction = Vec3(origin), Vec3(direction)
        if direction.length_squared() < .001:
            return None
        direction.normalize()
        for person in self.people:
            if _flat_distance(origin, person.position) > max_distance + 1.:
                continue
            hit = self._raycast_person(person, origin, direction, max_distance, width)
            if hit is not None:
                closest = hit
                max_distance = hit.distance
        return closest

    def close(self):
        self.events.unsubscribe("gunshot", self._gunshot)
        self.events.unsubscribe("explosion", self._explosion)
        self.events.unsubscribe("damage", self._damage_event)
        for person in self.people[:]:
            self._remove(person)
        self.root.remove_node()
        for template in self._templates.values():
            template.remove_node()
        self._templates.clear()

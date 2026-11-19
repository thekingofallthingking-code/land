"""Local traffic using the city's directed lanes and Bullet vehicles."""
from __future__ import annotations

from dataclasses import dataclass
import math
from random import Random

from panda3d.core import AudioSound, BitMask32, Vec2, Vec3

from game.entities.vehicles import ASSETS, Vehicle
from game.world.roads import CHUNK_SIZE, Lane

SPAWN_MIN = 29.0
SPAWN_MAX = 148.0
REMOVE_DISTANCE = 238.0
CORNER_LEAD = 9.0
STOP_DECELERATION = 3.8
MAX_CITY_VEHICLES = 25
ROAD_MASK = BitMask32.bit(0)


def _xy(position):
    return Vec2(position[0], position[1])


def _direction(start, end):
    direction = _xy(end) - _xy(start)
    direction.normalize()
    return direction


def _clamp(value, low, high):
    return min(high, max(low, value))


@dataclass(frozen=True, slots=True)
class Driver:
    archetype: str
    hostile: bool


@dataclass(frozen=True, slots=True)
class PathSection:
    start: Vec2
    direction: Vec2
    length: float
    progress: float


@dataclass(slots=True)
class TrafficDriver:
    identity: Driver
    lane: Lane
    outgoing: Lane
    sections: tuple[PathSection, ...]
    turn_speed: float
    cruise_factor: float
    segment: int = 0
    committed: bool = False
    held: bool = False
    next_think: float = 0.0
    throttle: float = 0.0
    steer: float = 0.0
    brake: float = 0.0
    target_speed: float = 0.0
    panic_until: float = 0.0
    blocked_since: float | None = None
    horn_cooldown: float = 0.0
    horn: AudioSound | None = None
    mode: str = "cruise"


def _path_sections(lane, outgoing):
    forward = _direction(lane.start, lane.end)
    onward = _direction(outgoing.start, outgoing.end)
    entry = _xy(lane.end) - forward * CORNER_LEAD
    finish = _xy(outgoing.start) + onward * CORNER_LEAD
    turn = forward.dot(onward) < 0.5
    points = [_xy(lane.start)]
    if turn:
        arm = abs((finish - entry).dot(forward)) * 0.56
        control_a = entry + forward * arm
        control_b = finish - onward * arm
        for step in range(9):
            t = step / 8.0
            s = 1.0 - t
            points.append(entry * s ** 3 + control_a * (3 * t * s ** 2)
                          + control_b * (3 * t ** 2 * s) + finish * t ** 3)
    else:
        points.append(finish)
    sections = []
    distance = 0.0
    for start, end in zip(points, points[1:]):
        offset = end - start
        length = offset.length()
        if length > 0.01:
            sections.append(PathSection(start, offset / length, length, distance))
            distance += length
    turn_speed = (4.9 if (finish - entry).length() < 11 else 6.7) if turn else math.inf
    return tuple(sections), turn_speed


def _path_progress(driver, position):
    best_error = math.inf
    best = 0.0
    for index in range(max(0, driver.segment - 1), min(len(driver.sections), driver.segment + 4)):
        section = driver.sections[index]
        relative = position - section.start
        along = _clamp(relative.dot(section.direction), 0.0, section.length)
        error = (relative - section.direction * along).length_squared()
        if error < best_error:
            best = section.progress + along
            best_error = error
            best_index = index
    driver.segment = best_index
    return best


def _path_point(sections, distance):
    for section in sections:
        if distance < section.progress + section.length:
            return section.start + section.direction * (distance - section.progress)
    last = sections[-1]
    return last.start + last.direction * (distance - last.progress)


class Traffic:
    """Time-slices lane decisions and owns only cars with traffic drivers."""

    def __init__(self, render, physics, city, events, *, audio_loader=None, cap=16, seed=4815):
        self.render = render
        self.physics = physics
        self.city = city
        self.graph = city.graph
        self.events = events
        self.audio_loader = audio_loader
        self.cap = min(MAX_CITY_VEHICLES, max(0, int(cap)))
        self.random = Random(seed)
        self.vehicles: list[Vehicle] = []
        self.drivers: dict[Vehicle, TrafficDriver] = {}
        self.elapsed = 0.0
        self._next_spawn = 0.0
        self._next_horn = 0.0
        self._road_candidates = ()
        self._spawn_center = None
        self._closed = False
        self.horn_count = 0
        self.events.subscribe("damage", self._damage)
        self.events.subscribe("gunshot", self._gunshot)

    def has_driver(self, vehicle):
        return vehicle in self.drivers

    def hold_vehicle(self, vehicle, hold=True):
        state = self.drivers.get(vehicle)
        if state is None:
            return False
        state.held = hold
        state.next_think = self.elapsed
        return True

    def take_vehicle(self, vehicle):
        """Transfer ownership without detaching or replacing the Bullet chassis."""
        state = self.drivers.pop(vehicle, None)
        if state is None:
            return None
        self.vehicles.remove(vehicle)
        self._stop_horn(state)
        vehicle.release_ai_driver()
        return state.identity

    def _stop_horn(self, state):
        if state.horn is not None:
            state.horn.stop()
            detach = getattr(self.audio_loader, "detachSound", None)
            if detach is not None:
                detach(state.horn)

    def _remove(self, vehicle):
        self.take_vehicle(vehicle)
        vehicle.close()

    def _pick_outgoing(self, lane):
        ahead = (lane.destination[0] * 2 - lane.origin[0], lane.destination[1] * 2 - lane.origin[1])
        options = [node for node in self.graph.neighbors(lane.destination) if node != lane.origin]
        if ahead in options and self.random.random() < 0.64:
            return self.graph.lane(lane.destination, ahead)
        turns = [node for node in options if node != ahead]
        return self.graph.lane(lane.destination, self.random.choice(turns or options or [lane.origin]))

    def spawn_on_lane(self, origin, destination, distance=42.0, kind="compact", *, next_destination=None):
        """Start a normal driver on a loaded directed lane at its metre offset."""
        if self._closed or len(self.vehicles) >= self.cap:
            return None
        lane = self.graph.lane(origin, destination)
        direction = _direction(lane.start, lane.end)
        point = _xy(lane.start) + direction * _clamp(distance, 16.0, CHUNK_SIZE - 19.0)
        if not self.city.is_loaded(point.x, point.y):
            return None
        road = self.physics.ray_test_closest(Vec3(point.x, point.y, 1.8),
                                             Vec3(point.x, point.y, -1), ROAD_MASK)
        if not road.has_hit() or road.get_hit_normal().z < .8 or road.get_hit_pos().z > .44:
            return None
        position = Vec3(point.x, point.y, road.get_hit_pos().z + 0.76)
        if any((car.position - position).length_squared() < 42.0 for car in self.vehicles):
            return None
        outgoing = self.graph.lane(destination, next_destination) if next_destination else self._pick_outgoing(lane)
        sections, turn_speed = _path_sections(lane, outgoing)
        heading = math.degrees(math.atan2(-direction.x, direction.y))
        vehicle = Vehicle(self.render, self.physics, kind, position, heading,
                          audio_loader=self.audio_loader, events=self.events)
        archetype = self.random.choices(("commuter", "local", "dockworker", "gang"), (43, 33, 20, 4))[0]
        driver = Driver(archetype, archetype == "gang" or self.random.random() < 0.16)
        self.vehicles.append(vehicle)
        self.drivers[vehicle] = TrafficDriver(
            driver, lane, outgoing, sections, turn_speed, self.random.uniform(0.82, 0.98),
            next_think=self.elapsed + self.random.uniform(0, 0.09),
        )
        return vehicle

    def _spawn_near(self, focus, obstacles, pedestrians):
        center = self.graph.nearest_intersection(focus.x, focus.y)
        if center != self._spawn_center:
            ix, iy = center
            self._road_candidates = tuple(
                self.graph.lane((x, y), neighbor)
                for x in range(ix - 2, ix + 3)
                for y in range(iy - 2, iy + 3)
                for neighbor in self.graph.neighbors((x, y))
            )
            self._spawn_center = center
        for _ in range(min(20, len(self._road_candidates))):
            lane = self.random.choice(self._road_candidates)
            distance = self.random.uniform(20.0, CHUNK_SIZE - 20.0)
            position = _xy(lane.start) + _direction(lane.start, lane.end) * distance
            if not SPAWN_MIN ** 2 <= (position - _xy(focus)).length_squared() <= SPAWN_MAX ** 2:
                continue
            if any((position - _xy(car.position)).length_squared() < 85 for car in obstacles):
                continue
            if any((position - _xy(point)).length_squared() < 16 for point in pedestrians):
                continue
            kind = self.random.choices(("compact", "sport", "van"), (58, 19, 23))[0]
            if self.spawn_on_lane(lane.origin, lane.destination, distance, kind) is not None:
                return

    def _damage(self, target, amount, source, **unused):
        if not isinstance(target, Vehicle) or source == "collision" or amount <= 0:
            return
        driver = self.drivers.get(target)
        if driver is not None:
            driver.panic_until = self.elapsed + self.random.uniform(7.0, 11.0)
            driver.next_think = self.elapsed

    def _gunshot(self, position, **unused):
        position = Vec3(position)
        for vehicle, driver in self.drivers.items():
            if (vehicle.position - position).length_squared() < 26.0 ** 2:
                driver.panic_until = self.elapsed + self.random.uniform(5.0, 8.0)
                driver.next_think = self.elapsed

    def _change_lane(self, state):
        state.lane = state.outgoing
        state.outgoing = self._pick_outgoing(state.lane)
        state.sections, state.turn_speed = _path_sections(state.lane, state.outgoing)
        state.segment = 0
        state.committed = False

    def _speed_for_signal(self, car, state, position, speed, target):
        lane = state.lane
        direction = _direction(lane.start, lane.end)
        remaining = (_xy(lane.stop) - position).dot(direction) - car.spec["length"] * .5 - .38
        if state.committed or remaining > 42:
            return target, False
        light = self.graph.signal(lane.destination, self.elapsed, lane.axis)
        stopping_distance = speed * speed / (2.0 * STOP_DECELERATION) + 1.5
        if light == "green" or light == "yellow" and remaining < stopping_distance:
            state.committed = remaining < .25
            return target, False
        return min(target, math.sqrt(2.0 * STOP_DECELERATION * max(0.0, remaining - .44))), True

    def _speed_for_obstacle(self, car, position, forward, speed, target, cars, pedestrians):
        right = Vec2(forward.y, -forward.x)
        front = car.spec["length"] * 0.5
        width = car.spec["width"] * 0.5
        horizon = max(13.0, speed * 1.45 + 8.0)
        cause = None
        for other in cars:
            if other is car:
                continue
            offset = _xy(other.position) - position
            ahead = offset.dot(forward)
            if ahead < 0.05 or ahead > horizon:
                continue
            other_forward = _xy(other.node.get_quat(other.render).get_forward())
            side_extent = abs(other_forward.dot(right)) * other.spec["length"] * .5
            side_extent += abs(other_forward.dot(forward)) * other.spec["width"] * .5
            if abs(offset.dot(right)) > width + side_extent + .40:
                continue
            gap = ahead - front - other.spec["length"] * .50
            speed_ahead = max(0.0, _xy(other.body.get_linear_velocity()).dot(forward))
            limit = speed_ahead + max(0.0, (gap - 2.1) * .76)
            if limit < target:
                target, cause = limit, "vehicle"
        for foot in pedestrians:
            offset = _xy(foot) - position
            ahead = offset.dot(forward)
            lateral = abs(offset.dot(right))
            if front * .35 < ahead < horizon and lateral < width + .98:
                gap = ahead - front - 2.25
                limit = math.sqrt(2.0 * 3.2 * max(0.0, gap))
                if limit < target:
                    target, cause = limit, "pedestrian"
        if cause is None and speed > .1:
            z = car.position.z + max(.14, car.spec["height"] * .19)
            ray_length = min(11.0, horizon)
            start = position + forward * (front + .25)
            end = start + forward * ray_length
            hit = self.physics.ray_test_closest(Vec3(start.x, start.y, z), Vec3(end.x, end.y, z), ROAD_MASK)
            if hit.has_hit():
                gap = ray_length * hit.get_hit_fraction() - 1.15
                limit = math.sqrt(2.0 * 3.7 * max(0.0, gap))
                if limit < target:
                    target, cause = limit, "obstacle"
        return target, cause

    def _horn(self, car, state, focus):
        if self.elapsed < max(state.horn_cooldown, self._next_horn):
            return
        distance = (car.position - focus).length()
        if distance > 62.0:
            return
        state.horn_cooldown = self.elapsed + self.random.uniform(5.0, 8.0)
        self._next_horn = self.elapsed + 1.2
        self.horn_count += 1
        if self.audio_loader is not None and state.horn is None:
            path = ASSETS / "horn.wav"
            if path.is_file():
                state.horn = self.audio_loader.loadSfx(str(path))
                attach = getattr(self.audio_loader, "attachSoundToObject", None)
                if attach is not None and state.horn is not None:
                    attach(state.horn, car.node)
        if state.horn is not None:
            state.horn.set_volume(max(.08, .63 * (1.0 - distance / 68.0)))
            state.horn.play()
        self.events.publish("traffic_horn", vehicle=car, position=car.position)

    def _think(self, car, state, focus, cars, pedestrians):
        speed = max(0.0, car.speed_kph / 3.6)
        position = _xy(car.position)
        forward = _xy(car.node.get_quat(car.render).get_forward())
        forward.normalize()
        lookahead = _clamp(2.7 + speed * .49, 3.4, 10.5)
        progress = _path_progress(state, position)
        last = state.sections[-1]
        finish = last.start + last.direction * last.length
        if progress > last.progress + last.length - 1.8 and (position - finish).dot(last.direction) > -2.0:
            self._change_lane(state)
            progress = _path_progress(state, position)
        aim = _path_point(state.sections, progress + lookahead) - position
        aim_heading = math.degrees(math.atan2(-aim.x, aim.y))
        heading_error = (aim_heading - car.heading + 180) % 360 - 180
        state.steer = _clamp(-heading_error / (16.0 + speed * .46), -1, 1)
        fleeing = self.elapsed < state.panic_until
        target = state.lane.speed_limit * state.cruise_factor * (1.25 if fleeing else 1.0)
        lane_direction = _direction(state.lane.start, state.lane.end)
        entry_distance = (_xy(state.lane.end) - position).dot(lane_direction) - CORNER_LEAD
        if math.isfinite(state.turn_speed):
            target = min(target, math.sqrt(state.turn_speed ** 2 + 2.0 * 3.5 * max(0.0, entry_distance)))
        if not fleeing:
            target, signal = self._speed_for_signal(car, state, position, speed, target)
        else:
            signal = False
        target, obstacle = self._speed_for_obstacle(car, position, forward, speed, target, cars, pedestrians)
        state.mode = obstacle or ("signal" if signal else "flee" if fleeing else "cruise")
        state.target_speed = target
        error = target - speed
        state.throttle = _clamp(error * .36 + .055, 0.0, 1.0) if target > .18 else 0.0
        state.brake = _clamp(-error * .26, 0.0, 1.0)
        if target <= .18:
            state.brake = max(.47, state.brake)
        if obstacle in ("pedestrian", "vehicle") and target < 1.1 and speed < 1.3:
            if state.blocked_since is None:
                state.blocked_since = self.elapsed
            elif self.elapsed - state.blocked_since > 1.35:
                self._horn(car, state, focus)
        else:
            state.blocked_since = None

    def update(self, dt, focus, pedestrians=(), *, obstacles=(), night=0.0, elapsed=None):
        if self._closed:
            return
        self.elapsed = self.elapsed + dt if elapsed is None else elapsed
        obstacle_cars = tuple(car for car in obstacles if car.physics_active and car not in self.drivers)
        foot_positions = tuple(Vec3(ped.position if hasattr(ped, "position") else ped) for ped in pedestrians
                               if getattr(ped, "state", None) != "dead")
        focus = Vec3(focus)
        for car in tuple(self.vehicles):
            if self.drivers[car].held:
                continue
            point = car.position
            xy_distance = (point - focus).length_squared()
            if (xy_distance > REMOVE_DISTANCE ** 2 or point.z < -3
                    or not self.city.is_loaded(point.x, point.y)):
                self._remove(car)
        room = min(self.cap, max(0, MAX_CITY_VEHICLES - len(obstacle_cars)))
        if len(self.vehicles) > room:
            remove_count = len(self.vehicles) - room
            available = (car for car in self.vehicles if not self.drivers[car].held)
            farthest = sorted(available, key=lambda car: (car.position - focus).length_squared(), reverse=True)
            for car in farthest[:remove_count]:
                self._remove(car)
        if len(self.vehicles) < room and self.elapsed >= self._next_spawn:
            self._next_spawn = self.elapsed + .22
            self._spawn_near(focus, obstacle_cars, foot_positions)
        cars = tuple(self.vehicles) + obstacle_cars
        for car, state in self.drivers.items():
            distance = (car.position - focus).length()
            if state.held:
                state.throttle = state.steer = 0.0
                state.brake = 1.0
                state.target_speed = 0.0
                state.mode = "held"
            elif self.elapsed >= state.next_think:
                state.next_think = self.elapsed + (.092 if distance < 75.0 else .179)
                self._think(car, state, focus, cars, foot_positions)
            volume = max(0.0, .145 * (1.0 - distance / 38.0))
            car.update(dt, state.throttle, state.steer, ai_driver=True, service_brake=state.brake,
                       ai_engine_volume=volume, night=night)

    def after_physics(self, dt):
        for car in self.vehicles:
            car.after_physics(dt)

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.events.unsubscribe("damage", self._damage)
        self.events.unsubscribe("gunshot", self._gunshot)
        for car in tuple(self.vehicles):
            self._remove(car)

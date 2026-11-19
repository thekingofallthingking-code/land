"""Arcade cruiser dispatch and localized road pursuit."""
from __future__ import annotations

from dataclasses import dataclass
import json
import math

from panda3d.core import AudioSound, BitMask32, Vec2, Vec3

from game.ai.traffic import Traffic, _clamp, _direction, _path_point, _path_progress, _path_sections, _xy
from game.entities.vehicles import ASSETS, ROOT
from game.world.roads import CHUNK_SIZE, LANE_OFFSET, ROAD_HALF_WIDTH

RULES = json.loads((ROOT / "game/data/police.json").read_text(encoding="utf-8"))
TOTAL_CAP = 12
CHASE_MASK = BitMask32.bit(0)


@dataclass(slots=True)
class Cruiser:
    role: str
    mode: str
    block_point: Vec2 | None = None
    block_axis: Vec2 | None = None
    deployed: bool = False
    next_contact: float = 0.0
    siren: AudioSound | None = None
    parked_at: float | None = None
    disabled_at: float | None = None
    route_at: float = 0.0
    goal: tuple[int, int] | None = None


class PoliceFleet(Traffic):
    """A fleet of emergency vehicles sharing the civilian lane follower."""

    def __init__(self, render, physics, city, events, *, audio_loader=None, cap=9, seed=137):
        self.total_cap = min(TOTAL_CAP, max(0, int(cap)))
        super().__init__(render, physics, city, events, audio_loader=audio_loader, cap=min(4, self.total_cap), seed=seed)
        self.units: dict = {}
        self._route_goal = None
        self._last_stars = 0
        self._last_mode = "clear"
        self._dispatch_at = math.inf
        self._retreat_at = math.inf
        self._block_point: Vec2 | None = None
        self._block_axis: Vec2 | None = None
        self._block_node: tuple[int, int] | None = None
        self._departed_count = 0
        self._ram_count = 0
        self._player_vehicle = None

    @property
    def roadblock_count(self):
        return sum(unit.mode == "roadblock" for unit in self.units.values())

    @property
    def ram_count(self):
        return self._ram_count

    def is_police(self, vehicle):
        return vehicle in self.units

    def has_driver(self, vehicle):
        return vehicle in self.units and not self.units[vehicle].deployed and vehicle.health > 0

    def sighting_sources(self):
        return tuple((car.position + Vec3(0, 0, .63), car.body) for car in self.vehicles if self.has_driver(car))

    def _pick_outgoing(self, lane):
        if self._route_goal is not None:
            route = self.graph.path(lane.destination, self._route_goal)
            if len(route) > 1 and route[1] != lane.origin:
                return self.graph.lane(lane.destination, route[1])
        return super()._pick_outgoing(lane)

    def _release_siren(self, unit):
        if unit.siren is None:
            return
        unit.siren.stop()
        detach = getattr(self.audio_loader, "detachSound", None)
        if detach is not None:
            detach(unit.siren)
        unit.siren = None

    def take_vehicle(self, vehicle):
        unit = self.units.get(vehicle)
        if unit is None or self.has_driver(vehicle):
            return None
        self.units.pop(vehicle)
        self._release_siren(unit)
        vehicle.set_emergency_lights(0.0, False)
        return super().take_vehicle(vehicle)

    def _remove(self, vehicle):
        unit = self.units.pop(vehicle, None)
        if unit is not None:
            self._release_siren(unit)
        super().take_vehicle(vehicle)
        vehicle.close()

    def clear(self):
        for car in tuple(self.vehicles):
            self._remove(car)
        self._last_stars = 0
        self._last_mode = "clear"
        self._dispatch_at = math.inf
        self._retreat_at = math.inf
        self._block_point = self._block_axis = self._block_node = None
        self._player_vehicle = None

    def _load_siren(self, car):
        path = ASSETS / "siren.wav"
        if self.audio_loader is None or not path.is_file():
            return None
        sound = self.audio_loader.loadSfx(str(path))
        if sound is not None:
            attach = getattr(self.audio_loader, "attachSoundToObject", None)
            if attach is not None:
                attach(sound, car.node)
            sound.set_loop(True)
        return sound

    def _update_siren(self, car, unit, distance, enabled):
        car.set_emergency_lights(self.elapsed, enabled)
        if unit.siren is None:
            return
        volume = max(0.0, .39 * (1.0 - distance / 114.0)) if enabled else 0.0
        unit.siren.set_volume(volume)
        if volume > .018 and unit.siren.status() != unit.siren.PLAYING:
            unit.siren.play()
        elif volume <= .018 and unit.siren.status() == unit.siren.PLAYING:
            unit.siren.stop()

    def _find_blockade(self, focus, heading):
        axis = Vec2(math.copysign(1.0, heading.x), 0) if abs(heading.x) > abs(heading.y) else Vec2(
            0, math.copysign(1.0, heading.y))
        near, far = RULES["roadblock_distance"]
        for advance in (78.0, 117.0, 147.0):
            aim = focus + axis * advance
            node = self.graph.nearest_intersection(aim.x, aim.y)
            center = _xy(self.graph.position(node))
            gap = (center - focus).dot(axis)
            sides = {(neighbor[0] - node[0], neighbor[1] - node[1]) for neighbor in self.graph.neighbors(node)}
            if near <= gap <= far and (int(axis.x), int(axis.y)) in sides:
                self._block_point = center - axis * 5.2
                self._block_axis = axis
                self._block_node = node
                return

    def _next_role(self, stars):
        roles = {unit.role for unit in self.units.values() if not unit.deployed or unit.role == "blocker"}
        if stars >= 3 and "blocker" not in roles and self._block_point is not None and self.vehicles:
            return "blocker"
        if "pursuer" not in roles:
            return "pursuer"
        if stars >= 2 and "flanker" not in roles:
            return "flanker"
        if stars >= 3 and self._block_point is not None and "blocker" in roles:
            if sum(unit.role == "blocker" for unit in self.units.values()) < 2:
                return "blocker"
        return "pursuer"

    def _spawn(self, focus, forward, stars, obstacles):
        role = self._next_role(stars)
        center = self.graph.nearest_intersection(focus.x, focus.y)
        min_gap, max_gap = RULES["spawn_distance"]
        target = self._block_point if role == "blocker" else focus
        goal = self._block_node if role == "blocker" else center
        self._route_goal = goal
        block_side = 1 if not any(unit.role == "blocker" for unit in self.units.values()) else -1
        if role == "blocker":
            axis = self._block_axis
            right = Vec2(axis.y, -axis.x)
            stop = target + right * (LANE_OFFSET * block_side)
        else:
            axis = stop = None
        points = []
        cx, cy = center
        for x in range(cx - 2, cx + 3):
            for y in range(cy - 2, cy + 3):
                origin = (x, y)
                for end in self.graph.neighbors(origin):
                    lane = self.graph.lane(origin, end)
                    direction = _direction(lane.start, lane.end)
                    distances = (28.0, 58.0, 91.0, 121.0)
                    for distance in distances:
                        pos = _xy(lane.start) + direction * distance
                        offset = pos - focus
                        gap = offset.length()
                        if not min_gap < gap < max_gap or not self.city.is_loaded(pos.x, pos.y):
                            continue
                        if any((pos - _xy(car.position)).length_squared() < 68 for car in obstacles):
                            continue
                        towards = target - pos
                        toward_dot = direction.dot(towards)
                        if role == "blocker":
                            # Prefer approaching the blockade on the same road from the far side.
                            gap_to_block = towards.length()
                            aligned = abs(axis.dot(direction)) > .8
                            score = gap_to_block + (0.0 if aligned else 16.0) - toward_dot * .34
                        else:
                            score = abs(gap - (43 if role == "pursuer" else 69))
                            score -= toward_dot * .34
                            score += offset.dot(forward) * (.075 if role == "pursuer" else -.055)
                        points.append((score + self.random.uniform(0.0, 5.0), lane, distance))
        for _, lane, distance in sorted(points, key=lambda row: row[0])[:10]:
            car = self.spawn_on_lane(lane.origin, lane.destination, distance, "police")
            if car is None:
                continue
            unit = Cruiser(role, "enroute", stop, axis, siren=self._load_siren(car), goal=goal)
            self.units[car] = unit
            self.events.publish("police_dispatch", vehicle=car, role=role, position=car.position)
            return car
        return None

    def _refresh_route(self, state, unit, goal):
        self._route_goal = goal
        if unit.goal == goal or self.elapsed < unit.route_at or state.segment:
            return
        unit.route_at = self.elapsed + 1.1
        unit.goal = goal
        if not goal:
            return
        outbound = self._pick_outgoing(state.lane)
        if outbound is not state.outgoing:
            state.outgoing = outbound
            state.sections, state.turn_speed = _path_sections(state.lane, outbound)

    def _lane_goal(self, state, position, speed):
        progress = _path_progress(state, position)
        last = state.sections[-1]
        finish = last.start + last.direction * last.length
        if progress > last.progress + last.length - 2.1 and (position - finish).dot(last.direction) > -2.4:
            self._change_lane(state)
            progress = _path_progress(state, position)
        lookahead = _clamp(3.0 + speed * .5, 4.0, 13.2)
        return _path_point(state.sections, progress + lookahead)

    def _clear_path(self, car, destination, ignored=None):
        start = car.position + Vec3(0, 0, .42)
        aim = Vec3(destination.x, destination.y, start.z)
        hits = self.physics.ray_test_all(start, aim, CHASE_MASK).get_hits()
        return not any(hit.get_node() not in (car.body, ignored) for hit in hits)

    def _roadway(self, point):
        x = abs(point.x - round(point.x / CHUNK_SIZE) * CHUNK_SIZE)
        y = abs(point.y - round(point.y / CHUNK_SIZE) * CHUNK_SIZE)
        return min(x, y) < ROAD_HALF_WIDTH - 1.0

    def _disembark(self, car, unit, focus, foot_count):
        if unit.deployed or foot_count >= self.total_cap - len(self.vehicles):
            return 0
        for side in (-1, 1):
            exit_point = car.exit_position(side)
            start = Vec3(exit_point.x, exit_point.y, exit_point.z + 1.0)
            end = start - Vec3(0, 0, 3.0)
            hit = self.physics.ray_test_closest(start, end, CHASE_MASK)
            if hit.has_hit() and hit.get_node() != car.body and hit.get_hit_normal().z > .64:
                feet = hit.get_hit_pos() + Vec3(0, 0, .045)
                if (feet - focus).length_squared() < 3.0 ** 2:
                    continue
                unit.deployed = True
                self._departed_count += 1
                self.events.publish("police_deploy_foot", position=feet, heading=car.heading, vehicle=car)
                return 1
        return 0

    def _blockade(self, car, unit, focus, position, speed, aim, target):
        to_stop = unit.block_point - position
        gap = to_stop.length()
        if unit.parked_at is not None:
            return aim, 0.0
        if gap < 30 and self._clear_path(car, unit.block_point):
            # A shallow diagonal final approach positions the cruiser across the lane.
            right = Vec2(unit.block_axis.y, -unit.block_axis.x)
            orientation = to_stop.normalized() if gap > .01 else right
            bias = right * (.27 if orientation.dot(right) >= 0 else -.27)
            aim = unit.block_point + bias * min(6.0, gap)
            target = min(target, math.sqrt(2.0 * 4.1 * max(0.0, gap - 1.35)))
            unit.mode = "roadblock_approach"
            if gap < 3.5 and speed < 1.8:
                unit.mode = "roadblock"
                unit.parked_at = self.elapsed
                self.events.publish("police_roadblock", vehicle=car, position=car.position)
                target = 0.0
        return aim, target

    def _combat_drive(self, car, unit, position, forward, focus, player_vehicle, target_forward, stars, target):
        if player_vehicle is None:
            return None, target, False
        relative = focus - position
        gap = relative.length()
        if gap > 34 or not self._roadway(position) or not self._roadway(focus):
            return None, target, False
        if not self._clear_path(car, focus, player_vehicle.body):
            return None, target, False
        chase_speed = abs(player_vehicle.speed_kph) / 3.6
        right = Vec2(target_forward.y, -target_forward.x)
        ahead = (position - focus).dot(target_forward)
        side = 1.0 if (position - focus).dot(right) >= 0 else -1.0
        if unit.role == "flanker":
            aim = focus + target_forward * 6.2 + right * (side * 2.0)
            if ahead > 3.0:
                unit.mode = "box"
                gap_to_slot = (aim - position).length()
                approach = .73 * max(0.0, gap_to_slot - 2.5)
                return aim, _clamp(chase_speed * .91 + approach, 0, target), False
            unit.mode = "flank"
            return aim, min(25, chase_speed + 7.5), False
        if stars >= 2 and gap < 25.0 and relative.dot(forward) > 2.0:
            unit.mode = "ram"
            aim = focus - target_forward * .7 + right * (side * .50)
            return aim, _clamp(chase_speed + 8.0, 8.0, 26.0), True
        unit.mode = "pursuit"
        return focus + target_forward * 3.0, min(24.0, chase_speed + 6.0), False

    def _contact(self, car, unit, player_vehicle, manifolds):
        if self.elapsed < unit.next_contact:
            return
        if (player_vehicle.position - car.position).length_squared() >= RULES["contact_distance"] ** 2:
            return
        impact = 0.0
        for contact in manifolds:
            bodies = (contact.get_node0(), contact.get_node1())
            if car.body in bodies and player_vehicle.body in bodies:
                impact = max(impact, sum(point.get_applied_impulse() for point in contact.get_manifold_points()))
        if impact < car.spec["mass"] * .7:
            return
        unit.next_contact = self.elapsed + 2.8
        self._ram_count += 1
        self.events.publish("police_ram", vehicle=car, target=player_vehicle, position=car.position)
        right = player_vehicle.node.get_quat(player_vehicle.render).get_right()
        side = (car.position - player_vehicle.position).dot(right)
        if abs(side) > .85 and abs(player_vehicle.speed_kph) > 12:
            strength = player_vehicle.spec["mass"] * .56
            player_vehicle.body.apply_torque_impulse(Vec3(0, 0, math.copysign(strength, side)))
            self.events.publish("police_pit", vehicle=car, target=player_vehicle, position=car.position)

    def _think_cruiser(self, car, state, unit, focus, player_vehicle, target_forward, wanted, cars, pedestrians):
        position = _xy(car.position)
        forward = _xy(car.node.get_quat(car.render).get_forward())
        forward.normalize()
        speed = max(0.0, car.speed_kph / 3.6)
        goal_position = Vec2(unit.block_point if unit.role == "blocker" else focus)
        if wanted.mode == "cooldown" or wanted.stars == 0:
            goal_position = position - _direction(position, focus) * 125.0
        elif wanted.mode == "pursuit" and player_vehicle is not None and unit.role != "blocker":
            lead = 28 if unit.role == "flanker" else 13
            goal_position += target_forward * lead
        goal = self.graph.nearest_intersection(goal_position.x, goal_position.y)
        self._refresh_route(state, unit, goal)
        aim = self._lane_goal(state, position, speed)
        unit.mode = "search" if wanted.mode == "search" else "pursuit" if wanted.mode == "pursuit" else "retreat"
        if unit.parked_at is not None:
            unit.mode = "roadblock" if unit.role == "blocker" else "parked"
        target = state.lane.speed_limit * (1.34 if wanted.mode == "pursuit" else .85)
        if math.isfinite(state.turn_speed):
            lane_direction = _direction(state.lane.start, state.lane.end)
            entry = (_xy(state.lane.end) - position).dot(lane_direction) - 9.0
            target = min(target, math.sqrt(state.turn_speed ** 2 + 2.0 * 4.1 * max(0.0, entry)))
        ramming = False
        if unit.parked_at is not None:
            target = 0.0
        elif unit.role == "blocker" and wanted.mode == "pursuit":
            aim, target = self._blockade(car, unit, focus, position, speed, aim, target)
        elif wanted.mode == "pursuit":
            direct, target, ramming = self._combat_drive(
                car, unit, position, forward, focus, player_vehicle, target_forward, wanted.stars, target)
            if direct is not None:
                aim = direct
            elif player_vehicle is None:
                gap = (focus - position).length()
                if gap < RULES["deploy_distance"]:
                    target = min(target, .92 * (gap - 11.0))
                    unit.mode = "dismount"
        body_to_ignore = player_vehicle if ramming else None
        dynamic = tuple(other for other in cars if other is not body_to_ignore)
        restricted, cause = self._speed_for_obstacle(car, position, forward, speed, target, dynamic, pedestrians)
        if not (ramming and cause == "obstacle"):
            target = restricted
        look = aim - position
        desired = math.degrees(math.atan2(-look.x, look.y))
        heading_error = (desired - car.heading + 180) % 360 - 180
        state.steer = _clamp(-heading_error / (15.0 + speed * .48), -1, 1) if unit.parked_at is None else 0.0
        state.target_speed = max(0.0, target)
        error = state.target_speed - speed
        state.throttle = _clamp(.43 * error + .055, 0, 1) if state.target_speed > .18 else 0.0
        state.brake = _clamp(-.24 * error, 0, 1)
        if state.target_speed <= .18:
            state.brake = max(state.brake, .77)

    def update(self, dt, elapsed, wanted, focus, *, player_vehicle=None, obstacles=(), pedestrians=(),
               foot_count=0, night=0.0):
        if self._closed:
            return
        self.elapsed = elapsed
        focal = Vec3(focus)
        position = _xy(focal)
        pursuing = wanted.stars > 0 and wanted.mode == "pursuit"
        searching = wanted.stars > 0 and wanted.mode == "search"
        self._player_vehicle = player_vehicle if pursuing else None
        star = min(3, max(0, wanted.stars))
        if pursuing and wanted.last_seen is not None:
            chase = _xy(wanted.last_seen)
        else:
            chase = _xy(wanted.last_seen) if searching and wanted.last_seen is not None else position
        target_forward = _xy(player_vehicle.node.get_quat(player_vehicle.render).get_forward()) if player_vehicle else Vec2(0, 1)
        if target_forward.length_squared() < .5:
            target_forward = Vec2(0, 1)
        target_forward.normalize()
        limits = RULES["dispatch"].get(str(star))
        if pursuing and (star > self._last_stars or self._last_mode != "pursuit"):
            self._dispatch_at = min(self._dispatch_at, elapsed + limits["delay"])
            self._retreat_at = math.inf
        if not pursuing and not searching and self._last_mode not in {"clear", "cooldown"}:
            self._retreat_at = elapsed + RULES["retreat_seconds"]
            self._dispatch_at = math.inf
        if star < 3:
            self._block_point = self._block_axis = self._block_node = None
        if pursuing and star >= 3 and player_vehicle is not None and self._block_point is None:
            self._find_blockade(chase, target_forward)
        self._last_stars, self._last_mode = star, wanted.mode
        active_obstacles = tuple(car for car in obstacles if car.physics_active and not self.is_police(car))
        foot_positions = tuple(Vec3(person.position if hasattr(person, "position") else person) for person in pedestrians
                               if getattr(person, "state", None) != "dead")
        for car in tuple(self.vehicles):
            point = car.position
            unit = self.units[car]
            if car.health <= 0 and unit.disabled_at is None:
                unit.disabled_at = elapsed
                unit.mode = "disabled"
            expired_wreck = (unit.disabled_at is not None
                             and elapsed - unit.disabled_at >= RULES["wreck_retire_seconds"]
                             and (point - focal).length_squared() > 18 ** 2)
            if (point.z < -3 or not self.city.is_loaded(point.x, point.y)
                    or (point - focal).length_squared() > RULES["abandon_distance"] ** 2
                    or elapsed >= self._retreat_at or expired_wreck):
                self._remove(car)
        excess = len(self.vehicles) + foot_count - self.total_cap
        if excess > 0:
            candidates = sorted(self.vehicles, key=lambda car: (
                self.units[car].deployed, (car.position - focal).length_squared()), reverse=True)
            for car in candidates[:excess]:
                self._remove(car)
        room = min(self.cap, self.total_cap - foot_count, limits["cruisers"] if limits else 0)
        if pursuing and len(self.vehicles) < room and elapsed >= self._dispatch_at:
            launched = self._spawn(chase, target_forward, star, (*active_obstacles, *self.vehicles))
            self._dispatch_at = elapsed + (limits["interval"] if launched is not None else 1.0)
        all_cars = tuple(self.vehicles) + active_obstacles
        for car in self.vehicles:
            unit = self.units[car]
            state = self.drivers[car]
            distance = (car.position - focal).length()
            if elapsed >= state.next_think and car.health > 0 and not unit.deployed:
                state.next_think = elapsed + (.076 if distance < 65 else .154)
                self._think_cruiser(car, state, unit, chase, player_vehicle if pursuing else None,
                                    target_forward, wanted, all_cars, foot_positions)
            if pursuing and not unit.deployed and abs(car.speed_kph) < 9.0 and (
                    car.health <= 0 and distance < 33 or unit.mode == "dismount" or
                    unit.parked_at is not None and distance < 34):
                foot_count += self._disembark(car, unit, focal, foot_count)
            active = car.health > 0 and not unit.deployed and unit.parked_at is None
            throttle, steer, brake = (state.throttle, state.steer, state.brake) if active else (0, 0, .9)
            car.update(dt, throttle, steer, ai_driver=active, service_brake=brake, night=night,
                       ai_engine_volume=max(0.0, .12 * (1.0 - distance / 45.0)))
            self._update_siren(car, unit, distance, (pursuing or searching) and car.health > 0)

    def after_physics(self, dt):
        super().after_physics(dt)
        if self._player_vehicle is None:
            return
        ramming = [(car, unit) for car, unit in self.units.items() if unit.mode == "ram"]
        if ramming:
            manifolds = self.physics.get_manifolds()
            for car, unit in ramming:
                self._contact(car, unit, self._player_vehicle, manifolds)

    def close(self):
        self.clear()
        super().close()

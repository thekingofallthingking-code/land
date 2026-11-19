"""A single cinematic search helicopter with a moving scene spotlight."""
from __future__ import annotations

import math

from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import BitMask32, PerspectiveLens, Point3, Spotlight, TransparencyAttrib, Vec2, Vec3

from game.world.mesh import Mesh

ROAD_MASK = BitMask32.bit(0)
SUN_SHADOW_MASK = BitMask32.bit(1)


def _airframe(parent):
    body = Mesh("Air response helicopter")
    paint = (.185, .236, .27, 1)
    glass = (.065, .162, .205, 1)
    long_rails = (.24, .26, .28, 1)
    # Ring sections share their vertices at the canopy, cabin and tapered tail.
    profiles = (
        (-5.0, .18, .14, .53), (-2.1, .44, -.02, .72), (-1.5, .88, -.47, 1.17),
        (.85, .92, -.55, 1.06), (1.91, .72, -.48, .72), (2.41, .44, -.25, .37),
    )
    rings = [((-width * .78, y, bottom), (width * .78, y, bottom),
              (width, y, bottom + .22), (width * .74, y, top),
              (-width * .74, y, top), (-width, y, bottom + .22))
             for y, width, bottom, top in profiles]
    body.face(rings[0], paint)
    body.face(rings[-1][::-1], paint)
    for ring_index, (near, far) in enumerate(zip(rings, rings[1:])):
        for side in range(len(near)):
            successor = (side + 1) % len(near)
            tint = glass if ring_index == 3 and side in (2, 3, 4) else paint
            body.face((near[side], far[side], far[successor], near[successor]), tint)
    for side in (-1, 1):
        body.box((side * .99, .18, -.92), (.14, 3.58, .12), long_rails, bottom=True)
        for y in (-.72, .90):
            body.box((side * .66, y, -.68), (.55, .14, .12), long_rails, bottom=True)
        body.box((side * .87, -.68, -.02), (.055, 1.14, .15), (.47, .54, .53, 1), bottom=True)
    body.box((0, -4.76, .64), (.18, .76, 1.25), paint, bottom=True)
    body.box((0, -4.61, .17), (1.63, .42, .12), long_rails, bottom=True)
    body.box((0, -.15, 1.19), (.63, 1.32, .19), paint, bottom=True)
    body.box((0, -.17, 1.56), (.19, .19, .54), long_rails, bottom=True)
    body.box((0, .77, -.70), (.38, .36, .25), long_rails, bottom=True)
    body.node().reparent_to(parent)

    main = Mesh("Main rotor")
    main.box((0, 0, 0), (.29, 9.6, .05), (.20, .23, .26, 1), bottom=True)
    main.box((0, 0, .013), (9.6, .29, .05), (.20, .23, .26, 1), bottom=True)
    main_rotor = main.node()
    main_rotor.reparent_to(parent)
    main_rotor.set_pos(0, -.17, 1.81)

    tail = Mesh("Tail rotor")
    tail.box((0, 0, 0), (.04, .15, 1.38), (.34, .37, .36, 1), bottom=True)
    tail.box((0, 0, 0), (.04, 1.38, .15), (.34, .37, .36, 1), bottom=True)
    tail_rotor = tail.node()
    tail_rotor.reparent_to(parent)
    tail_rotor.set_pos(.17, -4.78, .63)
    return main_rotor, tail_rotor


def _illumination_meshes(render, beam_ratio):
    cone = Mesh("Searchlight in the haze")
    sections = 12
    for start, end, alpha in ((.06, .37, .079), (.37, .82, .056), (.82, 1.0, .026)):
        for index in range(sections):
            a, b = (index * math.tau / sections), ((index + 1) * math.tau / sections)
            ring = tuple((math.cos(theta) * scale * beam_ratio, scale,
                          math.sin(theta) * scale * beam_ratio)
                         for theta, scale in ((a, start), (a, end), (b, end), (b, start)))
            cone.face(ring, (.98, .91, .68, alpha))
    beam = cone.node()

    disk = Mesh("Illuminated search area")
    for inner, outer, opacity in ((0, .49, .23), (.49, .66, .18), (.66, .81, .101),
                                  (.81, .93, .060), (.93, 1, .027)):
        for index in range(16):
            a, b = index * math.tau / 16, (index + 1) * math.tau / 16
            points = [(math.cos(a) * inner, math.sin(a) * inner, 0),
                      (math.cos(a) * outer, math.sin(a) * outer, 0),
                      (math.cos(b) * outer, math.sin(b) * outer, 0)]
            if inner:
                points.append((math.cos(b) * inner, math.sin(b) * inner, 0))
            disk.face(points, (.98, .91, .70, opacity), (0, 0, 1))
    ground = disk.node()
    for node in (beam, ground):
        node.reparent_to(render)
        node.set_transparency(TransparencyAttrib.M_alpha)
        node.set_light_off(1)
        node.set_shader_off(1)
        node.set_two_sided(True)
        node.set_depth_write(False)
        node.hide(SUN_SHADOW_MASK)
        node.hide()
    return beam, ground


class Helicopter:
    def __init__(self, render, physics, target, elapsed, config):
        self.render, self.physics = render, physics
        self.config = config
        self.angle = config["beam_angle"]
        self.beam_ratio = math.tan(math.radians(self.angle * .5))
        self.expire_at = math.inf
        self._next_clearance = self._next_light_test = elapsed
        self._desired_altitude = 0.0
        self._beam_enabled = False
        self._origin = Vec3()
        self._axis = Vec3(0, 0, -1)
        self._length = 0.0
        self._last_surface = None
        self._velocity = Vec2()
        self.root = render.attach_new_node("Harbor Air Patrol")
        self.root.hide(SUN_SHADOW_MASK)
        self.main_rotor, self.tail_rotor = _airframe(self.root)
        self.beam, self.ground = _illumination_meshes(render, self.beam_ratio)
        light = Spotlight("Harbor Air Patrol spotlight")
        light.set_priority(4)
        light.set_color((15.0, 12.9, 8.9, 1.0))
        light.set_attenuation((1.0, .019, .0023))
        light.set_exponent(8)
        lens = PerspectiveLens()
        lens.set_fov(self.angle)
        lens.set_near_far(1.0, 145.0)
        light.set_lens(lens)
        self.spotlight = render.attach_new_node(light)
        self._aim = Vec3(target)
        start = Vec3(target) + Vec3(22, -28, config["flight_altitude"])
        floor = self._height_at(start.x, start.y)
        start.z = max(start.z, floor + config["roof_clearance"])
        self.root.set_pos(start)

    @property
    def position(self):
        return self.root.get_pos(self.render)

    @property
    def sight_position(self):
        return Vec3(self._origin)

    def _height_at(self, x, y):
        ground = self.physics.ray_test_closest(Point3(x, y, 155), Point3(x, y, -3), ROAD_MASK)
        return ground.get_hit_pos().z if ground.has_hit() else 0.0

    def _set_beam(self, enabled):
        if self._beam_enabled == enabled:
            return
        self._beam_enabled = enabled
        if enabled:
            self.render.set_light(self.spotlight)
            self.beam.show()
        else:
            self.render.clear_light(self.spotlight)
            self.beam.hide()
            self.ground.hide()

    def illuminates(self, position):
        if not self._beam_enabled:
            return False
        offset = Vec3(position) - self._origin
        depth = offset.dot(self._axis)
        if depth < .75 or depth > self._length + 1.7:
            return False
        radius = depth * self.beam_ratio + .45
        return (offset - self._axis * depth).length_squared() < radius ** 2

    def _fly(self, dt, elapsed, target, departing):
        position = self.position
        phase = elapsed * .42
        if departing:
            away = Vec2(position.x - target.x, position.y - target.y)
            if not away.normalize():
                away = Vec2(0, 1)
            desired = position + Vec3(away.x * 72, away.y * 72, 20)
        else:
            radius = self.config["orbit_radius"]
            desired = Vec3(target.x + math.cos(phase) * radius, target.y + math.sin(phase) * radius,
                           target.z + self.config["flight_altitude"])
        horizontal = Vec2(desired.x - position.x, desired.y - position.y)
        requested = horizontal * 1.8
        cruise_speed = self.config["cruise_speed"]
        if requested.length_squared() > cruise_speed ** 2:
            requested.normalize()
            requested *= cruise_speed
        self._velocity += (requested - self._velocity) * (1.0 - math.exp(-dt * 4.5))
        moving = self._velocity.length_squared() > .25
        direction = self._velocity.normalized() if moving else Vec2(0, 1)
        x, y = position.x + self._velocity.x * dt, position.y + self._velocity.y * dt
        if elapsed >= self._next_clearance:
            self._next_clearance = elapsed + .14
            ceiling = max(self._height_at(position.x + direction.x * lead, position.y + direction.y * lead)
                          for lead in (0, 5, 10, 15, 20, 25, 31))
            self._desired_altitude = max(desired.z, ceiling + self.config["roof_clearance"])
        approach_ceiling = max(self._height_at(x, y), self._height_at(x + direction.x * 3, y + direction.y * 3))
        next_clearance = approach_ceiling + self.config["roof_clearance"] * .54
        if next_clearance > position.z:
            # Climb in place if a sharp change in direction reveals a rising roofline.
            self._desired_altitude = max(self._desired_altitude, approach_ceiling + self.config["roof_clearance"])
            x, y = position.x, position.y
        climb = (self._desired_altitude - position.z) * (1.0 - math.exp(-dt * 4.8))
        altitude = position.z + min(26 * dt, max(-24 * dt, climb))
        if moving:
            heading = math.degrees(math.atan2(-direction.x, direction.y))
            relative = (heading - self.root.get_h() + 180) % 360 - 180
            self.root.set_h(self.root.get_h() + relative * (1.0 - math.exp(-dt * 3.8)))
        self.root.set_p(-4.0 if moving else 0.0)
        self.root.set_r(3 * math.sin(phase))
        self.root.set_pos(x, y, altitude + math.sin(elapsed * 2.8) * .016)
        self.main_rotor.set_h((elapsed * 1450) % 360)
        self.tail_rotor.set_p((elapsed * 1830) % 360)

    def _point_beam(self, dt, elapsed, target, mode, night):
        desired = Vec3(target)
        if mode == "search":
            desired += Vec3(math.sin(elapsed * 1.62) * 13, math.cos(elapsed * 1.13) * 9, 0)
        self._aim += (desired - self._aim) * (1.0 - math.exp(-dt * 5.7))
        self._origin = self.position + Vec3(0, 0, -.78)
        endpoint = self._aim + Vec3(0, 0, -.18)
        axis = endpoint - self._origin
        distance = min(145.0, axis.length())
        self._axis = axis.normalized()
        if elapsed >= self._next_light_test:
            self._next_light_test = elapsed + .065
            ray = self.physics.ray_test_all(self._origin, self._origin + self._axis * (distance + 3), ROAD_MASK)
            surfaces = (hit for hit in ray.get_hits()
                        if isinstance(hit.get_node(), BulletRigidBodyNode) and not hit.get_node().get_mass())
            hit = min(surfaces, key=lambda surface: surface.get_hit_fraction(), default=None)
            self._last_surface = (hit.get_hit_pos(), hit.get_hit_normal()) if hit is not None else None
        self._length = distance
        if self._last_surface is not None:
            ground, normal = self._last_surface
            self._length = min(distance, (ground - self._origin).length()) + .19
            if normal.z > .72:
                self.ground.set_pos(ground + normal * .06)
                self.ground.set_scale(min(9.0, max(1.9, self._length * self.beam_ratio)))
                self.ground.set_alpha_scale(.48 + night * .52)
                self.ground.show()
            else:
                self.ground.hide()
        else:
            self.ground.hide()
        for node in (self.beam, self.spotlight):
            node.set_pos(self._origin)
            node.look_at(Point3(self._origin + self._axis))
        self.beam.set_scale(self._length)
        self.beam.set_alpha_scale(.24 + night * .76)

    def update(self, dt, elapsed, target, mode, night):
        active = mode in ("pursuit", "search")
        self._set_beam(active)
        self._fly(dt, elapsed, target, not active)
        if active:
            self._point_beam(dt, elapsed, target, mode, night)

    def close(self):
        self._set_beam(False)
        for node in (self.root, self.spotlight, self.beam, self.ground):
            node.remove_node()

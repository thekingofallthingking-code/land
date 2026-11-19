"""Mouse orbit, speed-sensitive chase and hood cameras."""

from __future__ import annotations

import math

from panda3d.core import BitMask32, Point3, Vec3


_STATIC_MASK = BitMask32.bit(0)
_UP = Vec3(0, 0, 1)


def _axes(heading):
    radians = math.radians(heading)
    return Vec3(-math.sin(radians), math.cos(radians), 0), Vec3(math.cos(radians), math.sin(radians), 0)


def _blend(dt, rate):
    return 1 - math.exp(-dt * rate)


class ThirdPersonCamera:
    def __init__(self, camera_node, physics, sensitivity=.23):
        self.node = camera_node
        self.physics = physics
        self.sensitivity = sensitivity
        self.heading = 20.0
        self.pitch = 13.0
        self.hood_view = False
        self._hood_yaw = 0.0
        self._hood_pitch = 0.0
        self._orbit_time = 0.0
        self._vehicle = None
        self._pivot = None
        self._boom_fraction = 1.0
        self._aim = 0.0
        self._recoil = 0.0
        self._shake = 0.0
        self._shake_clock = 0.0

    def mouse(self, dx, dy):
        if self.hood_view and self._vehicle is not None:
            self._hood_yaw = min(87, max(-87, self._hood_yaw - dx * self.sensitivity))
            self._hood_pitch = min(30, max(-22, self._hood_pitch - dy * self.sensitivity))
            return
        rate = self.sensitivity * (1 - .35 * self._aim)
        self.heading = (self.heading - dx * rate) % 360
        self.pitch = min(64, max(-15, self.pitch + dy * rate))
        if abs(dx) + abs(dy) > .02:
            self._orbit_time = 2.3

    def toggle_vehicle_view(self):
        if self._vehicle is not None:
            self.hood_view = not self.hood_view
            self._hood_yaw = self._hood_pitch = 0.0
            self._pivot = None
            self._boom_fraction = 1.0

    def recoil(self, degrees):
        self._recoil = min(13.0, self._recoil + degrees)

    def shake(self, magnitude):
        self._shake = min(.28, self._shake + magnitude * .055)

    def _clip(self, origin, desired, right, ignore):
        ray = desired - origin
        distance = ray.length()
        if distance < .05:
            return 1.0
        fraction = 1.0
        # These offsets approximate a small volume around the camera's near plane.
        for offset in (Vec3(), right * .22, right * -.22, _UP * -.15, _UP * .15):
            hit = self.physics.ray_test_closest(Point3(origin), Point3(desired + offset), _STATIC_MASK)
            if not hit.has_hit():
                continue
            if hit.get_node() in ignore:
                all_hits = self.physics.ray_test_all(Point3(origin), Point3(desired + offset), _STATIC_MASK)
                visible_hits = [item.get_hit_fraction() for item in all_hits.get_hits()
                                if item.get_node() not in ignore]
                if not visible_hits:
                    continue
                hit_fraction = min(visible_hits)
            else:
                hit_fraction = hit.get_hit_fraction()
            fraction = min(fraction, max(0, hit_fraction - .27 / distance))
        return fraction

    def _update_hood(self, vehicle):
        chassis = vehicle.node.get_quat()
        look, _ = _axes(self._hood_yaw)
        elevation = math.radians(self._hood_pitch - 2)
        look = look * math.cos(elevation) + _UP * math.sin(elevation)
        position = vehicle.hood_position()
        self.heading = (vehicle.heading + self._hood_yaw) % 360
        self.node.set_pos(position)
        self.node.look_at(Point3(position + chassis.xform(look)), chassis.xform(_UP))

    def update(self, dt, player, vehicle=None, snap=False, *, aiming=False):
        dt = max(0, dt)
        if self._vehicle is not vehicle:
            self._vehicle = vehicle
            self.hood_view = False
            self._orbit_time = 0
            self.pitch = 13
            self._recoil = 0
            if vehicle is not None:
                self.heading = vehicle.heading
            snap = True
        if vehicle is not None and self.hood_view:
            self._update_hood(vehicle)
            return
        self._orbit_time = max(0, self._orbit_time - dt)
        sight = float(aiming and vehicle is None)
        self._aim = sight if snap else self._aim + (sight - self._aim) * _blend(dt, 13)
        self._recoil *= math.exp(-8 * dt)

        ignore = (player.controller,)
        if vehicle is None:
            pivot = player.position + _UP * (player.EYE_HEIGHT - .13 + .10 * self._aim)
            distance = 4.6 - 2.62 * self._aim
            shoulder = .51 + .28 * self._aim
        else:
            ignore += (vehicle.body,)
            pivot = vehicle.camera_focus()
            speed = abs(vehicle.speed_kph)
            distance = 6.7 + min(2.7, speed * .021)
            shoulder = 0.0
            if self._orbit_time <= 0 and speed > 2:
                relative_heading = (vehicle.heading - self.heading + 180) % 360 - 180
                self.heading = (self.heading + relative_heading * _blend(dt, 2.9)) % 360
                self.pitch += (13 - self.pitch) * _blend(dt, .82)
        if self._pivot is None or snap:
            self._pivot = Vec3(pivot)
        else:
            self._pivot += (pivot - self._pivot) * _blend(dt, 16 if vehicle is None else 13)

        ahead, right = _axes(self.heading)
        elevated = math.radians(self.pitch - self._recoil)
        offset = -ahead * math.cos(elevated) + _UP * math.sin(elevated)
        desired = self._pivot + offset * distance + right * shoulder
        safe = self._clip(pivot, desired, right, ignore)
        if snap or safe <= self._boom_fraction:
            self._boom_fraction = safe
        else:
            self._boom_fraction += (safe - self._boom_fraction) * _blend(dt, 7)
        position = pivot + (desired - pivot) * self._boom_fraction
        target = self._pivot + right * (shoulder * .92) - offset * .65
        if self._shake > .001:
            self._shake_clock += dt * 35
            wave = right * math.sin(self._shake_clock) + _UP * math.cos(self._shake_clock * 1.27)
            position += wave * (self._shake * self._boom_fraction)
            self._shake *= math.exp(-5.5 * dt)
        self.node.set_pos(position)
        self.node.look_at(Point3(target), _UP)

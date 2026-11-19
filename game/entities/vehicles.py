"""Raycast-suspension vehicles and their procedural models."""
from __future__ import annotations

import json
import math
from pathlib import Path

from panda3d.bullet import BulletBoxShape, BulletRigidBodyNode, BulletVehicle, ZUp
from panda3d.core import (
    BitMask32,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    PerspectiveLens,
    Point3,
    Spotlight,
    TransformState,
    Vec3,
)

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets_generated"
VEHICLE_TYPES = json.loads((ROOT / "game/data/vehicles.json").read_text(encoding="utf-8"))
BUMPER = (0.09, 0.12, 0.14, 1.0)
WINDOW = (0.075, 0.17, 0.23, 1.0)
TRIM = (0.23, 0.28, 0.30, 1.0)
TIRE = (0.065, 0.075, 0.085, 1.0)
RIM = (0.48, 0.56, 0.61, 1.0)
GEAR_LIMITS = (0.23, 0.38, 0.53, 0.69, 0.85, 1.1)
GEAR_FORCE = (1.0, 0.84, 0.71, 0.60, 0.51, 0.44)


def _tint(color, value):
    return (*(channel * value for channel in color[:3]), color[3])


class _Mesh:
    """A small flat-shaded mesh, batched by render state."""

    def __init__(self, name):
        self.data = GeomVertexData(name, GeomVertexFormat.getV3n3c4(), Geom.UHStatic)
        self.vertex = GeomVertexWriter(self.data, "vertex")
        self.normal = GeomVertexWriter(self.data, "normal")
        self.color = GeomVertexWriter(self.data, "color")
        self.faces = GeomTriangles(Geom.UHStatic)

    def face(self, vertices, color):
        a, b, c = (Vec3(*vertex) for vertex in vertices[:3])
        normal = (b - a).cross(c - a)
        normal.normalize()
        start = self.vertex.getWriteRow()
        for vertex in vertices:
            self.vertex.addData3f(*vertex)
            self.normal.addData3f(normal)
            self.color.addData4f(*color)
        for index in range(1, len(vertices) - 1):
            self.faces.addVertices(start, start + index, start + index + 1)

    def loft(self, sections, color, x=0):
        """Connect trapezoidal cross-sections ordered from the tail to the nose."""
        rings = []
        for y, bottom_width, top_width, bottom, top in sections:
            rings.append((
                (x - bottom_width, y, bottom), (x + bottom_width, y, bottom),
                (x + top_width, y, top), (x - top_width, y, top),
            ))
        self.face(rings[0], _tint(color, 0.86))
        self.face(rings[-1][::-1], _tint(color, 0.92))
        for before, after in zip(rings, rings[1:]):
            for side, tint in enumerate((0.64, 0.90, 1.0, 0.90)):
                next_side = (side + 1) % 4
                self.face((before[side], after[side], after[next_side], before[next_side]), _tint(color, tint))

    def box(self, center, half, color):
        x, y, z = center
        w, length, h = half
        self.loft((
            (y - length, w, w, z - h, z + h),
            (y + length, w, w, z - h, z + h),
        ), color, x)

    def attach(self, parent, name):
        geometry = Geom(self.data)
        geometry.addPrimitive(self.faces)
        node = GeomNode(name)
        node.addGeom(geometry)
        return parent.attachNewNode(node)


def _body_mesh(parent, spec, kind):
    width, length = spec["width"] / 2, spec["length"] / 2
    color = spec["color"]
    belt = 0.51 if kind == "van" else 0.35
    roof = spec["height"] - 0.49
    if kind == "sport":
        belt = 0.29
    cabin_tail, cabin_nose = {
        "compact": (-0.81, 0.38),
        "sport": (-0.55, 0.32),
        "van": (-0.89, 0.42),
        "police": (-0.52, 0.31),
    }[kind]
    rear_slope = 0.12 if kind == "van" else 0.38
    nose_slope = 0.26 if kind == "van" else 0.49
    body = _Mesh("body")
    body.loft((
        (-length, width * 0.77, width * 0.82, 0.03, belt - 0.07),
        (-length + 0.20, width * 0.90, width * 0.98, -0.06, belt - 0.01),
        (-length * 0.62, width * 0.92, width, -0.06, belt),
        (length * 0.56, width * 0.91, width, -0.06, belt),
        (length - 0.18, width * 0.90, width * 0.91, -0.06, belt - 0.035),
        (length, width * 0.72, width * 0.80, 0.035, belt - 0.095),
    ), color)
    for side in (-1, 1):
        body.box((side * width * 0.965, 0.0, -0.025), (0.025, length * 0.53, 0.070), BUMPER)
    for y in (-length, length):
        body.box((0, y, 0.063), (width * 0.71, 0.045, 0.071), BUMPER)
    body.box((0, length + 0.045, 0.067), (width * 0.32, 0.013, 0.037), TRIM)
    body.box((0, -length - 0.045, 0.112), (0.19, 0.013, 0.065), (0.72, 0.77, 0.64, 1))
    tail, nose = cabin_tail * length, cabin_nose * length
    low, high = width * 0.90, width * (0.84 if kind == "van" else 0.69)
    cabin = _Mesh("cab")
    cabin.loft((
        (tail, low, low, belt - 0.01, belt + 0.015),
        (tail + rear_slope, low, high, belt - 0.01, roof),
        (nose, low, high, belt - 0.01, roof),
        (nose + nose_slope, low, low, belt - 0.01, belt + 0.015),
    ), _tint(color, 0.92))
    windows = _Mesh("windows")
    windshield_base = (nose + nose_slope + 0.013, belt + 0.035)
    windshield_top = (nose + 0.013, roof - 0.045)
    windows.face(((low * 0.89, *windshield_base), (-low * 0.89, *windshield_base),
                  (-high * 0.91, *windshield_top), (high * 0.91, *windshield_top)), WINDOW)
    rear_base = (tail - 0.013, belt + 0.034)
    rear_top = (tail + rear_slope - 0.013, roof - 0.045)
    windows.face(((-low * 0.86, *rear_base), (low * 0.86, *rear_base),
                  (high * 0.91, *rear_top), (-high * 0.91, *rear_top)), WINDOW)
    for side in (-1, 1):
        for y0, y1, top0, top1 in (
            (tail + 0.11, 0.0, tail + rear_slope + 0.095, -0.04),
            (0.07, nose + nose_slope - 0.13, 0.02, nose - 0.065),
        ):
            vertices = ((side * (low + 0.007), y0, belt + 0.035),
                        (side * (low + 0.007), y1, belt + 0.035),
                        (side * (high + 0.017), top1, roof - 0.062),
                        (side * (high + 0.017), top0, roof - 0.062))
            windows.face(vertices[::side], _tint(WINDOW, 0.83))
        body.box((side * (width + 0.045), nose + 0.10, belt + 0.065),
                 (0.10, 0.095, 0.046), BUMPER)
        for y in (-0.32, 0.35):
            body.box((side * (width - 0.015), y, belt - 0.074), (0.022, 0.12, 0.024), TRIM)
        if kind == "police":
            body.box((side * (width - 0.01), 0.0, belt - 0.12),
                     (0.017, length * 0.55, 0.064), (0.74, 0.80, 0.80, 1))
    if kind == "police":
        body.box((0, -0.09, roof + 0.095), (width * 0.57, 0.115, 0.055), BUMPER)
        body.box((-width * 0.28, -0.09, roof + 0.125), (width * 0.22, 0.117, 0.048),
                 (0.18, 0.42, 0.96, 1))
        body.box((width * 0.28, -0.09, roof + 0.125), (width * 0.22, 0.117, 0.048),
                 (0.88, 0.19, 0.16, 1))
    body_path = body.attach(parent, "paint")
    cabin.attach(body_path, "cabin")
    windows.attach(parent, "glass")
    lamps = _Mesh("front-lamps")
    tails = _Mesh("tail-lamps")
    for side in (-1, 1):
        lamps.box((side * width * 0.61, length - 0.004, belt - 0.115),
                  (width * 0.19, 0.044, 0.052), (0.85, 0.89, 0.76, 1))
        tails.box((side * width * 0.64, -length - 0.003, belt - 0.107),
                  (width * 0.18, 0.037, 0.052), (0.80, 0.12, 0.06, 1))
    return body_path, lamps.attach(parent, "headlamps"), tails.attach(parent, "taillamps")


def _wheel_mesh(parent, radius, width):
    mesh = _Mesh("tread-and-alloy")
    rings = [
        (-width * 0.53, radius * 0.66), (-width * 0.58, radius * 0.86),
        (-width * 0.42, radius), (width * 0.42, radius),
        (width * 0.58, radius * 0.86), (width * 0.53, radius * 0.66),
    ]
    steps = 12
    for index in range(steps):
        theta = math.tau * index / steps
        phi = math.tau * (index + 1) / steps
        for band, ((a, ra), (b, rb)) in enumerate(zip(rings, rings[1:])):
            color = _tint(TIRE, 0.82 + 0.18 * ((index + band) % 2)) if band == 2 else TIRE
            mesh.face(((a, ra * math.cos(theta), ra * math.sin(theta)),
                       (a, ra * math.cos(phi), ra * math.sin(phi)),
                       (b, rb * math.cos(phi), rb * math.sin(phi)),
                       (b, rb * math.cos(theta), rb * math.sin(theta))), color)
        for side in (-1, 1):
            x, r = side * width * 0.54, radius * 0.66
            vertices = (
                (x, 0, 0), (x, r * math.cos(theta), r * math.sin(theta)),
                (x, r * math.cos(phi), r * math.sin(phi)),
            )
            mesh.face(vertices[::side], RIM if index % 2 else TRIM)
    mesh.attach(parent, "wheel-visual")


class Vehicle:
    """A Bullet chassis with four independently suspended wheels."""

    def __init__(self, render, physics, kind, position, heading=0, *, audio_loader=None, events=None):
        self.render = render
        self.physics = physics
        self.kind = kind
        self.spec = spec = VEHICLE_TYPES[kind]
        self.name = spec["name"]
        self.events = events
        self.health = 100.0
        self.rpm = 850.0
        self.gear = 1
        self.occupied = False
        self.skid = 0.0
        self._steering = 0.0
        self._collision_cooldown = 0.0
        self._headlights = False
        self._night = 0.0
        self._braking = False
        self._handbrake = False
        self._handbrake_engagement = 0.0
        self._accelerator = 0.0
        self._closed = False
        self._physics_active = True

        self.body = BulletRigidBodyNode(self.name)
        self.body.setMass(spec["mass"])
        self.body.setDeactivationEnabled(False)
        self.body.setLinearDamping(0.035)
        self.body.setAngularDamping(0.30)
        self.body.setFriction(0.65)
        self.body.setRestitution(0.06)
        self.body.setCcdMotionThreshold(0.6)
        self.body.setCcdSweptSphereRadius(0.25)
        self.body.setIntoCollideMask(BitMask32.allOn())
        lower = BulletBoxShape(Vec3(spec["width"] * 0.46, spec["length"] * 0.48, 0.18))
        self.body.addShape(lower, TransformState.makePos(Vec3(0, 0, 0.10)))
        roof_height = (spec["height"] - 0.78) / 2
        roof = BulletBoxShape(Vec3(spec["width"] * 0.38, spec["length"] * 0.25, roof_height))
        self.body.addShape(roof, TransformState.makePos(Vec3(0, -0.18, 0.27 + roof_height)))
        self.node = render.attachNewNode(self.body)
        self.node.setPos(position)
        self.node.setH(heading)
        physics.attachRigidBody(self.body)

        self._paint, self._headlamps, self._taillamps = _body_mesh(self.node, spec, kind)
        self._paint.flattenStrong()
        self._headlights_nodes = [self._create_headlight(side) for side in (-1, 1)]
        self.chassis = BulletVehicle(physics, self.body)
        self.chassis.setCoordinateSystem(ZUp)
        physics.attachVehicle(self.chassis)
        self._wheel_nodes = []
        for is_front in (True, False):
            for side in (-1, 1):
                self._create_wheel(is_front, side)
        self._driven = {"front": (0, 1), "rear": (2, 3), "all": (0, 1, 2, 3)}[spec["drive"]]
        self._audio_loader = audio_loader
        self._engine, self._tire, self._crash = (self._load_sound(name) for name in ("engine", "tire", "crash"))

    @property
    def position(self):
        return self.node.getPos(self.render)

    @property
    def heading(self):
        return self.node.getH(self.render)

    @property
    def speed_kph(self):
        forward = self.node.getQuat(self.render).getForward()
        return 3.6 * forward.dot(self.body.getLinearVelocity())

    def camera_focus(self):
        return self.render.getRelativePoint(self.node, Point3(0, 0, self.spec["height"] * 0.56))

    def hood_position(self):
        return self.render.getRelativePoint(
            self.node, Point3(0, self.spec["length"] * 0.19, self.spec["height"] - 0.22)
        )

    def exit_position(self, side=-1):
        return self.render.getRelativePoint(self.node, Point3(side * (self.spec["width"] * 0.5 + 0.72), 0.1, -0.14))

    @property
    def physics_active(self):
        return self._physics_active

    def set_physics_active(self, active):
        """Pause a car while its supporting world chunk is streamed out."""
        if self._closed or active == self._physics_active:
            return
        self._physics_active = active
        if active:
            self.physics.attachRigidBody(self.body)
            self.physics.attachVehicle(self.chassis)
            self.body.setActive(True, True)
            self.node.show()
            for wheel in self._wheel_nodes:
                wheel.show()
            return
        self.physics.removeVehicle(self.chassis)
        self.occupied = False
        self._braking = False
        self._update_lights()
        for sound in (self._engine, self._tire, self._crash):
            if sound is not None:
                sound.stop()
        self.node.hide()
        for wheel in self._wheel_nodes:
            wheel.hide()

    def _create_wheel(self, is_front, side):
        spec = self.spec
        x = side * spec["width"] * 0.46
        y = spec["wheelbase"] * (0.5 if is_front else -0.5)
        wheel_node = self.render.attachNewNode(f"{self.kind}-wheel")
        wheel_node.setPos(self.render.getRelativePoint(self.node, Point3(x, y, -0.32)))
        _wheel_mesh(wheel_node, spec["wheel_radius"], spec["wheel_width"])
        wheel = self.chassis.createWheel()
        wheel.setNode(wheel_node.node())
        wheel.setChassisConnectionPointCs(Point3(x, y, 0.02))
        wheel.setFrontWheel(is_front)
        wheel.setWheelDirectionCs(Vec3(0, 0, -1))
        wheel.setWheelAxleCs(Vec3(1, 0, 0))
        wheel.setWheelRadius(spec["wheel_radius"])
        wheel.setMaxSuspensionTravelCm(29.0)
        wheel.setMaxSuspensionForce(spec["mass"] * 9.81 * 0.78)
        wheel.setSuspensionStiffness(37.0 if self.kind == "sport" else 32.0)
        wheel.setWheelsDampingRelaxation(2.75)
        wheel.setWheelsDampingCompression(4.35)
        wheel.setFrictionSlip(spec["grip"])
        wheel.setRollInfluence(0.13 if self.kind == "van" else 0.095)
        self._wheel_nodes.append(wheel_node)

    def _create_headlight(self, side):
        lens = PerspectiveLens()
        lens.setFov(47, 21)
        lens.setNearFar(0.2, 50)
        light = Spotlight(f"{self.name}-headlamp")
        light.setLens(lens)
        light.setColor((5.0, 4.55, 3.7, 1))
        light.setAttenuation((1.0, 0.058, 0.018))
        light.setExponent(10)
        path = self.node.attachNewNode(light)
        path.setPos(side * self.spec["width"] * 0.31, self.spec["length"] * 0.5, 0.24)
        path.lookAt(Point3(side * self.spec["width"] * 0.39, 18, -0.83))
        return path

    def _load_sound(self, name):
        path = ASSETS / f"{name}.wav"
        if self._audio_loader is None or not path.is_file():
            return None
        sound = self._audio_loader.loadSfx(str(path))
        if sound is not None:
            attach = getattr(self._audio_loader, "attachSoundToObject", None)
            if attach is not None:
                attach(sound, self.node)
            sound.setLoop(name != "crash")
        return sound

    def _update_lights(self):
        lights_active = self._night > 0.42 and self.occupied and self.health > 0
        if lights_active != self._headlights:
            for path in self._headlights_nodes:
                if lights_active:
                    self.render.setLight(path)
                else:
                    self.render.clearLight(path)
            self._headlamps.setLightOff(1) if lights_active else self._headlamps.clearLight()
            self._headlights = lights_active
        if self._braking or lights_active:
            self._taillamps.setLightOff(1)
            intensity = 1.5 if self._braking else 0.8
            self._taillamps.setColorScale(intensity, intensity, intensity, 1)
        else:
            self._taillamps.clearLight()
            self._taillamps.clearColorScale()

    def update(self, dt, throttle=0, steer=0, handbrake=False, *, occupied=False, night=0.0):
        """Apply the current inputs before stepping the Bullet world."""
        if not self._physics_active:
            return
        self.occupied = occupied
        self._night = night
        usable = occupied and self.health > 0
        throttle = max(-1.0, min(1.0, throttle)) if usable else 0.0
        steer = max(-1.0, min(1.0, steer)) if usable else 0.0
        self._handbrake = bool(handbrake and usable)
        engagement_rate = 8.0 if self._handbrake else 18.0
        self._handbrake_engagement += (
            float(self._handbrake) - self._handbrake_engagement
        ) * min(1.0, dt * engagement_rate)
        speed = self.speed_kph
        speed_fraction = abs(speed) / self.spec["top_speed"]
        steering_limit = 35.0 / (1.0 + (abs(speed) / 39.0) ** 1.36)
        self._steering += (-steer * steering_limit - self._steering) * min(1.0, dt * 7.5)
        for index in (0, 1):
            self.chassis.setSteeringValue(self._steering, index)

        self._braking = throttle * speed < -2.0 or self._handbrake
        engine = 0.0
        brake = 0.0
        prior_gear = self.gear
        if throttle < 0 and not self._braking and speed <= 2.0:
            self.gear = -1
        elif self.gear < 1 and speed > -2.0 and throttle >= 0:
            self.gear = 1
        if self.gear >= 1:
            if self.gear < len(GEAR_LIMITS) and speed_fraction > GEAR_LIMITS[self.gear - 1] * 0.91:
                self.gear += 1
            elif self.gear > 1 and speed_fraction < GEAR_LIMITS[self.gear - 2] * 0.77:
                self.gear -= 1
        gear_limit = GEAR_LIMITS[max(0, self.gear - 1)]
        if self.gear == -1:
            rpm_target = 850.0 + min(1.0, abs(speed) / 29.0) * 3800.0
        else:
            rpm_target = 850.0 + min(1.0, speed_fraction / gear_limit) * 6000.0
        rpm_target += 650 * abs(throttle)
        self.rpm += (min(7300.0, rpm_target) - self.rpm) * min(1.0, dt * 6.0)
        self._accelerator = abs(throttle)
        if not usable:
            brake = 28.0 if abs(speed) > 4 else 136.0
        elif self._braking and not self._handbrake:
            brake = 144.0 * abs(throttle)
        elif throttle:
            peak = self.spec["power"] * (0.70 + self.health * 0.003)
            if throttle < 0:
                engine = throttle * peak * 0.56 * max(0, 1.0 - abs(speed) / 34.0)
            elif prior_gear == self.gear:
                top_end = max(0.0, min(1.0, (1.015 - speed_fraction) * 9.0))
                engine = throttle * peak * GEAR_FORCE[self.gear - 1] * top_end
        else:
            brake = 0.75 if abs(speed) > 3 else 13.0
        for index in range(4):
            engagement = self._handbrake_engagement if index >= 2 else 0.0
            wheel = self.chassis.getWheel(index)
            wheel.setFrictionSlip(self.spec["grip"] * (1.0 - 0.56 * engagement))
            self.chassis.setBrake(max(brake, 72.0 * engagement), index)
            self.chassis.applyEngineForce(engine / len(self._driven) if index in self._driven else 0.0, index)
        self._update_lights()

    def apply_damage(self, amount, source="collision"):
        """Reduce chassis health and publish the common damage event."""
        damage = max(0.0, min(self.health, amount))
        self.health -= damage
        self._paint.setColorScale(0.62 + self.health * 0.0038)
        if damage and self.events is not None:
            self.events.publish("damage", target=self, amount=damage, source=source)

    def _check_collision(self, dt):
        self._collision_cooldown = max(0.0, self._collision_cooldown - dt)
        if self._collision_cooldown:
            return
        impact = 0.0
        for manifold in self.physics.getManifolds():
            if self.body in (manifold.getNode0(), manifold.getNode1()):
                applied = sum(point.getAppliedImpulse() for point in manifold.getManifoldPoints())
                impact = max(impact, applied / self.spec["mass"])
        if impact < 2.9:
            return
        self._collision_cooldown = 0.42
        self.apply_damage(min(75.0, (impact - 2.3) * 3.65))
        if self._crash is not None:
            self._crash.setVolume(min(0.95, 0.22 + impact * 0.047))
            self._crash.play()

    def _loop(self, sound, volume, pitch):
        if sound is None:
            return
        sound.setVolume(volume)
        sound.setPlayRate(pitch)
        if volume > 0.025 and sound.status() != sound.PLAYING:
            sound.play()
        elif volume <= 0.025 and sound.status() == sound.PLAYING:
            sound.stop()

    def after_physics(self, dt):
        """Read solved suspension and contact information after a Bullet step."""
        if not self._physics_active:
            return
        local_velocity = self.node.getQuat(self.render).conjugate().xform(self.body.getLinearVelocity())
        speed = abs(self.speed_kph)
        wheels = self.chassis.getWheels()
        in_contact = any(wheel.getRaycastInfo().isInContact() for wheel in wheels)
        slip_angle = abs(local_velocity.x) / max(4.0, abs(local_velocity.y))
        skid_target = min(1.0, max(0.0, slip_angle - 0.10) * 1.6)
        if self._handbrake and speed > 12.0:
            skid_target = max(skid_target, min(0.72, (speed - 12.0) / 52.0))
        self.skid += ((skid_target if in_contact else 0.0) - self.skid) * min(1.0, dt * 9.0)
        self._check_collision(dt)
        engine_volume = (0.28 + 0.27 * self._accelerator) if self.occupied and self.health > 0 else 0.0
        self._loop(self._engine, engine_volume, min(3.5, max(0.58, self.rpm / 1650.0)))
        self._loop(self._tire, self.skid * 0.48, 0.73 + min(0.72, speed * 0.009))

    def close(self):
        if self._closed:
            return
        self.set_physics_active(False)
        self._closed = True
        detach = getattr(self._audio_loader, "detachSound", None)
        for sound in (self._engine, self._tire, self._crash):
            if sound is not None:
                if detach is not None:
                    detach(sound)
        for wheel_node in self._wheel_nodes:
            wheel_node.removeNode()
        self.node.removeNode()

"""A Bullet character and its original low-poly, articulated pedestrian model."""

from __future__ import annotations

import math

from panda3d.bullet import BulletCapsuleShape, BulletCharacterControllerNode, ZUp
from panda3d.core import (
    BitMask32,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    Vec3,
)


class _Part:
    """Batch the colored faces for one animated joint into one draw call."""

    def __init__(self, parent, name):
        self.parent = parent
        self.name = name
        self.data = GeomVertexData(name, GeomVertexFormat.get_v3n3c4(), Geom.UH_static)
        self.vertices = GeomVertexWriter(self.data, "vertex")
        self.normals = GeomVertexWriter(self.data, "normal")
        self.colors = GeomVertexWriter(self.data, "color")
        self.triangles = GeomTriangles(Geom.UH_static)

    def _face(self, points, color):
        points = tuple(Vec3(*point) for point in points)
        normal = (points[1] - points[0]).cross(points[2] - points[0]).normalized()
        start = self.vertices.get_write_row()
        for point in points:
            self.vertices.add_data3(point)
            self.normals.add_data3(normal)
            self.colors.add_data4(*color)
        for index in range(1, len(points) - 1):
            self.triangles.add_vertices(start, start + index, start + index + 1)

    def rings(self, x, y, profiles, color, sides=10):
        rings = [
            [
                (x + width * math.cos(i * math.tau / sides),
                 y + offset + depth * math.sin(i * math.tau / sides), z)
                for i in range(sides)
            ]
            for z, width, depth, offset in profiles
        ]
        self._face(tuple(reversed(rings[0])), color)
        for low, high in zip(rings, rings[1:]):
            for i in range(sides):
                j = (i + 1) % sides
                self._face((low[i], low[j], high[j], high[i]), color)
        self._face(rings[-1], color)

    def box(self, center, size, color):
        x, y, z = center
        w, d, h = (scale * 0.5 for scale in size)
        points = (
            (x - w, y - d, z - h), (x + w, y - d, z - h),
            (x + w, y + d, z - h), (x - w, y + d, z - h),
            (x - w, y - d, z + h), (x + w, y - d, z + h),
            (x + w, y + d, z + h), (x - w, y + d, z + h),
        )
        for face in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                     (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            self._face(tuple(points[i] for i in face), color)

    def finish(self):
        geometry = Geom(self.data)
        geometry.add_primitive(self.triangles)
        node = GeomNode(self.name)
        node.add_geom(geometry)
        return self.parent.attach_new_node(node)


_JACKET = (0.93, 0.29, 0.10, 1)
_JACKET_TOP = (0.79, 0.19, 0.065, 1)
_SLEEVE = (0.075, 0.15, 0.18, 1)
_PANTS = (0.105, 0.133, 0.16, 1)
_POCKET = (0.153, 0.19, 0.22, 1)
_SKIN = (0.55, 0.33, 0.24, 1)
_HAIR = (0.079, 0.061, 0.054, 1)
_SOLE = (0.41, 0.46, 0.44, 1)
_REFLECTOR = (0.96, 0.67, 0.21, 1)


class _Rig:
    def __init__(self, root):
        self.root = root
        self.torso = root.attach_new_node("jacket pivot")
        self.torso.set_z(0.91)
        self._make_torso()
        self.head = self.torso.attach_new_node("head pivot")
        self.head.set_pos(0, 0.006, 0.60)
        self._make_head()
        self.arms = [self._make_arm(side) for side in (-1, 1)]
        self.legs = [self._make_leg(side) for side in (-1, 1)]
        self.phase = 0
        self.elapsed = 0
        self.motion = 0

    def _make_torso(self):
        body = _Part(self.torso, "windbreaker")
        body.rings(0, 0, ((-0.06, .179, .113, 0), (.02, .182, .122, 0),
                          (.12, .178, .122, 0)), _SLEEVE)
        body.rings(0, 0, ((.045, .176, .114, 0), (.11, .188, .128, 0),
                          (.29, .2, .135, 0), (.44, .218, .129, 0),
                          (.495, .206, .113, 0), (.542, .119, .091, 0)), _JACKET)
        body.rings(0, -.004, ((.497, .199, .107, 0), (.548, .115, .092, 0),
                              (.586, .083, .073, 0)), _JACKET_TOP)
        body.rings(0, -.085, ((.385, .092, .065, 0), (.471, .131, .083, 0),
                               (.554, .101, .056, 0)), _JACKET_TOP)
        body.rings(0, .003, ((.554, .062, .057, 0), (.648, .065, .059, 0)), _SKIN)
        body.box((0, .127, .299), (.012, .024, .358), _SLEEVE)
        body.box((0, .143, .397), (.018, .011, .036), _REFLECTOR)
        body.box((.101, .115, .173), (.082, .021, .02), _JACKET_TOP)
        body.box((-.101, .115, .173), (.082, .021, .02), _JACKET_TOP)
        body.box((.106, .118, .397), (.071, .014, .014), _REFLECTOR)
        body.box((-.107, -.129, .372), (.096, .015, .018), _REFLECTOR)
        body.finish()

    def _make_head(self):
        head = _Part(self.head, "head")
        head.rings(0, 0, ((.011, .059, .064, .007), (.052, .083, .078, .012),
                          (.112, .093, .087, .014), (.171, .091, .084, .006),
                          (.215, .074, .069, -.004)), _SKIN, 12)
        head.rings(0, 0, ((.159, .096, .087, -.004), (.204, .09, .083, 0),
                          (.234, .068, .064, -.004), (.24, .04, .041, -.004)), _HAIR, 12)
        head.rings(0, -.029, ((.073, .082, .049, 0), (.132, .096, .062, 0),
                              (.172, .094, .058, 0)), _HAIR)
        for side in (-1, 1):
            head.rings(side * .091, 0, ((.069, .017, .019, 0), (.098, .023, .022, 0),
                                      (.128, .016, .02, 0)), _SKIN, 8)
            head.box((side * .040, .092, .121), (.028, .009, .012), _HAIR)
            head.box((side * .041, .093, .140), (.036, .009, .007), _HAIR)
        head.box((0, .101, .104), (.022, .029, .036), _SKIN)
        head.box((0, .081, .063), (.045, .011, .007), (0.37, 0.19, 0.16, 1))
        head.finish()

    def _make_arm(self, side):
        shoulder = self.torso.attach_new_node(f"shoulder {side}")
        shoulder.set_pos(side * .222, 0, .447)
        sleeve = _Part(shoulder, "upper sleeve")
        sleeve.rings(0, 0, ((-.286, .064, .061, 0), (-.193, .077, .071, 0),
                            (-.047, .084, .082, 0), (.045, .065, .073, 0)), _SLEEVE)
        sleeve.rings(0, 0, ((-.091, .083, .078, 0), (-.043, .087, .085, 0),
                            (.045, .066, .075, 0)), _JACKET_TOP)
        sleeve.finish()
        elbow = shoulder.attach_new_node("elbow")
        elbow.set_z(-.272)
        forearm = _Part(elbow, "forearm and hand")
        forearm.rings(0, 0, ((-.204, .047, .046, 0), (-.16, .058, .054, 0),
                             (-.07, .065, .061, 0), (.017, .06, .058, 0)), _SLEEVE)
        forearm.rings(0, 0, ((-.272, .031, .039, .008), (-.243, .044, .043, .009),
                             (-.189, .042, .042, 0)), _SKIN, 8)
        forearm.finish()
        return shoulder, elbow

    def _make_leg(self, side):
        hip = self.root.attach_new_node(f"hip {side}")
        hip.set_pos(side * .095, 0, .91)
        thigh = _Part(hip, "trouser upper")
        thigh.rings(0, 0, ((-.422, .068, .075, 0), (-.294, .077, .084, 0),
                           (-.103, .099, .109, 0), (.043, .107, .111, 0)), _PANTS)
        thigh.box((side * .093, -.02, -.189), (.035, .087, .119), _POCKET)
        thigh.finish()
        knee = hip.attach_new_node("knee")
        knee.set_z(-.413)
        shin = _Part(knee, "trouser lower")
        shin.rings(0, 0, ((-.404, .052, .056, 0), (-.255, .063, .064, 0),
                          (-.109, .072, .068, 0), (.017, .071, .075, 0)), _PANTS)
        shin.finish()
        boot = knee.attach_new_node("ankle")
        boot.set_z(-.389)
        shoe = _Part(boot, "boot")
        shoe.rings(0, 0, ((-.103, .068, .123, .057), (-.076, .071, .124, .056)), _SOLE, 8)
        shoe.rings(0, 0, ((-.079, .072, .122, .055), (-.041, .072, .119, .051),
                          (.001, .065, .107, .048), (.042, .053, .066, .014)), _SLEEVE, 8)
        shoe.box((0, .101, .002), (.074, .037, .013), _POCKET)
        shoe.finish()
        return hip, knee, boot

    def update(self, dt, speed, grounded):
        self.elapsed += dt
        blend = 1 - math.exp(-12 * dt)
        target_motion = min(speed / 3.1, 1.0) if grounded else 0
        self.motion += (target_motion - self.motion) * blend
        self.phase += dt * min(12.5, 4.0 + speed * 1.08) if speed > .09 else 0
        swing = 24 + min(18, speed * 2.1)
        run = min(1, max(0, (speed - 3.7) / 3.8))
        if not grounded:
            for i, ((shoulder, elbow), (hip, knee, boot)) in enumerate(zip(self.arms, self.legs)):
                shoulder.set_p(19 + 7 * i)
                shoulder.set_r((-1 if i == 0 else 1) * 16)
                elbow.set_p(51)
                hip.set_p(22 - 30 * i)
                knee.set_p(-27 - 12 * i)
                boot.set_p(-7)
            self.torso.set_pos(0, 0, .91)
            self.torso.set_hpr(0, -6, 0)
            self.head.set_p(6)
            return
        for i, ((shoulder, elbow), (hip, knee, boot)) in enumerate(zip(self.arms, self.legs)):
            phase = self.phase + i * math.pi
            stride = math.sin(phase)
            lift = max(0, math.cos(phase))
            hips = stride * swing * self.motion
            knees = -(4 + lift * (24 + 28 * run)) * self.motion
            hip.set_p(hips)
            knee.set_p(knees)
            boot.set_p(-(hips + knees) * .6)
            shoulder.set_p(-stride * (19 + run * 13) * self.motion)
            shoulder.set_r((-1 if i == 0 else 1) * (9 + run * 3))
            elbow.set_p(9 + (10 + run * 34) * self.motion + max(0, -stride) * 12 * self.motion)
        breath = math.sin(self.elapsed * 2.6) * .005
        lateral = math.cos(self.phase) * self.motion
        bob = (1 - abs(math.cos(self.phase))) * (.021 + .018 * run) * self.motion
        self.torso.set_pos(lateral * .018, 0, .91 + breath + bob)
        self.torso.set_hpr(-lateral * 5, -run * 12, lateral * 3)
        self.head.set_p(run * 7)


class Player:
    """Input is applied before stepping Bullet. Animate after the physics step."""

    EYE_HEIGHT = 1.55
    CAPSULE_HEIGHT = 1.78
    _FOOT_OFFSET = CAPSULE_HEIGHT * .5 - .04  # Bullet's grounding margin.
    WALK_SPEED = 3.55
    SPRINT_SPEED = 7.1

    def __init__(self, render, physics, spawn):
        self.physics = physics
        self._render = render
        radius = .325
        self._capsule = BulletCapsuleShape(radius, self.CAPSULE_HEIGHT - 2 * radius, ZUp)
        self.controller, self.node = self._create_controller()
        self._rig_root = self.node.attach_new_node("player art")
        self._rig_root.set_z(-self._FOOT_OFFSET)
        self._rig = _Rig(self._rig_root)
        self.health = 100.0
        self.money = 0
        self.active = False
        self._velocity = Vec3()
        self._jump_held = False
        self._jump_buffer = 0
        self._place(spawn)
        self.set_active(True)

    def _create_controller(self):
        controller = BulletCharacterControllerNode(self._capsule, .30, "player controller")
        controller.set_gravity(16.5)
        controller.set_fall_speed(32)
        controller.set_jump_speed(5.6)
        controller.set_max_jump_height(1)
        node = self._render.attach_new_node(controller)
        node.set_collide_mask(BitMask32.bit(0) | BitMask32.bit(1))
        return controller, node

    @property
    def position(self):
        """World position at the feet of the controller."""
        return self.node.get_pos() - Vec3(0, 0, self._FOOT_OFFSET)

    @property
    def heading(self):
        return self._rig_root.get_h()

    @property
    def grounded(self):
        return self.active and self.controller.is_on_ground()

    def set_active(self, active):
        if self.active == active:
            return
        self.active = active
        if active:
            self.physics.attach_character(self.controller)
            self._rig_root.show()
        else:
            self._velocity = Vec3()
            self._jump_buffer = 0
            self._jump_held = False
            self.controller.set_linear_movement(Vec3(), False)
            self.physics.remove_character(self.controller)
            self._rig_root.hide()
        self._last_feet = self.position

    def _place(self, feet):
        feet = Vec3(feet)
        self.node.set_pos(feet + Vec3(0, 0, self._FOOT_OFFSET))
        self._last_feet = feet

    def teleport(self, feet, heading=None):
        # Bullet keeps vertical velocity when moving an existing controller.
        # Replace its kinematic state so a recent jump cannot carry through a warp.
        if self.active:
            self.physics.remove_character(self.controller)
        old_node = self.node
        self.controller, self.node = self._create_controller()
        self._rig_root.reparent_to(self.node)
        old_node.remove_node()
        self._place(feet)
        if heading is not None:
            self._rig_root.set_h(heading)
        self._velocity = Vec3()
        self._jump_buffer = 0
        self._jump_held = False
        if self.active:
            self.physics.attach_character(self.controller)

    def move(self, forward, strafe, camera_heading, sprint, jump, dt):
        if not self.active or dt <= 0:
            return
        radians = math.radians(camera_heading)
        ahead = Vec3(-math.sin(radians), math.cos(radians), 0)
        right = Vec3(math.cos(radians), math.sin(radians), 0)
        direction = ahead * forward + right * strafe
        strength = min(1.0, direction.length())
        velocity = Vec3()
        if strength > .001:
            direction.normalize()
            velocity = direction * strength * (self.SPRINT_SPEED if sprint else self.WALK_SPEED)
            desired_heading = math.degrees(math.atan2(-direction.x, direction.y))
            yaw_difference = (desired_heading - self.heading + 180) % 360 - 180
            self._rig_root.set_h(self.heading + yaw_difference * (1 - math.exp(-16 * dt)))
        responsiveness = 15 if self.grounded else 4.2
        self._velocity += (velocity - self._velocity) * (1 - math.exp(-responsiveness * dt))
        self.controller.set_linear_movement(self._velocity, False)

        if jump and not self._jump_held:
            self._jump_buffer = .135
        self._jump_held = jump
        if self._jump_buffer > 0 and self.controller.can_jump():
            self.controller.do_jump()
            self._jump_buffer = 0
        self._jump_buffer = max(0, self._jump_buffer - dt)

    def animate(self, dt):
        if not self.active or dt <= 0:
            return
        feet = self.position
        travel = feet - self._last_feet
        self._last_feet = feet
        planar_speed = min(self.SPRINT_SPEED, math.hypot(travel.x, travel.y) / dt)
        self._rig.update(dt, planar_speed, self.grounded)

    def close(self):
        self.set_active(False)
        self.node.remove_node()

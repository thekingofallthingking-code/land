"""Raycast-suspension vehicles and their procedural models."""
from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path

from panda3d.bullet import BulletBoxShape, BulletRigidBodyNode, BulletVehicle, ZUp
from panda3d.core import Filename
from panda3d.core import (
    BitMask32,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    Material,
    NodePath,
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
GLASS_EDGE = (0.025, 0.071, 0.10, 1.0)
GLASS_TOP = (0.095, 0.19, 0.25, 1.0)
CHROME = (0.58, 0.64, 0.66, 1.0)
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

    def face(self, vertices, color, *, corner_colors=None):
        a, b, c = (Vec3(*vertex) for vertex in vertices[:3])
        normal = (b - a).cross(c - a)
        normal.normalize()
        start = self.vertex.getWriteRow()
        for index, vertex in enumerate(vertices):
            self.vertex.addData3f(*vertex)
            self.normal.addData3f(normal)
            self.color.addData4f(*(corner_colors[index] if corner_colors else color))
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


def _finish(path, roughness, metallic=0.0):
    finish = Material(path.get_name())
    finish.set_base_color((1, 1, 1, 1))
    finish.set_roughness(roughness)
    finish.set_metallic(metallic)
    path.set_material(finish)


def _station(profile, y):
    for previous, following in zip(profile, profile[1:]):
        if y <= following[0]:
            blend = (y - previous[0]) / (following[0] - previous[0])
            return tuple(a + (b - a) * blend for a, b in zip(previous[1:], following[1:]))
    return profile[-1][1:]


def _rolling_shell(mesh, profile, spec, color):
    """A chamfered body with open fenders around the four wheel positions."""
    outer = spec["wheel_radius"] + .071
    axle = spec["wheelbase"] * .5
    arch_center = -.303
    stations = {section[0] for section in profile}
    for axle_y in (-axle, axle):
        stations.update(axle_y + outer * fraction for fraction in (-1, -.78, -.54, -.28, 0, .28, .54, .78, 1))
    rings = []
    samples = []
    for y in sorted(stations):
        lower, upper, floor, crown = _station(profile, y)
        nearest = abs(abs(y) - axle)
        if nearest < outer:
            raised = math.sqrt(outer * outer - nearest * nearest) + arch_center
            floor = max(floor, min(crown - .13, raised))
            upper += .026 * (1.0 - nearest / outer)
        lip = min(floor + .038, crown - .09)
        shoulder = crown - .045
        rings.append((
            (-lower * .91, y, floor), (lower * .91, y, floor),
            (lower, y, lip), (upper, y, shoulder),
            (upper * .94, y, crown), (-upper * .94, y, crown),
            (-upper, y, shoulder), (-lower, y, lip),
        ))
        samples.append((y, lower, upper, lip, shoulder, crown))
    mesh.face(rings[0], _tint(color, .84))
    mesh.face(rings[-1][::-1], _tint(color, .89))
    for behind, ahead in zip(rings, rings[1:]):
        for side, tint in enumerate((.47, .67, .88, 1.07, 1.01, 1.07, .88, .67)):
            following = (side + 1) % 8
            mesh.face((behind[side], ahead[side], ahead[following], behind[following]), _tint(color, tint))
    return samples


def _side_detail(mesh, samples, side, points, color, stand_off=.012):
    vertices = []
    for y, z in points:
        low, high, lip, shoulder, _ = _station(samples, y)
        blend = min(1.0, max(0.0, (z - lip) / (shoulder - lip)))
        x = side * (low + (high - low) * blend + stand_off)
        vertices.append((x, y, z))
    mesh.face(vertices[::side], color)


def _driver_outline(parent, low, high, belt, roof, nose, windshield_base, windshield_top):
    mesh = _Mesh("driver outline")
    tint = _tint(WINDOW, 0.58)
    height = roof - belt
    head = tuple((math.cos(i * math.tau / 10) * .112, .70 + math.sin(i * math.tau / 10) * .145)
                 for i in range(10))
    shoulders = ((-.20, .14), (.20, .14), (.16, .39), (.095, .55), (-.11, .55), (-.16, .39))

    def side(u, fraction):
        return (-((1 - fraction) * low + fraction * high) - .023,
                nose - .225 + u, belt + fraction * height)

    def front(u, fraction):
        return (-low * .51 + u,
                windshield_base[0] + (windshield_top[0] - windshield_base[0]) * fraction + .014,
                windshield_base[1] + (windshield_top[1] - windshield_base[1]) * fraction)

    for transform in (side, front):
        for feature in (head, shoulders):
            mesh.face(tuple(transform(*point) for point in reversed(feature)), tint)
    driver = mesh.attach(parent, "driver outline")
    driver.hide()
    return driver


def _plate(mesh, tail, z, kind):
    plate = (0.74, 0.79, 0.68, 1)
    ink = (0.13, 0.20, 0.22, 1)
    pattern = {
        "compact": ("110", "010", "011", "010", "111"),
        "sport": ("111", "001", "011", "100", "111"),
        "van": ("111", "101", "111", "001", "111"),
        "police": ("101", "101", "111", "001", "001"),
        "swat": ("111", "100", "111", "101", "111"),
    }[kind]
    mesh.box((0, tail - .060, z), (.204, .020, .065), BUMPER)
    mesh.box((0, tail - .080, z), (.177, .008, .050), plate)
    for digit, offset in ((("100", "100", "100", "101", "111"), -.112),
                          (("111", "001", "011", "001", "111"), -.018), (pattern, .077)):
        for row, pixels in enumerate(digit):
            for column, pixel in enumerate(pixels):
                if pixel == "1":
                    x = offset + column * .0155
                    low = z + .033 - row * .014
                    y = tail - .090
                    mesh.face(((x, y, low), (x + .013, y, low), (x + .013, y, low + .011),
                               (x, y, low + .011)), ink)


def _fascia(mesh, length, width, belt, kind):
    for end in (-1, 1):
        y = length * end
        mesh.loft(((y - .087, width * .68, width * .74, -.012, .11),
                   (y + .087, width * .68, width * .74, -.012, .11)), BUMPER)
    grille_width = width * (.39 if kind in ("van", "swat") else .31)
    grille_height = .091 if kind in ("van", "swat") else .057
    grille_z = belt * .45
    mesh.box((0, length + .030, grille_z), (grille_width, .021, grille_height), TRIM)
    mesh.box((0, length + .054, grille_z), (grille_width * .89, .004, grille_height * .71), BUMPER)
    for height in (-.48, 0.0, .48):
        mesh.box((0, length + .061, grille_z + height * grille_height),
                 (grille_width * .83, .005, .006), CHROME)
    mesh.box((0, length + .067, grille_z + .003), (.034, .007, .028), CHROME)
    for side in (-1, 1):
        mesh.box((side * width * .49, -length - .083, .015), (.073, .016, .026), CHROME)
        mesh.box((side * width * .49, -length - .103, .015), (.049, .009, .016), BUMPER)
    _plate(mesh, -length, .13, kind)


def _door_details(mesh, samples, side, length, belt, kind):
    top, base = belt - .062, max(.021, belt - .301)
    splits = (length * -.55, -.05, length * .43) if kind != "sport" else (-.79, .98)
    groove = (0.058, 0.087, 0.10, 1)
    for y in splits:
        _side_detail(mesh, samples, side, ((y, base), (y + .012, base),
                                           (y + .012, top), (y, top)), groove)
    rear, front = splits[0], splits[-1]
    _side_detail(mesh, samples, side, ((rear, base), (front, base), (front, base + .012), (rear, base + .012)),
                 groove)
    handles = (.39,) if kind == "sport" else (-.30, .38)
    for y in handles:
        _side_detail(mesh, samples, side, ((y - .08, top - .03), (y + .09, top - .03),
                                           (y + .08, top), (y - .07, top)), TRIM, .021)
    _side_detail(mesh, samples, side, ((rear + .03, base - .04), (front - .02, base - .04),
                                       (front - .04, base - .017), (rear + .05, base - .017)), BUMPER)
    if kind == "police":
        center = belt * .54
        _side_detail(mesh, samples, side, ((rear, center - .05), (front, center - .05),
                                           (front - .10, center + .116), (rear + .16, center + .116)),
                     (.60, .68, .71, 1), .019)
        badge = ((.13, center + .077), (.21, center + .077), (.24, center + .038),
                 (.17, center - .015), (.10, center + .038))
        _side_detail(mesh, samples, side, badge[::-1], (.79, .58, .25, 1), .025)
    elif kind == "van":
        center = belt * .45
        _side_detail(mesh, samples, side, ((-.99, center - .024), (.87, center - .024),
                                           (.75, center + .034), (-.88, center + .034)),
                     (.80, .76, .56, 1), .015)


def _lamp_face(mesh, x, y, z, half_w, half_h, color, side):
    chamfer = min(half_w, half_h) * .38
    points = ((x - half_w + chamfer, y, z - half_h), (x + half_w - chamfer, y, z - half_h),
              (x + half_w, y, z - half_h + chamfer), (x + half_w, y, z + half_h - chamfer),
              (x + half_w - chamfer, y, z + half_h), (x - half_w + chamfer, y, z + half_h),
              (x - half_w, y, z + half_h - chamfer), (x - half_w, y, z - half_h + chamfer))
    mesh.face(points[::-side], color)


def _upper_trim(mesh, profile, kind, width, length, hood_base, roof, color):
    if kind in ("van", "swat"):
        for side in (-1, 1):
            rail = side * width * .54
            mesh.box((rail, -.36, roof + .012), (.029, length * .39, .033), TRIM)
        return
    if kind != "sport":
        return
    start, end = hood_base + .09, length * .84
    if start >= end:
        return
    for side in (-1, 1):
        center = side * width * .44
        for fraction in (.0, .19, .38):
            y = start + (end - start) * fraction
            lip = y + .055
            z, high = _station(profile, y)[3] + .012, _station(profile, lip)[3] + .012
            mesh.face(((center - .11, y, z), (center + .11, y, z),
                       (center + .084, lip, high), (center - .098, lip, high)), _tint(color, .37))


def _body_mesh(parent, spec, kind):
    width, length = spec["width"] / 2, spec["length"] / 2
    color = spec["color"]
    is_van = kind in ("van", "swat")
    emergency = kind in ("police", "swat")
    belt = 0.51 if is_van else 0.35
    roof = spec["height"] - 0.49
    if kind == "sport":
        belt = 0.29
    cabin_tail, cabin_nose = {
        "compact": (-0.81, 0.38),
        "sport": (-0.55, 0.32),
        "van": (-0.89, 0.42),
        "police": (-0.52, 0.31),
        "swat": (-0.89, 0.42),
    }[kind]
    rear_slope = 0.12 if is_van else .52 if kind == "sport" else .38
    nose_slope = 0.26 if is_van else .67 if kind == "sport" else .49
    body = _Mesh("body")
    profile = (
        (-length, width * 0.77, width * 0.82, 0.03, belt - 0.07),
        (-length + 0.20, width * 0.90, width * 0.98, -0.06, belt - 0.01),
        (-length * 0.62, width * 0.92, width, -0.06, belt),
        (length * 0.56, width * 0.91, width, -0.06, belt),
        (length - 0.18, width * 0.90, width * 0.91, -0.06, belt - 0.035),
        (length, width * 0.72, width * 0.80, 0.035, belt - 0.095),
    )
    samples = _rolling_shell(body, profile, spec, color)
    body.box((0, 0, -.14), (width * .70, length * .84, .073), BUMPER)
    for axle_y in (-spec["wheelbase"] * .5, spec["wheelbase"] * .5):
        body.box((0, axle_y, -.242), (width * .86, .125, .076), TRIM)
    _fascia(body, length, width, belt, kind)
    for side in (-1, 1):
        _door_details(body, samples, side, length, belt, kind)
    tail, nose = cabin_tail * length, cabin_nose * length
    low, high = width * 0.90, width * (0.84 if is_van else 0.69)
    body.loft((
        (tail, low, low, belt - 0.01, belt + 0.015),
        (tail + rear_slope, low, high, belt - 0.01, roof),
        (nose, low, high, belt - 0.01, roof),
        (nose + nose_slope, low, low, belt - 0.01, belt + 0.015),
    ), _tint(color, 0.92))
    _upper_trim(body, profile, kind, width, length, nose + nose_slope, roof, color)
    windows = _Mesh("windows")
    base_z, top_z = belt + .057, roof - .054
    slope_height = roof - belt - .015
    base_slope = (roof - base_z) / slope_height
    top_slope = (roof - top_z) / slope_height
    windshield_base = (nose + nose_slope * base_slope + .012, base_z)
    windshield_top = (nose + nose_slope * top_slope + .012, top_z)
    windows.face(((low * 0.89, *windshield_base), (-low * 0.89, *windshield_base),
                  (-high * 0.91, *windshield_top), (high * 0.91, *windshield_top)), WINDOW,
                 corner_colors=(GLASS_EDGE, GLASS_EDGE, GLASS_TOP, GLASS_TOP))
    rear_base = (tail + rear_slope * (1 - base_slope) - .012, base_z)
    rear_top = (tail + rear_slope * (1 - top_slope) - .012, top_z)
    if kind != "swat":
        windows.face(((-low * 0.86, *rear_base), (low * 0.86, *rear_base),
                      (high * 0.91, *rear_top), (-high * 0.91, *rear_top)), WINDOW,
                     corner_colors=(GLASS_EDGE, GLASS_EDGE, GLASS_TOP, GLASS_TOP))
    for side in (-1, 1):
        for y0, y1, top0, top1 in (
            (tail + 0.11, 0.0, tail + rear_slope + 0.095, -0.04),
            (0.07, nose + nose_slope - 0.13, 0.02, nose - 0.065),
        ):
            if kind == "swat" and y0 < 0:
                armor = (0.20, 0.29, 0.33, 1)
                body.box((side * (low + .018), -.83, belt + .22), (.028, .79, .13), armor)
                body.box((side * (low + .05), -.83, belt + .23), (.007, .38, .022), (.68, .72, .63, 1))
                continue
            low_z, high_z = belt + .042, roof - .061
            low_x = low + (high - low) * ((low_z - belt + .01) / (roof - belt + .01)) + .015
            high_x = low + (high - low) * ((high_z - belt + .01) / (roof - belt + .01)) + .015
            vertices = ((side * low_x, y0, low_z), (side * low_x, y1, low_z),
                        (side * high_x, top1, high_z), (side * high_x, top0, high_z))
            tint = (GLASS_EDGE, GLASS_EDGE, _tint(GLASS_TOP, .82), _tint(GLASS_TOP, .82))
            windows.face(vertices[::side], WINDOW, corner_colors=tint[::side])
        body.box((side * (width + .012), nose + .102, belt + .071), (.102, .063, .049), BUMPER)
        body.box((side * (width + .025), nose + .113, belt + .084), (.102, .045, .025), color)
        body.box((side * (width + .026), nose + .035, belt + .072), (.067, .010, .025), CHROME)
    if emergency:
        body.box((0, -0.09, roof + 0.095), (width * 0.57, 0.115, 0.055), BUMPER)
        body.box((-width * 0.28, -0.09, roof + 0.125), (width * 0.22, 0.117, 0.048),
                 (0.18, 0.42, 0.96, 1))
        body.box((width * 0.28, -0.09, roof + 0.125), (width * 0.22, 0.117, 0.048),
                 (0.88, 0.19, 0.16, 1))
    if kind == "swat":
        body.box((0, length + .11, .04), (width * .72, .092, .079), TRIM)
        body.box((0, -length - .10, .13), (width * .67, .084, .071), BUMPER)
        for side in (-1, 1):
            body.box((side * width * .72, length + .08, .20), (.061, .066, .21), BUMPER)
    body_path = body.attach(parent, "paint and trim")
    _finish(body_path, .37 if kind == "sport" else .46, .13)
    _finish(windows.attach(parent, "glazing"), .26, .07)
    lamps = _Mesh("front-lamps")
    tails = _Mesh("tail-lamps")
    for side in (-1, 1):
        head_x, tail_x = side * width * .602, side * width * .635
        head_z, tail_z = belt - .132, belt - .139
        head_h = .038 if kind == "sport" else .052 if not is_van else .061
        for x, y, z, h, end in ((head_x, length + .007, head_z, head_h, 1),
                                 (tail_x, -length - .007, tail_z, .057, -1)):
            body_face = lamps if end == 1 else tails
            casing = (0.27, .32, .32, 1) if end == 1 else (.27, .048, .032, 1)
            lens = (.76, .84, .77, 1) if end == 1 else (.69, .074, .047, 1)
            _lamp_face(body_face, x, y, z, width * .204, h, casing, end)
            _lamp_face(body_face, x, y + end * .007, z, width * .179, h * .76, lens, end)
            accent = (.99, .95, .79, 1) if end == 1 else (.95, .22, .104, 1)
            _lamp_face(body_face, x, y + end * .014, z + h * .30, width * .157, h * .17, accent, end)
    silhouette = _driver_outline(parent, low, high, belt, roof, nose, windshield_base, windshield_top)
    return body_path, lamps.attach(parent, "headlamps"), tails.attach(parent, "taillamps"), silhouette


@lru_cache(maxsize=16)
def _wheel_model(radius, width, kind):
    mesh = _Mesh("tread-and-alloy")
    rings = [
        (-width * 0.53, radius * 0.66), (-width * 0.58, radius * 0.83),
        (-width * 0.42, radius), (width * 0.42, radius),
        (width * 0.58, radius * 0.83), (width * 0.53, radius * 0.66),
    ]
    steps = 16
    spokes, alloy = {
        "compact": (6, (.50, .57, .59, 1)), "sport": (10, (.61, .66, .66, 1)),
        "van": (5, (.36, .41, .42, 1)), "police": (8, (.27, .34, .37, 1)),
        "swat": (6, (.27, .31, .31, 1)),
    }[kind]
    pocket = (0.09, 0.12, 0.13, 1)

    def rim_vertex(side, offset, size, angle):
        return (side * width * offset, radius * size * math.cos(angle), radius * size * math.sin(angle))

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
            outer = (rim_vertex(side, .534, .66, theta), rim_vertex(side, .534, .66, phi),
                     rim_vertex(side, .570, .563, phi), rim_vertex(side, .570, .563, theta))
            mesh.face(outer[::side], alloy)
            back = ((side * width * .536, 0, 0), rim_vertex(side, .536, .564, theta),
                    rim_vertex(side, .536, .564, phi))
            mesh.face(back[::side], pocket)
            hub = ((side * width * .595, 0, 0), rim_vertex(side, .595, .227, theta),
                   rim_vertex(side, .595, .227, phi))
            mesh.face(hub[::side], _tint(alloy, .77))
    for index in range(spokes):
        turn = math.tau * index / spokes
        for side in (-1, 1):
            spoke = (rim_vertex(side, .574, .196, turn - .22),
                     rim_vertex(side, .574, .568, turn - .088),
                     rim_vertex(side, .574, .568, turn + .072),
                     rim_vertex(side, .574, .196, turn + .20))
            mesh.face(spoke[::side], alloy)
    template = NodePath("shared wheel geometry")
    wheel = mesh.attach(template, f"{kind}-rim")
    _finish(wheel, .69, .05)
    return wheel


def _wheel_mesh(parent, radius, width, kind):
    _wheel_model(radius, width, kind).instance_to(parent)


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
        self.ai_driver = False
        self._ai_engine_volume = 0.0
        self.skid = 0.0
        self._steering = 0.0
        self._collision_cooldown = 0.0
        self._headlights = False
        self._lamp_lenses_on = False
        self._tail_intensity = 0.0
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

        self._paint, self._headlamps, self._taillamps, self._silhouette = _body_mesh(self.node, spec, kind)
        self._emergency_lamps = self._create_emergency_lamps() if kind in ("police", "swat") else ()
        self._emergency_phase = -1
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

    def _set_driver(self, occupied, ai_driver):
        if (self.occupied, self.ai_driver) == (occupied, ai_driver):
            return
        self.occupied = occupied
        self.ai_driver = ai_driver
        if occupied or ai_driver:
            self._silhouette.show()
        else:
            self._silhouette.hide()

    def release_ai_driver(self):
        self._set_driver(self.occupied, False)
        self._ai_engine_volume = 0.0
        self._update_lights()

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
        self._set_driver(False, False)
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
        _wheel_mesh(wheel_node, spec["wheel_radius"], spec["wheel_width"], self.kind)
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
        wheel.setRollInfluence(0.13 if self.kind in ("van", "swat") else 0.095)
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

    def _create_emergency_lamps(self):
        width = self.spec["width"] * .5
        roof = self.spec["height"] - .49
        lamps = []
        for side, tint in ((-1, (.18, .51, 1, 1)), (1, (1, .19, .11, 1))):
            mesh = _Mesh("emergency lamp")
            mesh.box((side * width * .28, -.09, roof + .125),
                     (width * .225, .122, .051), tint)
            lamp = mesh.attach(self.node, "Emergency flash")
            lamp.set_shader_off(1)
            lamp.set_light_off(1)
            lamp.set_color_scale(2.2, 2.2, 2.2, 1)
            lamp.hide()
            lamps.append(lamp)
        return tuple(lamps)

    def set_emergency_lights(self, elapsed, enabled):
        if not self._emergency_lamps:
            return
        phase = int(elapsed * 7.0) % 2 if enabled else -1
        if phase == self._emergency_phase:
            return
        self._emergency_phase = phase
        for index, lamp in enumerate(self._emergency_lamps):
            if index == phase:
                lamp.show()
            else:
                lamp.hide()

    def _load_sound(self, name):
        path = ASSETS / f"{name}.wav"
        if self._audio_loader is None or not path.is_file():
            return None
        sound = self._audio_loader.loadSfx(Filename.from_os_specific(str(path)))
        if sound is not None:
            attach = getattr(self._audio_loader, "attachSoundToObject", None)
            if attach is not None:
                attach(sound, self.node)
            sound.setLoop(name != "crash")
        return sound

    def _update_lights(self):
        lights_active = self._night > 0.42 and self.occupied and self.health > 0
        lenses_active = self._night > 0.42 and (self.occupied or self.ai_driver) and self.health > 0
        if lights_active != self._headlights:
            for path in self._headlights_nodes:
                if lights_active:
                    self.render.setLight(path)
                else:
                    self.render.clearLight(path)
            self._headlights = lights_active
        if lenses_active != self._lamp_lenses_on:
            if lenses_active:
                self._headlamps.setShaderOff(1)
                self._headlamps.setLightOff(1)
            else:
                self._headlamps.clearShader()
                self._headlamps.clearLight()
            self._lamp_lenses_on = lenses_active
        intensity = 1.5 if self._braking else 0.8 if lenses_active else 0.0
        if intensity == self._tail_intensity:
            return
        self._tail_intensity = intensity
        if intensity:
            self._taillamps.setShaderOff(1)
            self._taillamps.setLightOff(1)
            self._taillamps.setColorScale(intensity, intensity, intensity, 1)
        else:
            self._taillamps.clearShader()
            self._taillamps.clearLight()
            self._taillamps.clearColorScale()

    def update(self, dt, throttle=0, steer=0, handbrake=False, *, occupied=False,
               ai_driver=False, service_brake=0.0, ai_engine_volume=0.0, night=0.0):
        """Apply the current inputs before stepping the Bullet world."""
        if not self._physics_active:
            return
        self._set_driver(occupied, ai_driver)
        self._ai_engine_volume = ai_engine_volume
        self._night = night
        usable = (occupied or ai_driver) and self.health > 0
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

        brake_pedal = max(0.0, min(1.0, service_brake)) if usable else 0.0
        self._braking = throttle * speed < -2.0 or self._handbrake or brake_pedal > 0.1
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
        elif brake_pedal > 0:
            brake = 156.0 * brake_pedal
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
        if self.ai_driver and self.health > 0:
            engine_volume = self._ai_engine_volume * (0.70 + 0.30 * self._accelerator)
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

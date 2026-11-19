"""The streamed Harbor City world and its Bullet collision geometry."""

from dataclasses import dataclass
from heapq import nsmallest
from math import floor
from random import Random

from panda3d.bullet import BulletBoxShape, BulletConvexHullShape, BulletRigidBodyNode
from panda3d.core import BitMask32, Point3, PointLight, TransformState, Vec3, Vec4

from .design import (
    BENCH_FACING, BENCH_REACH, BENCH_TOP, DISTRICT_BUILDERS, HOSPITAL_NAME,
    HOSPITAL_POSITION, SHOP_NAME, SHOP_POSITION, SIDEWALK, bench, bench_layout,
    street_lamp, street_surfaces, traffic_signal,
)
from .mesh import Mesh
from .minimap import write_minimap
from .roads import (CHUNK_MAX, CHUNK_MIN, CHUNK_SIZE, CITY_MAX, CITY_MIN,
                    DISTRICT_NAMES, ROAD_HALF_WIDTH, RoadGraph, district_at)

STATIC_MASK = BitMask32.bit(0)
CITY_SEED = 4812
SIGNALS = ("red", "yellow", "green")
SIGNAL_AXES = ("east_west", "north_south")


@dataclass(slots=True)
class Chunk:
    root: object
    body: object
    glow: object
    signals: tuple
    lamps: tuple
    seats: tuple


@dataclass(frozen=True, slots=True)
class BenchSeat:
    position: Vec3
    approach: Vec3
    heading: float


class Collision:
    """One compound static body per chunk, with every shape in local space."""

    def __init__(self, body):
        self.body = body

    def box(self, center, size):
        self.body.addShape(BulletBoxShape(Vec3(*(dim * .5 for dim in size))),
                           TransformState.makePos(Vec3(*center)))

    def hull(self, points):
        hull = BulletConvexHullShape()
        for point in points:
            hull.addPoint(Point3(*point))
        self.body.addShape(hull)


def _coast(mesh, collision, ix, iy):
    edge = ROAD_HALF_WIDTH - .4
    inner = -ROAD_HALF_WIDTH
    length = CHUNK_SIZE + (2 * ROAD_HALF_WIDTH if ix == CHUNK_MAX else 0)
    south_north = {CHUNK_MIN: -edge, CHUNK_MAX: CHUNK_SIZE + edge}
    if iy in south_north:
        y = south_north[iy]
        center = (inner + length * .5, y, .53)
        size = (length, .47, 1.05)
        mesh.box(center, size, (.37, .42, .43))
        collision.box(center, size)
        mesh.slab(inner, y - .16, inner + length, y + .16, 1.06, (.66, .64, .54))
    length = CHUNK_SIZE + (2 * ROAD_HALF_WIDTH if iy == CHUNK_MAX else 0)
    if ix in south_north:
        x = south_north[ix]
        center = (x, inner + length * .5, .53)
        size = (.47, length, 1.05)
        mesh.box(center, size, (.37, .42, .43))
        collision.box(center, size)
        mesh.slab(x - .16, inner, x + .16, inner + length, 1.06, (.66, .64, .54))
    if iy == CHUNK_MIN:
        for offset, tint in ((11, (.34, .57, .60)), (18, (.28, .49, .55)),
                             (30, (.25, .45, .52)), (51, (.23, .42, .49))):
            for x in (2, 36, 71, 102):
                mesh.slab(x, -offset, x + 25, -offset + .22, -.38, tint)
    if ix == CHUNK_MAX:
        for offset in (12, 21, 38, 57):
            for y in (6, 37, 71, 107):
                mesh.slab(CHUNK_SIZE + offset, y, CHUNK_SIZE + offset + .17,
                          y + 23, -.38, (.29, .48, .53))


class City:
    """Owns static geometry, collision, navigation, and cartography."""

    def __init__(self, render, physics, seed=CITY_SEED, radius=2):
        self.render = render
        self.physics = physics
        self.root = render.attachNewNode("Harbor City")
        self.seed = seed
        self.radius = max(1, int(radius))
        self.graph = RoadGraph()
        self.loaded_chunks: dict[tuple[int, int], Chunk] = {}
        self.spawn = Vec3(9.8, 22.8, .19)
        self.hospital = Vec3(*HOSPITAL_POSITION)
        self.hospital_name = HOSPITAL_NAME
        self.shop = Vec3(*SHOP_POSITION)
        self.shop_name = SHOP_NAME
        self.car_spawns = (
            ("compact", Vec3(6.35, 24, 1.0), 0),
            ("sport", Vec3(6.35, 66, 1.0), 0),
            ("van", Vec3(-6.35, 51, 1.0), 180),
            ("police", Vec3(55, 6.35, 1.0), 90),
            ("compact", Vec3(94, -6.35, 1.0), -90),
            ("van", Vec3(150.35, 65, 1.0), 0),
            ("sport", Vec3(-48, 6.35, 1.0), 90),
            ("police", Vec3(6.35, -72, 1.0), 0),
        )
        self._night = 0.
        self._signal_time = 0.
        self._lamp_focus = None
        self._last_position = Vec3(self.spawn)
        self._lights_enabled = False
        self._streetlights = []
        for i in range(2):
            light = PointLight(f"Street lamp {i + 1}")
            light.setAttenuation(Vec3(1, .045, .048))
            self._streetlights.append(self.root.attachNewNode(light))
        self._water()

    @staticmethod
    def contains(x, y):
        return CITY_MIN <= x <= CITY_MAX and CITY_MIN <= y <= CITY_MAX

    @staticmethod
    def _chunk_at(x, y):
        return (max(CHUNK_MIN, min(CHUNK_MAX, floor(x / CHUNK_SIZE))),
                max(CHUNK_MIN, min(CHUNK_MAX, floor(y / CHUNK_SIZE))))

    def district(self, x, y):
        return DISTRICT_NAMES[district_at(*self._chunk_at(x, y))]

    @property
    def bench_seats(self) -> tuple[BenchSeat, ...]:
        """Seating positions in active chunks, ordered by chunk and layout."""
        return tuple(seat for key in sorted(self.loaded_chunks)
                     for seat in self.loaded_chunks[key].seats)

    def is_loaded(self, x, y):
        """Test for ground collision in the streamed pavement owner's chunk."""
        key = self._pavement_chunk_at(x, y)
        return self.contains(x, y) and key in self.loaded_chunks

    def _pavement_chunk_at(self, x, y):
        return self._chunk_at(x + ROAD_HALF_WIDTH, y + ROAD_HALF_WIDTH)

    def minimap(self, path):
        return write_minimap(path, seed=self.seed)

    def _water(self):
        sea = Mesh("Bay surface")
        color = (.185, .345, .41)
        shore_min = CITY_MIN - ROAD_HALF_WIDTH
        shore_max = CITY_MAX + ROAD_HALF_WIDTH
        distance = 8192.
        sea.slab(-distance, -distance, distance, shore_min, -.42, color)
        sea.slab(-distance, shore_max, distance, distance, -.42, color)
        sea.slab(-distance, shore_min, shore_min, shore_max, -.42, color)
        sea.slab(shore_max, shore_min, distance, shore_max, -.42, color)
        sea.node().reparentTo(self.root)

    def update(self, position, eager=False):
        """Keep the player chunk present and amortize new work after startup."""
        self._last_position = Vec3(*position)
        cx, cy = self._pavement_chunk_at(position[0], position[1])
        radius = self.radius
        wanted = {
            (x, y)
            for x in range(max(CHUNK_MIN, cx - radius), min(CHUNK_MAX, cx + radius) + 1)
            for y in range(max(CHUNK_MIN, cy - radius), min(CHUNK_MAX, cy + radius) + 1)
        }
        missing = sorted(wanted - self.loaded_chunks.keys(),
                         key=lambda key: ((key[0] - cx) ** 2 + (key[1] - cy) ** 2, key))
        loading = missing if eager else missing[:1]
        for key in loading:
            self.loaded_chunks[key] = self._build_chunk(*key)
        for key in self.loaded_chunks.keys() - wanted:
            self._drop_chunk(key)
        if self._lights_enabled:
            self._update_streetlights(force=bool(loading))

    def _build_chunk(self, ix, iy):
        key = f"{ix},{iy}"
        root = self.root.attachNewNode(f"City chunk {key}")
        world_x, world_y = ix * CHUNK_SIZE, iy * CHUNK_SIZE
        root.setPos(world_x, world_y, 0)
        surface = Mesh(f"Buildings and roads {key}")
        glow = Mesh(f"Lights and windows {key}")
        lamps = []
        body = BulletRigidBodyNode(f"City collider {key}")
        body.setIntoCollideMask(STATIC_MASK)
        body.setFriction(.84)
        collision = Collision(body)
        extra_x = 2 * ROAD_HALF_WIDTH if ix == CHUNK_MAX else 0
        extra_y = 2 * ROAD_HALF_WIDTH if iy == CHUNK_MAX else 0
        collision.box((63.5 + extra_x * .5, 63.5 + extra_y * .5, -.52),
                      (CHUNK_SIZE + extra_x, CHUNK_SIZE + extra_y, 1.04))
        collision.box((72, 72, .07), (127, 127, .22))
        rng = Random(self.seed * 71_719 + ix * 1_010_831 + iy * 2_732_977)
        district = district_at(ix, iy)
        street_surfaces(surface, ix, iy, district, rng)
        DISTRICT_BUILDERS[district](surface, glow, collision, ix, iy, rng)
        seats = []
        for x, y, facing in bench_layout(district, ix, iy):
            bench(surface, collision, x, y, facing)
            dx, dy, heading = BENCH_FACING[facing]
            seat_x, seat_y = world_x + x, world_y + y
            seats.append(BenchSeat(
                Vec3(seat_x, seat_y, BENCH_TOP),
                Vec3(seat_x + dx * BENCH_REACH, seat_y + dy * BENCH_REACH, SIDEWALK + .01),
                heading,
            ))
        for along in (28, 68, 108):
            for x, y, dx, dy in ((9.75, along, -1, 0),
                                 (134.25, along, 1, 0),
                                 (along, 9.75, 0, -1),
                                 (along, 134.25, 0, 1)):
                px, py, pz = street_lamp(surface, glow, x, y, dx, dy)
                lamps.append(Vec3(world_x + px, world_y + py, pz))
                collision.box((x, y, 3.2), (.25, .25, 6.04))
        signal_meshes = tuple({
            color: Mesh(f"{axis} {color} {key}") for color in SIGNALS
        } for axis in SIGNAL_AXES)
        if ix > CHUNK_MIN and iy > CHUNK_MIN:
            for x, y, side in ((-10.2, 10.2, "north"), (10.2, -10.2, "south"),
                               (10.2, 10.2, "east"), (-10.2, -10.2, "west")):
                traffic_signal(surface, signal_meshes, x, y, side)
        _coast(surface, collision, ix, iy)
        surface.node().reparentTo(root)
        glow_node = glow.node()
        glow_node.reparentTo(root)
        glow_node.setLightOff(1)
        glow_node.setShaderOff(1)
        self._apply_night(glow_node)

        signal_nodes = tuple({color: mesh.node() for color, mesh in axis.items()}
                             for axis in signal_meshes)
        for axis in signal_nodes:
            for signal in axis.values():
                signal.reparentTo(root)
                signal.setLightOff(1)
                signal.setShaderOff(1)
        chunk = Chunk(root, body, glow_node, signal_nodes, tuple(lamps), tuple(seats))
        self._apply_signals((ix, iy), chunk)
        collider_node = root.attachNewNode(body)
        collider_node.setPos(0, 0, 0)
        self.physics.attachRigidBody(body)
        return chunk

    def _drop_chunk(self, key):
        chunk = self.loaded_chunks.pop(key)
        self.physics.removeRigidBody(chunk.body)
        chunk.root.removeNode()

    def _apply_night(self, node):
        if self._night <= .06:
            node.hide()
        else:
            node.show()
            strength = min(1.48, .38 + self._night * 1.1)
            node.setColorScale(strength, strength, strength, 1)

    def _update_streetlights(self, force=False):
        position = self._last_position
        if not force and self._lamp_focus is not None and (position - self._lamp_focus).lengthSquared() < 49:
            return
        lamps = (lamp for chunk in self.loaded_chunks.values() for lamp in chunk.lamps)
        nearest = nsmallest(len(self._streetlights), lamps,
                            key=lambda lamp: (lamp - position).lengthSquared())
        if not nearest:
            return
        self._lamp_focus = Vec3(position)
        for light, lamp in zip(self._streetlights, nearest):
            light.setPos(lamp)

    def set_night(self, amount):
        # Daylight headlights and night lighting can be independently managed.
        new_amount = max(0., min(1., float(amount)))
        if abs(new_amount - self._night) < .007:
            return
        self._night = new_amount
        for chunk in self.loaded_chunks.values():
            self._apply_night(chunk.glow)
        active = new_amount > .17
        if active != self._lights_enabled:
            for light in self._streetlights:
                if active:
                    self.render.setLight(light)
                else:
                    self.render.clearLight(light)
            self._lights_enabled = active
            if active:
                self._update_streetlights(force=True)
        if active:
            intensity = min(2.2, (new_amount - .17) * 2.65)
            for light in self._streetlights:
                light.node().setColor(Vec4(intensity, intensity * .67, intensity * .36, 1))

    def _apply_signals(self, key, chunk):
        for axis, signals in zip(SIGNAL_AXES, chunk.signals):
            lit = self.graph.signal(key, self._signal_time, axis)
            for color, node in signals.items():
                if color == lit:
                    node.show()
                else:
                    node.hide()

    def set_signal_time(self, elapsed):
        """Update visible lamps at their one-second phase resolution."""
        stamp = int(elapsed)
        if stamp == self._signal_time:
            return
        self._signal_time = stamp
        for key, chunk in self.loaded_chunks.items():
            self._apply_signals(key, chunk)

    def close(self):
        for key in tuple(self.loaded_chunks):
            self._drop_chunk(key)
        if self._lights_enabled:
            for light in self._streetlights:
                self.render.clearLight(light)
        self.root.removeNode()

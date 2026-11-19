"""Short-lived, pooled arcade combat effects with reusable geometry."""
from dataclasses import dataclass
from math import atan2, hypot, sin
from random import Random

from panda3d.core import BitMask32, CardMaker, NodePath, PNMImage, Point3, Texture, TransparencyAttrib, Vec3

from game.world.mesh import Mesh

DECAL_CAP = 48
DECAL_LIFETIME = 22.0
_DECAL_FADE = 4.0


@dataclass
class _Particle:
    node: NodePath
    duration: float = 0.0
    remaining: float = 0.0
    velocity: Vec3 | None = None


def _flare_geometry(name, colors):
    mesh = Mesh(name)
    ring = ((1, .32, 0), (0, .32, 1), (-1, .32, 0), (0, .32, -1))
    for i in range(len(ring)):
        a, b = ring[i], ring[(i + 1) % len(ring)]
        mesh.face(((0, 0, 0), a, b), colors[0])
        mesh.face(((0, 1, 0), b, a), colors[1])
    return mesh.node()


def _bullet_hole_card():
    size = 48
    rng = Random(71120)
    image = PNMImage(size, size, 4)
    for y in range(size):
        for x in range(size):
            u, v = (x + .5) / size * 2 - 1, (y + .5) / size * 2 - 1
            angle = atan2(v, u)
            radius = hypot(u * 1.10, v) + .058 * sin(7 * angle) + .042 * sin(13 * angle + .7)
            grain = rng.random()
            hole = max(0.0, 1.0 - (radius / .38) ** 2)
            scorch = max(0.0, 1.0 - (radius / .83) ** 2)
            edge = max(0.0, 1.0 - abs(radius - .43) / .22) * grain ** 4
            alpha = min(.92, .85 * hole + scorch * (.17 + .25 * grain) + .29 * edge)
            value = .026 + .15 * edge + .085 * grain * (1 - hole)
            image.set_xel_a(x, y, value, value * .91, value * .79, alpha)
    texture = Texture("procedural chipped paint")
    texture.load(image)
    texture.set_wrap_u(Texture.WM_clamp)
    texture.set_wrap_v(Texture.WM_clamp)
    texture.set_magfilter(Texture.FT_linear)
    texture.set_minfilter(Texture.FT_linear)
    card = CardMaker("bullet-hole quad")
    card.set_frame(-1, 1, -1, 1)
    quad = NodePath(card.generate())
    quad.set_texture(texture)
    return quad


class CombatEffects:
    def __init__(self, parent, seed):
        self._random = Random(seed)
        self.root = parent.attach_new_node("arcade combat effects")
        self.root.set_light_off()
        self.root.set_shader_off()
        self.root.set_two_sided(True)
        self.root.set_depth_write(False)
        self.root.set_transparency(TransparencyAttrib.M_alpha)
        self.root.hide(BitMask32.bit(1))  # Keep the flash geometry out of the sun's shadow pass.
        self._flash = self._make_pool("flash", 6, _flare_geometry("flash", ((1, .94, .62), (1, .51, .12))))
        self._tracer = self._make_pool("tracer", 16, _flare_geometry("tracer", ((1, .56, .19), (1, .96, .65))))
        self._spark = self._make_pool("spark", 32, _flare_geometry("spark", ((1, .68, .27), (1, .98, .77))))
        self._decals = self._make_pool("bullet hole", DECAL_CAP, _bullet_hole_card())
        self._flash_index = self._tracer_index = self._spark_index = self._decal_index = 0

    def _make_pool(self, name, capacity, template):
        pool = []
        for index in range(capacity):
            node = self.root.attach_new_node(f"{name} {index}")
            template.instance_to(node)
            node.hide()
            pool.append(_Particle(node))
        return pool

    @staticmethod
    def _show(particle, start, direction, duration, *, brightness=1.0):
        particle.node.set_pos(start)
        particle.node.look_at(Point3(start + direction))
        particle.node.set_color_scale(brightness, brightness, brightness, 1.0)
        particle.node.show()
        particle.duration = particle.remaining = duration
        particle.velocity = None

    def flash(self, start, direction, *, scale=1.0):
        flash = self._flash[self._flash_index]
        self._flash_index = (self._flash_index + 1) % len(self._flash)
        self._show(flash, start, direction, .068, brightness=2.5)
        flash.node.set_scale(.14 * scale, .50 * scale, .12 * scale)
        flash.node.set_r(self._random.uniform(-70, 70))

    def tracer(self, start, end):
        delta = end - start
        travel = delta.length()
        if travel < .05:
            return
        direction = delta / travel
        tracer = self._tracer[self._tracer_index]
        self._tracer_index = (self._tracer_index + 1) % len(self._tracer)
        self._show(tracer, start, direction, .093, brightness=1.8)
        length = min(3.2, travel)
        tracer.velocity = direction * (min(34.0, travel) - length) / tracer.duration
        tracer.node.set_scale(.014, length, .014)

    def impact(self, position, normal, *, soft=False):
        for _ in range(3 if soft else 5):
            spark = self._spark[self._spark_index]
            self._spark_index = (self._spark_index + 1) % len(self._spark)
            jitter = Vec3(*(self._random.uniform(-1, 1) for _ in range(3)))
            direction = normal * 1.4 + jitter
            direction.normalize()
            self._show(spark, position + normal * .025, direction, self._random.uniform(.10, .23), brightness=1.7)
            width = self._random.uniform(.016, .030)
            spark.node.set_scale(width, self._random.uniform(.067, .15), width)
            if soft:
                spark.node.set_color_scale(0.56, 0.93, 1.35, 1.0)
            spark.velocity = direction * self._random.uniform(2.1, 5.4)

    def bullet_hole(self, position, normal, *, scale=1.0):
        if normal.length_squared() < .4:
            return
        decal = self._decals[self._decal_index]
        self._decal_index = (self._decal_index + 1) % len(self._decals)
        start = position + normal * .011
        self._show(decal, start, normal, DECAL_LIFETIME)
        decal.node.set_depth_offset(1)
        decal.node.set_scale(self._random.uniform(.075, .105) * scale)
        decal.node.set_r(self._random.uniform(-180, 180))

    def update(self, dt):
        for pool in (self._flash, self._tracer, self._spark):
            for particle in pool:
                if particle.remaining <= 0:
                    continue
                particle.remaining -= dt
                if particle.remaining <= 0:
                    particle.node.hide()
                    continue
                color = particle.node.get_color_scale()
                particle.node.set_color_scale(color.x, color.y, color.z, particle.remaining / particle.duration)
                if particle.velocity is not None:
                    particle.node.set_pos(particle.node.get_pos() + particle.velocity * dt)
                if pool is self._spark:
                    particle.velocity.z -= 13.0 * dt
        for decal in self._decals:
            if decal.remaining > 0:
                decal.remaining -= dt
                if decal.remaining <= 0:
                    decal.node.hide()
                elif decal.remaining < _DECAL_FADE:
                    decal.node.set_color_scale(1, 1, 1, decal.remaining / _DECAL_FADE)

    def clear(self):
        for pool in (self._flash, self._tracer, self._spark, self._decals):
            for particle in pool:
                particle.node.hide()
                particle.remaining = 0.0

    def close(self):
        self.root.remove_node()

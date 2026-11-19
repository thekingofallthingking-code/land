"""Short-lived, pooled arcade combat effects with reusable geometry."""
from dataclasses import dataclass
from random import Random

from panda3d.core import BitMask32, NodePath, Point3, TransparencyAttrib, Vec3

from game.world.mesh import Mesh


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
        self._flash = self._make_pool("flash", 6, ((1, .94, .62), (1, .51, .12)))
        self._tracer = self._make_pool("tracer", 16, ((1, .56, .19), (1, .96, .65)))
        self._spark = self._make_pool("spark", 32, ((1, .68, .27), (1, .98, .77)))
        self._flash_index = self._tracer_index = self._spark_index = 0

    def _make_pool(self, name, capacity, colors):
        template = _flare_geometry(name, colors)
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

    def clear(self):
        for pool in (self._flash, self._tracer, self._spark):
            for particle in pool:
                particle.node.hide()
                particle.remaining = 0.0

    def close(self):
        self.root.remove_node()

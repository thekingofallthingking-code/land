"""Deterministic coastal showers and one streamed rain draw call."""
from math import exp, isfinite, sin

import numpy as np
from panda3d.core import (
    BitMask32, BoundingBox, Geom, GeomNode, GeomTriangles, GeomVertexData,
    GeomVertexFormat, Point3, TransparencyAttrib, Vec3,
)

_DROP_COUNT = {"Low": 250, "Medium": 440, "High": 680}
_RAIN_VERTEX = np.dtype([("point", "=f4", 3), ("color", "u1", 4)])
_VERTEX_FORMAT = GeomVertexFormat.get_v3c4()
assert _RAIN_VERTEX.itemsize == _VERTEX_FORMAT.get_array(0).get_stride()


def _smoothstep(value):
    fraction = min(1.0, max(0.0, value))
    return fraction * fraction * (3 - 2 * fraction)


def _shower(hour, start, end, peak, fade_in, fade_out):
    age, duration = (hour - start) % 24, (end - start) % 24
    if age >= duration:
        return 0.0
    return peak * _smoothstep(age / fade_in) * _smoothstep((duration - age) / fade_out)


def rain_at_hour(hour):
    """Light dawn rain, a heavier harbor squall and a short late-night drizzle."""
    return max(_shower(hour, 4.7, 8.2, .43, .74, .96),
               _shower(hour, 17.35, 21.0, .92, .90, 1.1),
               _shower(hour, 23.5, 1.8, .29, .62, .85))


class Weather:
    def __init__(self, render, camera, quality, rendered=True):
        self.render = render
        self.camera = camera
        self.intensity = 0.0
        self.override = None
        self._initialized = False
        self._anchor = None
        self.node = None
        self.drop_cap = _DROP_COUNT[quality]
        if not rendered:
            return
        rng = np.random.default_rng(79603)
        count = self.drop_cap
        self._lower = np.array((-15.0, -15.0, -4.8), dtype=np.float32)
        self._span = np.array((30.0, 30.0, 20.0), dtype=np.float32)
        self._position = rng.uniform(0, 1, (count, 3)).astype(np.float32) * self._span + self._lower
        self._fall = rng.uniform(17, 29, count).astype(np.float32)
        self._length = rng.uniform(.20, .65, count).astype(np.float32)
        self._width = rng.uniform(.010, .027, (count, 1)).astype(np.float32)
        self._opacity = rng.uniform(56, 139, count).astype(np.float32)
        self._population = rng.random(count)
        self._vertices = np.zeros(count * 4, dtype=_RAIN_VERTEX)
        colors = self._vertices["color"].reshape(count, 4, 4)
        colors[:, :2, :3] = (166, 199, 224)
        colors[:, 2:, :3] = (137, 173, 205)
        self._data = GeomVertexData("rain streams", _VERTEX_FORMAT, Geom.UH_stream)
        self._data.set_num_rows(count * 4)
        strips = GeomTriangles(Geom.UH_static)
        for index in range(count):
            base = index * 4
            strips.add_vertices(base, base + 1, base + 2)
            strips.add_vertices(base, base + 2, base + 3)
        strips.close_primitive()
        shape = Geom(self._data)
        shape.add_primitive(strips)
        rain = GeomNode("camera-local harbor rain")
        rain.add_geom(shape)
        rain.set_bounds(BoundingBox(Point3(-16, -16, -6), Point3(16, 16, 17)))
        rain.set_final(True)
        self.node = render.attach_new_node(rain)
        self.node.set_depth_write(False)
        self.node.set_light_off()
        self.node.set_shader_off()
        self.node.set_two_sided(True)
        self.node.set_transparency(TransparencyAttrib.M_alpha)
        self.node.hide(BitMask32.bit(1))
        self.node.hide()

    def update(self, dt, hour, focus):
        if not isfinite(dt) or not isfinite(hour):
            return self.intensity
        dt = max(0.0, dt)
        target = rain_at_hour(hour) if self.override is None else min(1.0, max(0.0, self.override))
        if not self._initialized or dt == 0:
            self.intensity = target
            self._initialized = True
        else:
            self.intensity += (target - self.intensity) * (1 - exp(-2.1 * dt))
        if self.node is None:
            return self.intensity
        if self.intensity < .012:
            self.node.hide()
            self._anchor = None
            return self.intensity

        anchor = self.camera.get_pos(self.render) if self.camera is not None else Vec3(focus)
        motion = min(.12, dt)
        if self._anchor is not None:
            self._position -= np.asarray(tuple(anchor - self._anchor), dtype=np.float32)
        self._anchor = Vec3(anchor)
        wind = 2.2 + self.intensity * 7.7 + 1.2 * sin(hour * .7)
        self._position[:, 0] += wind * motion
        self._position[:, 1] -= wind * .42 * motion
        self._position[:, 2] -= self._fall * motion
        self._position = np.remainder(self._position - self._lower, self._span) + self._lower
        self.node.set_pos(anchor)
        right = self.camera.get_quat(self.render).get_right() if self.camera is not None else Vec3(1, 0, 0)
        self._write_geometry(wind, right)
        self.node.show()
        return self.intensity

    def _write_geometry(self, wind, right):
        vertices = self._vertices["point"]
        width = self._width * np.asarray(tuple(right), dtype=np.float32)
        vertices[0::4] = self._position - width
        vertices[1::4] = self._position + width
        tail = self._position.copy()
        tail[:, 0] -= self._length * (wind / self._fall)
        tail[:, 1] += self._length * (wind * .42 / self._fall)
        tail[:, 2] += self._length
        vertices[2::4] = tail + width * .18
        vertices[3::4] = tail - width * .18
        distance = np.einsum("ij,ij->i", self._position, self._position)
        near = np.clip((distance - .23) / 1.8, 0.0, 1.0)
        density = self._population < (.1 + self.intensity * .85)
        alpha = self._opacity * near * density * (.30 + .70 * self.intensity)
        colors = self._vertices["color"].reshape(self.drop_cap, 4, 4)
        colors[:, :2, 3] = alpha.astype(np.uint8)[:, None]
        colors[:, 2:, 3] = (alpha * .18).astype(np.uint8)[:, None]
        self._data.modify_array(0).modify_handle().set_data(self._vertices.tobytes())

    def close(self):
        if self.node is not None:
            self.node.remove_node()
            self.node = None

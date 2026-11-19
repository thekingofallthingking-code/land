"""Material-free, flat-shaded world geometry batched by chunk."""

from array import array
from functools import lru_cache
from math import cos, sin, tau
from struct import Struct

from panda3d.core import (
    Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
    NodePath, Vec3,
)


VERTEX_FORMAT = GeomVertexFormat.getV3n3c4()
# Panda's V3n3c4 layout stores native float32 positions and normals, then RGBA8.
VERTEX = Struct("=6f4B")
assert VERTEX.size == VERTEX_FORMAT.getArray(0).getStride()


@lru_cache(maxsize=512)
def _rgba_bytes(color):
    rgba = (*color, 1.0) if len(color) == 3 else color
    return tuple(int(max(0.0, min(1.0, channel)) * 255) for channel in rgba)


class Mesh:
    """A single indexed draw for many small architectural details."""

    def __init__(self, name):
        self.name = name
        self.vertices = bytearray()
        self.triangles = []
        self.vertex_count = 0

    def face(self, points, color, normal=None):
        if normal is None:
            axis = (Vec3(*points[1]) - Vec3(*points[0])).cross(
                Vec3(*points[2]) - Vec3(*points[0]))
            axis.normalize()
            normal = tuple(axis)
        start = self.vertex_count
        n = len(points)
        self.vertex_count += n
        nx, ny, nz = normal
        red, green, blue, alpha = _rgba_bytes(color)
        extend = self.vertices.extend
        pack = VERTEX.pack
        for x, y, z in points:
            extend(pack(x, y, z, nx, ny, nz, red, green, blue, alpha))
        self.triangles.extend((start, start + 1, start + 2))
        if n == 4:
            self.triangles.extend((start, start + 2, start + 3))
        elif n > 4:
            for i in range(2, n - 1):
                self.triangles.extend((start, start + i, start + i + 1))

    def slab(self, x0, y0, x1, y1, z, color):
        self.face(((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)),
                  color, (0, 0, 1))

    def box(self, center, size, color, bottom=False):
        x, y, z = center
        dx, dy, dz = (dimension * .5 for dimension in size)
        l0, r0, f0, b0 = x - dx, x + dx, y - dy, y + dy
        floor, roof = z - dz, z + dz
        side = tuple(channel * .83 for channel in color[:3])
        side_y = tuple(channel * .91 for channel in color[:3])
        self.slab(l0, f0, r0, b0, roof, color)
        self.face(((l0, f0, floor), (r0, f0, floor),
                   (r0, f0, roof), (l0, f0, roof)), side_y, (0, -1, 0))
        self.face(((r0, b0, floor), (l0, b0, floor),
                   (l0, b0, roof), (r0, b0, roof)), side_y, (0, 1, 0))
        self.face(((l0, b0, floor), (l0, f0, floor),
                   (l0, f0, roof), (l0, b0, roof)), side, (-1, 0, 0))
        self.face(((r0, f0, floor), (r0, b0, floor),
                   (r0, b0, roof), (r0, f0, roof)), side, (1, 0, 0))
        if bottom:
            self.face(((l0, b0, floor), (r0, b0, floor),
                       (r0, f0, floor), (l0, f0, floor)), side, (0, 0, -1))

    def cone(self, x, y, z, height, lower, upper, color, sides=7):
        low = tuple((x + cos(i * tau / sides) * lower,
                     y + sin(i * tau / sides) * lower, z) for i in range(sides))
        high = tuple((x + cos(i * tau / sides) * upper,
                      y + sin(i * tau / sides) * upper, z + height)
                     for i in range(sides))
        for i in range(sides):
            j = (i + 1) % sides
            self.face((low[i], low[j], high[j], high[i]), color)
        if upper > 0:
            self.face(high, color, (0, 0, 1))

    def node(self):
        if not self.vertices:
            return NodePath(self.name)
        data = GeomVertexData(self.name, VERTEX_FORMAT, Geom.UHStatic)
        data.modifyArray(0).modifyHandle().setData(bytes(self.vertices))
        tris = GeomTriangles(Geom.UHStatic)
        wide_indices = self.vertex_count > 65535
        if wide_indices:
            tris.setIndexType(Geom.NTUint32)
        indices = array("I" if wide_indices else "H", self.triangles)
        tris.modifyVertices().modifyHandle().setData(indices.tobytes())
        tris.closePrimitive()
        geom = Geom(data)
        geom.addPrimitive(tris)
        node = GeomNode(self.name)
        node.addGeom(geom)
        return NodePath(node)

"""Material-free, flat-shaded world geometry batched by chunk."""

from math import cos, sin, tau

from panda3d.core import (
    Geom, GeomNode, GeomTriangles, GeomVertexData, GeomVertexFormat,
    GeomVertexWriter, NodePath, Vec3,
)


class Mesh:
    """A single indexed draw for many small architectural details."""

    def __init__(self, name):
        self.name = name
        self.vertices = []
        self.triangles = []

    def face(self, points, color, normal=None):
        if normal is None:
            axis = (Vec3(*points[1]) - Vec3(*points[0])).cross(
                Vec3(*points[2]) - Vec3(*points[0]))
            axis.normalize()
            normal = tuple(axis)
        start = len(self.vertices)
        rgba = (*color, 1.0) if len(color) == 3 else color
        self.vertices.extend((point, normal, rgba) for point in points)
        self.triangles.extend((start, start + i, start + i + 1)
                              for i in range(1, len(points) - 1))

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
        data = GeomVertexData(self.name, GeomVertexFormat.getV3n3c4(),
                              Geom.UHStatic)
        data.setNumRows(len(self.vertices))
        pos = GeomVertexWriter(data, "vertex")
        norm = GeomVertexWriter(data, "normal")
        colors = GeomVertexWriter(data, "color")
        for position, normal, color in self.vertices:
            pos.addData3(*position)
            norm.addData3(*normal)
            colors.addData4(*color)
        tris = GeomTriangles(Geom.UHStatic)
        if len(self.vertices) > 65535:
            tris.setIndexType(Geom.NTUint32)
        for a, b, c in self.triangles:
            tris.addVertices(a, b, c)
        tris.closePrimitive()
        geom = Geom(data)
        geom.addPrimitive(tris)
        node = GeomNode(self.name)
        node.addGeom(geom)
        return NodePath(node)

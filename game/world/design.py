"""Procedural district architecture and street furniture."""

from math import cos, sin, tau

from .roads import CHUNK_MAX, CHUNK_SIZE, ROAD_HALF_WIDTH


PAVING = {
    "downtown": (.48, .49, .49),
    "residential": (.51, .47, .43),
    "harbor": (.40, .43, .45),
    "beachfront": (.61, .53, .43),
    "park": (.40, .46, .40),
}
OFFICE_PALETTE = (
    (.24, .36, .44), (.48, .43, .38), (.33, .46, .48),
    (.64, .57, .47), (.42, .48, .54), (.43, .32, .32),
)
HOUSE_PALETTE = (
    (.70, .45, .31), (.72, .62, .43), (.38, .56, .51),
    (.57, .65, .65), (.69, .62, .53), (.44, .48, .60),
)
CONTAINER_PALETTE = (
    (.18, .43, .48), (.62, .30, .19), (.74, .56, .25),
    (.30, .35, .51), (.38, .51, .34),
)
GLASS = ((.15, .27, .34), (.21, .36, .42), (.25, .40, .44))
LIT_GLASS = ((.96, .61, .26), (.95, .76, .44), (.61, .82, .83))
POST = (.17, .24, .26)
TRIM = (.20, .29, .32)
YELLOW = (.93, .69, .27)
WHITE = (.84, .84, .74)
GRASS = (.30, .40, .29)
DEEP_GRASS = (.23, .36, .29)
ROAD = (.19, .22, .25)
SIDEWALK = .18
SHOP_POSITION = (15.6, 46, SIDEWALK + .01)
HOSPITAL_POSITION = (13.5, -28, SIDEWALK + .01)
SHOP_NAME = "Tideway Supply"
HOSPITAL_NAME = "Breakwater Clinic"
BENCH_TOP = .75
BENCH_REACH = 1.05
BENCH_FACING = {
    "north": (0, 1, 0.0),
    "south": (0, -1, 180.0),
    "west": (-1, 0, 90.0),
}

PIXEL_FONT = {
    "A": (2, 5, 7, 5, 5), "B": (6, 5, 6, 5, 6), "C": (3, 4, 4, 4, 3),
    "D": (6, 5, 5, 5, 6), "E": (7, 4, 6, 4, 7), "F": (7, 4, 6, 4, 4),
    "G": (3, 4, 5, 5, 3), "H": (5, 5, 7, 5, 5), "I": (7, 2, 2, 2, 7),
    "J": (1, 1, 1, 5, 2), "K": (5, 5, 6, 5, 5), "L": (4, 4, 4, 4, 7),
    "M": (5, 7, 7, 5, 5), "N": (5, 7, 7, 7, 5), "O": (2, 5, 5, 5, 2),
    "P": (6, 5, 6, 4, 4), "Q": (2, 5, 5, 2, 1), "R": (6, 5, 6, 5, 5),
    "S": (3, 4, 2, 1, 6), "T": (7, 2, 2, 2, 2), "U": (5, 5, 5, 5, 7),
    "V": (5, 5, 5, 5, 2), "W": (5, 5, 7, 7, 5), "X": (5, 5, 2, 5, 5),
    "Y": (5, 5, 2, 2, 2), "Z": (7, 1, 2, 4, 7), " ": (0, 0, 0, 0, 0),
    "0": (7, 5, 5, 5, 7), "1": (2, 6, 2, 2, 7), "2": (6, 1, 2, 4, 7),
    "3": (6, 1, 2, 1, 6), "4": (5, 5, 7, 1, 1), "5": (7, 4, 6, 1, 6),
    "6": (3, 4, 6, 5, 2), "7": (7, 1, 2, 4, 4), "8": (2, 5, 2, 5, 2),
    "9": (2, 5, 3, 1, 6),
}


def panel(mesh, face, plane, start, end, floor, roof, color):
    """A vertical flat rectangle where U is X on Y faces and Y on X faces."""
    if face == "south":
        points = ((start, plane, floor), (end, plane, floor),
                  (end, plane, roof), (start, plane, roof))
        normal = (0, -1, 0)
    elif face == "north":
        points = ((end, plane, floor), (start, plane, floor),
                  (start, plane, roof), (end, plane, roof))
        normal = (0, 1, 0)
    elif face == "west":
        points = ((plane, end, floor), (plane, start, floor),
                  (plane, start, roof), (plane, end, roof))
        normal = (-1, 0, 0)
    else:
        points = ((plane, start, floor), (plane, end, floor),
                  (plane, end, roof), (plane, start, roof))
        normal = (1, 0, 0)
    mesh.face(points, color, normal)


def lettering(mesh, face, plane, center, bottom, scale, text, color):
    letters = text[::-1] if face in ("west", "north") else text
    step = scale if face in ("east", "south") else -scale
    # The swath increases in world coordinates on every face. Flip each glyph
    # as well as their order when a viewer's screen runs the other way.
    start = center - (len(text) * 4 - 1) * scale * .5
    for i, symbol in enumerate(letters):
        for row, pattern in enumerate(PIXEL_FONT[symbol]):
            for col in range(3):
                if pattern & (4 >> col):
                    column = col if step > 0 else 2 - col
                    x = start + (i * 4 + column) * scale
                    y = bottom + (4 - row) * scale
                    panel(mesh, face, plane, x, x + scale * .87,
                          y, y + scale * .87, color)


def street_surfaces(mesh, chunk_x, chunk_y, district, rng):
    half = ROAD_HALF_WIDTH
    extent = CHUNK_SIZE - half
    edge_x = extent + (2 * half if chunk_x == CHUNK_MAX else 0)
    edge_y = extent + (2 * half if chunk_y == CHUNK_MAX else 0)
    mesh.slab(-half, -half, edge_x, half, .002, ROAD)
    mesh.slab(-half, half, half, edge_y, .002, ROAD)
    if chunk_x == CHUNK_MAX:
        mesh.slab(extent, half, edge_x, edge_y, .002, ROAD)
    if chunk_y == CHUNK_MAX:
        mesh.slab(half, extent, extent, edge_y, .002, ROAD)
    pavement = PAVING[district]
    mesh.box((72, 72, .03), (127, 127, .30), pavement)
    for offset in (half + .12, extent - .12):
        mesh.slab(offset - .10, half, offset + .10, extent, .187, WHITE)
        mesh.slab(half, offset - .10, extent, offset + .10, .187, WHITE)
    for start in range(15, CHUNK_SIZE - 14, 12):
        mesh.slab(start, -.09, start + 5.2, .09, .012, YELLOW)
        mesh.slab(-.09, start, .09, start + 5.2, .012, YELLOW)
    for offset in (-7.15, 7.15):
        mesh.slab(14, offset - .07, CHUNK_SIZE - 14, offset + .07, .012, WHITE)
        mesh.slab(offset - .07, 14, offset + .07, CHUNK_SIZE - 14, .012, WHITE)
    for offset in (-7.7, -5.8, -3.9, -2.0, -.1, 1.8, 3.7, 5.6, 7.5):
        for center in (11.1, CHUNK_SIZE - 11.1):
            mesh.slab(offset, center - .92, offset + .63, center + .92, .013, WHITE)
            mesh.slab(center - .92, offset, center + .92, offset + .63, .013, WHITE)
    for center, low, high in ((13.25, -7.2, -.13), (CHUNK_SIZE - 13.25, .13, 7.2)):
        mesh.slab(low, center - .14, high, center + .14, .013, WHITE)
        mesh.slab(center - .14, -high, center + .14, -low, .013, WHITE)
    for along in range(21, CHUNK_SIZE - 17, 8):
        shade = tuple(c * rng.uniform(.87, .93) for c in pavement)
        mesh.slab(8.8, along, 12.0, along + .06, .189, shade)
        mesh.slab(along, 8.8, along + .06, 12.0, .189, shade)
    for along, off in ((30, 1.3), (81, -2.3), (102, 5.3), (119, -6.1)):
        dark = (.16, .19, .22)
        mesh.slab(off, along, off + 1.45, along + .76, .006, dark)
        mesh.slab(along, -off - .76, along + 1.45, -off, .006, dark)
    if district in ("downtown", "residential"):
        for along in (19, 29, 43, 54, 61, 71, 82, 94, 105, 116):
            mesh.slab(5.05, along, 7.15, along + .10, .014, (.61, .62, .59))
            mesh.slab(along, -7.15, along + .10, -5.05, .014, (.61, .62, .59))


def street_lamp(mesh, glow, x, y, dx, dy):
    mesh.cone(x, y, SIDEWALK, .29, .34, .22, POST, 6)
    mesh.cone(x, y, SIDEWALK + .29, 6.1, .13, .075, POST, 6)
    mesh.box((x + dx * .74, y + dy * .74, 6.42),
             (max(.16, abs(dx) * 1.6), max(.16, abs(dy) * 1.6), .14), POST)
    lx, ly = x + dx * 1.53, y + dy * 1.53
    mesh.box((lx, ly, 6.42), (.61, .45, .17), TRIM, bottom=True)
    glow.box((lx, ly, 6.33), (.46, .36, .04), (.99, .74, .38), bottom=True)
    return lx, ly, 6.2


def traffic_signal(mesh, signal_sets, x, y, side):
    # Keep the signal housing in the static draw. Each lampset has its own
    # tiny mesh so an intersection can swap lights without rebuilding roads.
    axis = 1 if side in ("north", "south") else 0
    mesh.cone(x, y, SIDEWALK, 4.7, .15, .08, POST, 6)
    mesh.box((x, y, 4.48), (.45, .44, 1.08), (.12, .16, .17), bottom=True)
    face_plane = (y if axis else x) + (-.23 if side in ("south", "west") else .23)
    face_center = x if axis else y
    for color, on, height in (
        ("red", (.99, .22, .16), 4.80),
        ("yellow", (1, .66, .16), 4.48),
        ("green", (.29, .91, .51), 4.16),
    ):
        panel(mesh, side, face_plane, face_center - .134, face_center + .134,
              height - .134, height + .134, tuple(c * .27 for c in on))
        panel(signal_sets[axis][color], side,
              face_plane + (-.01 if side in ("south", "west") else .01),
              face_center - .119, face_center + .119, height - .119, height + .119, on)


def tree(mesh, collider, x, y, rng, palm=False):
    sx = rng.uniform(.84, 1.25)
    trunk_height = (5.7 if palm else 3.5) * sx
    collider.box((x, y, SIDEWALK + trunk_height * .5), (.40 * sx, .40 * sx, trunk_height))
    if palm:
        mesh.cone(x, y, SIDEWALK, trunk_height, .26 * sx, .14 * sx, (.42, .33, .27), 6)
        z = SIDEWALK + trunk_height
        for i in range(7):
            a = i * tau / 7 + rng.uniform(-.18, .18)
            dx, dy = cos(a), sin(a)
            color = (.24 + (i % 2) * .10, .43, .33)
            mesh.face(((x, y, z + .2), (x + dx * 1.35 + dy * .52,
                       y + dy * 1.35 - dx * .52, z + .28),
                       (x + dx * 2.55, y + dy * 2.55, z - .63),
                       (x + dx * 1.35 - dy * .52, y + dy * 1.35 + dx * .52,
                       z + .29)), color, (0, 0, 1))
        return
    mesh.cone(x, y, SIDEWALK, trunk_height, .26 * sx, .18 * sx, (.38, .32, .24), 6)
    foliage = rng.choice(((.28, .45, .33), (.34, .48, .28), (.24, .40, .32)))
    mesh.cone(x, y, 2.35 * sx, 1.1 * sx, .96 * sx, 2.05 * sx, foliage)
    mesh.cone(x, y, 3.45 * sx, 2.2 * sx, 2.05 * sx, 1.05 * sx, foliage)
    mesh.cone(x, y, 5.65 * sx, .71 * sx, 1.05 * sx, .18 * sx,
              tuple(c * 1.12 for c in foliage))


def bench_layout(district, ix, iy):
    """Bench centers and orientations shared by the mesh and seat positions."""
    if district == "park":
        return tuple((x, y, facing) for x in (23, 52, 86, 113)
                     for y, facing in ((66.15, "north"), (75.8, "south")))
    if district == "residential":
        return ((12.7, 69.1, "west"),)
    if district == "downtown" and (ix, iy) == (0, 0):
        return ((24, 26.65, "west"), (24, 32, "west"))
    if district == "beachfront":
        return tuple((x, y + .92, "north") for x, y in
                     ((33, 76), (63, 89), (75, 106), (108, 110)))
    return ()


def bench(mesh, collider, x, y, facing):
    dx, dy, _ = BENCH_FACING[facing]
    wood = (.56, .36, .24)
    edge = (.65, .43, .29)

    def transform(part, size):
        along, forward, height = part
        length, depth, thickness = size
        center = (x - dy * along + dx * forward, y + dx * along + dy * forward, height)
        dimensions = (depth, length, thickness) if dx else size
        return center, dimensions

    for slat in (-.214, 0, .214):
        center, size = transform((0, slat, BENCH_TOP - .055), (2.4, .205, .11))
        mesh.box(center, size, edge if slat > 0 else wood)
    for height in (.906, 1.12):
        center, size = transform((0, -.31, height), (2.4, .095, .17))
        mesh.box(center, size, wood)
    for end in (-.93, .93):
        center, size = transform((end, -.015, .41), (.17, .50, .46))
        mesh.box(center, size, POST)
        center, size = transform((end, -.32, .948), (.12, .12, .47))
        mesh.box(center, size, POST)
    collider.box(*transform((0, 0, .465), (2.4, .63, .57)))
    collider.box(*transform((0, -.31, .98), (2.4, .12, .46)))


def kiosk(mesh, glow, collider, x, y, label, palette):
    mesh.box((x, y, 1.92), (7.6, 4.3, 3.48), palette)
    collider.box((x, y, 1.92), (7.6, 4.3, 3.48))
    mesh.box((x, y - .75, 3.75), (8.3, 6.0, .19), POST)
    mesh.box((x, y - 2.21, 2.55), (6.0, .15, 1.23), TRIM)
    panel(mesh, "south", y - 2.30, x - 2.65, x + 2.65, 2.11, 3.04, GLASS[1])
    mesh.box((x, y - 2.3, 3.55), (5.9, .22, .55), TRIM)
    lettering(mesh, "south", y - 2.43, x, 3.35, .08, label, (.94, .72, .40))
    panel(glow, "south", y - 2.31, x - 2.65, x + 2.65, 2.11, 3.04, (.93, .60, .30))


def structure(mesh, collider, x, y, width, depth, base, height, color):
    center = (x, y, base + height * .5)
    size = (width, depth, height)
    mesh.box(center, size, color)
    collider.box(center, size)


def window_rows(mesh, glow, x, y, width, depth, base, floors, floor_step, rng,
                style="punched"):
    front_edges = (
        ("south", y - depth * .5 - .075, x - width * .5, width, -1),
        ("north", y + depth * .5 + .075, x - width * .5, width, 1),
        ("west", x - width * .5 - .075, y - depth * .5, depth, -1),
        ("east", x + width * .5 + .075, y - depth * .5, depth, 1),
    )
    for face, plane, start, span, outward in front_edges:
        columns = max(1, round(span / (2.95 if style == "curtain" else 4.6)))
        spacing = (span - 1.35) / columns
        pane = spacing * {"curtain": .96, "ribbon": .86, "punched": .58}[style]
        if style == "ribbon":
            for floor in range(floors):
                bottom = base + floor * floor_step + .49
                panel(mesh, face, plane, start + .55, start + span - .55,
                      bottom, bottom + floor_step * .65, TRIM)
            plane += outward * .045
        for column in range(columns):
            center = start + .675 + (column + .5) * spacing
            for floor in range(floors):
                bottom = base + floor * floor_step + .68
                top = bottom + floor_step * {"curtain": .76, "ribbon": .51,
                                             "punched": .46}[style]
                color = GLASS[(column * 5 + floor + rng.randrange(3)) % 3]
                panel(mesh, face, plane, center - pane * .5, center + pane * .5,
                      bottom, top, color)
                if rng.random() < (.35 if floors > 2 else .55):
                    panel(glow, face, plane + outward * .05, center - pane * .5,
                          center + pane * .5, bottom, top, rng.choice(LIT_GLASS))


def tower(mesh, glow, collider, x, y, rng, landmark=False):
    style = rng.choice(("ribbon", "punched", "curtain"))
    width = rng.uniform(29.0, 42.0)
    depth = rng.uniform(30.0, 44.0)
    floors = rng.randint(5, 14)
    if landmark:
        width, depth, floors = 39, 35, 17
        style = "curtain"
    if style == "punched" and not landmark:
        floors = rng.randint(3, 9)
    podium = 5.6 if style == "curtain" else 4.3
    finish = rng.choice(OFFICE_PALETTE)
    if style == "curtain":
        finish = rng.choice(((.25, .40, .47), (.26, .43, .46), (.32, .32, .40)))
    roof = SIDEWALK + podium + floors * 3.2
    structure(mesh, collider, x, y, width, depth, SIDEWALK, podium, finish)
    mesh.box((x, y, SIDEWALK + podium), (width + 1.2, depth + 1.2, .35), TRIM)
    window_rows(mesh, glow, x, y, width, depth, SIDEWALK, 1, podium, rng, "ribbon")
    tx, ty = x + rng.uniform(-2, 2), y + rng.uniform(-2, 2)
    tw, td = width - rng.uniform(5, 11), depth - rng.uniform(5, 11)
    if landmark:
        tx, ty = x, y
        finish = (.35, .42, .53)
    structure(mesh, collider, tx, ty, tw, td, SIDEWALK + podium, floors * 3.2, finish)
    window_rows(mesh, glow, tx, ty, tw, td, SIDEWALK + podium, floors, 3.2, rng, style)
    band = tuple(c * .67 for c in finish)
    mesh.box((tx, ty, roof - .4), (tw + .55, td + .55, .82), band)
    rooftop_height = 5.6 if landmark else 2.45
    mesh.box((tx, ty, roof + rooftop_height * .5),
             (tw * .50, td * .54, rooftop_height), finish)
    if style == "punched":
        for height in (roof - 4.0, SIDEWALK + podium + .6):
            mesh.box((tx, ty, height), (tw + .34, td + .34, .19), band)
    if style == "curtain":
        accent = (.34, .57, .57) if landmark else (.29, .44, .50)
        for ox in (-1, 1):
            for oy in (-1, 1):
                mesh.box((tx + ox * tw * .5, ty + oy * td * .5,
                          roof - floors * 1.6), (.36, .36, floors * 3.2), accent)
    if landmark or rng.random() < .36:
        mesh.cone(tx + tw * .12, ty, roof + rooftop_height, 6.8, .27, .10, TRIM, 6)
        glow.box((tx + tw * .12, ty, roof + rooftop_height + 6.8),
                 (.31, .31, .30), (.95, .21, .16))


def shop_awning(mesh, glow, x, y, label):
    color = (.17, .35, .39)
    mesh.box((x, y + .24, 3.15), (11.7, 1.75, .32), color)
    mesh.box((x, y - .64, 3.34), (11.2, .17, 1.04), TRIM)
    for offset in (-5.1, 5.1):
        mesh.box((x + offset, y + .97, 1.7), (.21, .21, 3.06), TRIM)
    lettering(mesh, "south", y - .735, x, 3.08, .109, label, (.96, .79, .48))
    lettering(glow, "south", y - .749, x, 3.08, .109, label, (.99, .67, .32))


def landmark_frontage(mesh, glow, collider, x, y, width, depth, name,
                      facade, accent, lit_glass):
    """A street-facing storefront with a clear approach from the west."""
    west = x - width * .5
    structure(mesh, collider, x, y, width, depth, SIDEWALK, 4.6, facade)
    mesh.box((x, y, 4.79), (width + .3, depth + .4, .25), accent)
    mesh.box((west - .35, y, 3.42), (1.2, depth - .7, .20), accent)
    mesh.slab(12.35, y - 1.38, west, y + 1.38, .194, (.61, .59, .53))
    panel(mesh, "west", west - .056, y - 1.13, y + 1.13, SIDEWALK, 3.08, TRIM)
    panel(mesh, "west", west - .065, y - .90, y + .90, .45, 2.85, GLASS[1])
    mesh.box((west - .084, y, 1.62), (.10, .065, 2.51), accent)
    for offset in (-3.15, 3.15):
        center = y + offset
        panel(mesh, "west", west - .072, center - 1.50, center + 1.50,
              1.30, 3.0, TRIM)
        panel(mesh, "west", west - .083, center - 1.37, center + 1.37,
              1.41, 2.88, GLASS[1])
        panel(glow, "west", west - .12, center - 1.37, center + 1.37,
              1.41, 2.88, lit_glass)
    panel(mesh, "west", west - .065, y - 4.93, y + 4.93, 3.71, 4.56, accent)
    lettering(mesh, "west", west - .095, y, 3.83, .131, name.upper(), WHITE)
    lettering(glow, "west", west - .12, y, 3.83, .131, name.upper(), lit_glass)
    return west


def supply_store(mesh, glow, collider):
    feet_x, y, _ = SHOP_POSITION
    west = landmark_frontage(mesh, glow, collider, feet_x + 7.8, y, 9.8, 12.4,
                             SHOP_NAME, (.38, .45, .43), (.46, .25, .16),
                             (.98, .72, .44))
    for y_end in (y - 5.5, y + 5.5):
        mesh.box((west - .33, y_end, 1.77), (.29, .31, 3.18), (.27, .29, .26))


def clinic(mesh, glow, collider, iy):
    feet_x, world_y, _ = HOSPITAL_POSITION
    y = world_y - iy * CHUNK_SIZE
    west = landmark_frontage(mesh, glow, collider, feet_x + 6.95, y, 6.7, 15.4,
                             HOSPITAL_NAME, (.65, .68, .62), (.14, .38, .40),
                             (.66, .85, .83))
    mesh.box((west + .33, y, 5.46), (1.14, 2.4, 1.24), (.19, .43, .45))
    for canvas, plane, color in ((mesh, west - .265, WHITE),
                                 (glow, west - .29, (.71, .94, .92))):
        panel(canvas, "west", plane, y - .17, y + .17, 5.02, 5.90, color)
        panel(canvas, "west", plane, y - .44, y + .44, 5.29, 5.63, color)


def downtown(mesh, glow, collider, ix, iy, rng):
    central = (ix, iy) == (0, 0)
    if central:
        # The starting block leaves a small pedestrian plaza to reveal the
        # skyline behind the first car and keep the spawn free of obstructions.
        mesh.slab(16, 15, 64, 58, .184, (.42, .45, .44))
        for x in (16, 64):
            mesh.slab(x - .08, 15, x + .08, 58, .19, (.62, .60, .53))
        for y in (15, 58):
            mesh.slab(16, y - .08, 64, y + .08, .19, (.62, .60, .53))
        for x in range(18, 64, 3):
            mesh.slab(x, 15.4, x + .045, 57.6, .19, (.36, .38, .37))
        for y in range(18, 58, 3):
            mesh.slab(16.4, y, 63.6, y + .045, .19, (.36, .38, .37))
        supply_store(mesh, glow, collider)
        mesh.box((17.2, 36, 1.81), (.46, 4.9, 3.26), (.23, .30, .34))
        mesh.box((16.95, 36, 2.86), (.09, 4.67, .83), (.10, .29, .33))
        lettering(mesh, "west", 16.895, 36, 2.68, .098, "EXCHANGE", (.88, .82, .60))
        lettering(glow, "west", 16.883, 36, 2.68, .098, "EXCHANGE", (.91, .79, .54))
        for x, y in ((35, 30), (44, 30), (53, 30), (57, 46)):
            mesh.box((x, y, .41), (3.4, 3.4, .46), (.33, .40, .40))
            tree(mesh, collider, x, y, rng)
        tower(mesh, glow, collider, 42, 93, rng, landmark=True)
    else:
        tower(mesh, glow, collider, 43, 43, rng)
        tower(mesh, glow, collider, 45, 104, rng)
        if (ix, iy) == (0, -1):
            clinic(mesh, glow, collider, iy)
    tower(mesh, glow, collider, 105, 42, rng)
    tower(mesh, glow, collider, 104, 104, rng)
    names = ("TIDEWAY", "ATLAS", "NORTHLINE", "SEAGLASS", "UNION")
    shop_awning(mesh, glow, 101, 19, names[(ix + iy) % len(names)])
    for pos in (25, 60, 89, 122):
        tree(mesh, collider, 14.9, pos, rng)
    for pos in (23, 59, 88, 121):
        tree(mesh, collider, pos, 14.9, rng)


def bungalow(mesh, glow, collider, x, y, rng):
    width, depth = rng.uniform(17, 21), rng.uniform(19, 27)
    floors = 1 if rng.random() < .65 else 2
    color = rng.choice(HOUSE_PALETTE)
    high = 2.6 * floors + .64
    structure(mesh, collider, x, y, width, depth, SIDEWALK, high, color)
    window_rows(mesh, glow, x, y, width, depth, SIDEWALK, floors, 2.6, rng)
    roof = SIDEWALK + high
    left, right, front, back = x - width / 2 - .65, x + width / 2 + .65, y - depth / 2 - .5, y + depth / 2 + .5
    peak = roof + width * .21
    roof_color = (.35, .32, .33)
    mesh.face(((left, front, roof), (x, front, peak),
               (x, back, peak), (left, back, roof)), roof_color)
    mesh.face(((x, front, peak), (right, front, roof),
               (right, back, roof), (x, back, peak)), (.44, .36, .33))
    mesh.face(((left, front, roof), (right, front, roof), (x, front, peak)),
              color, (0, -1, 0))
    mesh.face(((right, back, roof), (left, back, roof), (x, back, peak)),
              color, (0, 1, 0))
    mesh.box((x + 3.0, y + 1.7, roof + 2.0), (1.03, 1.08, 4.0), (.53, .43, .39))
    mesh.slab(x - 1.5, front - 5.0, x + 1.5, front, .191, (.57, .54, .47))


def residential(mesh, glow, collider, _ix, _iy, rng):
    mesh.slab(13, 13, 131, 131, .184, GRASS)
    mesh.slab(13, 68.5, 131, 72, .191, (.54, .52, .44))
    for x in (28, 68, 109):
        for y in (41, 101):
            bungalow(mesh, glow, collider, x, y, rng)
            tree(mesh, collider, x - 9, y - 16, rng)
            tree(mesh, collider, x + 10, y + 14, rng)
    for along in (21, 58, 94, 120):
        tree(mesh, collider, 14, along, rng)


def container(mesh, collider, x, y, bottom, rng):
    width, depth, height = 3.3, 12.1, 2.83
    color = rng.choice(CONTAINER_PALETTE)
    structure(mesh, collider, x, y, width, depth, bottom, height, color)
    lip = tuple(c * .72 for c in color)
    for offset in (-.51, .51):
        x_face = x + offset * width
        for rib in range(-5, 6):
            mesh.box((x_face, y + rib, bottom + height * .5), (.09, .11, height * .87), lip)
    for offset in (-.92, .92):
        mesh.box((x + offset, y - depth * .501, bottom + height * .5),
                 (.07, .06, height * .82), POST)


def harbor(mesh, glow, collider, ix, iy, rng):
    mesh.slab(13, 13, 131, 131, .184, (.35, .36, .38))
    finish = rng.choice(((.51, .53, .49), (.49, .44, .38), (.37, .46, .47)))
    structure(mesh, collider, 38, 72, 39, 57, SIDEWALK, 10, finish)
    mesh.box((38, 72, 10.29), (40.4, 58.3, .28), TRIM)
    window_rows(mesh, glow, 38, 72, 39, 57, 5.7, 1, 4, rng)
    face_y = 43.49
    panel(mesh, "south", face_y, 28, 48, .30, 5.5, (.18, .25, .29))
    for z in range(1, 6):
        panel(mesh, "south", face_y - .02, 28, 48, z - .13, z, (.31, .35, .37))
    lettering(mesh, "south", face_y - .04, 38, 7.53, .26, f"PIER {ix + 2}",
              (.82, .73, .56))
    for x in (77, 82, 89, 100, 106, 119):
        for y in (33, 51, 70):
            if rng.random() < .16:
                continue
            container(mesh, collider, x, y, SIDEWALK, rng)
            if rng.random() < .42:
                container(mesh, collider, x, y, SIDEWALK + 2.83, rng)
    steel = (.70, .47, .21)
    if (ix + iy) % 2 == 0:
        for x in (78, 123):
            for y in (99, 115):
                structure(mesh, collider, x, y, 1.3, 1.3, SIDEWALK, 22.0, steel)
        for y in (99, 115):
            mesh.box((100.5, y, 22.2), (48.0, 1.65, 1.4), steel)
        mesh.box((111, 107, 22.0), (3, 16, .73), steel)
        mesh.box((111, 107, 16.4), (.12, .12, 11.1), POST)
        mesh.box((111, 107, 10.9), (2.1, 2.2, .34), YELLOW)
    for x in (28, 51, 68, 98):
        mesh.box((x, 21.5, .25), (8, .17, .10), YELLOW)
    if (ix + iy) % 3 == 0:
        ramp(mesh, collider, 44, 114)


def ramp(mesh, collider, x, y):
    x0, x1 = x - 4.6, x + 4.6
    y0, y1 = y - 5.2, y + 5.2
    lo, hi = .185, 2.52
    a, b, c, d = (x0, y0, lo), (x1, y0, lo), (x1, y1, lo), (x0, y1, lo)
    e, f = (x0, y1, hi), (x1, y1, hi)
    mesh.face((a, b, f, e), (.47, .46, .43))
    mesh.face((b, c, f), (.37, .38, .36))
    mesh.face((c, d, e, f), (.38, .40, .40))
    mesh.face((d, a, e), (.34, .40, .40))
    collider.hull((a, b, c, d, e, f))
    slope = (hi - lo) / (y1 - y0)
    for x_start in (x0 + .23, x1 - .44):
        mesh.face(((x_start, y0, lo + .016), (x_start + .21, y0, lo + .016),
                   (x_start + .21, y1, lo + .016 + slope * (y1 - y0)),
                   (x_start, y1, lo + .016 + slope * (y1 - y0))), YELLOW)


def beachfront(mesh, glow, collider, ix, iy, rng):
    sand = (.68, .58, .44)
    mesh.slab(13, 13, 131, 131, .185, sand)
    mesh.slab(12.5, 39.2, 131.5, 48.3, .188, (.52, .40, .30))
    for i in range(101):
        x = 13.2 + i * 1.16
        mesh.slab(x, 39.2, x + .08, 48.3, .193, (.43, .34, .27))
    for x, y in ((25, 26), (48, 29), (65, 24), (111, 26), (21, 60), (40, 64),
                 (72, 60), (94, 59), (111, 79), (43, 103), (98, 105)):
        tree(mesh, collider, x, y, rng, palm=True)
    label = "BLUE FIN" if (ix + iy) % 2 else "SEABREEZE"
    kiosk(mesh, glow, collider, 82, 34, label, rng.choice(HOUSE_PALETTE))
    surfer_colors = ((.75, .37, .33), (.27, .56, .62), (.75, .59, .35))
    for x, y in ((33, 76), (63, 89), (75, 106), (108, 110)):
        mesh.cone(x, y, SIDEWALK, 2.8, .066, .066, POST, 6)
        mesh.cone(x, y, 2.54, .70, 2.35, .06, rng.choice(surfer_colors), 8)
    if iy == -8 and ix % 2 == 0:
        ramp(mesh, collider, 126, 100)


def park(mesh, glow, collider, ix, iy, rng):
    mesh.slab(13, 13, 131, 131, .184, DEEP_GRASS)
    for x0, y0, x1, y1 in ((13, 67, 131, 75), (67, 13, 75, 131)):
        mesh.slab(x0, y0, x1, y1, .190, (.59, .54, .44))
    for x in (25, 46, 90, 112):
        for y in (25, 46, 93, 111):
            tree(mesh, collider, x + rng.uniform(-3, 3), y + rng.uniform(-3, 3), rng)
    if (ix + iy) % 2 == 0:
        kiosk(mesh, glow, collider, 48, 61, "GROVE", (.35, .47, .33))
    else:
        x, y = 98, 99
        mesh.cone(x, y, SIDEWALK, .55, 13.4, 13.1, (.55, .58, .51), 16)
        mesh.cone(x, y, .749, .01, 12.5, 12.5, (.23, .43, .45), 16)
        mesh.cone(x, y, .75, 2.1, 2.2, .65, (.68, .68, .58), 8)
        mesh.cone(x, y, 2.82, .32, .65, 2.6, (.59, .63, .58), 10)
        mesh.cone(x, y, 3.15, .06, 2.35, 2.35, (.30, .55, .56), 10)


DISTRICT_BUILDERS = {
    "downtown": downtown,
    "residential": residential,
    "harbor": harbor,
    "beachfront": beachfront,
    "park": park,
}

"""Menus and instruments for the on-foot and driving views."""

import math
from pathlib import Path

from direct.gui.DirectButton import DirectButton
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    CardMaker, Filename, Geom, GeomNode, GeomTriangles, GeomVertexData,
    GeomVertexFormat, GeomVertexWriter, Point2, SamplerState, TextNode, TextureStage,
    TransparencyAttrib,
)

PAPER = (0.96, 0.95, 0.88, 1)
PALE = (0.76, 0.83, 0.80, 1)
MUTED = (0.57, 0.68, 0.67, 1)
MINT = (0.62, 0.93, 0.80, 1)
ORANGE = (1.00, 0.57, 0.31, 1)
DARK = (0.035, 0.08, 0.10, 0.94)
NORTH = 1152.0
MAP_SIZE = 0.302
WORDMARK = {
    "A": (((0, 0), (.34, 1), (.68, 0)), ((.13, .36), (.55, .36))),
    "B": (((0, 0), (0, 1), (.46, 1), (.63, .84), (.63, .65), (.46, .51), (0, .51)),
          ((.46, .51), (.68, .35), (.68, .17), (.50, 0), (0, 0))),
    "C": (((.70, .89), (.57, 1), (.16, 1), (0, .84), (0, .16), (.16, 0), (.55, 0), (.70, .13)),),
    "H": (((0, 0), (0, 1)), ((.70, 0), (.70, 1)), ((0, .49), (.70, .49))),
    "I": (((.00, 1), (.68, 1)), ((.34, 1), (.34, 0)), ((.00, 0), (.68, 0))),
    "O": (((.15, 0), (0, .15), (0, .85), (.15, 1), (.56, 1), (.71, .85), (.71, .15),
           (.56, 0), (.15, 0)),),
    "R": (((0, 0), (0, 1), (.51, 1), (.66, .85), (.66, .65), (.51, .50), (0, .50)),
          ((.36, .50), (.71, 0))),
    "T": (((.00, 1), (.70, 1)), ((.35, 1), (.35, 0))),
    "Y": (((0, 1), (.35, .49), (.70, 1)), ((.35, .49), (.35, 0))),
}


def _panel(parent, name, left, right, bottom, top, color, *, sort=0):
    maker = CardMaker(name)
    maker.set_frame(left, right, bottom, top)
    node = parent.attach_new_node(maker.generate(), sort)
    node.set_color(*color)
    if color[3] < 1:
        node.set_transparency(TransparencyAttrib.M_alpha)
    return node


def _map_card(parent):
    maker = CardMaker("city map")
    maker.set_frame(0, MAP_SIZE, 0, MAP_SIZE)
    maker.set_uv_range(Point2(0, 0), Point2(1, 1))
    return parent.attach_new_node(maker.generate(), 1)


def _map_arrow(parent):
    data = GeomVertexData("map direction", GeomVertexFormat.get_v3(), Geom.UH_static)
    vertex = GeomVertexWriter(data, "vertex")
    for x, z in ((0.0, 0.018), (-0.012, -0.011), (0.0, -0.006), (0.012, -0.011)):
        vertex.add_data3(x, 0, z)
    triangles = GeomTriangles(Geom.UH_static)
    triangles.add_vertices(0, 1, 2)
    triangles.add_vertices(0, 2, 3)
    mesh = Geom(data)
    mesh.add_primitive(triangles)
    node = GeomNode("map direction")
    node.add_geom(mesh)
    direction = parent.attach_new_node(node, 4)
    direction.set_two_sided(True)
    direction.set_color(*ORANGE)
    return direction


def _gradient(parent):
    data = GeomVertexData("menu shade gradient", GeomVertexFormat.get_v3c4(), Geom.UH_static)
    vertex = GeomVertexWriter(data, "vertex")
    color = GeomVertexWriter(data, "color")
    triangles = GeomTriangles(Geom.UH_static)
    for index, (x, opacity) in enumerate(((-.02, .96), (.83, .96), (1.10, .45), (1.56, 0))):
        for z in (-2.01, .01):
            vertex.add_data3(x, 0, z)
            color.add_data4(.022, .05, .066, opacity)
        if index:
            a = 2 * (index - 1)
            triangles.add_vertices(a, a + 2, a + 1)
            triangles.add_vertices(a + 1, a + 2, a + 3)
    mesh = Geom(data)
    mesh.add_primitive(triangles)
    node = GeomNode("menu shade")
    node.add_geom(mesh)
    node = parent.attach_new_node(node)
    node.set_transparency(TransparencyAttrib.M_alpha)


def _wordmark(parent, word, x, z):
    data = GeomVertexData(word, GeomVertexFormat.get_v3(), Geom.UH_static)
    vertex = GeomVertexWriter(data, "vertex")
    triangles = GeomTriangles(Geom.UH_static)
    height = .132
    half_stroke = .047
    row = 0

    for index, letter in enumerate(word):
        for line in WORDMARK[letter]:
            for start, end in zip(line, line[1:]):
                dx, dz = end[0] - start[0], end[1] - start[1]
                length = math.hypot(dx, dz)
                ux, uz = half_stroke * dx / length, half_stroke * dz / length
                for px, pz in (
                    (start[0] - ux + uz, start[1] - uz - ux),
                    (end[0] + ux + uz, end[1] + uz - ux),
                    (start[0] - ux - uz, start[1] - uz + ux),
                    (end[0] + ux - uz, end[1] + uz + ux),
                ):
                    vertex.add_data3(x + height * (px + index * .91), 0, z + height * pz)
                triangles.add_vertices(row, row + 1, row + 2)
                triangles.add_vertices(row + 2, row + 1, row + 3)
                row += 4
    mesh = Geom(data)
    mesh.add_primitive(triangles)
    node = GeomNode(word)
    node.add_geom(mesh)
    mark = parent.attach_new_node(node, 4)
    mark.set_color(*PAPER)


def _text(parent, value, x, z, size, color, font, *, align=TextNode.A_left, mutable=False):
    return OnscreenText(
        parent=parent, text=value, pos=(x, z), scale=size, fg=color,
        align=align, font=font, mayChange=mutable, sort=5,
    )


def _set_text(label, value):
    if label.text != value:
        label.text = value


class Overlay:
    """Aspect-aware presentation of the app state and the current player instruments."""

    def __init__(self, base, on_play, on_resume, on_quit, minimap_path):
        self.base = base
        self.sans = base.loader.load_font("cmss12")
        self.mono = base.loader.load_font("cmtt12")
        self.roots = []
        self.buttons = []
        self.help_visible = False
        self.debug_visible = False
        self.notice_time = 0.0

        self.menu = self._root(base.a2dTopLeft, "main menu")
        self.paused = self._root(base.a2dTopLeft, "pause menu")
        self.hud_top_left = self._root(base.a2dTopLeft, "locality")
        self.hud_top_right = self._root(base.a2dTopRight, "health and cash")
        self.hud_bottom_left = self._root(base.a2dBottomLeft, "minimap")
        self.hud_bottom_right = self._root(base.a2dBottomRight, "driving instruments")
        self.hud_bottom_center = self._root(base.a2dBottomCenter, "context prompts")
        self.help = self._root(base.aspect2d, "controls help", sort=60)
        self.debug = self._root(base.a2dTopLeft, "debug information", sort=50)
        self.hud = (
            self.hud_top_left, self.hud_top_right, self.hud_bottom_left,
            self.hud_bottom_right, self.hud_bottom_center,
        )

        self._build_menu(on_play, on_resume, on_quit)
        self._build_hud(minimap_path)
        self._build_help()
        self._build_debug()
        self.set_state("menu")

    def _root(self, anchor, name, *, sort=0):
        root = anchor.attach_new_node(name, sort)
        self.roots.append(root)
        return root

    def _button(self, parent, label, z, command, primary=False):
        color = ORANGE if primary else (.09, .17, .20, 1)
        fg = (.05, .10, .12, 1) if primary else PAPER
        button = DirectButton(
            parent=parent, text=label, text_align=TextNode.A_left,
            text_font=self.sans, text_fg=fg, text_scale=.045, text_pos=(.023, -.013),
            pos=(.135, 0, z), frameSize=(0, .605, -.055, .055),
            frameColor=(
                color,
                (0.84, 0.46, 0.27, 1) if primary else (0.08, .13, .16, 1),
                (1.0, 0.69, 0.46, 1) if primary else (0.16, .26, .28, 1),
                (.15, .21, .23, 1),
            ),
            relief=1, borderWidth=(0, 0), pressEffect=False, command=command,
            sortOrder=9,
        )
        self.buttons.append(button)
        return button

    def _build_menu(self, on_play, on_resume, on_quit):
        for parent in (self.menu, self.paused):
            _gradient(parent)
            _panel(parent, "title rule", .137, .303, -.281, -.273, ORANGE)
        _wordmark(self.menu, "HARBOR", .143, -.504)
        _wordmark(self.menu, "CITY", .143, -.672)
        _text(self.paused, "PAUSED", .129, -.542, .128, PAPER, self.sans)
        _text(self.paused, "HARBOR CITY", .138, -.635, .041, MINT, self.mono)

        for parent, label, action in ((self.menu, "Play", on_play), (self.paused, "Resume", on_resume)):
            self._button(parent, label, -.938, action, primary=True)
            self._button(parent, "Controls", -1.068, self.toggle_help)
            self._button(parent, "Quit", -1.198, on_quit)

    def _build_hud(self, minimap_path):
        parent = self.hud_top_left
        _panel(parent, "locality backdrop", .048, .541, -.173, -.048, DARK)
        _panel(parent, "locality stripe", .048, .053, -.173, -.048, MINT)
        self.district = _text(parent, "Harbor City", .073, -.097, .042, PAPER, self.sans, mutable=True)
        self.time = _text(parent, "", .075, -.146, .034, MINT, self.mono, mutable=True)

        parent = self.hud_top_right
        _panel(parent, "status backdrop", -.398, -.048, -.173, -.048, DARK)
        self.money = _text(parent, "$0", -.071, -.093, .044, MINT, self.mono,
                           align=TextNode.A_right, mutable=True)
        _text(parent, "HEALTH", -.376, -.089, .025, PALE, self.mono)
        self.health_text = _text(parent, "100", -.376, -.139, .038, PAPER, self.mono, mutable=True)
        _panel(parent, "health background", -.272, -.071, -.147, -.130, (.17, .26, .27, 1))
        self.health_bar = parent.attach_new_node("health bar", 2)
        self.health_bar.set_pos(-.272, 0, -.147)
        _panel(self.health_bar, "health fill", 0, .201, 0, .017, MINT)

        parent = self.hud_bottom_left
        _panel(parent, "minimap frame", .048, .382, .048, .423, DARK)
        _text(parent, "N", .068, .388, .029, PALE, self.mono)
        _text(parent, "F1  CONTROLS", .359, .388, .024, MUTED, self.mono, align=TextNode.A_right)
        self.map_origin = parent.attach_new_node("map contents")
        self.map_origin.set_pos(.064, 0, .064)
        self.map_image = _map_card(self.map_origin)
        self.map_stage = TextureStage.get_default()
        self.map_zoom = .24
        texture = None
        if minimap_path and Path(minimap_path).is_file():
            texture = self.base.loader.load_texture(
                Filename.from_os_specific(str(minimap_path)), okMissing=True,
            )
        if texture is not None:
            texture.set_wrap_u(SamplerState.WM_clamp)
            texture.set_wrap_v(SamplerState.WM_clamp)
            texture.set_minfilter(SamplerState.FT_linear)
            texture.set_magfilter(SamplerState.FT_linear)
            self.map_image.set_texture(texture)
            self.map_image.set_tex_scale(self.map_stage, self.map_zoom, self.map_zoom)
        else:
            self.map_image.set_color(.13, .28, .31, 1)
        self.map_arrow = _map_arrow(self.map_origin)

        parent = self.hud_bottom_right
        _panel(parent, "instrument backdrop", -.500, -.048, .048, .305, DARK)
        _panel(parent, "instrument stripe", -.500, -.048, .300, .305, ORANGE)
        self.speed = _text(parent, "000", -.461, .137, .113, PAPER, self.mono, mutable=True)
        _text(parent, "KM/H", -.073, .142, .032, PALE, self.mono, align=TextNode.A_right)
        self.car_health = _text(parent, "CAR 100%", -.459, .244, .029, PALE, self.mono, mutable=True)
        self.gear = _text(parent, "N", -.075, .216, .057, MINT, self.mono,
                          align=TextNode.A_right, mutable=True)
        _panel(parent, "rev backdrop", -.463, -.073, .075, .088, (.17, .26, .27, 1))
        self.rev_bar = parent.attach_new_node("rev bar", 2)
        self.rev_bar.set_pos(-.463, 0, .075)
        self.rev_fill = _panel(self.rev_bar, "rev fill", 0, .390, 0, .013, MINT)

        parent = self.hud_bottom_center
        self.context_group = parent.attach_new_node("context")
        _panel(self.context_group, "context backdrop", -.355, .355, .048, .118, DARK)
        self.context = _text(self.context_group, "", 0, .071, .038, PAPER, self.sans,
                             align=TextNode.A_center, mutable=True)
        self.notice_group = parent.attach_new_node("notification")
        _panel(self.notice_group, "notification backdrop", -.355, .355, .133, .213, DARK)
        self.notice = _text(self.notice_group, "", 0, .161, .04, MINT, self.sans,
                            align=TextNode.A_center, mutable=True)
        self.notice_group.hide()

    def _build_help(self):
        _panel(self.help, "controls backdrop", -.52, .52, -.67, .67, (.027, .065, .081, .98))
        _panel(self.help, "controls top rule", -.52, .52, .661, .67, ORANGE)
        _text(self.help, "Controls", -.445, .536, .080, PAPER, self.sans)
        _text(self.help, "ON FOOT", -.445, .429, .035, MINT, self.mono)
        _text(self.help, "DRIVING", .027, .429, .035, MINT, self.mono)

        for index, ((walk_key, walk_action), (car_key, car_action)) in enumerate(zip(
            (("WASD", "Move"), ("MOUSE", "Look"), ("SHIFT", "Sprint"), ("SPACE", "Jump"), ("F", "Enter vehicle")),
            (("W / S", "Accelerate / reverse"), ("A / D", "Steer"), ("SPACE", "Handbrake"), ("C", "Change camera"), ("F", "Exit vehicle")),
        )):
            z = .347 - index * .084
            _text(self.help, walk_key, -.445, z, .033, PAPER, self.mono)
            _text(self.help, walk_action, -.260, z, .033, PALE, self.sans)
            _text(self.help, car_key, .027, z, .033, PAPER, self.mono)
            _text(self.help, car_action, .203, z, .033, PALE, self.sans)

        _panel(self.help, "controls divider", -.445, .445, -.105, -.103, (.23, .36, .37, 1))
        for index, (key, action) in enumerate((("ESC", "Pause"), ("F1", "Controls"), ("F3", "Debug view"), ("F5", "Quicksave"))):
            z = -.179 - index * .073
            _text(self.help, key, -.445, z, .033, PAPER, self.mono)
            _text(self.help, action, -.260, z, .035, PALE, self.sans)
        _text(self.help, "F1  CLOSE", .445, -.582, .032, ORANGE, self.mono, align=TextNode.A_right)

    def _build_debug(self):
        _panel(self.debug, "debug backdrop", .048, .636, -.552, -.201, (.024, .057, .075, .95))
        self.debug_text = _text(self.debug, "", .074, -.258, .033, MINT, self.mono, mutable=True)

    def set_state(self, state):
        if state not in {"menu", "playing", "paused"}:
            raise ValueError(f"Unknown overlay state {state!r}")
        self.state = state
        self.help_visible = False
        self._sync_visibility()

    def _sync_visibility(self):
        playing = self.state == "playing"
        self.menu.show() if self.state == "menu" else self.menu.hide()
        self.paused.show() if self.state == "paused" else self.paused.hide()
        self.help.show() if self.help_visible else self.help.hide()
        self.debug.show() if playing and self.debug_visible else self.debug.hide()
        for group in self.hud:
            group.show() if playing else group.hide()

    def toggle_help(self):
        self.help_visible = not self.help_visible
        self._sync_visibility()

    def toggle_debug(self):
        self.debug_visible = not self.debug_visible
        self._sync_visibility()

    def notify(self, text):
        _set_text(self.notice, text)
        self.notice_time = 2.8
        self.notice_group.show()

    def _update_minimap(self, position, heading):
        extent = NORTH * 2
        u = (float(position[0]) + NORTH) / extent
        v = (float(position[1]) + NORTH) / extent
        half_map = self.map_zoom / 2
        left = min(1 - self.map_zoom, max(0, u - half_map))
        bottom = min(1 - self.map_zoom, max(0, v - half_map))
        self.map_image.set_tex_offset(self.map_stage, left, bottom)
        x = min(1, max(0, (u - left) / self.map_zoom))
        z = min(1, max(0, (v - bottom) / self.map_zoom))
        margin = .014
        self.map_arrow.set_pos(margin + x * (MAP_SIZE - margin * 2), 0, margin + z * (MAP_SIZE - margin * 2))
        self.map_arrow.set_r(-heading)

    def update(self, dt, *, district="", position=(0, 0, 0), heading=0, speed=0,
               rpm=0, gear="", health=100, money=0, hour=17, context="", fps=0,
               debug_info="", driving=False, car_health=100):
        if self.state != "playing":
            return
        _set_text(self.district, district or "Harbor City")
        minutes = int(hour * 60) % 1440
        _set_text(self.time, f"{minutes // 60:02}:{minutes % 60:02}")
        _set_text(self.money, f"${money:,.0f}")
        _set_text(self.health_text, f"{max(0, min(100, health)):0.0f}")
        self.health_bar.set_sx(max(.001, min(1, health / 100)))
        self._update_minimap(position, heading)

        if driving:
            self.hud_bottom_right.show()
            _set_text(self.speed, f"{min(999, abs(speed)):03.0f}")
            _set_text(self.gear, "R" if gear == -1 else str(gear))
            _set_text(self.car_health, f"CAR {car_health:.0f}%")
            self.rev_bar.set_sx(max(.002, min(1, rpm / 7000)))
            self.rev_fill.set_color(*(ORANGE if rpm > 5750 else MINT))
        else:
            self.hud_bottom_right.hide()

        if context:
            _set_text(self.context, context)
            self.context_group.show()
        else:
            self.context_group.hide()

        if self.notice_time > 0:
            self.notice_time = max(0, self.notice_time - dt)
            if self.notice_time == 0:
                self.notice_group.hide()

        if self.debug_visible:
            rate = fps if math.isfinite(fps) else 0
            _set_text(self.debug_text, f"{rate:5.1f} FPS\n{debug_info}")

    def destroy(self):
        for button in self.buttons:
            button.destroy()
        for root in self.roots:
            root.remove_node()

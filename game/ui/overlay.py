"""Menus and instruments for the on-foot and driving views."""

import math
from pathlib import Path

from direct.gui import DirectGuiGlobals as DGG
from direct.gui.DirectButton import DirectButton
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    CardMaker, Filename, Geom, GeomNode, GeomTriangles, GeomVertexData,
    GeomVertexFormat, GeomVertexWriter, LineSegs, Point2, SamplerState, TextNode, TextureStage,
    TransparencyAttrib,
)

from game.core.config import PRESETS, WEAPON_KEYS

PAPER = (0.96, 0.95, 0.88, 1)
PALE = (0.76, 0.83, 0.80, 1)
MUTED = (0.57, 0.68, 0.67, 1)
MINT = (0.62, 0.93, 0.80, 1)
ORANGE = (1.00, 0.57, 0.31, 1)
ARMOR = (0.49, 0.76, 1.00, 1)
DARK = (0.035, 0.08, 0.10, 0.94)
CONTROL_DARK = (.09, .17, .20, 1)
CONTROL_HOVER = (.16, .26, .28, 1)
NORTH = 1152.0
MAP_SIZE = 0.302
WORDMARK = {
    "A": (((0, 0), (.34, 1), (.68, 0)), ((.13, .36), (.55, .36))),
    "B": (((0, 0), (0, 1), (.46, 1), (.63, .84), (.63, .65), (.46, .51), (0, .51)),
          ((.46, .51), (.68, .35), (.68, .17), (.50, 0), (0, 0))),
    "C": (((.70, .89), (.57, 1), (.16, 1), (0, .84), (0, .16), (.16, 0), (.55, 0), (.70, .13)),),
    "D": (((0, 0), (0, 1), (.44, 1), (.71, .75), (.71, .25), (.44, 0), (0, 0)),),
    "E": (((.69, 1), (0, 1), (0, 0), (.69, 0)), ((0, .50), (.57, .50))),
    "H": (((0, 0), (0, 1)), ((.70, 0), (.70, 1)), ((0, .49), (.70, .49))),
    "I": (((.00, 1), (.68, 1)), ((.34, 1), (.34, 0)), ((.00, 0), (.68, 0))),
    "O": (((.15, 0), (0, .15), (0, .85), (.15, 1), (.56, 1), (.71, .85), (.71, .15),
           (.56, 0), (.15, 0)),),
    "R": (((0, 0), (0, 1), (.51, 1), (.66, .85), (.66, .65), (.51, .50), (0, .50)),
          ((.36, .50), (.71, 0))),
    "S": (((.70, .88), (.57, 1), (.16, 1), (0, .84), (0, .69), (.16, .51), (.53, .51),
           (.70, .33), (.70, .15), (.55, 0), (.15, 0), (0, .14)),),
    "T": (((.00, 1), (.70, 1)), ((.35, 1), (.35, 0))),
    "U": (((0, 1), (0, .18), (.17, 0), (.53, 0), (.70, .18), (.70, 1)),),
    "W": (((0, 1), (.14, 0), (.36, .56), (.57, 0), (.72, 1)),),
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


def _star(parent, x, z):
    data = GeomVertexData("wanted star", GeomVertexFormat.get_v3(), Geom.UH_static)
    vertices = GeomVertexWriter(data, "vertex")
    vertices.add_data3(0, 0, 0)
    triangles = GeomTriangles(Geom.UH_static)
    for index in range(10):
        angle = math.pi * index / 5
        radius = .022 if index % 2 == 0 else .010
        vertices.add_data3(math.sin(angle) * radius, 0, math.cos(angle) * radius)
        triangles.add_vertices(0, index + 1, (index + 1) % 10 + 1)
    geometry = Geom(data)
    geometry.add_primitive(triangles)
    mesh = GeomNode("wanted star")
    mesh.add_geom(geometry)
    star = parent.attach_new_node(mesh, 2)
    star.set_pos(x, 0, z)
    star.set_two_sided(True)
    return star


def _clip_minimap_segment(x0, z0, x1, z1):
    """Clip a segment to the map card, keeping endpoints on its boundary."""
    dx, dz = x1 - x0, z1 - z0
    lower, upper = 0.0, 1.0
    for distance, slope in ((x0, dx), (MAP_SIZE - x0, -dx), (z0, dz), (MAP_SIZE - z0, -dz)):
        if slope > 0:
            lower = max(lower, -distance / slope)
        elif slope < 0:
            upper = min(upper, -distance / slope)
        elif distance < 0:
            return None
    if lower > upper:
        return None
    return x0 + lower * dx, z0 + lower * dz, x0 + upper * dx, z0 + upper * dz


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


def _wordmark(parent, word, x, z, *, height=.132, color=PAPER):
    data = GeomVertexData(word, GeomVertexFormat.get_v3(), Geom.UH_static)
    vertex = GeomVertexWriter(data, "vertex")
    triangles = GeomTriangles(Geom.UH_static)
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
    mark.set_color(*color)


def _text(parent, value, x, z, size, color, font, *, align=TextNode.A_left, mutable=False, wrap=None):
    return OnscreenText(
        parent=parent, text=value, pos=(x, z), scale=size, fg=color,
        align=align, font=font, mayChange=mutable, sort=5, wordwrap=wrap,
    )


def _set_text(label, value):
    if label.text != value:
        label.text = value


class Overlay:
    """Aspect-aware presentation of the app state and the current player instruments."""

    def __init__(self, base, on_play, on_resume, on_quit, minimap_path, *,
                 on_quality=None, on_rebind=None, on_save=None, on_load=None):
        self.base = base
        self.sans = base.loader.load_font("cmss12")
        self.mono = base.loader.load_font("cmtt12")
        self.roots = []
        self.buttons = []
        self.help_visible = False
        self.debug_visible = False
        self.notice_time = 0.0
        self.hit_time = 0.0
        self.dialogue_open = False
        self.shop_open = False
        self.wasted_open = False
        self.busted_open = False
        self.aiming = False
        self.armed = False
        self.driving = False
        self.panel = None
        self.rebinding = None
        self.binding_rows = {}
        self.binding_labels = {}
        self.fire_key = "LMB"
        self.reload_key = "R"
        self.on_quality = on_quality
        self.on_rebind = on_rebind
        self.on_save = on_save
        self.on_load = on_load

        self.menu = self._root(base.a2dTopLeft, "main menu")
        self.paused = self._root(base.a2dTopLeft, "pause menu")
        self.hud_top_left = self._root(base.a2dTopLeft, "locality")
        self.hud_top_right = self._root(base.a2dTopRight, "health and cash")
        self.hud_top_center = self._root(base.a2dTopCenter, "current objective")
        self.hud_bottom_left = self._root(base.a2dBottomLeft, "minimap")
        self.hud_bottom_right = self._root(base.a2dBottomRight, "driving instruments")
        self.hud_bottom_center = self._root(base.a2dBottomCenter, "context prompts")
        self.help = self._root(base.aspect2d, "controls help", sort=60)
        self.debug = self._root(base.a2dTopLeft, "debug information", sort=50)
        self.combat_hud = self._root(base.a2dBottomRight, "weapon instruments")
        self.reticle = self._root(base.aspect2d, "aim reticle")
        self.hit_marker = self._root(base.aspect2d, "hit marker")
        self.dialogue = self._root(base.a2dBottomCenter, "conversation", sort=35)
        self.shop = self._root(base.a2dBottomCenter, "shop", sort=35)
        self.wasted = self._root(base.aspect2d, "wasted", sort=65)
        self.busted = self._root(base.aspect2d, "busted", sort=65)
        self.settings = self._root(base.aspect2d, "settings", sort=70)
        self.saves = self._root(base.aspect2d, "save slots", sort=70)
        self.hud = (
            self.hud_top_left, self.hud_top_right, self.hud_top_center, self.hud_bottom_left,
            self.hud_bottom_right, self.hud_bottom_center,
        )

        self._build_menu(on_play, on_resume, on_quit)
        self._build_hud(minimap_path)
        self._build_help()
        self._build_debug()
        self._build_combat()
        self._build_dialogue()
        self._build_settings()
        self._build_saves()
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
            buttons = []
            if self.on_load or (parent == self.paused and self.on_save):
                buttons.append(("Load game" if parent == self.menu else "Save / load", self.open_saves))
            if self.on_quality or self.on_rebind:
                buttons.append(("Settings", self.open_settings))
            buttons.extend((("Controls", self.toggle_help), ("Quit", on_quit)))
            self._button(parent, label, -.938, action, primary=True)
            for index, (title, invoke) in enumerate(buttons):
                self._button(parent, title, -1.068 - index * .130, invoke)

    def _build_hud(self, minimap_path):
        parent = self.hud_top_left
        _panel(parent, "locality backdrop", .048, .541, -.173, -.048, DARK)
        _panel(parent, "locality stripe", .048, .053, -.173, -.048, MINT)
        self.district = _text(parent, "Harbor City", .073, -.097, .042, PAPER, self.sans, mutable=True)
        self.time = _text(parent, "", .075, -.146, .034, MINT, self.mono, mutable=True)

        parent = self.hud_top_right
        _panel(parent, "status backdrop", -.398, -.048, -.228, -.048, DARK)
        self.money = _text(parent, "$0", -.071, -.093, .044, MINT, self.mono,
                           align=TextNode.A_right, mutable=True)
        _text(parent, "HEALTH", -.376, -.089, .025, PALE, self.mono)
        self.health_text = _text(parent, "100", -.376, -.139, .038, PAPER, self.mono, mutable=True)
        _panel(parent, "health background", -.272, -.071, -.147, -.130, (.17, .26, .27, 1))
        self.health_bar = parent.attach_new_node("health bar", 2)
        self.health_bar.set_pos(-.272, 0, -.147)
        _panel(self.health_bar, "health fill", 0, .201, 0, .017, MINT)
        _text(parent, "ARMOR", -.376, -.200, .025, ARMOR, self.mono)
        self.armor_text = _text(parent, "0", -.272, -.200, .034, PAPER, self.mono, mutable=True)
        _panel(parent, "armor background", -.196, -.071, -.201, -.184, (.17, .26, .27, 1))
        self.armor_bar = parent.attach_new_node("armor bar", 2)
        self.armor_bar.set_pos(-.196, 0, -.201)
        _panel(self.armor_bar, "armor fill", 0, .125, 0, .017, ARMOR)
        self.wanted_group = parent.attach_new_node("wanted status")
        _panel(self.wanted_group, "wanted backdrop", -.398, -.048, -.365, -.243, DARK)
        _panel(self.wanted_group, "wanted stripe", -.398, -.048, -.249, -.243, ORANGE)
        self.wanted_stars = [_star(self.wanted_group, -.223 + .060 * step, -.286) for step in range(-2, 3)]
        self.wanted_message = _text(self.wanted_group, "", -.223, -.342, .038, ORANGE, self.sans,
                                    align=TextNode.A_center, mutable=True)
        self.wanted_group.hide()

        self.objective_group = self.hud_top_center.attach_new_node("objective")
        _panel(self.objective_group, "objective backdrop", -.451, .451, -.148, -.048, DARK)
        _panel(self.objective_group, "objective stripe", -.451, .451, -.053, -.048, MINT)
        self.objective = _text(self.objective_group, "", 0, -.111, .041, PAPER, self.sans,
                               align=TextNode.A_center, mutable=True)
        self.objective_group.hide()

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
        self.route_layer = self.map_origin.attach_new_node(GeomNode("directions"), 2)
        self.route_points = ()
        self.route_corner = (0, 0)
        self.map_arrow = _map_arrow(self.map_origin)
        self.map_waypoint = self.map_origin.attach_new_node("destination ping", 3)
        self.map_waypoint.set_r(45)
        _panel(self.map_waypoint, "destination outline", -.012, .012, -.012, .012, DARK)
        _panel(self.map_waypoint, "destination fill", -.008, .008, -.008, .008, MINT, sort=1)
        self.map_waypoint.hide()

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
        _panel(self.help, "controls backdrop", -.81, .81, -.60, .67, (.027, .065, .081, .98))
        _panel(self.help, "controls top rule", -.81, .81, .661, .67, ORANGE)
        _text(self.help, "Controls", -.722, .536, .080, PAPER, self.sans)
        columns = (
            (-.722, "ON FOOT", (
                ("WASD", "Move", "walk"), ("MOUSE", "Look", ""), ("SHIFT", "Sprint", "sprint"),
                ("SPACE", "Jump", "jump"), ("F", "Enter / Steal vehicle", "interact"),
                ("E", "Talk / Shop", "talk"),
            )),
            (-.207, "DRIVING", (
                ("W / S", "Accelerate / Reverse", "drive"), ("A / D", "Steer", "steer"),
                ("SPACE", "Handbrake", "jump"), ("C", "Change camera", "vehicle_view"),
                ("F", "Exit vehicle", "interact"),
            )),
            (.327, "COMBAT", (
                ("RMB", "Aim", "aim"), ("LMB", "Attack", "fire"), ("R", "Reload", "reload"),
                ("1-9,0,-", "Select weapon", ""), ("Q", "Next weapon", "cycle_weapon"),
            )),
        )
        self.help_keys = {}
        for x, heading, controls in columns:
            _text(self.help, heading, x, .428, .037, MINT, self.mono)
            for index, (key, action, setting) in enumerate(controls):
                z = .344 - index * .073
                key_label = _text(self.help, key, x, z, .034, PAPER, self.mono, mutable=bool(setting))
                if setting:
                    self.help_keys.setdefault(setting, []).append(key_label)
                _text(self.help, action, x + .167, z, .036, PALE, self.sans)

        _panel(self.help, "controls divider", -.722, .724, -.112, -.110, (.23, .36, .37, 1))
        common = (("ESC", "Pause"), ("F1", "Controls"), ("F3", "Debug view"), ("F5", "Quicksave"))
        for index, (key, action) in enumerate(common):
            x, z = (-.722, -.207)[index // 2], -.207 - (index % 2) * .075
            _text(self.help, key, x, z, .034, PAPER, self.mono)
            _text(self.help, action, x + .167, z, .036, PALE, self.sans)
        _text(self.help, "F1  CLOSE", .724, -.500, .033, ORANGE, self.mono, align=TextNode.A_right)

    def _build_debug(self):
        _panel(self.debug, "debug backdrop", .048, .636, -.552, -.201, (.024, .057, .075, .95))
        self.debug_text = _text(self.debug, "", .074, -.258, .033, MINT, self.mono, mutable=True)

    def _menu_control(self, parent, title, left, right, height, command, *args, align=TextNode.A_center):
        horizontal = (right - left) / 2
        button = DirectButton(
            parent=parent, pos=(left + horizontal, 0, height), text=title,
            text_font=self.sans, text_scale=.042, text_fg=PAPER, text_align=align,
            text_pos=(0 if align == TextNode.A_center else -.95 * horizontal, -.013),
            frameSize=(-horizontal, horizontal, -.035, .035),
            frameColor=(CONTROL_DARK, (.09, .14, .17, 1), CONTROL_HOVER, (.065, .12, .145, 1)),
            relief=1, borderWidth=(0, 0), pressEffect=False, sortOrder=8,
            command=command, extraArgs=list(args), state=DGG.NORMAL if command else DGG.DISABLED,
        )
        self.buttons.append(button)
        return button

    def _build_settings(self):
        _panel(self.settings, "settings backdrop", -.72, .72, -.825, .827, (.027, .065, .081, .99))
        _panel(self.settings, "settings accent", -.72, .72, .820, .827, MINT)
        _text(self.settings, "Settings", -.641, .669, .085, PAPER, self.sans)
        _text(self.settings, "Graphics quality", -.641, .531, .045, MINT, self.sans)
        self.quality_controls = {}
        for index, preset in enumerate(PRESETS):
            left = -.641 + .277 * index
            self.quality_controls[preset] = self._menu_control(
                self.settings, preset, left, left + .259, .439, self.on_quality, preset,
            )
        _text(self.settings, "Controls", -.641, .293, .045, MINT, self.sans)
        self.rebind_prompt = _text(
            self.settings, "", .627, .293, .032, ORANGE, self.sans, align=TextNode.A_right, mutable=True,
        )
        _panel(self.settings, "controls backdrop", -.641, .641, -.467, .218, (.045, .09, .105, 1))
        self.binding_container = self.settings.attach_new_node("key bindings", 7)
        self._menu_control(self.settings, "Back", -.641, -.370, -.715, self.close_panel)
        self.settings_message = _text(
            self.settings, "", .620, -.731, .036, PALE, self.sans, align=TextNode.A_right, mutable=True,
        )

    def _build_saves(self):
        _panel(self.saves, "save slots backdrop", -.72, .72, -.49, .49, (.027, .065, .081, .99))
        _panel(self.saves, "save slots accent", -.72, .72, .483, .49, MINT)
        self.saves_title = _text(self.saves, "Save slots", -.641, .343, .085, PAPER, self.sans, mutable=True)
        self.save_slots = {}
        for slot in range(1, 4):
            z = .174 - (slot - 1) * .164
            _panel(self.saves, "save slot card", -.642, .642, z - .052, z + .068, (.070, .125, .148, 1))
            _text(self.saves, f"Slot {slot}", -.609, z + .019, .049, PAPER, self.sans)
            caption = _text(self.saves, "Empty", -.609, z - .032, .036, PALE, self.sans, mutable=True)
            save = self._menu_control(self.saves, "Save", .194, .391, z + .006, self.on_save, slot)
            load = self._menu_control(self.saves, "Load", .411, .608, z + .006, self.on_load, slot)
            load["state"] = DGG.DISABLED
            load["text_fg"] = MUTED
            self.save_slots[slot] = caption, save, load
        self._menu_control(self.saves, "Back", -.641, -.370, -.370, self.close_panel)
        self.saves_message = _text(
            self.saves, "", .620, -.385, .036, ORANGE, self.sans, align=TextNode.A_right, mutable=True,
        )

    def set_settings(self, quality, bindings, labels=None, *, message=""):
        labels = labels or {}
        for preset, button in self.quality_controls.items():
            selected = quality == preset
            button["frameColor"] = (MINT if selected else CONTROL_DARK,
                                    (.09, .14, .17, 1), CONTROL_HOVER, (.065, .12, .145, 1))
            button["text_fg"] = (.04, .10, .11, 1) if selected else PAPER
        _set_text(self.settings_message, message)
        self.binding_labels = {action: labels.get(action, action.replace("_", " ").title()) for action in bindings}
        if tuple(bindings) != tuple(self.binding_rows):
            for button, _ in self.binding_rows.values():
                button.destroy()
                self.buttons.remove(button)
            self.binding_rows.clear()
            rows = (len(bindings) + 1) // 2
            spacing = min(.104, .64 / max(1, rows))
            for index, action in enumerate(bindings):
                left = -.618 if index < rows else .012
                z = .142 - spacing * (index % rows)
                button = self._menu_control(
                    self.binding_container, self.binding_labels[action], left, left + .604, z, self.on_rebind, action,
                    align=TextNode.A_left,
                )
                key = _text(button, "", .272, -.013, .036, MINT, self.mono,
                            align=TextNode.A_right, mutable=True)
                self.binding_rows[action] = button, key
        for action, binding in bindings.items():
            button, key = self.binding_rows[action]
            button["text"] = self.binding_labels[action]
            _set_text(key, self._control_label(binding))
        self._update_help_keys(bindings)
        self.fire_key = self._control_label(bindings.get("fire", "mouse1"))
        self.reload_key = self._control_label(bindings.get("reload", "r"))
        cycle_key = self._control_label(bindings.get("cycle_weapon", "q"))
        _set_text(self.cycle_hint, f"{cycle_key}  NEXT")
        talk_key = self._control_label(bindings.get("talk", "e"))
        for prompt in (self.dialogue_exit, self.shop_exit):
            _set_text(prompt, f"{talk_key}  CLOSE")

    def _update_help_keys(self, bindings):
        groups = {
            "walk": ("forward", "left", "back", "right"),
            "drive": ("forward", "back"),
            "steer": ("left", "right"),
        }
        for setting, labels in self.help_keys.items():
            actions = groups.get(setting, (setting,))
            if all(action in bindings for action in actions):
                keys = [self._control_label(bindings[action]) for action in actions]
                name = "WASD" if keys == ["W", "A", "S", "D"] else " / ".join(keys)
                for label in labels:
                    _set_text(label, name)
                    label.setTextScale(min(.034, .276 / len(name)))

    @staticmethod
    def _control_label(key):
        labels = {"mouse1": "LMB", "mouse2": "MMB", "mouse3": "RMB", "escape": "ESC",
                  "lshift": "L SHIFT", "rshift": "R SHIFT",
                  "arrow_up": "UP", "arrow_down": "DOWN", "arrow_left": "LEFT", "arrow_right": "RIGHT"}
        return labels.get(key, str(key).upper().replace("_", " "))

    def set_rebinding(self, action=None, message=""):
        self.rebinding = action
        if action and not message:
            message = f"Press a key for {self.binding_labels.get(action, action)}"
        _set_text(self.rebind_prompt, message)

    def set_slots(self, slots, *, message=""):
        for slot, (caption, _, load) in self.save_slots.items():
            description = slots.get(slot)
            _set_text(caption, str(description) if description else "Empty")
            enabled = bool(description and self.on_load)
            load["state"] = DGG.NORMAL if enabled else DGG.DISABLED
            load["text_fg"] = PAPER if enabled else MUTED
        _set_text(self.saves_message, message)

    def open_settings(self):
        self.panel = "settings"
        self.help_visible = False
        self.set_rebinding()
        self._sync_visibility()

    def open_saves(self):
        self.panel = "saves"
        self.help_visible = False
        _set_text(self.saves_title, "Load game" if self.state == "menu" else "Save / load")
        for _, save, _ in self.save_slots.values():
            save.show() if self.state == "paused" and self.on_save else save.hide()
        self._sync_visibility()

    def close_panel(self):
        if self.panel is None:
            return False
        self.panel = None
        self.set_rebinding()
        self._sync_visibility()
        return True

    def _build_combat(self):
        parent = self.combat_hud
        _panel(parent, "weapon backdrop", -.500, -.048, .048, .271, DARK)
        _panel(parent, "weapon stripe", -.500, -.048, .266, .271, ORANGE)
        self.weapon_name = _text(parent, "", -.459, .213, .042, PAPER, self.sans, mutable=True)
        self.weapon_hotkey = parent.attach_new_node("selected weapon key", 1)
        _panel(self.weapon_hotkey, "weapon key backdrop", -.111, -.064, .203, .247, CONTROL_DARK)
        self.weapon_key = _text(self.weapon_hotkey, "", -.0875, .213, .032, MINT, self.mono,
                                align=TextNode.A_center, mutable=True)
        self.weapon_hotkey.hide()
        self.ammo_text = _text(parent, "", -.459, .101, .082, PAPER, self.mono, mutable=True)
        self.ammo_status = _text(parent, "", -.074, .168, .030, ORANGE, self.mono,
                                 align=TextNode.A_right, mutable=True)
        self.cycle_hint = _text(parent, "Q  NEXT", -.074, .064, .030, PALE, self.mono,
                                align=TextNode.A_right, mutable=True)

        bars = ((-.024, -.010, -.002, .002), (.010, .024, -.002, .002),
                (-.002, .002, -.024, -.010), (-.002, .002, .010, .024),
                (-.0015, .0015, -.0015, .0015))
        for left, right, bottom, top in bars:
            _panel(self.reticle, "reticle outline", left - .0015, right + .0015,
                   bottom - .0015, top + .0015, (.02, .05, .06, .86))
            _panel(self.reticle, "reticle bar", left, right, bottom, top, PAPER, sort=1)

        self.hit_bars = []
        for angle in (45, 135, 225, 315):
            arm = self.hit_marker.attach_new_node("hit marker arm")
            arm.set_r(angle)
            _panel(arm, "hit marker outline", -.004, .004, .011, .031, (.02, .05, .06, .90))
            self.hit_bars.append(_panel(arm, "hit marker fill", -.0025, .0025, .013, .029, PAPER, sort=1))

        _panel(self.wasted, "wasted backdrop", -.88, .88, -.215, .217, (.024, .040, .05, .95))
        _panel(self.wasted, "wasted stripe", -.88, .88, .209, .217, ORANGE)
        _wordmark(self.wasted, "WASTED", -.294, -.019, height=.112, color=ORANGE)
        self.wasted_countdown = _text(self.wasted, "", 0, -.111, .053, PAPER, self.sans,
                                      align=TextNode.A_center, mutable=True)
        _panel(self.busted, "busted backdrop", -.88, .88, -.215, .217, (.024, .04, .065, .95))
        _panel(self.busted, "busted stripe", -.88, .88, .209, .217, ARMOR)
        _wordmark(self.busted, "BUSTED", -.294, -.019, height=.112, color=ARMOR)
        self.busted_countdown = _text(self.busted, "", 0, -.111, .053, PAPER, self.sans,
                                      align=TextNode.A_center, mutable=True)

    def _build_dialogue(self):
        _panel(self.dialogue, "dialogue backdrop", -.580, .580, .250, .579, DARK)
        _panel(self.dialogue, "dialogue stripe", -.580, .580, .573, .579, MINT)
        self.dialogue_speaker = _text(self.dialogue, "", -.539, .505, .055, MINT, self.sans, mutable=True)
        self.dialogue_line = _text(self.dialogue, "", -.539, .430, .045, PAPER, self.sans, mutable=True, wrap=23)
        self.dialogue_exit = _text(self.dialogue, "E  CLOSE", .541, .283, .031, ORANGE, self.mono,
                                   align=TextNode.A_right, mutable=True)

        _panel(self.shop, "shop backdrop", -.872, .872, .250, 1.164, DARK)
        _panel(self.shop, "shop stripe", -.872, .872, 1.156, 1.164, ORANGE)
        self.shop_speaker = _text(self.shop, "", -.827, 1.080, .062, MINT, self.sans, mutable=True)
        self.shop_line = _text(self.shop, "", -.827, 1.005, .043, PAPER, self.sans, mutable=True, wrap=36)
        self.shop_fields = []
        for index in range(len(WEAPON_KEYS)):
            column, item_index = divmod(index, 6)
            left = -.827 + .849 * column
            z = .835 - item_index * .097
            row = self.shop.attach_new_node("shop item", 2)
            _panel(row, "shop item shade", left, left + .805, z - .026, z + .045, (.087, .145, .16, 1))
            _panel(row, "shop key backdrop", left, left + .067, z - .026, z + .045, (.056, .108, .125, 1))
            key = _text(row, "", left + .034, z, .041, ORANGE, self.mono,
                        align=TextNode.A_center, mutable=True)
            item = _text(row, "", left + .092, z, .044, PAPER, self.sans, mutable=True)
            price = _text(row, "", left + .780, z, .040, MINT, self.mono,
                          align=TextNode.A_right, mutable=True)
            self.shop_fields.append((row, key, item, price))
        _text(self.shop, "Choose an item key", -.827, .285, .039, PALE, self.sans)
        self.shop_exit = _text(self.shop, "E  CLOSE", .827, .285, .036, ORANGE, self.mono,
                               align=TextNode.A_right, mutable=True)

    def set_state(self, state):
        if state not in {"menu", "playing", "paused"}:
            raise ValueError(f"Unknown overlay state {state!r}")
        self.state = state
        self.help_visible = False
        self.panel = None
        self.set_rebinding()
        self._sync_visibility()

    def _sync_visibility(self):
        outcome = self.wasted_open or self.busted_open
        playing = self.state == "playing" and not outcome
        self.menu.show() if self.state == "menu" and not self.panel else self.menu.hide()
        self.paused.show() if self.state == "paused" and not self.panel else self.paused.hide()
        self.help.show() if self.help_visible and not outcome and not self.panel else self.help.hide()
        self.settings.show() if self.panel == "settings" else self.settings.hide()
        self.saves.show() if self.panel == "saves" else self.saves.hide()
        self.debug.show() if playing and self.debug_visible else self.debug.hide()
        for group in self.hud:
            group.show() if playing else group.hide()
        self.hud_bottom_right.show() if playing and self.driving else self.hud_bottom_right.hide()
        self._sync_combat_visibility()

    def _sync_combat_visibility(self):
        playing = self.state == "playing" and not (self.wasted_open or self.busted_open)
        engaging = playing and not self.dialogue_open and not self.help_visible and not self.driving
        conversation = playing and not self.help_visible and self.dialogue_open
        self.combat_hud.show() if engaging and self.armed else self.combat_hud.hide()
        self.reticle.show() if engaging and self.aiming else self.reticle.hide()
        self.hit_marker.show() if engaging and self.hit_time > 0 else self.hit_marker.hide()
        self.dialogue.show() if conversation and not self.shop_open else self.dialogue.hide()
        self.shop.show() if conversation and self.shop_open else self.shop.hide()
        self.wasted.show() if self.state == "playing" and self.wasted_open else self.wasted.hide()
        self.busted.show() if self.state == "playing" and self.busted_open else self.busted.hide()

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

    def flash_hit(self, killed=False):
        self.hit_time = .25 if killed else .16
        for bar in self.hit_bars:
            bar.set_color(*(ORANGE if killed else PAPER))
        self._sync_combat_visibility()

    def show_dialogue(self, speaker, line, *, shop=()):
        rows = tuple(shop)
        self.dialogue_open = True
        self.shop_open = bool(rows)
        if self.shop_open:
            _set_text(self.shop_speaker, speaker)
            _set_text(self.shop_line, line)
            for index, (row, key, item, price) in enumerate(self.shop_fields):
                if index < len(rows):
                    for label, value in zip((key, item, price), rows[index]):
                        _set_text(label, str(value))
                    price_width = max(price.textNode.get_width(), 1)
                    price_scale = min(.040, .203 / price_width)
                    price.setTextScale(price_scale)
                    available = .658 - price_width * price_scale
                    item.setTextScale(min(.044, available / max(item.textNode.get_width(), 1)))
                    row.show()
                else:
                    row.hide()
        else:
            _set_text(self.dialogue_speaker, speaker)
            _set_text(self.dialogue_line, line)
        self._sync_combat_visibility()

    def hide_dialogue(self):
        self.dialogue_open = False
        self.shop_open = False
        self._sync_combat_visibility()

    def show_wasted(self, seconds):
        _set_text(self.wasted_countdown, f"Hospital respawn in {max(0, math.ceil(seconds))} s")
        if not self.wasted_open:
            self.wasted_open = True
            self.busted_open = False
            self.help_visible = False
            self.hit_time = 0.0
            self.hide_dialogue()
            self._sync_visibility()

    def hide_wasted(self):
        if self.wasted_open:
            self.wasted_open = False
            self._sync_visibility()

    def show_busted(self, seconds):
        _set_text(self.busted_countdown, f"Release in {max(0, math.ceil(seconds))} s")
        if not self.busted_open:
            self.busted_open = True
            self.wasted_open = False
            self.help_visible = False
            self.hit_time = 0.0
            self.hide_dialogue()
            self._sync_visibility()

    def hide_busted(self):
        if self.busted_open:
            self.busted_open = False
            self._sync_visibility()

    def _update_route(self, left, bottom, gps_route):
        points = tuple((float(point[0]), float(point[1])) for point in gps_route)
        old_left, old_bottom = self.route_corner
        if points == self.route_points and max(abs(left - old_left), abs(bottom - old_bottom)) < .0015:
            return
        self.route_points = points
        self.route_corner = left, bottom
        self.route_layer.node().remove_all_geoms()
        if len(points) < 2:
            return
        extent = NORTH * 2
        scale = MAP_SIZE / self.map_zoom
        projected = [(((x + NORTH) / extent - left) * scale, ((y + NORTH) / extent - bottom) * scale)
                     for x, y in points]
        line = LineSegs("gps route")
        line.set_thickness(2.5)
        line.set_color(*MINT)
        for start, end in zip(projected, projected[1:]):
            clip = _clip_minimap_segment(*start, *end)
            if clip:
                x0, z0, x1, z1 = clip
                line.move_to(x0, 0, z0)
                line.draw_to(x1, 0, z1)
        line.create(self.route_layer.node())

    def _update_minimap(self, position, heading, waypoint, gps_route=()):
        extent = NORTH * 2
        u = (float(position[0]) + NORTH) / extent
        v = (float(position[1]) + NORTH) / extent
        half_map = self.map_zoom / 2
        left = min(1 - self.map_zoom, max(0, u - half_map))
        bottom = min(1 - self.map_zoom, max(0, v - half_map))
        self.map_image.set_tex_offset(self.map_stage, left, bottom)
        self._update_route(left, bottom, () if gps_route is None else gps_route)
        margin = .018
        self.map_arrow.set_pos(
            min(MAP_SIZE - margin, max(margin, (u - left) * MAP_SIZE / self.map_zoom)), 0,
            min(MAP_SIZE - margin, max(margin, (v - bottom) * MAP_SIZE / self.map_zoom)),
        )
        self.map_arrow.set_r(-heading)
        if waypoint is None:
            self.map_waypoint.hide()
            return
        target_u = (float(waypoint[0]) + NORTH) / extent
        target_v = (float(waypoint[1]) + NORTH) / extent
        self.map_waypoint.set_pos(
            min(MAP_SIZE - margin, max(margin, (target_u - left) * MAP_SIZE / self.map_zoom)), 0,
            min(MAP_SIZE - margin, max(margin, (target_v - bottom) * MAP_SIZE / self.map_zoom)),
        )
        self.map_waypoint.show()

    def update(self, dt, *, district="", position=(0, 0, 0), heading=0, speed=0,
               rpm=0, gear="", health=100, money=0, hour=17, context="", fps=0,
               debug_info="", driving=False, car_health=100, armor=0, weapon="",
               weapon_slot=None, ammo=None, reserve=None, reloading=False, aiming=False, objective="", waypoint=None,
               wanted=0, wanted_status="", gps_route=()):
        if self.state != "playing":
            return
        _set_text(self.district, district or "Harbor City")
        minutes = int(hour * 60) % 1440
        _set_text(self.time, f"{minutes // 60:02}:{minutes % 60:02}")
        _set_text(self.money, f"${money:,.0f}")
        _set_text(self.health_text, f"{max(0, min(100, health)):0.0f}")
        self.health_bar.set_sx(max(.001, min(1, health / 100)))
        _set_text(self.armor_text, f"{max(0, min(100, armor)):0.0f}")
        self.armor_bar.set_sx(max(.001, min(1, armor / 100)))
        self._update_minimap(position, heading, waypoint, gps_route)
        _set_text(self.objective, objective)
        self.objective_group.show() if objective else self.objective_group.hide()
        if wanted > 0:
            for index, star in enumerate(self.wanted_stars):
                star.set_color(*(ORANGE if index < wanted else (.33, .35, .34, 1)))
            _set_text(self.wanted_message, wanted_status)
            self.wanted_group.show()
        else:
            self.wanted_group.hide()

        self.driving = driving
        if driving and not (self.wasted_open or self.busted_open):
            self.hud_bottom_right.show()
            _set_text(self.speed, f"{min(999, abs(speed)):03.0f}")
            _set_text(self.gear, "R" if gear == -1 else str(gear))
            _set_text(self.car_health, f"CAR {car_health:.0f}%")
            self.rev_bar.set_sx(max(.002, min(1, rpm / 7000)))
            self.rev_fill.set_color(*(ORANGE if rpm > 5750 else MINT))
        else:
            self.hud_bottom_right.hide()

        self.aiming = aiming
        self.armed = bool(weapon)
        if self.armed and not driving:
            if self.weapon_name.text != weapon:
                _set_text(self.weapon_name, weapon)
                self.weapon_name.setTextScale(min(.042, .332 / max(self.weapon_name.textNode.get_width(), 1)))
            hotkey = WEAPON_KEYS.get(weapon_slot, "")
            _set_text(self.weapon_key, hotkey)
            self.weapon_hotkey.show() if hotkey else self.weapon_hotkey.hide()
            ammunition = "" if ammo is None else str(ammo) if reserve is None else f"{ammo} / {reserve}"
            _set_text(self.ammo_text, ammunition)
            if ammo is None:
                status = f"{self.fire_key}  ATTACK"
            elif reloading:
                status = "RELOADING"
            elif ammo == 0:
                status = f"{self.reload_key}  RELOAD" if reserve else "OUT OF AMMO"
            else:
                status = ""
            _set_text(self.ammo_status, status)
        if self.hit_time > 0:
            self.hit_time = max(0, self.hit_time - dt)
        self._sync_combat_visibility()

        if context and not self.dialogue_open:
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

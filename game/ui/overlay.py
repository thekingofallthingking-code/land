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
ARMOR = (0.49, 0.76, 1.00, 1)
DARK = (0.035, 0.08, 0.10, 0.94)
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

    def __init__(self, base, on_play, on_resume, on_quit, minimap_path):
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
        self.aiming = False
        self.armed = False
        self.driving = False

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
                ("WASD", "Move"), ("MOUSE", "Look"), ("SHIFT", "Sprint"), ("SPACE", "Jump"),
                ("F", "Enter / Steal vehicle"), ("E", "Talk / Shop"),
            )),
            (-.207, "DRIVING", (
                ("W / S", "Accelerate / Reverse"), ("A / D", "Steer"), ("SPACE", "Handbrake"),
                ("C", "Change camera"), ("F", "Exit vehicle"),
            )),
            (.327, "COMBAT", (
                ("RMB", "Aim"), ("LMB", "Attack"), ("R", "Reload"), ("1-5", "Select weapon"),
            )),
        )
        for x, heading, controls in columns:
            _text(self.help, heading, x, .428, .037, MINT, self.mono)
            for index, (key, action) in enumerate(controls):
                z = .344 - index * .073
                _text(self.help, key, x, z, .034, PAPER, self.mono)
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

    def _build_combat(self):
        parent = self.combat_hud
        _panel(parent, "weapon backdrop", -.500, -.048, .048, .271, DARK)
        _panel(parent, "weapon stripe", -.500, -.048, .266, .271, ORANGE)
        self.weapon_name = _text(parent, "", -.459, .213, .042, PAPER, self.sans, mutable=True)
        _text(parent, "1-5", -.074, .214, .032, MINT, self.mono, align=TextNode.A_right)
        self.ammo_text = _text(parent, "", -.459, .101, .082, PAPER, self.mono, mutable=True)
        self.ammo_status = _text(parent, "", -.074, .168, .030, ORANGE, self.mono,
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

    def _build_dialogue(self):
        _panel(self.dialogue, "dialogue backdrop", -.580, .580, .250, .579, DARK)
        _panel(self.dialogue, "dialogue stripe", -.580, .580, .573, .579, MINT)
        self.dialogue_speaker = _text(self.dialogue, "", -.539, .505, .055, MINT, self.sans, mutable=True)
        self.dialogue_line = _text(self.dialogue, "", -.539, .430, .045, PAPER, self.sans, mutable=True, wrap=23)
        _text(self.dialogue, "E  CLOSE", .541, .283, .031, ORANGE, self.mono, align=TextNode.A_right)

        _panel(self.shop, "shop backdrop", -.606, .606, .250, 1.011, DARK)
        _panel(self.shop, "shop stripe", -.606, .606, 1.003, 1.011, ORANGE)
        self.shop_speaker = _text(self.shop, "", -.564, .927, .060, MINT, self.sans, mutable=True)
        self.shop_line = _text(self.shop, "", -.564, .852, .041, PAPER, self.sans, mutable=True, wrap=27)
        self.shop_fields = []
        for index in range(5):
            z = .678 - index * .073
            row = self.shop.attach_new_node("shop item", 2)
            _panel(row, "shop item shade", -.565, .565, z - .021, z + .035, (.087, .145, .16, 1))
            key = _text(row, "", -.540, z, .038, ORANGE, self.mono, mutable=True)
            item = _text(row, "", -.472, z, .041, PAPER, self.sans, mutable=True)
            price = _text(row, "", .540, z, .036, MINT, self.mono, align=TextNode.A_right, mutable=True)
            self.shop_fields.append((row, key, item, price))
        _text(self.shop, "1-5  BUY", -.562, .277, .031, PALE, self.mono)
        _text(self.shop, "E  CLOSE", .562, .277, .031, ORANGE, self.mono, align=TextNode.A_right)

    def set_state(self, state):
        if state not in {"menu", "playing", "paused"}:
            raise ValueError(f"Unknown overlay state {state!r}")
        self.state = state
        self.help_visible = False
        self._sync_visibility()

    def _sync_visibility(self):
        playing = self.state == "playing" and not self.wasted_open
        self.menu.show() if self.state == "menu" else self.menu.hide()
        self.paused.show() if self.state == "paused" else self.paused.hide()
        self.help.show() if self.help_visible and not self.wasted_open else self.help.hide()
        self.debug.show() if playing and self.debug_visible else self.debug.hide()
        for group in self.hud:
            group.show() if playing else group.hide()
        self.hud_bottom_right.show() if playing and self.driving else self.hud_bottom_right.hide()
        self._sync_combat_visibility()

    def _sync_combat_visibility(self):
        playing = self.state == "playing" and not self.wasted_open
        engaging = playing and not self.dialogue_open and not self.help_visible and not self.driving
        conversation = playing and not self.help_visible and self.dialogue_open
        self.combat_hud.show() if engaging and self.armed else self.combat_hud.hide()
        self.reticle.show() if engaging and self.aiming else self.reticle.hide()
        self.hit_marker.show() if engaging and self.hit_time > 0 else self.hit_marker.hide()
        self.dialogue.show() if conversation and not self.shop_open else self.dialogue.hide()
        self.shop.show() if conversation and self.shop_open else self.shop.hide()
        self.wasted.show() if self.state == "playing" and self.wasted_open else self.wasted.hide()

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
            self.help_visible = False
            self.hit_time = 0.0
            self.hide_dialogue()
            self._sync_visibility()

    def hide_wasted(self):
        if self.wasted_open:
            self.wasted_open = False
            self._sync_visibility()

    def _update_minimap(self, position, heading, waypoint):
        extent = NORTH * 2
        u = (float(position[0]) + NORTH) / extent
        v = (float(position[1]) + NORTH) / extent
        half_map = self.map_zoom / 2
        left = min(1 - self.map_zoom, max(0, u - half_map))
        bottom = min(1 - self.map_zoom, max(0, v - half_map))
        self.map_image.set_tex_offset(self.map_stage, left, bottom)
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
               ammo=None, reserve=None, reloading=False, aiming=False, objective="", waypoint=None):
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
        self._update_minimap(position, heading, waypoint)
        _set_text(self.objective, objective)
        self.objective_group.show() if objective else self.objective_group.hide()

        self.driving = driving
        if driving and not self.wasted_open:
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
            _set_text(self.weapon_name, weapon)
            ammunition = "" if ammo is None else str(ammo) if reserve is None else f"{ammo} / {reserve}"
            _set_text(self.ammo_text, ammunition)
            if ammo is None:
                status = "LMB  ATTACK"
            elif reloading:
                status = "RELOADING"
            elif ammo == 0:
                status = "R  RELOAD" if reserve else "OUT OF AMMO"
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

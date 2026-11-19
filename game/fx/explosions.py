"""Pooled sprites, shock rings, fragments and scorched surfaces."""
from collections import deque
from dataclasses import dataclass
from math import atan2, cos, hypot, sin, tau
from random import Random

from panda3d.core import Filename
from panda3d.core import BitMask32, CardMaker, NodePath, PNMImage, Point3, Texture, TransparencyAttrib, Vec3

from game.tools.assets import ASSET_DIR
from game.world.mesh import Mesh


def _card(name, *, billboard):
    rng = Random(6410)
    edge = 48
    image = PNMImage(edge, edge, 4)
    for y in range(edge):
        for x in range(edge):
            u, v = (x + .5) / edge * 2 - 1, (y + .5) / edge * 2 - 1
            angle = atan2(v, u)
            radius = hypot(u, v) + .082 * sin(angle * 5) + .071 * sin(angle * 9 + .6)
            shade = max(0.0, 1.0 - radius * radius)
            grain = rng.uniform(.80, 1)
            if name == "flame":
                red, green, blue = 1.0, .075 + .89 * shade**2.6, .012 + .53 * shade**6
                alpha = min(.94, max(0, shade - .12) * 1.52) * grain
            else:
                value = (.043 + .083 * grain) if name == "smoke" else (.030 + .065 * grain)
                red, green, blue = value * 1.08, value, value * .91
                alpha = shade**1.6 * grain * (.54 if name == "smoke" else .77)
            image.set_xel_a(x, y, red, green, blue, alpha)
    texture = Texture(name)
    texture.load(image)
    texture.set_wrap_u(Texture.WM_clamp)
    texture.set_wrap_v(Texture.WM_clamp)
    texture.set_magfilter(Texture.FT_linear)
    texture.set_minfilter(Texture.FT_linear)
    card = CardMaker(name)
    card.set_frame(-1, 1, -1, 1)
    art = NodePath(card.generate())
    art.set_texture(texture)
    if billboard:
        art.set_billboard_point_eye()
    return art


def _shock_ring():
    mesh = Mesh("shockwave ring")
    for index in range(40):
        a, b = tau * index / 40, tau * (index + 1) / 40
        for inner, outer, color in (
            (.91, .97, (1, .49, .17, .28)),
            (.97, 1.0, (1, .91, .58, .78)),
            (1.0, 1.04, (.89, .83, .65, .26)),
        ):
            mesh.face(((cos(a) * inner, sin(a) * inner, 0), (cos(a) * outer, sin(a) * outer, 0),
                       (cos(b) * outer, sin(b) * outer, 0), (cos(b) * inner, sin(b) * inner, 0)),
                      color, (0, 0, 1))
    return mesh.node()


def _fragment():
    mesh = Mesh("torn debris")
    mesh.box((0, 0, 0), (.34, .11, .19), (.29, .22, .16), bottom=True)
    mesh.box((.067, -.065, .035), (.15, .06, .088), (.49, .32, .16), bottom=True)
    return mesh.node()


def projectile_art(kind):
    mesh = Mesh(kind)
    if kind == "grenade":
        mesh.cone(0, 0, -.06, .14, .081, .058, (.39, .52, .32), 8)
        mesh.box((0, 0, .09), (.063, .065, .034), (.67, .64, .37), bottom=True)
    else:
        mesh.box((0, -.14, 0), (.076, .26, .075), (.62, .68, .54), bottom=True)
        mesh.box((0, -.27, 0), (.15, .09, .028), (.22, .28, .23), bottom=True)
        mesh.box((0, -.27, 0), (.028, .09, .15), (.24, .29, .23), bottom=True)
        mesh.box((0, .016, 0), (.05, .069, .054), (.83, .31, .17), bottom=True)
    return mesh.node()


@dataclass(slots=True)
class _Particle:
    node: NodePath
    time: float = 0.0
    duration: float = 1.0
    velocity: Vec3 | None = None
    floor: float | None = None
    gravity: float = 0.0
    scale: float = 1.0
    growth: float = 0.0
    brightness: float = 1.0
    fade: float = 1.0


class _Pool:
    def __init__(self, parent, template, count):
        self.ready = deque()
        self.active = deque()
        for idx in range(count):
            node = parent.attach_new_node(f"{template.get_name()} {idx}")
            template.instance_to(node)
            node.hide()
            self.ready.append(_Particle(node))

    def emit(self, point, duration, scale, growth=0.0, *, velocity=None, gravity=0.0,
             floor=None, brightness=1.0, fade=None):
        particle = self.ready.popleft() if self.ready else self.active.popleft()
        particle.time, particle.duration = 0.0, duration
        particle.velocity, particle.gravity, particle.floor = velocity, gravity, floor
        particle.scale, particle.growth, particle.brightness = scale, growth, brightness
        particle.fade = duration if fade is None else fade
        particle.node.set_pos(point)
        particle.node.set_hpr(0, 0, 0)
        particle.node.set_scale(scale)
        particle.node.set_color_scale(brightness, brightness, brightness, 1)
        particle.node.show()
        self.active.append(particle)
        return particle.node

    def update(self, dt):
        for _ in range(len(self.active)):
            particle = self.active.popleft()
            particle.time += dt
            if particle.time >= particle.duration:
                particle.node.hide()
                self.ready.append(particle)
                continue
            self.active.append(particle)
            if particle.velocity is not None:
                position = particle.node.get_pos() + particle.velocity * dt
                particle.velocity.z -= particle.gravity * dt
                if particle.floor is not None:
                    if position.z < particle.floor:
                        position.z = particle.floor
                        particle.velocity *= .53
                        particle.velocity.z = abs(particle.velocity.z)
                    particle.node.set_hpr(particle.node.get_hpr() + Vec3(168, 126, -201) * dt)
                particle.node.set_pos(position)
            if particle.growth:
                particle.node.set_scale(particle.scale + particle.growth * (particle.time / particle.duration))
            remaining = particle.duration - particle.time
            if remaining < particle.fade:
                brightness = particle.brightness
                particle.node.set_color_scale(brightness, brightness, brightness, remaining / particle.fade)

    def clear(self):
        while self.active:
            particle = self.active.popleft()
            particle.node.hide()
            self.ready.append(particle)


class BlastEffects:
    def __init__(self, render, limits, audio_loader, camera):
        self._random = Random(50781)
        self._render = render
        self.root = render.attach_new_node("blast effects")
        self.root.set_light_off()
        self.root.set_shader_off()
        self.root.set_depth_write(False)
        self.root.set_two_sided(True)
        self.root.set_transparency(TransparencyAttrib.M_alpha)
        self.root.hide(BitMask32.bit(1))
        self.fire = _Pool(self.root, _card("flame", billboard=True), limits["fire"])
        self.smoke = _Pool(self.root, _card("smoke", billboard=True), limits["smoke"])
        self.debris = _Pool(self.root, _fragment(), limits["debris"])
        self.rings = _Pool(self.root, _shock_ring(), limits["rings"])
        self.scorch = _Pool(self.root, _card("scorch", billboard=False), limits["scorch"])
        self._pools = (self.fire, self.smoke, self.debris, self.rings, self.scorch)
        self._camera = camera
        self._sounds = []
        self._sound_slot = 0
        if audio_loader is not None and (ASSET_DIR / "blast.wav").is_file():
            for _ in range(5):
                sound = audio_loader.load_sfx(Filename.from_os_specific(str(ASSET_DIR / "blast.wav")))
                if sound is not None:
                    self._sounds.append((sound, Vec3(), 0.0))

    def burst(self, position, ground, size, radius):
        rng = self._random
        self.fire.emit(position, .60, size * .32, size * .88, velocity=Vec3(0, 0, 1.2), brightness=2.7)
        for _ in range(4 if len(self.fire.ready) < 18 else 6):
            x, y, z = rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(.05, 1.1)
            start = position + Vec3(x, y, z) * size * .41
            self.fire.emit(start, rng.uniform(.31, .69), size * .19, size * .61,
                           velocity=Vec3(x, y, z * 2.8) * 2.6, brightness=rng.uniform(1.6, 2.5))
        for index in range(4):
            self.smoke.emit(position + Vec3(rng.uniform(-1, 1), rng.uniform(-1, 1), index * .67),
                            rng.uniform(2.8, 4.7), size * (.24 + index * .05), size * .64,
                            velocity=Vec3(rng.uniform(-.65, .65), rng.uniform(-.65, .65), 1.3 + .5 * index),
                            fade=2.1)
        floor = ground.z if ground is not None else position.z - .9
        for _ in range(min(13, max(6, len(self.debris.ready) // 2))):
            drift = Vec3(rng.uniform(-8.0, 8.0), rng.uniform(-8.0, 8.0), rng.uniform(4.5, 11.0))
            self.debris.emit(position, rng.uniform(.85, 2.30), rng.uniform(.52, 1.50),
                             velocity=drift, gravity=15.5, floor=floor, fade=.45)
        if ground is not None:
            flat = ground + Vec3(0, 0, .027)
            self.rings.emit(flat, .56, .4, radius * 1.25, brightness=1.5)
            node = self.scorch.emit(flat, 65.0, size * .91, fade=9.0)
            node.look_at(Point3(flat + Vec3(0, 0, 1)), Vec3(0, 1, 0))
            node.set_r(rng.uniform(-180, 180))
            node.set_depth_offset(1)
        self._play(position, size)

    def fumes(self, position, burning=False):
        rng = self._random
        movement = Vec3(rng.uniform(-.3, .55), rng.uniform(-.27, .24), rng.uniform(.80, 1.47))
        self.smoke.emit(position, rng.uniform(1.4, 2.7), .34, rng.uniform(.5, 1.08),
                        velocity=movement, fade=1.6)
        if burning:
            self.fire.emit(position, .34, .28, .48, velocity=movement * 2.1, brightness=1.63)

    def exhaust(self, position):
        self.fire.emit(position, .12, .10, .16, brightness=1.5)
        self.smoke.emit(position, .45, .12, .29, fade=.38)

    def _play(self, position, size):
        if not self._sounds:
            return
        index = self._sound_slot
        self._sound_slot = (index + 1) % len(self._sounds)
        sound, _, _ = self._sounds[index]
        gain = min(1.0, .64 + size * .085)
        self._sounds[index] = sound, Vec3(position), gain
        self._locate_sound(sound, position, gain)
        sound.set_play_rate(self._random.uniform(.89, 1.09))
        sound.stop()
        sound.play()

    def _locate_sound(self, sound, position, gain):
        if self._camera is None:
            sound.set_volume(gain)
            return
        relative = self._camera.get_relative_point(self._render, Point3(position))
        distance = relative.length()
        sound.set_volume(gain / (1 + (distance / 23) ** 1.5))
        sound.set_balance(max(-.96, min(.96, relative.x / max(4.0, distance))))

    def update(self, dt):
        for pool in self._pools:
            pool.update(dt)
        for sound, position, gain in self._sounds:
            if sound.status() == sound.PLAYING:
                self._locate_sound(sound, position, gain)

    def clear(self):
        for pool in self._pools:
            pool.clear()
        for sound, _, _ in self._sounds:
            sound.stop()

    def close(self):
        self.clear()
        self.root.remove_node()

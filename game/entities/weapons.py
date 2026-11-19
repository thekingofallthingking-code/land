"""Data-driven arcade inventory, aiming, hits and weapon presentation."""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, radians, sin, sqrt, tan, tau
import json
from pathlib import Path
from random import Random

from panda3d.bullet import BulletRigidBodyNode
from panda3d.core import BitMask32, PandaNode, Point3, Vec3

from game.fx.combat import CombatEffects
from game.tools.assets import ASSET_DIR
from game.world.mesh import Mesh

_ROOT = Path(__file__).resolve().parents[2]
_WORLD_MASK = BitMask32.bit(0)
_UP = Vec3(0, 0, 1)


@dataclass(frozen=True)
class WeaponSpec:
    id: str
    slot: int
    name: str
    damage: float
    range_meters: float
    rounds_per_second: float
    recoil_degrees: float
    capacity: int = 0
    starter_reserve: int = 0
    reserve_limit: int = 0
    reload_seconds: float = 0.0
    spread_degrees: float = 0.0
    head_multiplier: float = 1.0
    pellets: int = 1
    automatic: bool = False
    starting: bool = False


_SPECS = tuple(WeaponSpec(**spec) for spec in json.loads(
    (_ROOT / "game/data/weapons.json").read_text(encoding="utf-8")
)["weapons"])
WEAPON_SPECS = {spec.id: spec for spec in _SPECS}
_SLOTS = {spec.slot: spec for spec in _SPECS}


@dataclass
class _Supply:
    magazine: int
    reserve: int


@dataclass(frozen=True)
class HitTarget:
    entity: object
    body: PandaNode


@dataclass(frozen=True)
class ShotResult:
    recoil: float
    hit: bool
    headshot: bool
    target: object | None


@dataclass(frozen=True)
class _Contact:
    position: Vec3
    normal: Vec3
    distance: float
    target: object | None
    headshot: bool = False
    soft: bool = False
    scenery: bool = False


class _CombatAudio:
    def __init__(self, render, loader):
        self._loader = loader
        self._root = render.attach_new_node("weapon audio")
        self._sounds = {}
        self._indices = {}
        self._volume = {
            "pistol": .56, "smg": .47, "shotgun": .73, "rifle": .58,
            "melee": .51, "dry": .36, "reload": .36,
        }
        if loader is None:
            return
        attach = getattr(loader, "attachSoundToObject", None)
        for key in self._volume:
            path = ASSET_DIR / f"weapon-{key}.wav"
            if not path.is_file():
                continue
            pool = []
            for _ in range(3 if key in ("pistol", "smg", "rifle") else 1):
                sound = loader.loadSfx(str(path))
                if sound is None:
                    continue
                location = self._root.attach_new_node(key)
                if attach is not None:
                    attach(sound, location)
                pool.append((sound, location))
            if pool:
                self._sounds[key] = pool
                self._indices[key] = 0

    def play(self, key, position=None, *, gain=1.0, pitch=1.0):
        pool = self._sounds.get(key)
        if not pool:
            return
        index = self._indices[key]
        self._indices[key] = (index + 1) % len(pool)
        sound, location = pool[index]
        if position is not None:
            location.set_pos(position)
        sound.stop()
        sound.set_volume(self._volume[key] * gain)
        sound.set_play_rate(pitch)
        sound.play()

    def close(self):
        detach = getattr(self._loader, "detachSound", None)
        for pool in self._sounds.values():
            for sound, _ in pool:
                sound.stop()
                if detach is not None:
                    detach(sound)
        self._root.remove_node()


class WeaponSystem:
    def __init__(self, render, physics, events, *, audio_loader=None, seed=86317):
        self.physics = physics
        self.events = events
        self.effects = CombatEffects(render, seed + 1)
        self._audio = _CombatAudio(render, audio_loader)
        self._random = Random(seed)
        self._pitch = Random(seed + 2)
        self._inventory = self._starting_inventory()
        self.selected = WEAPON_SPECS["pistol"]
        self.cooldown = 0.0
        self.reload_remaining = 0.0

    @staticmethod
    def _starting_inventory():
        return {spec.id: _Supply(spec.capacity, spec.starter_reserve)
                for spec in _SPECS if spec.starting}

    @property
    def ammo(self) -> tuple[int, int]:
        supply = self._inventory[self.selected.id]
        return supply.magazine, supply.reserve

    def owns(self, weapon_id: str) -> bool:
        return weapon_id in self._inventory

    def grant_weapon(self, weapon_id: str, reserve_rounds: int | None = None) -> bool:
        spec = WEAPON_SPECS.get(weapon_id)
        if spec is None or self.owns(weapon_id):
            return False
        reserve = spec.starter_reserve if reserve_rounds is None else max(0, reserve_rounds)
        self._inventory[weapon_id] = _Supply(spec.capacity, min(spec.reserve_limit, reserve))
        return True

    def add_ammo(self, weapon_id: str, rounds: int) -> int:
        supply = self._inventory.get(weapon_id)
        if supply is None or rounds <= 0:
            return 0
        added = min(rounds, WEAPON_SPECS[weapon_id].reserve_limit - supply.reserve)
        supply.reserve += added
        return added

    def select(self, slot: int) -> bool:
        spec = _SLOTS.get(slot)
        if spec is None or not self.owns(spec.id):
            return False
        if spec is not self.selected:
            self.selected = spec
            self.reload_remaining = 0.0
        return True

    def reload(self) -> bool:
        magazine, reserve = self.ammo
        if self.reload_remaining > 0 or magazine >= self.selected.capacity or not reserve:
            return False
        self.reload_remaining = self.selected.reload_seconds
        self._audio.play("reload")
        return True

    def update(self, dt: float) -> None:
        if not isfinite(dt) or dt <= 0:
            return
        self.cooldown = max(0.0, self.cooldown - dt)
        if self.reload_remaining > 0:
            self.reload_remaining = max(0.0, self.reload_remaining - dt)
            if self.reload_remaining == 0:
                supply = self._inventory[self.selected.id]
                rounds = min(self.selected.capacity - supply.magazine, supply.reserve)
                supply.magazine += rounds
                supply.reserve -= rounds
        self.effects.update(dt)

    def snapshot(self) -> dict:
        return {
            "selected": self.selected.id,
            "inventory": {weapon_id: {"magazine": supply.magazine, "reserve": supply.reserve}
                          for weapon_id, supply in self._inventory.items()},
        }

    def restore(self, data: object) -> None:
        self._inventory = self._starting_inventory()
        self.selected = WEAPON_SPECS["pistol"]
        self.cooldown = self.reload_remaining = 0.0
        self.effects.clear()
        if not isinstance(data, dict) or not isinstance(data.get("inventory"), dict):
            return
        for weapon_id, supply in data["inventory"].items():
            spec = WEAPON_SPECS.get(weapon_id)
            if spec is None or not isinstance(supply, dict):
                continue
            magazine, reserve = supply.get("magazine"), supply.get("reserve")
            if type(magazine) is int and type(reserve) is int:
                self._inventory[weapon_id] = _Supply(
                    min(spec.capacity, max(0, magazine)), min(spec.reserve_limit, max(0, reserve)))
        selected = data.get("selected")
        if isinstance(selected, str) and self.owns(selected):
            self.selected = WEAPON_SPECS[selected]

    def _obstacle(self, origin, end, ignore, targets):
        delta = end - origin
        span = delta.length()
        if span < 1e-5:
            return None
        query = self.physics.ray_test_closest(Point3(origin), Point3(end), _WORLD_MASK)
        if not query.has_hit():
            return None
        if query.get_node() in ignore:
            query = self.physics.ray_test_all(Point3(origin), Point3(end), _WORLD_MASK)
            candidates = (hit for hit in query.get_hits() if hit.get_node() not in ignore)
            query = min(candidates, key=lambda hit: hit.get_hit_fraction(), default=None)
            if query is None:
                return None
        body = query.get_node()
        return _Contact(query.get_hit_pos(), query.get_hit_normal(), span * query.get_hit_fraction(),
                        targets.get(body), scenery=isinstance(body, BulletRigidBodyNode) and body.is_static())

    def _trace(self, origin, direction, distance, ignore, targets, people):
        end = origin + direction * distance
        contact = self._obstacle(origin, end, ignore, targets)
        if people is not None:
            hit = people.raycast(origin, direction, contact.distance if contact else distance)
            if hit is not None:
                contact = _Contact(hit.position, hit.normal, hit.distance, hit.person, hit.headshot, soft=True)
        return contact

    def _melee_contact(self, origin, direction, spec, ignore, targets, people):
        end = origin + direction * spec.range_meters
        contact = self._obstacle(origin, end, ignore, targets)
        if people is not None:
            hit = people.melee_target(origin, direction, spec.range_meters)
            if hit is not None:
                wall = self._obstacle(origin, hit.position, ignore, targets)
                if wall is None and (contact is None or hit.distance <= contact.distance + .05):
                    contact = _Contact(hit.position, hit.normal, hit.distance, hit.person, soft=True)
        return contact

    def _directions(self, forward, aimed, spec):
        spread = tan(radians(spec.spread_degrees * (.48 if aimed else 1.0)))
        right = forward.cross(_UP)
        if right.length_squared() < 1e-8:
            right = Vec3(1, 0, 0)
        right.normalize()
        up = right.cross(forward)
        for index in range(spec.pellets):
            if spec.pellets > 1 and index == 0:
                yield forward  # Anchor the shot pattern to the crosshair.
                continue
            angle = self._random.random() * tau
            radius = spread * sqrt(self._random.random())
            direction = forward + (right * cos(angle) + up * sin(angle)) * radius
            direction.normalize()
            yield direction

    def fire(self, origin, direction, *, aimed=False, pressed=False,
             targets=(), ignore=(), owner=None, people=None, muzzle=None) -> ShotResult | None:
        """Use the aim ray to target the crosshair, then fire from the muzzle."""
        spec = self.selected
        if self.reload_remaining > 0 or self.cooldown > 1e-8 or (not pressed and not spec.automatic):
            return None
        origin, direction = Vec3(origin), Vec3(direction)
        start = Vec3(muzzle) if muzzle is not None else origin
        if not all(isfinite(part) for vector in (origin, direction, start) for part in vector):
            return None
        if direction.length_squared() < 1e-8:
            return None
        direction.normalize()
        melee = spec.id == "melee"
        supply = self._inventory[spec.id]
        if not melee and supply.magazine == 0:
            if not self.reload() and pressed:
                self._audio.play("dry", origin)
            return None

        self.cooldown = 1 / spec.rounds_per_second
        mapping = {target.body: target.entity for target in targets}
        if melee:
            self.events.publish("melee", position=origin, direction=direction, weapon=spec.id, owner=owner)
            self._audio.play("melee", origin)
            contact = self._melee_contact(origin, direction, spec, ignore, mapping, people)
            if contact is None:
                return ShotResult(spec.recoil_degrees, False, False, None)
            if contact.target is not None:
                self._publish_hit(contact, spec.damage, direction, spec.id, owner)
            self.effects.impact(contact.position, contact.normal, soft=contact.soft)
            return ShotResult(spec.recoil_degrees, contact.target is not None, False, contact.target)

        supply.magazine -= 1
        near_wall = self._obstacle(origin, start, ignore, mapping) if muzzle is not None else None
        if near_wall:
            start = origin
        elif muzzle is not None:
            crosshair = self._trace(origin, direction, spec.range_meters, ignore, mapping, people)
            focus = crosshair.position if crosshair else origin + direction * spec.range_meters
            convergence = Vec3(focus - start)
            if convergence.dot(direction) > .12:
                direction = convergence.normalized()
        self.events.publish("gunshot", position=start, direction=direction, weapon=spec.id, owner=owner)
        self._audio.play(spec.id, start, pitch=self._pitch.uniform(.96, 1.04))
        self.effects.flash(start, direction, scale=1.42 if spec.id == "shotgun" else 1)
        hits = {}
        for index, ray in enumerate(self._directions(direction, aimed, spec)):
            contact = near_wall or self._trace(start, ray, spec.range_meters, ignore, mapping, people)
            end = contact.position if contact else start + ray * spec.range_meters
            if index < 4 and (not near_wall or index == 0):
                self.effects.tracer(start, end)
                if contact is not None:
                    self.effects.impact(end, contact.normal, soft=contact.soft)
                    if contact.scenery:
                        self.effects.bullet_hole(end, contact.normal, scale=.78 if spec.pellets > 1 else 1.0)
            if contact is not None and contact.target is not None:
                damage = spec.damage * (spec.head_multiplier if contact.headshot else 1.0)
                key = id(contact.target)
                total, representative, path = hits.get(key, (0.0, contact, ray))
                if contact.headshot and not representative.headshot:
                    representative, path = contact, ray
                hits[key] = (total + damage, representative, path)
            if near_wall:
                break
        for total, contact, ray in hits.values():
            self._publish_hit(contact, total, ray, spec.id, owner)
        headshot = any(contact.headshot for _, contact, _ in hits.values())
        main = max(hits.values(), key=lambda hit: hit[0], default=None)
        recoil = spec.recoil_degrees * (.80 if aimed else 1.0)
        return ShotResult(recoil, bool(hits), headshot, main[1].target if main else None)

    def _publish_hit(self, contact, amount, direction, weapon, owner):
        self.events.publish("weapon_hit", target=contact.target, amount=amount, position=contact.position,
                            direction=direction, headshot=contact.headshot, weapon=weapon, owner=owner)

    def npc_shot(self, origin, end, blocked=False):
        direction = end - origin
        if direction.length_squared() < 1e-8:
            return
        direction.normalize()
        self.effects.flash(origin, direction, scale=.84)
        self.effects.tracer(origin, end)
        if blocked:
            self.effects.impact(end, -direction)
        self._audio.play("pistol", origin, gain=.67, pitch=self._pitch.uniform(.91, .97))

    def close(self):
        self.effects.close()
        self._audio.close()


# The right-hand grip sits at the origin and the model points along local +Y.
_MODEL_LAYOUT = {
    "pistol": (.12, .35, .14, .10, (.49, .58, .62)),
    "smg": (.17, .47, .16, .22, (.30, .56, .48)),
    "shotgun": (.16, .77, .14, .33, (.61, .34, .18)),
    "rifle": (.15, .69, .15, .32, (.52, .48, .33)),
}


def build_weapon_model(parent, weapon_id):
    root = parent.attach_new_node(f"held {weapon_id}")
    dimensions = _MODEL_LAYOUT.get(weapon_id)
    if dimensions is None:
        return root
    width, barrel, upper, stock, accent = dimensions
    steel = (.16, .20, .22)
    grip = (.09, .11, .13)
    mesh = Mesh(f"{weapon_id} procedural gear")
    mesh.box((0, barrel * .37, upper), (width, barrel * .78, upper * .70), accent, bottom=True)
    mesh.box((0, barrel * .61, upper * .98), (width * .47, barrel * .78, upper * .34), steel, bottom=True)
    mesh.box((0, 0, 0), (width * .73, .12, .24), grip, bottom=True)
    if weapon_id != "pistol":
        mesh.box((0, -stock * .43, upper * .79), (width * .63, stock, upper * .51), steel, bottom=True)
        mesh.box((0, -stock * .88, upper * .57), (width * .89, .08, upper * 1.17), grip, bottom=True)
    if weapon_id in ("smg", "rifle"):
        mesh.box((0, barrel * .28, .047), (width * .64, .121, .21), steel, bottom=True)
    mesh.box((0, barrel * .73, upper * 1.44), (.036, .052, .033), grip, bottom=True)
    mesh.node().reparent_to(root)
    return root


def weapon_muzzle(weapon_id) -> Point3:
    """Position of the muzzle in the held model's local coordinates."""
    dimensions = _MODEL_LAYOUT.get(weapon_id)
    if dimensions is None:
        return Point3()
    _, barrel, upper, _, _ = dimensions
    return Point3(0, barrel, upper * .98)

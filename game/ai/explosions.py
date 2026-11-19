"""Deterministic, bounded arcade blasts and destructible city props."""
from collections import deque
from dataclasses import dataclass
from math import isfinite
from weakref import WeakKeyDictionary

from panda3d.bullet import BulletBoxShape, BulletCylinderShape, BulletRigidBodyNode, ZUp
from panda3d.core import BitMask32, NodePath, Point3, TransformState, Vec3

from game.core.config import ROOT, read_json
from game.core.rules import damage_falloff
from game.entities.vehicles import Vehicle
from game.entities.weapons import HitTarget
from game.fx.explosions import BlastEffects, projectile_art
from game.world.design import lettering
from game.world.mesh import Mesh

_CONFIG = read_json(ROOT / "game/data/explosions.json")
_MASK = BitMask32.bit(0)
_UP = Vec3(0, 0, 1)


@dataclass(eq=False, slots=True)
class ExplosiveProp:
    id: str
    kind: str
    position: Vec3
    max_health: float
    health: float
    model: NodePath | None = None
    intact: NodePath | None = None
    wreck: NodePath | None = None
    collider: NodePath | None = None
    body: BulletRigidBodyNode | None = None
    burning_until: float = 0.0
    next_smoke: float = 0.0


@dataclass(slots=True)
class _Blast:
    position: Vec3
    kind: str
    owner: object | None = None
    source: object | None = None


@dataclass(slots=True)
class _Projectile:
    node: NodePath
    position: Vec3
    velocity: Vec3
    kind: str
    owner: object | None
    remaining: float
    next_puff: float = 0.0
    resting: bool = False


@dataclass(slots=True)
class _VehicleFire:
    owner: object | None = None
    credit_until: float = 0.0
    wrecked: bool = False
    burning_until: float = 0.0
    next_smoke: float = 0.0
    next_burn: float = 0.0


def _prop_art(kind, burnt):
    mesh = Mesh(f"{kind} {'wreck' if burnt else 'intact'}")
    metal = (.26, .28, .30)
    yellow = (.93, .59, .19)
    red = (.72, .22, .13)
    grime = (.16, .14, .12)
    if kind == "barrel":
        if burnt:
            mesh.box((.08, -.05, .19), (.69, .49, .36), grime, bottom=True)
            mesh.cone(-.1, .09, .20, .16, .25, .21, metal, 9)
        else:
            for z, height, radius, top, color in (
                (.04, .26, .32, .36, red), (.30, .19, .364, .367, metal),
                (.49, .24, .363, .36, yellow), (.73, .22, .36, .32, red),
                (.95, .07, .32, .31, metal),
            ):
                mesh.cone(0, 0, z, height, radius, top, color, 12)
            mesh.cone(.15, 0, 1.02, .07, .074, .067, metal)
    else:
        mesh.box((0, 0, .01), (8.7, 5.6, .08), (.43, .45, .43))
        mesh.box((0, 0, .11), (2.5, 1.55, .21), metal)
        for x in (-3.45, 3.45):
            for y in (-1.7, 1.7):
                mesh.box((x, y, 1.72), (.26, .26, 3.5), metal)
        roof = (.35, .28, .22) if burnt else (.28, .45, .47)
        mesh.box((0, 0, 3.62), (8.1, 4.8, .55), roof, bottom=True)
        mesh.box((0, -2.39, 3.59), (8.0, .09, .37), red if not burnt else grime)
        lettering(mesh, "south", -2.45, 0, 3.46, .061, "LANTERN FUEL", (.91, .83, .60))
        if burnt:
            mesh.box((-.39, .00, .32), (1.12, .7, .57), grime, bottom=True)
            mesh.box((.68, .14, .22), (.75, .48, .39), metal, bottom=True)
        else:
            for x in (-.53, .53):
                mesh.box((x, 0, .83), (.72, .61, 1.28), red, bottom=True)
                mesh.box((x, -.32, 1.09), (.56, .053, .44), yellow)
                mesh.box((x, -.36, 1.14), (.40, .039, .18), (.10, .26, .29))
                mesh.box((x + .39, -.04, .55), (.075, .10, .77), metal)
    return mesh.node()


def _prop_body(prop):
    body = BulletRigidBodyNode(prop.id)
    if prop.kind == "barrel":
        body.add_shape(BulletCylinderShape(.353, 1.04, ZUp), TransformState.make_pos(Vec3(0, 0, .52)))
    else:
        body.add_shape(BulletBoxShape(Vec3(.99, .37, .68)), TransformState.make_pos(Vec3(0, 0, .79)))
    body.set_into_collide_mask(_MASK)
    return body


class ExplosionSystem:
    def __init__(self, render, physics, city, events, *, quality="Medium", audio_loader=None, camera=None):
        self.render, self.physics, self.city, self.events = render, physics, city, events
        self.root = render.attach_new_node("destructible city fixtures")
        self._projectile_root = render.attach_new_node("explosive projectiles")
        self._limit = _CONFIG["limits"][quality]
        self.fx = BlastEffects(render, self._limit, audio_loader, camera)
        self.props = {
            row["id"]: ExplosiveProp(row["id"], row["kind"], Vec3(*row["position"]),
                                     float(row["health"]), float(row["health"]))
            for row in _CONFIG["props"]
        }
        self._prop_templates = {
            (kind, burnt): _prop_art(kind, burnt)
            for kind in ("barrel", "fuel") for burnt in (False, True)
        }
        self._projectile_spares = {}
        for kind in _CONFIG["projectiles"]:
            template = projectile_art(kind)
            spares = []
            for idx in range(self._limit["projectiles"]):
                node = self._projectile_root.attach_new_node(f"{kind} {idx}")
                template.instance_to(node)
                node.hide()
                spares.append(node)
            self._projectile_spares[kind] = spares
        self._projectiles = deque()
        self._pending = deque(maxlen=64)
        self._vehicles = WeakKeyDictionary()
        self._elapsed = 0.0
        self._next_props = 0.0
        self.blast_count = 0
        self._sync_props()
        self.events.subscribe("projectile_launch", self._launch)
        self.events.subscribe("weapon_hit", self._weapon_hit)

    @property
    def targets(self):
        return tuple(HitTarget(prop, prop.body) for prop in self.props.values() if prop.body is not None)

    @property
    def projectile_count(self):
        return len(self._projectiles)

    def _sync_props(self):
        self._next_props = self._elapsed + .28
        for prop in self.props.values():
            visible = self.city.is_loaded(prop.position.x, prop.position.y)
            if visible and prop.model is None:
                prop.model = self.root.attach_new_node(prop.id)
                prop.model.set_pos(prop.position)
                prop.intact = prop.model.attach_new_node("intact")
                prop.wreck = prop.model.attach_new_node("wreck")
                self._prop_templates[(prop.kind, False)].instance_to(prop.intact)
                self._prop_templates[(prop.kind, True)].instance_to(prop.wreck)
                self._show_prop(prop)
            elif not visible and prop.model is not None:
                self._remove_prop(prop)

    def _show_prop(self, prop):
        if prop.health > 0:
            prop.wreck.hide()
            prop.intact.show()
            if prop.body is None:
                prop.body = _prop_body(prop)
                prop.collider = prop.model.attach_new_node(prop.body)
                self.physics.attach_rigid_body(prop.body)
        else:
            prop.intact.hide()
            prop.wreck.show()
            self._detach_prop_body(prop)

    def _detach_prop_body(self, prop):
        if prop.body is not None:
            self.physics.remove_rigid_body(prop.body)
            prop.collider.remove_node()
            prop.collider = prop.body = None

    def _remove_prop(self, prop):
        self._detach_prop_body(prop)
        prop.model.remove_node()
        prop.model = prop.intact = prop.wreck = None

    def _affect_prop(self, prop, amount, owner):
        if prop.health <= 0 or amount <= 0:
            return
        prop.health = max(0.0, prop.health - amount)
        if prop.health == 0:
            if prop.model is not None:
                self._show_prop(prop)
            prop.burning_until = self._elapsed + (8.5 if prop.kind == "fuel" else 3.8)
            point = prop.position + _UP * (.77 if prop.kind == "fuel" else .53)
            self.detonate(point, prop.kind, owner, source=prop)

    def _weapon_hit(self, target, amount, owner=None, **_):
        if isinstance(target, ExplosiveProp):
            self._affect_prop(target, amount, owner)
        elif isinstance(target, Vehicle) and amount > 0:
            state = self._vehicles.setdefault(target, _VehicleFire())
            state.owner, state.credit_until = owner, self._elapsed + 22

    def detonate(self, position, kind="barrel", owner=None, *, source=None):
        point = Vec3(position)
        if kind not in _CONFIG["blasts"] or not all(isfinite(component) for component in point):
            return
        self._pending.append(_Blast(point, kind, owner, source))

    def _launch(self, position, direction, weapon, owner=None):
        spec = _CONFIG["projectiles"].get(weapon)
        if spec is None:
            return
        point, forward = Vec3(position), Vec3(direction)
        if not all(isfinite(x) for vector in (point, forward) for x in vector) or forward.length_squared() < .0001:
            return
        forward.normalize()
        if len(self._projectiles) == self._limit["projectiles"]:
            self._release(self._projectiles.popleft(), explode=True)
        node = self._projectile_spares[weapon].pop()
        node.set_pos(point)
        node.look_at(Point3(point + forward))
        node.show()
        velocity = forward * spec["speed"] + _UP * spec["loft"]
        self._projectiles.append(_Projectile(node, point, velocity, weapon, owner, spec["life"]))

    def _release(self, item, *, explode):
        if explode:
            self.detonate(item.position + _UP * .10, item.kind, item.owner, source=item)
        item.node.hide()
        self._projectile_spares[item.kind].append(item.node)

    def _nearest(self, start, end, ignore=()):
        q = self.physics.ray_test_closest(Point3(start), Point3(end), _MASK)
        if not q.has_hit():
            return None
        if q.get_node() in ignore:
            candidates = self.physics.ray_test_all(Point3(start), Point3(end), _MASK)
            return min((h for h in candidates.get_hits() if h.get_node() not in ignore),
                       key=lambda h: h.get_hit_fraction(), default=None)
        return q

    def _step_projectile(self, item, dt, people):
        item.remaining -= dt
        if item.remaining <= 0:
            return False
        if item.resting:
            return True
        spec = _CONFIG["projectiles"][item.kind]
        item.velocity -= _UP * spec["gravity"] * dt
        origin = item.position
        destination = origin + item.velocity * dt
        owner_body = getattr(item.owner, "controller", None)
        hit = self._nearest(origin, destination, (owner_body,))
        if item.kind == "rocket":
            segment = destination - origin
            length = segment.length()
            if length < 1e-6:
                return True
            heading = segment / length
            upper = (hit.get_hit_fraction() * length) if hit is not None else length
            for person in people:
                if person is item.owner or not person.alive:
                    continue
                center = person.position + _UP
                radius = .51
                delta = center - origin
                along = delta.dot(heading)
                if -.10 <= along <= upper and (delta - heading * along).length_squared() <= radius**2:
                    item.position = origin + heading * max(0, along)
                    return False
        if hit is not None:
            normal = hit.get_hit_normal()
            item.position = Vec3(hit.get_hit_pos() + normal * .10)
            if item.kind == "rocket":
                return False
            velocity = item.velocity - normal * (2 * item.velocity.dot(normal))
            item.velocity = velocity * spec["bounce"]
            if normal.z > .56 and item.velocity.length_squared() < 5.3:
                item.velocity = Vec3()
                item.resting = True
        else:
            item.position = destination
        item.node.set_pos(item.position)
        if item.kind == "grenade":
            item.node.set_p(item.node.get_p() + 340 * dt)
        elif self._elapsed >= item.next_puff:
            self.fx.exhaust(item.position - item.velocity.normalized() * .28)
            item.next_puff = self._elapsed + .041
        return True

    def _ground_at(self, position, ignore=()):
        q = self._nearest(position + _UP * 1.2, position - _UP * 7, ignore)
        if q is None or q.get_hit_normal().z < .66:
            return None
        body = q.get_node()
        return Vec3(q.get_hit_pos()) if isinstance(body, BulletRigidBodyNode) and body.is_static() else None

    def _coverage(self, origin, target, ignore):
        if (target - origin).length_squared() < .045:
            return 1.0
        q = self._nearest(origin, target, ignore)
        body = q.get_node() if q is not None else None
        return .38 if isinstance(body, BulletRigidBodyNode) and body.is_static() else 1.0

    def _kick_car(self, vehicle, radial, strength):
        heading = Vec3(radial.x, radial.y, 0.0)
        if heading.length_squared() < .005:
            motion = vehicle.body.get_linear_velocity()
            heading.set(motion.x, motion.y, 0.0)
            if heading.length_squared() < .005:
                heading.set(1, 0, 0)
        heading.normalize()
        mass = vehicle.body.get_mass()
        impulse = (heading + _UP * .69) * (strength * mass)
        roll = Vec3(-heading.y, heading.x, .17) * (strength * mass * .38)
        vehicle.body.set_active(True, True)
        vehicle.body.apply_central_impulse(impulse)
        vehicle.body.apply_torque_impulse(roll)
        angular = vehicle.body.get_angular_velocity()
        if angular.length_squared() > 13**2:
            vehicle.body.set_angular_velocity(angular.normalized() * 13)

    def _break_car(self, vehicle, state):
        if state.wrecked:
            return
        state.wrecked = True
        state.burning_until = self._elapsed + _CONFIG["vehicle"]["wreck_seconds"]
        owner = state.owner if state.credit_until >= self._elapsed else None
        self.detonate(vehicle.position + _UP * .38, "vehicle", owner, source=vehicle)

    def _damage_actors(self, blast, spec, people, player, player_vehicle, ignore):
        for actor in (*people, player):
            if actor is None or actor.health <= 0:
                continue
            point = actor.position + _UP * 1.02
            car = player_vehicle if actor is player else None
            if car is not None:
                point = car.position + _UP * .5
            radial = point - blast.position
            amount = damage_falloff(spec["damage"], radial.length(), spec["radius"])
            if amount <= 0:
                continue
            covered = self._coverage(blast.position, point, (*ignore, getattr(car, "body", None)))
            self.events.publish("damage", target=actor, amount=amount * covered * (.72 if car else 1.0),
                                source=blast.owner, direction=radial.normalized(), kind="explosion")

    def _apply_blast(self, blast, focus, vehicles, people, player, player_vehicle):
        spec = _CONFIG["blasts"][blast.kind]
        position, radius = blast.position, spec["radius"]
        self.blast_count += 1
        source_body = getattr(blast.source, "body", None)
        ignore = (source_body, getattr(player, "controller", None))
        ground = self._ground_at(position, ignore)
        if (position - focus).length_squared() < 190**2:
            self.fx.burst(position, ground, spec["size"], radius)
        self.events.publish("explosion", position=position, radius=radius, owner=blast.owner,
                            cause=blast.kind, shake=spec["shake"], source=blast.source)
        self._damage_actors(blast, spec, people, player, player_vehicle, ignore)
        for vehicle in vehicles:
            if not vehicle.physics_active:
                continue
            radial = vehicle.position - position
            remaining = damage_falloff(1.0, radial.length(), radius)
            if remaining <= 0:
                continue
            cover = self._coverage(position, vehicle.position, (*ignore, vehicle.body))
            self_blast = .39 if vehicle is blast.source else 1.0
            self._kick_car(vehicle, radial, spec["push"] * remaining * cover * self_blast)
            if vehicle.health > 0:
                state = self._vehicles.setdefault(vehicle, _VehicleFire())
                if blast.owner is not None:
                    state.owner, state.credit_until = blast.owner, self._elapsed + 22
                credit = state.owner if state.credit_until >= self._elapsed else None
                vehicle.apply_damage(spec["vehicle_damage"] * remaining * cover, source=credit or "explosion")
                if vehicle.health <= 0:
                    self._break_car(vehicle, state)
        for prop in self.props.values():
            if prop.model is not None and prop.health > 0:
                point = prop.position + _UP * .55
                damage = damage_falloff(spec["vehicle_damage"], (point - position).length(), radius)
                if damage > 0:
                    covered = self._coverage(position, point, (*ignore, prop.body))
                    self._affect_prop(prop, covered * damage, blast.owner)

    def _vehicle_fire(self, focus, vehicles):
        settings = _CONFIG["vehicle"]
        for vehicle in vehicles:
            if not vehicle.physics_active or vehicle.health > settings["smoke_health"]:
                continue
            state = self._vehicles.setdefault(vehicle, _VehicleFire())
            burning = vehicle.health <= settings["fire_health"]
            if vehicle.health <= 0:
                self._break_car(vehicle, state)
                burning = self._elapsed < state.burning_until
                if not burning:
                    continue
            elif burning and state.next_burn <= self._elapsed:
                state.next_burn = self._elapsed + .25
                credit = state.owner if state.credit_until >= self._elapsed else None
                vehicle.apply_damage(settings["burn_per_second"] * .25, source=credit or "fire")
                if vehicle.health <= 0:
                    self._break_car(vehicle, state)
            if state.next_smoke <= self._elapsed and (vehicle.position - focus).length_squared() < 111**2:
                state.next_smoke = self._elapsed + (.16 if burning else .37)
                point = vehicle.hood_position() + _UP * .12
                self.fx.fumes(point, burning)

    def update(self, dt, focus, vehicles=(), people=(), player=None, *, player_vehicle=None):
        if dt < 0 or not isfinite(dt):
            return
        self._elapsed += dt
        if self._elapsed >= self._next_props:
            self._sync_props()
        peds = tuple(people)
        for _ in range(len(self._projectiles)):
            item = self._projectiles.popleft()
            if self._step_projectile(item, dt, peds):
                self._projectiles.append(item)
            else:
                self._release(item, explode=True)
        self._vehicle_fire(focus, vehicles)
        for _ in range(self._limit["blasts_per_tick"]):
            if not self._pending:
                break
            self._apply_blast(self._pending.popleft(), focus, vehicles, peds, player, player_vehicle)
        for prop in self.props.values():
            if (prop.model is not None and prop.burning_until > self._elapsed
                    and prop.next_smoke <= self._elapsed and (prop.position - focus).length_squared() < 111**2):
                prop.next_smoke = self._elapsed + .24
                self.fx.fumes(prop.position + _UP * .60, True)
        self.fx.update(dt)

    def snapshot(self):
        return {prop.id: prop.health for prop in self.props.values()}

    def restore(self, data, vehicles=()):
        self._pending.clear()
        while self._projectiles:
            self._release(self._projectiles.popleft(), explode=False)
        self.fx.clear()
        self._vehicles.clear()
        for vehicle in vehicles:
            if vehicle.health <= 0:
                self._vehicles[vehicle] = _VehicleFire(wrecked=True)
        for prop in self.props.values():
            value = data.get(prop.id) if isinstance(data, dict) else None
            if type(value) in (int, float) and isfinite(value):
                prop.health = max(0.0, min(prop.max_health, value))
            else:
                prop.health = prop.max_health
            prop.burning_until = prop.next_smoke = 0.0
            if prop.model is not None:
                self._show_prop(prop)
        self._sync_props()

    def close(self):
        self.events.unsubscribe("projectile_launch", self._launch)
        self.events.unsubscribe("weapon_hit", self._weapon_hit)
        for prop in self.props.values():
            if prop.model is not None:
                self._remove_prop(prop)
        self.fx.close()
        self._projectile_root.remove_node()
        self.root.remove_node()

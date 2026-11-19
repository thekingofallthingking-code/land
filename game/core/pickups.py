"""Local collectibles placed by pedestrian and game events."""
from dataclasses import dataclass
from math import sin

from panda3d.core import NodePath, Vec3

from game.world.mesh import Mesh


@dataclass
class Pickup:
    position: Vec3
    node: NodePath
    cash: int = 0
    weapon: str = ""
    rounds: int = 0
    age: float = 0


def pickup_mesh(weapon):
    mesh = Mesh("weapon pickup" if weapon else "cash pickup")
    if weapon:
        mesh.box((0, 0, .08), (.13, .40, .14), (.20, .38, .48), bottom=True)
        mesh.box((0, .20, .08), (.08, .12, .076), (.61, .74, .81), bottom=True)
        mesh.box((0, -.056, -.018), (.09, .11, .11), (.22, .24, .29), bottom=True)
    else:
        for z, color in ((.00, (.30, .63, .45)), (.026, (.59, .84, .60))):
            mesh.box((0, 0, z), (.27, .16, .036), color, bottom=True)
        mesh.box((0, 0, .05), (.073, .164, .012), (.87, .81, .58))
    return mesh.node()


class Pickups:
    LIMIT = 36

    def __init__(self, render, events):
        self.root = render.attach_new_node("collectibles")
        self.events = events
        self.items: list[Pickup] = []
        self.meshes = {False: pickup_mesh(False), True: pickup_mesh(True)}
        events.subscribe("cash_drop", self.drop_cash)
        events.subscribe("weapon_drop", self.drop_weapon)

    def _add(self, position, *, cash=0, weapon="", rounds=0):
        if len(self.items) == self.LIMIT:
            self.items.pop(0).node.remove_node()
        anchor = self.root.attach_new_node("pickup")
        self.meshes[bool(weapon)].instance_to(anchor)
        anchor.set_pos(position + Vec3(0, 0, .25))
        self.items.append(Pickup(Vec3(position), anchor, cash, weapon, rounds))

    def drop_cash(self, position, amount, **_):
        if amount > 0:
            self._add(position, cash=int(amount))

    def drop_weapon(self, position, weapon_id, rounds=0, **_):
        if weapon_id:
            self._add(position, weapon=weapon_id, rounds=max(0, int(rounds)))

    def update(self, dt, player, weapons, focus):
        remaining = []
        for pickup in self.items:
            pickup.age += dt
            distance = (focus - pickup.position).length_squared()
            if player.active and pickup.age > .22 and distance < 1.35 ** 2:
                if pickup.cash:
                    player.money += pickup.cash
                    message = f"+${pickup.cash}"
                elif weapons.owns(pickup.weapon):
                    weapons.add_ammo(pickup.weapon, pickup.rounds)
                    message = "Ammo collected"
                else:
                    weapons.grant_weapon(pickup.weapon, pickup.rounds)
                    message = "Weapon collected"
                self.events.publish("pickup_collected", message=message, pickup=pickup)
            elif pickup.age < 180 and distance < 260 ** 2:
                pickup.node.set_h(pickup.age * 96)
                pickup.node.set_z(pickup.position.z + .27 + .06 * sin(pickup.age * 4))
                remaining.append(pickup)
                continue
            pickup.node.remove_node()
        self.items = remaining

    def close(self):
        self.events.unsubscribe("cash_drop", self.drop_cash)
        self.events.unsubscribe("weapon_drop", self.drop_weapon)
        self.root.remove_node()
        self.items.clear()

"""The first delivery job, driven by events from the shared city."""
from math import cos, hypot, sin, tau

from panda3d.core import Vec3

from game.core.config import ROOT, read_json
from game.world.mesh import Mesh


def _marker(parent, position, radius, color):
    mesh = Mesh("job marker")
    for index in range(24):
        left = index * tau / 24
        right = (index + 1) * tau / 24
        outer = radius + .12
        mesh.face((
            (cos(left) * radius, sin(left) * radius, 0),
            (cos(left) * outer, sin(left) * outer, 0),
            (cos(right) * outer, sin(right) * outer, 0),
            (cos(right) * radius, sin(right) * radius, 0),
        ), color, (0, 0, 1))
    stem = .62 if radius < 1 else 1.15
    mesh.cone(0, 0, stem, .37, .14, 0, color, sides=4)
    mesh.cone(0, 0, stem, -.37, .14, 0, color, sides=4)
    mark = mesh.node()
    mark.reparent_to(parent)
    mark.set_pos(position + Vec3(0, 0, .035))
    mark.set_two_sided(True)
    mark.set_light_off(1)
    mark.set_shader_off(1)
    return mark


class DeliveryJob:
    def __init__(self, render, city, events):
        self.spec = read_json(ROOT / "game/data/missions.json")["missions"][0]
        self.title = self.spec["title"]
        self.start = Vec3(*self.spec["start"])
        self.destination = Vec3(*self.spec["destination"])
        self.city = city
        self.events = events
        self.state = "available"
        self.vehicle = None
        self.root = render.attach_new_node("delivery job")
        self.contact_marker = _marker(self.root, self.start, .72, (.92, .63, .24))
        self.drop_marker = _marker(self.root, self.destination, 2.8, (.34, .82, .64))
        self.drop_marker.hide()
        events.subscribe("carjacking", self.on_carjacking)

    def offered_at(self, position):
        return self.state == "available" and (position - self.start).length_squared() <= 3.1 ** 2

    def accept(self):
        self.state = "find_car"

    def on_carjacking(self, vehicle, **_):
        if self.state == "find_car":
            self.vehicle = vehicle
            self.state = "deliver"

    def update(self, player, occupied, vehicles):
        if self.state == "deliver":
            if self.vehicle not in vehicles or self.vehicle.health <= 0:
                self.vehicle = None
                self.state = "find_car"
            elif player.health > 0 and occupied is self.vehicle:
                delta = self.vehicle.position - self.destination
                speed = self.vehicle.body.get_linear_velocity().length() * 3.6
                if delta.length_squared() < self.spec["arrival_radius"] ** 2 and speed <= self.spec["maximum_finish_kph"]:
                    player.money += self.spec["reward"]
                    self.state = "complete"
                    self.vehicle = None
                    self.events.publish("mission_completed", title=self.title, reward=self.spec["reward"])
        if self.state == "available" and self.city.is_loaded(self.start.x, self.start.y):
            self.contact_marker.show()
        else:
            self.contact_marker.hide()
        if self.state == "deliver" and self.city.is_loaded(self.destination.x, self.destination.y):
            self.drop_marker.show()
        else:
            self.drop_marker.hide()

    def objective(self, position):
        if self.state == "find_car":
            return f"{self.title}  /  Take a car with a driver"
        if self.state == "deliver":
            distance = hypot(position.x - self.destination.x, position.y - self.destination.y)
            return f'{self.title}  /  {self.spec["destination_name"]}   {distance:.0f} m'
        return ""

    def waypoint(self):
        if self.state == "available":
            return self.start
        if self.state == "deliver":
            return self.destination
        return None

    def snapshot(self, vehicles):
        index = vehicles.index(self.vehicle) if self.vehicle in vehicles else None
        return {"id": self.spec["id"], "state": self.state, "vehicle": index}

    def restore(self, data, cars):
        self.state = "available"
        self.vehicle = None
        if not isinstance(data, dict) or data.get("id") != self.spec["id"]:
            return
        state = data.get("state")
        if state in ("find_car", "complete"):
            self.state = state
        elif state == "deliver":
            index = data.get("vehicle")
            self.vehicle = cars.get(index) if type(index) is int else None
            self.state = "deliver" if self.vehicle is not None else "find_car"

    def close(self):
        self.events.unsubscribe("carjacking", self.on_carjacking)
        self.root.remove_node()

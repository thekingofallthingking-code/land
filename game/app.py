"""Harbor City application and fixed-step simulation."""
from dataclasses import dataclass
import logging
import os
from pathlib import Path

from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.bullet import BulletWorld
from panda3d.core import (
    BitMask32, ClockObject, Filename, ModifierButtons, Vec3, WindowProperties,
)

from game.core.camera import ThirdPersonCamera
from game.core.config import ASSETS, PRESETS, ROOT, Settings, memory_gib, pick_quality, project_file, read_json, write_json
from game.core.events import EventBus
from game.core.lighting import CityLighting
from game.entities.player import Player
from game.entities.vehicles import Vehicle
from game.tools.assets import ensure_assets
from game.ui.overlay import Overlay
from game.world import City

STEP = 1 / 60
SETTINGS_FILE = ROOT / "settings.json"
SAVE_FILE = ROOT / "save.json"


@dataclass
class Controls:
    forward: float = 0
    side: float = 0
    sprint: bool = False
    jump: bool = False
    interact: bool = False
    camera: bool = False


class HarborCity(ShowBase):
    def __init__(self, options):
        self.options = options
        self.headless = options.self_test and not options.offscreen
        self.testing = options.self_test or options.offscreen
        self.game_state = "menu"
        self.occupied = None
        self.elapsed = 0.0
        self.accumulator = 0.0
        self.jump_queued = False
        self.pointer_centered = False
        self.keys: set[str] = set()
        self.pressed: set[str] = set()
        self.vehicle_audio = None
        self.ambience = None
        self.settings = Settings.load(SETTINGS_FILE)
        self.settings_path = SETTINGS_FILE
        self.save_path = SAVE_FILE
        window_type = "none" if self.headless else "offscreen" if self.testing else "onscreen"
        super().__init__(windowType=window_type)
        self.disable_mouse()
        if not self.headless and self.win is None:
            raise RuntimeError("Panda3D could not open a window. Update your graphics driver or try --quality Low.")
        if self.headless:
            self.camera = self.render.attach_new_node("simulated camera")
        else:
            self.camLens.set_fov(76)
            self.camLens.set_near(0.19)

        renderer = self.win.get_gsg().get_driver_renderer() if self.win else ""
        quality = options.quality or self.settings.quality
        if not quality:
            quality = pick_quality(renderer, os.cpu_count() or 1, memory_gib())
            self.settings.quality = quality
            if not self.testing:
                self.settings.save(self.settings_path)
        self.quality = quality
        preset = PRESETS[quality]
        logging.info("Quality %s, renderer %s", quality, renderer or "headless")
        if not self.headless:
            self.camLens.set_far(preset["far"])
        self.physics = BulletWorld()
        self.physics.set_gravity(Vec3(0, 0, -9.81))
        self.events = EventBus()
        self.city = City(self.render, self.physics, radius=preset["radius"])
        self.city.update(self.city.spawn, eager=True)
        self.player = Player(self.render, self.physics, self.city.spawn)
        self.follow_camera = ThirdPersonCamera(self.camera, self.physics, sensitivity=self.settings.sensitivity)
        self.lighting = CityLighting(self, preset, self.city.root, rendered=not self.headless)
        if options.hour is not None:
            self.lighting.hour = options.hour % 24
        if not self.headless:
            ensure_assets()
            self.enableSoundEffects(True)
            if self.sfxManagerList:
                self.sfxManagerList[0].set_volume(self.settings.volume)
            if not self.testing:
                self.vehicle_audio = self.loader
                self.ambience = self.loader.load_sfx(str(ASSETS / "harbor.wav"))
                self.ambience.set_loop(True)
                self.ambience.set_volume(.21)
                self.ambience.play()
        self.vehicles = [
            Vehicle(self.render, self.physics, kind, position, heading,
                    audio_loader=self.vehicle_audio, events=self.events)
            for kind, position, heading in self.city.car_spawns
        ]
        self.overlay = None
        if not self.headless:
            minimap = project_file(ASSETS / "minimap.png")
            if not minimap.is_file():
                self.city.minimap(minimap)
            self.overlay = Overlay(self, self.begin_play, self.resume, self.userExit, minimap)
        self.set_state("menu")
        self.follow_camera.update(0, self.player, snap=True)
        self.lighting.update(0, self.player.position, self.camera.get_pos())
        self.city.set_night(self.lighting.night)
        for _ in range(80):
            self.update_simulation(STEP, Controls(), advance_clock=False)
        if not self.testing:
            self.bind_inputs()
            self.task_mgr.add(self.tick, "harbor city frame", sort=10)
        if options.play:
            self.begin_play()

    def bind_inputs(self):
        self.buttonThrowers[0].node().set_modifier_buttons(ModifierButtons())
        for key in ("w", "a", "s", "d", "shift", "space", "f", "c"):
            self.accept(key, self.press, [key])
            self.accept(key + "-up", self.keys.discard, [key])
        self.accept("escape", self.escape)
        self.accept("f1", self.overlay.toggle_help)
        self.accept("f3", self.overlay.toggle_debug)
        self.accept("f5", self.quicksave)
        self.accept("enter", self.resume_or_start)

    def windowEvent(self, window):
        super().windowEvent(window)
        if not self.testing and window == self.win and not window.get_properties().get_foreground():
            if self.game_state == "playing":
                self.set_state("paused")

    def press(self, key):
        if self.game_state == "playing" and key not in self.keys:
            self.keys.add(key)
            self.pressed.add(key)

    def set_state(self, state):
        self.game_state = state
        self.keys.clear()
        self.pressed.clear()
        self.jump_queued = False
        self.pointer_centered = False
        if self.overlay:
            self.overlay.set_state(state)
        if not self.testing and self.win:
            properties = WindowProperties()
            properties.set_cursor_hidden(state == "playing")
            properties.set_mouse_mode(WindowProperties.M_confined if state == "playing" else WindowProperties.M_absolute)
            self.win.request_properties(properties)

    def begin_play(self):
        if self.game_state != "menu":
            return
        if not self.testing:
            self.load_save()
        self.set_state("playing")
        self.follow_camera.update(0, self.player, self.occupied, snap=True)

    def resume(self):
        if self.game_state == "paused":
            self.set_state("playing")

    def resume_or_start(self):
        if self.game_state == "menu":
            self.begin_play()
        else:
            self.resume()

    def escape(self):
        if self.game_state == "playing":
            self.set_state("paused")
        elif self.game_state == "paused":
            self.resume()

    def sample_controls(self):
        center_x, center_y = self.win.get_x_size() // 2, self.win.get_y_size() // 2
        pointer = self.win.get_pointer(0)
        if pointer.get_in_window():
            if self.pointer_centered:
                self.follow_camera.mouse(pointer.get_x() - center_x, pointer.get_y() - center_y)
            self.pointer_centered = self.win.move_pointer(0, center_x, center_y)
        else:
            self.pointer_centered = False
        controls = Controls(
            forward=float("w" in self.keys) - float("s" in self.keys),
            side=float("d" in self.keys) - float("a" in self.keys),
            sprint="shift" in self.keys,
            jump="space" in (self.keys if self.occupied else self.pressed),
            interact="f" in self.pressed,
            camera="c" in self.pressed,
        )
        self.pressed.clear()
        return controls

    def focus(self):
        return self.occupied.position if self.occupied else self.player.position

    def nearby_vehicle(self):
        distance = 3.8 ** 2
        nearest = None
        feet = self.player.position
        start = feet + Vec3(0, 0, 1.0)
        player_body = self.player.node.node()
        for vehicle in self.vehicles:
            if not vehicle.physics_active:
                continue
            candidate = (vehicle.position - feet).length_squared()
            if candidate < distance:
                end = vehicle.position + Vec3(0, 0, .55)
                ray = self.physics.ray_test_all(start, end, BitMask32.bit(0))
                if any(hit.get_node() not in (player_body, vehicle.body) for hit in ray.get_hits()):
                    continue
                distance, nearest = candidate, vehicle
        return nearest

    def interact_vehicle(self):
        if not self.occupied:
            if vehicle := self.nearby_vehicle():
                self.occupied = vehicle
                self.player.set_active(False)
                self.events.publish("vehicle_enter", vehicle=vehicle)
                self.follow_camera.update(0, self.player, vehicle, snap=True)
            return
        vehicle = self.occupied
        if vehicle.body.get_linear_velocity().length_squared() > (19 / 3.6) ** 2:
            if self.overlay:
                self.overlay.notify("Slow down to exit")
            return
        position = self.safe_exit(vehicle)
        if position is None:
            if self.overlay:
                self.overlay.notify("No space to exit")
            return
        self.occupied = None
        self.player.teleport(position, vehicle.heading)
        self.player.set_active(True)
        self.events.publish("vehicle_exit", vehicle=vehicle)
        self.follow_camera.update(0, self.player, snap=True)

    def safe_exit(self, vehicle):
        center = vehicle.position
        first = vehicle.exit_position()
        left = center - (first - center)
        left.z = first.z
        for point in (first, left):
            start = Vec3(center.x, center.y, center.z + .35)
            end = Vec3(point.x, point.y, center.z + .35)
            contact = self.physics.ray_test_all(start, end, BitMask32.bit(0))
            if any(hit.get_node() != vehicle.body for hit in contact.get_hits()):
                continue
            ground = self.physics.ray_test_closest(end, end - Vec3(0, 0, 2.8), BitMask32.bit(0))
            if ground.has_hit() and ground.get_hit_normal().z > .55:
                feet = ground.get_hit_pos() + Vec3(0, 0, .04)
                if self.player.has_clearance(feet):
                    return feet
        return None

    def advance(self, dt, controls):
        if self.game_state != "playing":
            self.update_presentation(dt)
            return
        if controls.interact:
            self.interact_vehicle()
        if controls.camera and self.occupied:
            self.follow_camera.toggle_vehicle_view()
        if not self.occupied:
            self.jump_queued |= controls.jump
        self.accumulator += max(0.0, min(dt, .10))
        while self.accumulator + 1e-9 >= STEP:
            self.update_simulation(STEP, controls)
            self.jump_queued = False
            self.accumulator = max(0.0, self.accumulator - STEP)
        self.update_presentation(dt)

    def update_simulation(self, dt, controls, *, advance_clock=True):
        if not self.occupied:
            self.player.move(controls.forward, controls.side, self.follow_camera.heading,
                             controls.sprint, self.jump_queued, dt)
        for vehicle in self.vehicles:
            occupied = vehicle is self.occupied
            vehicle.update(dt, controls.forward if occupied else 0,
                           controls.side if occupied else 0, controls.jump if occupied else False,
                           occupied=occupied, night=self.lighting.night)
        self.physics.do_physics(dt, 0)
        for vehicle in self.vehicles:
            vehicle.after_physics(dt)
        self.player.animate(dt)
        if advance_clock:
            self.elapsed += dt
            if self.focus().z < -12 or not self.city.contains(self.focus().x, self.focus().y):
                self.recover()

    def recover(self):
        if self.occupied:
            vehicle = self.occupied
            _, spawn, heading = self.city.car_spawns[self.vehicles.index(vehicle)]
            vehicle.node.set_pos(spawn)
            vehicle.node.set_hpr(heading, 0, 0)
            vehicle.body.set_linear_velocity(Vec3())
            vehicle.body.set_angular_velocity(Vec3())
            self.occupied = None
            self.player.set_active(True)
        self.city.update(self.city.spawn, eager=True)
        self.sync_vehicles()
        self.player.teleport(self.city.spawn)
        self.follow_camera.update(0, self.player, snap=True)
        if self.overlay:
            self.overlay.notify("Returned to Breakwater Avenue")

    def sync_vehicles(self):
        for vehicle in self.vehicles:
            point = vehicle.position
            vehicle.set_physics_active(vehicle is self.occupied or self.city.is_loaded(point.x, point.y))

    def update_presentation(self, dt):
        focus = self.focus()
        live_dt = dt if self.game_state == "playing" else 0
        if self.game_state == "playing":
            self.city.update(focus)
            self.sync_vehicles()
            self.follow_camera.update(dt, self.player, self.occupied)
        night = self.lighting.update(live_dt, focus, self.camera.get_pos())
        self.city.set_night(night)
        if self.overlay:
            vehicle = self.occupied
            nearby = None if vehicle else self.nearby_vehicle()
            context = "F   Exit vehicle" if vehicle else "F   Enter vehicle" if nearby else ""
            speed, rpm, gear = (vehicle.speed_kph, vehicle.rpm, vehicle.gear) if vehicle else (0, 0, "")
            fps = ClockObject.get_global_clock().get_average_frame_rate()
            self.overlay.update(
                dt, district=self.city.district(focus.x, focus.y), position=focus,
                heading=vehicle.heading if vehicle else self.follow_camera.heading,
                speed=speed, rpm=rpm, gear=gear, health=self.player.health,
                money=self.player.money, hour=self.lighting.hour, context=context,
                fps=fps, debug_info=f"{self.quality}  |  {len(self.city.loaded_chunks)} chunks  |  "
                f"{len(self.vehicles)} cars\nX {focus.x:.0f}  Y {focus.y:.0f}  Z {focus.z:.1f}",
                driving=vehicle is not None, car_health=vehicle.health if vehicle else 100,
            )

    def tick(self, task):
        dt = min(ClockObject.get_global_clock().get_dt(), .10)
        controls = self.sample_controls() if self.game_state == "playing" else Controls()
        self.advance(dt, controls)
        return Task.cont

    def quicksave(self):
        if self.game_state != "playing":
            return
        values = {
            "schema": 1, "on_foot": list(self.player.position), "heading": self.follow_camera.heading,
            "hour": self.lighting.hour, "health": self.player.health, "money": self.player.money,
            "occupied": self.vehicles.index(self.occupied) if self.occupied else None,
            "vehicles": [{"position": list(car.position), "hpr": list(car.node.get_hpr()), "health": car.health}
                         for car in self.vehicles],
        }
        try:
            write_json(self.save_path, values)
        except (OSError, ValueError):
            logging.exception("Quicksave failed")
            if self.overlay:
                self.overlay.notify("Save unavailable")
            return
        if self.overlay:
            self.overlay.notify("Drive saved")

    @staticmethod
    def valid_vector(value):
        return isinstance(value, list) and len(value) == 3 and all(
            isinstance(item, (float, int)) and -100_000 <= item <= 100_000 for item in value
        )

    def load_save(self):
        data = read_json(self.save_path)
        point = data.get("on_foot")
        if data.get("schema") != 1 or not self.valid_vector(point) or not self.city.contains(*point[:2]):
            return
        self.player.teleport(Vec3(*point))
        for key, low, high in (("health", 0, 100), ("money", 0, 2 ** 31 - 1)):
            value = data.get(key)
            if isinstance(value, (float, int)) and low <= value <= high:
                setattr(self.player, key, int(value))
        for key, target in (("hour", self.lighting), ("heading", self.follow_camera)):
            value = data.get(key)
            if isinstance(value, (float, int)) and -100_000 <= value <= 100_000:
                setattr(target, key, value % (24 if key == "hour" else 360))
        records = data.get("vehicles")
        if isinstance(records, list):
            for car, record in zip(self.vehicles, records):
                if not isinstance(record, dict):
                    continue
                pos, hpr = record.get("position"), record.get("hpr")
                if self.valid_vector(pos) and self.valid_vector(hpr) and self.city.contains(*pos[:2]):
                    car.node.set_pos(*pos)
                    car.node.set_hpr(*hpr)
                    car.body.set_linear_velocity(Vec3())
                    car.body.set_angular_velocity(Vec3())
                health = record.get("health")
                if isinstance(health, (float, int)) and 0 <= health <= 100:
                    car.health = health
        index = data.get("occupied")
        if type(index) is int and 0 <= index < len(self.vehicles):
            self.occupied = self.vehicles[index]
            self.player.set_active(False)
        self.city.update(self.focus(), eager=True)
        self.sync_vehicles()

    def snapshot(self, path: Path):
        if not self.win:
            raise RuntimeError("Screenshot requires --offscreen.")
        if not self.win.save_screenshot(Filename.from_os_specific(str(project_file(path)))):
            raise RuntimeError(f"Could not save screenshot: {path}")

    def close(self):
        if self.ambience:
            self.ambience.stop()
        if self.overlay:
            self.overlay.destroy()
        for vehicle in self.vehicles:
            vehicle.close()
        self.player.close()
        self.city.close()
        self.lighting.close()
        self.destroy()

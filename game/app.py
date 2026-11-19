"""Harbor City application and fixed-step simulation."""
from dataclasses import dataclass
import logging
import os
from pathlib import Path
from time import perf_counter

from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.bullet import BulletWorld
from panda3d.core import (
    BitMask32, ClockObject, Filename, ModifierButtons, Vec3, WindowProperties,
)

from game.ai.pedestrians import Pedestrian, PedestrianManager
from game.ai.traffic import Traffic
from game.core.camera import ThirdPersonCamera
from game.core.config import ASSETS, PRESETS, ROOT, Settings, memory_gib, pick_quality, project_file, read_json, write_json
from game.core.events import EventBus
from game.core.lighting import CityLighting
from game.core.performance import PerformanceLog
from game.core.pickups import Pickups
from game.core.rules import apply_damage
from game.entities.player import Player
from game.entities.vehicles import Vehicle
from game.entities.weapons import HitTarget, WEAPON_SPECS, WeaponSystem, build_weapon_model, weapon_muzzle
from game.tools.assets import ensure_assets
from game.ui.overlay import Overlay
from game.world import City

STEP = 1 / 60
SETTINGS_FILE = ROOT / "settings.json"
SAVE_FILE = ROOT / "save.json"
MAX_STOLEN_CARS = 12


@dataclass
class Controls:
    forward: float = 0
    side: float = 0
    sprint: bool = False
    jump: bool = False
    interact: bool = False
    camera: bool = False
    talk: bool = False
    aim: bool = False
    fire: bool = False
    fire_pressed: bool = False
    reload: bool = False
    weapon_slot: int = 0


@dataclass
class Carjacking:
    vehicle: Vehicle
    remaining: float = .72


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
        self.fire_queued = False
        self.aiming = False
        self.conversation = None
        self.theft = None
        self.respawn_remaining = 0.0
        self.last_frame_time = None
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
        self.performance = PerformanceLog.from_app(self, options)
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
        pedestrian_limit, traffic_limit = {"Low": (18, 9), "Medium": (26, 13), "High": (36, 17)}[quality]
        self.peds = PedestrianManager(self.render, self.physics, self.city, self.events, limit=pedestrian_limit)
        self.traffic = Traffic(self.render, self.physics, self.city, self.events,
                               audio_loader=self.vehicle_audio, cap=traffic_limit)
        self.weapons = WeaponSystem(self.render, self.physics, self.events, audio_loader=self.vehicle_audio)
        self.pickups = Pickups(self.render, self.events)
        self.store = read_json(ROOT / "game/data/shop.json")
        self.held_model = None
        self.refresh_held_model()
        self.events.subscribe("weapon_hit", self.on_weapon_hit)
        self.events.subscribe("damage", self.on_damage)
        self.events.subscribe("pickup_collected", self.on_pickup)
        self.events.subscribe("pedestrian_bump", self.on_pedestrian_bump)
        self.events.subscribe("npc_shot", self.on_npc_shot)
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
        for key in ("w", "a", "s", "d", "shift", "space", "f", "c", "e",
                    "mouse1", "mouse3", "r", "1", "2", "3", "4", "5"):
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
        if state != "playing":
            self.end_conversation()
        self.keys.clear()
        self.pressed.clear()
        self.jump_queued = False
        self.fire_queued = False
        self.aiming = False
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
            talk="e" in self.pressed,
            aim="mouse3" in self.keys,
            fire="mouse1" in self.keys,
            fire_pressed="mouse1" in self.pressed,
            reload="r" in self.pressed,
            weapon_slot=next((slot for slot in range(1, 6) if str(slot) in self.pressed), 0),
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
        for vehicle in (*self.vehicles, *self.traffic.vehicles):
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
        if self.respawn_remaining or self.theft:
            return
        if not self.occupied:
            if vehicle := self.nearby_vehicle():
                if self.traffic.has_driver(vehicle):
                    if vehicle.body.get_linear_velocity().length_squared() > (20 / 3.6) ** 2:
                        self.show_notice("Approach a slow or stopped car")
                        return
                    if self.safe_exit(vehicle) is None:
                        self.show_notice("No room to move the driver")
                        return
                    self.traffic.hold_vehicle(vehicle)
                    self.theft = Carjacking(vehicle)
                    self.player.attack_pose()
                else:
                    self.enter_vehicle(vehicle)
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

    def enter_vehicle(self, vehicle):
        self.end_conversation()
        self.occupied = vehicle
        self.aiming = False
        self.player.set_active(False)
        self.events.publish("vehicle_enter", vehicle=vehicle)
        self.follow_camera.update(0, self.player, vehicle, snap=True)

    def update_carjacking(self, dt):
        theft = self.theft
        vehicle = theft.vehicle
        if self.respawn_remaining or not vehicle.physics_active or (vehicle.position - self.player.position).length_squared() > 5 ** 2:
            if self.traffic.has_driver(vehicle):
                self.traffic.hold_vehicle(vehicle, False)
            self.theft = None
            return
        theft.remaining -= dt
        if theft.remaining < .40 and self.traffic.has_driver(vehicle):
            exit_point = self.safe_exit(vehicle, prefer_side=1)
            if exit_point is None:
                self.traffic.hold_vehicle(vehicle, False)
                self.theft = None
                self.show_notice("No room to move the driver")
                return
            driver = self.traffic.take_vehicle(vehicle)
            if driver is None:
                self.theft = None
                return
            if len(self.vehicles) >= len(self.city.car_spawns) + MAX_STOLEN_CARS:
                self.vehicles.pop(len(self.city.car_spawns)).close()
            self.vehicles.append(vehicle)
            person = self.peds.spawn_at(exit_point, driver.archetype, priority=True)
            if person is not None:
                self.peds.displaced_driver(person, self.player.position, hostile=driver.hostile,
                                           from_position=vehicle.position)
            self.events.publish("crime", kind="car_theft", position=vehicle.position, offender=self.player)
            self.events.publish("carjacking", vehicle=vehicle, offender=self.player)
        if theft.remaining <= 0:
            self.theft = None
            self.enter_vehicle(vehicle)

    def safe_exit(self, vehicle, prefer_side=-1):
        center = vehicle.position
        first = vehicle.exit_position(prefer_side)
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

    def show_notice(self, message):
        if self.overlay:
            self.overlay.notify(message)

    def refresh_held_model(self):
        if self.held_model is not None:
            self.held_model.remove_node()
        self.held_model = build_weapon_model(self.player.weapon_socket, self.weapons.selected.id)

    def on_pickup(self, message, **_):
        self.show_notice(message)

    def on_pedestrian_bump(self, message, position, **_):
        if (position - self.focus()).length_squared() < 8 ** 2:
            self.show_notice(message)

    def on_npc_shot(self, origin, end, blocked=False, **_):
        self.weapons.npc_shot(origin, end, blocked=blocked)

    def on_weapon_hit(self, target, amount, position, direction=None, headshot=False, owner=None, weapon=None, **_):
        killed = False
        if isinstance(target, Pedestrian) and target.alive:
            target.take_damage(amount, source=owner, direction=direction, headshot=headshot,
                               kind="melee" if weapon == "melee" else "gunshot")
            killed = not target.alive
        elif isinstance(target, Vehicle):
            target.apply_damage(amount, source="weapon")
        else:
            return
        if owner is self.player and self.overlay:
            self.overlay.flash_hit(killed=killed)

    def on_damage(self, target, amount, source=None, kind=None, **_):
        if isinstance(target, Vehicle) and kind == "npc_gunshot":
            target.apply_damage(amount, source="npc_gunshot")
        if target is not self.player or self.respawn_remaining:
            return
        self.player.health, self.player.armor = apply_damage(self.player.health, self.player.armor, amount)
        if self.player.health <= 0:
            self.respawn_remaining = 3.0
            death_position = Vec3(self.focus())
            self.occupied = None
            self.player.set_active(False)
            self.player.teleport(death_position)
            self.end_conversation()
            self.aiming = False
            self.fire_queued = False
            self.events.publish("player_death", position=death_position, source=source)

    def respawn(self):
        self.respawn_remaining = 0
        self.city.update(self.city.hospital, eager=True)
        self.player.teleport(self.city.hospital, 90)
        self.player.health = 100
        self.player.armor = 0
        self.player.set_active(True)
        self.follow_camera.heading = 90
        self.follow_camera.update(0, self.player, snap=True)
        if self.overlay:
            self.overlay.hide_wasted()
            self.overlay.notify(self.city.hospital_name)
        self.events.publish("player_respawn", position=self.player.position)

    def toggle_conversation(self):
        if self.conversation:
            self.end_conversation()
        elif not self.occupied and not self.theft:
            person = self.peds.nearby(self.player.position)
            if person is not None:
                self.conversation = person
                self.show_conversation(self.peds.talk(person, self.player.position))

    def show_conversation(self, line):
        if self.overlay:
            self.overlay.show_dialogue(self.conversation.display_name, line,
                                       shop=self.shop_rows() if self.shop_is_open() else ())

    def end_conversation(self):
        if self.conversation is not None:
            self.conversation = None
            if self.overlay:
                self.overlay.hide_dialogue()

    def shop_is_open(self):
        return self.conversation.is_shopkeeper and self.conversation.mood not in ("afraid", "angry")

    def shop_offer(self, slot):
        offer = self.store["offers"][slot - 1]
        owned = self.weapons.owns(offer["weapon"])
        name = WEAPON_SPECS[offer["weapon"]].name
        label = f'{name}  +{offer["rounds"]} ammo' if owned else name
        return offer, owned, label, offer["ammo_price"] if owned else offer["price"]

    def shop_rows(self):
        rows = [(str(slot), label, f"${price}") for slot, (_, _, label, price) in
                enumerate((self.shop_offer(slot) for slot in range(1, 5)), 1)]
        armor_price = self.store["armor_price"]
        rows.append(("5", "Body armor", "Full" if self.player.armor >= 100 else f"${armor_price}"))
        return rows

    def buy_item(self, slot):
        if slot == 5:
            price = self.store["armor_price"]
            if self.player.armor >= 100:
                self.show_conversation("You're already covered.")
                return
            if self.player.money < price:
                self.show_conversation("Come back when you've got the cash.")
                return
            self.player.armor = 100
        else:
            offer, owned, _, price = self.shop_offer(slot)
            if self.player.money < price:
                self.show_conversation("Come back when you've got the cash.")
                return
            if owned:
                if not self.weapons.add_ammo(offer["weapon"], offer["rounds"]):
                    self.show_conversation("Your ammo reserve is full.")
                    return
            else:
                self.weapons.grant_weapon(offer["weapon"], offer["rounds"])
        self.player.money -= price
        self.show_conversation("All yours. Stay safe out there.")

    def handle_controls(self, controls):
        if self.respawn_remaining:
            return
        if controls.talk:
            self.toggle_conversation()
        if self.conversation:
            if controls.weapon_slot and self.shop_is_open():
                self.buy_item(controls.weapon_slot)
            return
        if controls.interact:
            self.interact_vehicle()
        if self.occupied:
            if controls.camera:
                self.follow_camera.toggle_vehicle_view()
        elif not self.theft:
            if controls.weapon_slot and self.weapons.select(controls.weapon_slot):
                self.refresh_held_model()
            if controls.reload:
                self.weapons.reload()
            self.jump_queued |= controls.jump
            self.fire_queued |= controls.fire_pressed

    def fire_weapon(self, pressed):
        direction = self.camera.get_quat(self.render).get_forward()
        origin = self.camera.get_pos(self.render)
        if self.weapons.selected.id == "melee":
            direction.z = 0
            direction.normalize()
            origin = self.player.position + Vec3(0, 0, 1.12)
            muzzle = None
        else:
            muzzle = self.render.get_relative_point(self.held_model, weapon_muzzle(self.weapons.selected.id))
        targets = tuple(HitTarget(vehicle, body=vehicle.body)
                        for vehicle in (*self.vehicles, *self.traffic.vehicles) if vehicle.physics_active)
        shot = self.weapons.fire(origin, direction, aimed=self.aiming, pressed=pressed,
                                 targets=targets, people=self.peds, ignore=(self.player.controller,),
                                 owner=self.player, muzzle=muzzle)
        if shot is not None:
            self.player.attack_pose()
            self.follow_camera.recoil(shot.recoil)

    def advance(self, dt, controls):
        if self.game_state != "playing":
            self.update_presentation(dt)
            return
        self.handle_controls(controls)
        self.aiming = bool(controls.aim and self.player.active and not self.conversation and not self.theft)
        self.accumulator += max(0.0, min(dt, .10))
        while self.accumulator + 1e-9 >= STEP:
            self.update_simulation(STEP, controls)
            self.jump_queued = False
            self.fire_queued = False
            self.accumulator = max(0.0, self.accumulator - STEP)
        self.update_presentation(dt)

    def update_simulation(self, dt, controls, *, advance_clock=True):
        self.weapons.update(dt)
        if advance_clock and self.theft is not None:
            self.update_carjacking(dt)
        if not self.occupied:
            can_move = not self.conversation and not self.theft
            firing = advance_clock and can_move and self.player.active and (controls.fire or self.fire_queued)
            self.player.move(controls.forward if can_move else 0, controls.side if can_move else 0,
                             self.follow_camera.heading, controls.sprint, self.jump_queued and can_move, dt,
                             aiming=self.aiming or firing)
            self.player.combat_pose(armed=self.weapons.selected.id != "melee",
                                    aiming=self.aiming or firing, pitch=self.follow_camera.pitch)
            if firing:
                self.fire_weapon(self.fire_queued)
        if advance_clock:
            walkers = (*self.peds.people, self.player) if self.player.active else self.peds.people
            self.traffic.update(dt, self.focus(), walkers, obstacles=self.vehicles,
                                night=self.lighting.night, elapsed=self.elapsed)
        for vehicle in self.vehicles:
            occupied = vehicle is self.occupied
            vehicle.update(dt, controls.forward if occupied else 0,
                           controls.side if occupied else 0, controls.jump if occupied else False,
                           occupied=occupied, night=self.lighting.night)
        self.physics.do_physics(dt, 0)
        for vehicle in self.vehicles:
            vehicle.after_physics(dt)
        self.traffic.after_physics(dt)
        self.player.animate(dt)
        if advance_clock:
            self.elapsed += dt
            self.city.set_signal_time(self.elapsed)
            focus = self.focus()
            self.peds.update(dt, self.elapsed, focus, self.player,
                             vehicles=(*self.vehicles, *self.traffic.vehicles), occupied=self.occupied)
            self.pickups.update(dt, self.player, self.weapons, focus)
            if self.respawn_remaining:
                self.respawn_remaining -= dt
                if self.respawn_remaining <= 0:
                    self.respawn()
            elif focus.z < -12 or not self.city.contains(focus.x, focus.y):
                self.recover()

    def recover(self):
        if self.occupied:
            vehicle = self.occupied
            index = self.vehicles.index(vehicle)
            if index < len(self.city.car_spawns):
                _, spawn, heading = self.city.car_spawns[index]
                vehicle.node.set_pos(spawn)
                vehicle.node.set_hpr(heading, 0, 0)
                vehicle.body.set_linear_velocity(Vec3())
                vehicle.body.set_angular_velocity(Vec3())
            else:
                self.vehicles.remove(vehicle)
                vehicle.close()
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
            self.follow_camera.update(dt, self.player, self.occupied, aiming=self.aiming)
            if (self.conversation and (not self.conversation.alive or
                                       (self.conversation.position - focus).length_squared() > 4.8 ** 2)):
                self.end_conversation()
        night = self.lighting.update(live_dt, focus, self.camera.get_pos())
        self.city.set_night(night)
        if self.overlay:
            vehicle = self.occupied
            context = self.context_prompt()
            speed, rpm, gear = (vehicle.speed_kph, vehicle.rpm, vehicle.gear) if vehicle else (0, 0, "")
            ammo, reserve = self.weapons.ammo if self.weapons.selected.id != "melee" else (None, None)
            fps = ClockObject.get_global_clock().get_average_frame_rate()
            self.overlay.update(
                dt, district=self.city.district(focus.x, focus.y), position=focus,
                heading=vehicle.heading if vehicle else self.follow_camera.heading,
                speed=speed, rpm=rpm, gear=gear, health=self.player.health,
                money=self.player.money, hour=self.lighting.hour, context=context,
                fps=fps, debug_info=f"{self.quality}  |  {len(self.city.loaded_chunks)} chunks  |  "
                f"{len(self.vehicles) + len(self.traffic.vehicles)} cars\n"
                f"{len(self.peds.people)} pedestrians  |  X {focus.x:.0f}  Y {focus.y:.0f}",
                driving=vehicle is not None, car_health=vehicle.health if vehicle else 100,
                armor=self.player.armor, weapon=self.weapons.selected.name, ammo=ammo, reserve=reserve,
                reloading=self.weapons.reload_remaining > 0, aiming=self.aiming,
            )
            if self.respawn_remaining:
                self.overlay.show_wasted(self.respawn_remaining)

    def context_prompt(self):
        if self.respawn_remaining or self.conversation:
            return ""
        if self.occupied:
            return "F   Exit vehicle"
        if self.theft:
            return "Taking the wheel"
        person = self.peds.nearby(self.player.position)
        if person is not None:
            return "E   Shop" if person.is_shopkeeper else "E   Talk"
        vehicle = self.nearby_vehicle()
        if vehicle is not None:
            return "F   Take the wheel" if self.traffic.has_driver(vehicle) else "F   Enter vehicle"
        return ""

    def tick(self, task):
        now = perf_counter()
        if self.last_frame_time is not None:
            self.performance.record(now - self.last_frame_time)
        self.last_frame_time = now
        dt = min(ClockObject.get_global_clock().get_dt(), .10)
        controls = self.sample_controls() if self.game_state == "playing" else Controls()
        self.advance(dt, controls)
        return Task.cont

    def quicksave(self):
        if self.game_state != "playing" or self.respawn_remaining:
            return
        values = {
            "schema": 2, "on_foot": list(self.player.position), "heading": self.follow_camera.heading,
            "hour": self.lighting.hour, "health": self.player.health, "money": self.player.money,
            "armor": self.player.armor, "weapons": self.weapons.snapshot(),
            "occupied": self.vehicles.index(self.occupied) if self.occupied else None,
            "vehicles": [{"kind": car.kind, "position": list(car.position),
                          "hpr": list(car.node.get_hpr()), "health": car.health}
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
        if data.get("schema") not in (1, 2) or not self.valid_vector(point) or not self.city.contains(*point[:2]):
            return
        self.occupied = None
        self.player.set_active(True)
        self.player.teleport(Vec3(*point))
        for key, low, high in (("health", 1, 100), ("armor", 0, 100), ("money", 0, 2 ** 31 - 1)):
            value = data.get(key)
            if isinstance(value, (float, int)) and low <= value <= high:
                setattr(self.player, key, int(value))
        for key, target in (("hour", self.lighting), ("heading", self.follow_camera)):
            value = data.get(key)
            if isinstance(value, (float, int)) and -100_000 <= value <= 100_000:
                setattr(target, key, value % (24 if key == "hour" else 360))
        if isinstance(data.get("weapons"), dict):
            self.weapons.restore(data["weapons"])
            self.refresh_held_model()
        records = data.get("vehicles")
        cars = dict(enumerate(self.vehicles))
        if isinstance(records, list):
            base_count = len(self.city.car_spawns)
            for car in self.vehicles[base_count:]:
                car.close()
            del self.vehicles[base_count:]
            cars = dict(enumerate(self.vehicles))
            kinds = {kind for kind, _, _ in self.city.car_spawns}
            for record_index, record in enumerate(records[:base_count + MAX_STOLEN_CARS]):
                if not isinstance(record, dict):
                    continue
                pos, hpr = record.get("position"), record.get("hpr")
                valid_pose = self.valid_vector(pos) and self.valid_vector(hpr) and self.city.contains(*pos[:2])
                car = cars.get(record_index)
                if car is None and valid_pose and isinstance(record.get("kind"), str) and record["kind"] in kinds:
                    car = Vehicle(self.render, self.physics, record["kind"], Vec3(*pos), hpr[0],
                                  audio_loader=self.vehicle_audio, events=self.events)
                    self.vehicles.append(car)
                    cars[record_index] = car
                if car is None:
                    continue
                if valid_pose:
                    car.node.set_pos(*pos)
                    car.node.set_hpr(*hpr)
                    car.body.set_linear_velocity(Vec3())
                    car.body.set_angular_velocity(Vec3())
                health = record.get("health")
                if isinstance(health, (float, int)) and 0 <= health <= 100:
                    car.health = health
        index = data.get("occupied")
        if type(index) is int and index in cars:
            self.occupied = cars[index]
            self.player.set_active(False)
        self.city.update(self.focus(), eager=True)
        self.sync_vehicles()

    def snapshot(self, path: Path):
        if not self.win:
            raise RuntimeError("Screenshot requires --offscreen.")
        if not self.win.save_screenshot(Filename.from_os_specific(str(project_file(path)))):
            raise RuntimeError(f"Could not save screenshot: {path}")

    def close(self):
        self.performance.finish()
        if self.ambience:
            self.ambience.stop()
        if self.overlay:
            self.overlay.destroy()
        self.weapons.close()
        self.pickups.close()
        self.peds.close()
        self.traffic.close()
        for vehicle in self.vehicles:
            vehicle.close()
        self.player.close()
        self.city.close()
        self.lighting.close()
        self.destroy()

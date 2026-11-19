"""Deterministic Section 2 scenarios exercised through the game's controls."""

from panda3d.core import Vec3

from game.app import Controls, STEP
from game.core.config import LOGS


def _walk_to(app, point, heading=0):
    app.player.teleport(point, heading)
    app.city.update(point, eager=True)
    app.follow_camera.heading = heading
    app.follow_camera.pitch = 0
    app.follow_camera.update(0, app.player, snap=True)


def _step(app, seconds, **inputs):
    controls = Controls(**inputs)
    for _ in range(round(seconds / STEP)):
        app.advance(STEP, controls)


def _button(app, **inputs):
    app.advance(STEP, Controls(**inputs))


def check_market(app):
    _walk_to(app, app.city.shop + Vec3(-1.05, 0, 0))
    _step(app, .40)
    assert len(app.peds.people) > 1, "Pedestrian streaming left the city empty"
    assert app.traffic.vehicles, "Traffic did not spawn near the player"
    _button(app, talk=True)
    assert app.conversation and app.conversation.is_shopkeeper, "E did not open Tideway Supply"
    app.player.money = 500
    _button(app, weapon_slot=2)
    assert app.weapons.owns("smg") and app.player.money == 365, "The store did not sell the SMG"
    _button(app, weapon_slot=5)
    assert app.player.armor == 100 and app.player.money == 310, "The store did not sell body armor"
    app.weapons.add_ammo("smg", 100_000)
    _button(app, weapon_slot=2)
    assert app.player.money == 310, "The store charged for full reserves"
    _button(app, talk=True)
    assert app.conversation is None
    _button(app, weapon_slot=2)
    assert app.weapons.selected.id == "smg", "The purchased weapon was unavailable from its slot"
    _button(app, weapon_slot=1)


def check_combat(app):
    feet = Vec3(12, -67, .19)
    _walk_to(app, feet)
    target = app.peds.spawn_at(feet + Vec3(0, 4.8, 0), "local", pinned=True)
    assert target is not None, "Could not stage a pedestrian for the combat replay"
    _step(app, .30, aim=True)
    app.camera.look_at(target.position + Vec3(0, 0, 1.64 * target.height))
    health = target.health
    magazine, reserve = app.weapons.ammo
    _button(app, aim=True, fire=True, fire_pressed=True)
    assert app.weapons.ammo == (magazine - 1, reserve), "LMB did not consume a magazine round"
    assert target.health < health - app.weapons.selected.damage, "Aimed head hit did not apply its multiplier"
    assert target.state == "knocked_down" and target.hostility > 0, "Hit reaction or hostility was lost"
    assert app.follow_camera._recoil > 0, "The shot did not recoil the camera"
    _button(app, reload=True)
    _step(app, app.weapons.selected.reload_seconds + .12)
    assert app.weapons.ammo == (magazine, reserve - 1), "Reload did not transfer a reserve round"

    gang = app.peds.spawn_at(feet + Vec3(.6, 7, 0), "gang", pinned=True)
    assert gang is not None, "Could not stage a gang pedestrian"
    armor = app.player.armor
    gang.take_damage(8, source=app.player)
    _step(app, 1.75)
    assert app.player.armor < armor and app.player.health == 100, "Retaliation did not hit the player's armor"
    cash = app.player.money
    app.events.publish("weapon_hit", target=gang, amount=250, position=gang.position,
                       owner=app.player, weapon="pistol")
    assert not gang.alive and any(item.weapon for item in app.pickups.items), "Armed NPC did not drop its weapon"
    _walk_to(app, gang.position)
    _step(app, .40)
    assert app.player.money > cash, "Approaching the dropped cash did not collect it"
    assert not any(item.weapon for item in app.pickups.items), "Approaching dropped arms did not collect them"


def check_carjacking_and_respawn(app):
    _walk_to(app, Vec3(11.5, 111, .19))
    if len(app.traffic.vehicles) >= app.traffic.cap:
        farthest = max(app.traffic.vehicles, key=lambda car: (car.position - app.player.position).length_squared())
        app.traffic.take_vehicle(farthest)
        farthest.close()
    traffic = app.traffic.spawn_on_lane((0, 0), (0, 1), distance=110)
    assert traffic is not None and app.traffic.has_driver(traffic), "Could not stage a traffic driver"
    exit_point = app.safe_exit(traffic)
    assert exit_point is not None, "The staged traffic car has no clear entry"
    _walk_to(app, exit_point, traffic.heading)
    _button(app, interact=True)
    assert app.theft and app.theft.vehicle is traffic, "F did not begin the carjacking"
    _step(app, .46)
    assert any(person.drag is not None for person in app.peds.people), "The driver did not animate out of the car"
    _step(app, .45)
    assert app.occupied is traffic and traffic in app.vehicles and not app.traffic.has_driver(traffic), "Traffic ownership was not transferred"
    _step(app, .9, forward=1)
    assert traffic.speed_kph > 5, "The stolen vehicle did not drive"

    app.save_path = LOGS / "selftest-section2-save.json"
    app.quicksave()
    count = len(app.vehicles)
    app.load_save()
    assert len(app.vehicles) == count and app.occupied is app.vehicles[-1], "The stolen car did not survive saving"
    assert app.weapons.owns("smg") and app.player.armor > 0, "The purchase or armor did not survive saving"
    app.events.publish("damage", target=app.player, amount=250, source="self-test")
    assert app.respawn_remaining > 0 and not app.player.active and not app.occupied, "Death did not release the car"
    _step(app, 3.16)
    assert app.player.active and app.player.health == 100 and app.player.armor == 0, "Respawn did not restore the character"
    assert (app.player.position - app.city.hospital).length() < .16, "Respawn missed Breakwater Clinic"


def run_city_replay(app):
    check_market(app)
    check_combat(app)
    check_carjacking_and_respawn(app)
    print("SECTION 2 REPLAY PASS | population, shop, aim/head hit, reload, retaliation, pickups, carjacking, save and clinic", flush=True)

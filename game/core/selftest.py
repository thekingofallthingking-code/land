"""Bounded integration replay using the same controls and simulation as the game."""
import math
import statistics
import time

from panda3d.bullet import BulletBoxShape, BulletRigidBodyNode
from panda3d.core import BitMask32, Vec3

from game.app import STEP, Controls
from game.core.config import LOGS, Settings, write_json


def step(app, seconds, **controls):
    for _ in range(round(seconds / STEP)):
        app.advance(STEP, Controls(**controls))


def assert_finite(app):
    vectors = [app.player.position, app.camera.get_pos(), app.camera.get_hpr()]
    for vehicle in app.vehicles:
        vectors.extend((vehicle.position, vehicle.node.get_hpr(), vehicle.body.get_linear_velocity()))
        assert math.isfinite(vehicle.rpm) and math.isfinite(vehicle.speed_kph), "Nonfinite vehicle telemetry"
        assert 0 <= vehicle.health <= 100, "Vehicle health outside its range"
    assert all(math.isfinite(value) for vector in vectors for value in vector), "Nonfinite scene transform"


def check_vehicle_clearance(app):
    vehicle = app.vehicles[0]
    box = BulletRigidBodyNode("self-test obstacle")
    box.add_shape(BulletBoxShape(Vec3(.27, .27, .24)))
    box.set_into_collide_mask(BitMask32.bit(0))
    obstacle = app.render.attach_new_node(box)
    start = app.player.position
    middle = (start + vehicle.position) / 2
    obstacle.set_pos(middle.x, middle.y, start.z + 1.0)
    app.physics.attach_rigid_body(box)
    try:
        assert app.nearby_vehicle() is None, "A barrier failed to prevent vehicle entry"
    finally:
        app.physics.remove_rigid_body(box)

    preferred = app.safe_exit(vehicle)
    assert preferred is not None, "Expected a clear starting vehicle exit"
    obstacle.set_pos(preferred + Vec3(0, 0, 1.53))
    app.physics.attach_rigid_body(box)
    try:
        other_side = app.safe_exit(vehicle)
        assert other_side is not None and (other_side - preferred).length() > 1, "Obstructed exit was selected"
    finally:
        app.physics.remove_rigid_body(box)
        obstacle.remove_node()

    app.interact_vehicle()
    assert app.occupied is vehicle
    vehicle.body.set_linear_velocity(vehicle.node.get_quat().get_right() * 8)
    try:
        app.interact_vehicle()
        assert app.occupied is vehicle, "Exit allowed while the car was sliding sideways"
    finally:
        vehicle.body.set_linear_velocity(Vec3())
    app.interact_vehicle()
    assert app.occupied is None
    app.player.teleport(start)


def run_self_test(app, duration):
    started = time.perf_counter()
    app.begin_play()
    assert app.game_state == "playing"
    assert app.nearby_vehicle() is app.vehicles[0], "The first car is out of reach at spawn"
    check_vehicle_clearance(app)
    malformed = LOGS / "selftest-settings.json"
    write_json(malformed, {"quality": []})
    assert Settings.load(malformed).quality == "", "Invalid quality setting did not fall back to defaults"
    assert not app.valid_vector([0, 0, 10 ** 500]), "Out-of-range save position was accepted"
    original = Vec3(app.player.position)
    step(app, .65, forward=-1, sprint=True)
    assert (app.player.position - original).length() > 2.5, "Sprint did not move the controller"
    ground_z = app.player.position.z
    app.advance(STEP, Controls(jump=True))
    step(app, .23)
    assert app.player.position.z > ground_z + .2, "Jump did not clear the ground"
    step(app, 1.0)
    app.set_state("paused")
    paused_position = Vec3(app.player.position)
    step(app, .3, forward=1)
    assert (app.player.position - paused_position).length() < .001, "Simulation advanced while paused"
    app.resume()

    for vehicle in app.vehicles:
        assert app.occupied is None
        exit_point = app.safe_exit(vehicle)
        if exit_point is None:
            exit_point = vehicle.position + Vec3(1.8, 0, 0)
        app.player.teleport(exit_point, vehicle.heading)
        app.advance(STEP, Controls(interact=True))
        assert app.occupied is vehicle, f"Could not enter {vehicle.node.get_name()}"
        app.advance(STEP, Controls(camera=True))
        app.advance(STEP, Controls(camera=True))
        step(app, .95, forward=1)
        assert vehicle.speed_kph > 5, f"{vehicle.node.get_name()} did not accelerate"
        step(app, .85, jump=True)
        app.advance(STEP, Controls(interact=True))
        assert app.occupied is None, f"Could not exit {vehicle.node.get_name()}"
        assert_finite(app)

    save = LOGS / "selftest-save.json"
    app.save_path = save
    app.quicksave()
    saved_position = Vec3(app.player.position)
    app.player.teleport(app.city.spawn)
    app.load_save()
    assert (app.player.position - saved_position).length() < .05, "Save position round trip failed"

    app.player.teleport(app.city.spawn)
    app.city.update(app.player.position, eager=True)
    app.sync_vehicles()
    parked_transforms = [Vec3(car.position) for car in app.vehicles]
    view_before = set(app.city.loaded_chunks)
    app.player.teleport(Vec3(650, 0, .6))
    app.city.update(app.player.position, eager=True)
    assert set(app.city.loaded_chunks) != view_before, "City chunks did not stream"
    app.sync_vehicles()
    assert not any(car.physics_active for car in app.vehicles), "Distant car physics is still active"
    step(app, .3)
    assert all((car.position - pose).length() < .01 for car, pose in zip(app.vehicles, parked_transforms)), "A parked car moved while streamed out"
    app.player.teleport(app.city.spawn)
    app.city.update(app.player.position, eager=True)
    assert set(app.city.loaded_chunks) == view_before, "City failed to reload the original neighbourhood"
    app.sync_vehicles()
    assert all(car.physics_active for car in app.vehicles), "Cars did not reactivate after streaming"
    app.lighting.hour = 1.
    app.update_presentation(0)
    assert app.lighting.night > .95, "Night cycle failed"
    app.lighting.hour = 12.
    app.update_presentation(0)
    assert app.lighting.night < .05, "Day cycle failed"

    samples = []
    max_chunks = len(app.city.loaded_chunks)
    tick_count = 0
    times_up = started + duration
    while time.perf_counter() < times_up:
        tick_start = time.perf_counter()
        phase = tick_count % 480
        app.advance(STEP, Controls(
            forward=.55 if phase < 160 else -.55 if 240 <= phase < 400 else 0,
            sprint=40 <= phase < 60, jump=phase in (20, 270),
        ))
        if not app.headless:
            app.task_mgr.step()
        samples.append(time.perf_counter() - tick_start)
        max_chunks = max(max_chunks, len(app.city.loaded_chunks))
        assert_finite(app)
        tick_count += 1
        time.sleep(max(0., tick_start + STEP - time.perf_counter()))
    assert tick_count > duration * 7, "Simulation throughput fell below 7 updates per second"
    duration_run = time.perf_counter() - started
    print(f"SELF-TEST PASS | {duration_run:.1f} s | {tick_count} scripted ticks | "
          f"{tick_count / duration_run:.1f} scripted ticks/s | "
          f"{1 / statistics.mean(samples):.1f} uncapped update FPS | "
          f"{max_chunks} peak chunks | {len(app.vehicles)} vehicles | 1 player", flush=True)
    if app.options.screenshot:
        from game.core.config import SCREENSHOTS
        from game.core.config import project_file
        project_file(SCREENSHOTS).mkdir(exist_ok=True)
        app.snapshot(SCREENSHOTS / app.options.screenshot)

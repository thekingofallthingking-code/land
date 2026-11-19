"""Scripted witnessed crime, pursuit, escape, blast and mission scenarios."""
from panda3d.core import Vec3

from game.core.config import LOGS, ROOT, read_json
from game.core.section2_replay import _button, _step, _walk_to


def _relocate_car(app, point, *, heading=None):
    car = app.occupied
    app.city.update(point, eager=True)
    car.node.set_pos(point)
    if heading is not None:
        car.node.set_hpr(heading, 0, 0)
    car.body.set_linear_velocity(Vec3())
    car.body.set_angular_velocity(Vec3())
    app.sync_vehicles()
    app.follow_camera.update(0, app.player, car, snap=True)


def _steal_witnessed_car(app):
    _walk_to(app, Vec3(11.1, 107, .19))
    if len(app.traffic.vehicles) >= app.traffic.cap:
        farthest = max(app.traffic.vehicles, key=lambda car: (car.position - app.player.position).length_squared())
        app.traffic.take_vehicle(farthest)
        farthest.close()
    car = app.traffic.spawn_on_lane((0, 0), (0, 1), distance=103)
    assert car is not None
    bystander = app.peds.spawn_at(Vec3(11.1, car.position.y + 1.5, .19), "local", pinned=True, priority=True)
    assert bystander is not None
    point = app.safe_exit(car)
    assert point is not None
    _walk_to(app, point, car.heading)
    _button(app, interact=True)
    _step(app, .88)
    assert app.occupied is car and not app.traffic.has_driver(car)
    assert app.wanted.stars >= 1, "A visible carjacking failed to register"
    return car, bystander


def exercise_pursuit(app):
    app.wanted.clear()
    app.police.clear()
    app.foot_police.clear()
    app.events.publish("gunshot", position=Vec3(-1080, -1080, 1.5), owner=app.player)
    assert app.wanted.stars == 0, "A shot with nobody nearby counted as witnessed"
    car, bystander = _steal_witnessed_car(app)
    car.body.set_linear_velocity(Vec3())
    _button(app, interact=True)
    assert app.occupied is None
    _walk_to(app, bystander.position + Vec3(0, -3.2, 0))
    app.player.armor = 100
    _button(app, weapon_slot=1)
    for _ in range(6):
        if app.wanted.stars == 3:
            break
        app.camera.look_at(app.player.position + Vec3(0, 8, 5.8))
        _button(app, aim=True, fire=True, fire_pressed=True)
        _step(app, .90)
    assert app.wanted.stars == 3, "Witnessed gunfire did not produce a three-star pursuit"
    app.enter_vehicle(car)
    _step(app, 3.4, forward=.55)
    assert app.wanted.stars == 3 and app.police.vehicles, "Cruisers did not dispatch during the chase"
    assert any(unit.speed_kph > 2 for unit in app.police.vehicles), "Cruisers stayed parked during pursuit"
    assert len(app.police.vehicles) + len(app.foot_police.officers) <= app.police_cap
    return car


def stage_chaos_benchmark(app):
    app.begin_play()
    _step(app, .2)
    exercise_pursuit(app)


def blast_ahead(app):
    target = app.focus()
    car = app.occupied
    ahead = car.node.get_quat().get_forward() if car else Vec3(0, 1, 0)
    point = target + ahead * 18
    point.z = .45
    app.explosions.detonate(point, "fuel", app.player)


def _check_arrest(app):
    app.police.clear()
    app.foot_police.clear()
    app.wanted.clear()
    _button(app, interact=True)
    assert not app.occupied
    point = app.city.spawn + Vec3(1.8, 3., 0)
    _walk_to(app, point)
    witness = app.peds.spawn_at(point + Vec3(0, 3.4, 0), pinned=True, priority=True)
    assert witness is not None
    app.events.publish("crime", kind="car_theft", position=point, offender=app.player, witnesses=(witness,))
    officer = app.foot_police.spawn_at(point + Vec3(0, 1.3, 0), heading=180)
    assert officer is not None
    cash = app.player.money
    _step(app, 1.65)
    assert app.busted and app.respawn_remaining > 0 and not app.player.active, "A stopped player could not be arrested"
    assert app.player.money == max(0, cash - 70)
    _step(app, 3.18)
    assert app.player.active and not app.busted and app.wanted.stars == 0
    assert (app.player.position - app.city.spawn).length() < .16


def run_section3_replay(app):
    seen = []

    def record(kind, witnesses, **_):
        if witnesses:
            seen.append(kind)

    app.events.subscribe("witnessed_crime", record)
    try:
        car = exercise_pursuit(app)
    finally:
        app.events.unsubscribe("witnessed_crime", record)
    assert "car_theft" in seen and "shooting" in seen
    _relocate_car(app, Vec3(3.4, -967, .75), heading=0)
    _step(app, 7)
    assert app.wanted.mode == "search", (
        f"Police did not enter search after losing sight: {app.wanted.mode}, "
        f"last seen {app.elapsed - app.wanted.last_seen_time:.1f}s ago, focus {app.focus()}, "
        f"health {app.player.health}, respawn {app.respawn_remaining:.1f}s"
    )
    _step(app, 26)
    assert app.wanted.stars == 0, "Wanted level failed to cool down away from police"
    _button(app, interact=True)
    assert app.occupied is None

    _walk_to(app, Vec3(11.1, -63, .19))
    _step(app, .25)
    prop = app.explosions.props["exchange-fuel"]
    blasts = app.explosions.blast_count
    app.explosions.detonate(prop.position, "fuel", app.player, source=prop)
    _step(app, 1.25)
    assert app.explosions.blast_count > blasts, "The fuel blast did not resolve"
    assert any(item.health <= 0 for item in app.explosions.props.values() if item is not prop), "The blast failed to chain"
    limits = read_json(ROOT / "game/data/explosions.json")["limits"][app.quality]
    for name in ("fire", "smoke", "rings", "debris", "scorch"):
        pool = getattr(app.explosions.fx, name)
        assert len(pool.active) + len(pool.ready) == limits[name], f"{name} exceeded its pooled budget"
    assert app.explosions.projectile_count <= limits["projectiles"]

    race = app.activities.missions["exchange_sprint"]
    _walk_to(app, Vec3(*race.start))
    _button(app, talk=True)
    assert app.activities.active is race, "The race did not start from its contact"
    app.enter_vehicle(car)
    cash = app.player.money
    for checkpoint in race.checkpoints:
        _relocate_car(app, Vec3(*checkpoint) + Vec3(0, 0, .76))
        _step(app, .07)
    assert race.id in app.activities.completed and app.player.money == cash + race.reward

    app.save_path = LOGS / "selftest-section3-save.json"
    app.quicksave()
    app.load_save()
    assert app.occupied is not None and race.id in app.activities.completed
    assert app.player.money == cash + race.reward
    _check_arrest(app)
    print("SECTION 3 REPLAY PASS | witnessed theft and shooting, three-star pursuit, escape, chain blast, race, save and arrest", flush=True)

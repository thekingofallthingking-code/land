"""Scene adapter that resolves witnesses against streamed actors and Bullet occlusion."""
from panda3d.core import BitMask32, Vec3

from game.core.wanted import OFFENSES

MASK = BitMask32.bit(0)


def clear_sight(physics, origin, target, ignore=()):
    hit = physics.ray_test_closest(origin, target, MASK)
    if not hit.has_hit():
        return True
    if hit.get_node() not in ignore:
        return False
    all_hits = physics.ray_test_all(origin, target, MASK)
    return all(result.get_node() in ignore for result in all_hits.get_hits())


def witnesses_for(physics, kind, position, people, drivers=(), *, ignore=(), victim=None):
    radius = OFFENSES[kind]["range"]
    position = Vec3(position)
    target = position + Vec3(0, 0, .65 if kind != "shooting" else .05)
    candidates = [
        (person, person.position + Vec3(0, 0, 1.53), None)
        for person in people
        if person.alive and person is not victim and getattr(person, "state", "") != "knocked_down"
        and (person.position - position).length_squared() <= radius ** 2
    ]
    candidates.extend(
        (vehicle, vehicle.position + Vec3(0, .05, .87), vehicle.body)
        for vehicle in drivers if vehicle is not victim and vehicle.health > 0 and vehicle.physics_active
        and (vehicle.position - position).length_squared() <= radius ** 2
    )
    candidates.sort(key=lambda item: (item[1] - position).length_squared())
    witnesses = []
    for actor, eyes, body in candidates:
        if clear_sight(physics, eyes, target, (*ignore, body)):
            witnesses.append(actor)
            if len(witnesses) >= 4:
                break
    return tuple(witnesses)

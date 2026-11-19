"""Pure combat rules shared by tests and future gameplay systems."""
import math


def damage_falloff(base: float, distance: float, radius: float) -> float:
    if radius <= 0 or base <= 0 or not all(map(math.isfinite, (base, distance, radius))):
        return 0.0
    return base * max(0.0, 1.0 - max(0.0, distance) / radius)


def apply_damage(health: float, armor: float, amount: float) -> tuple[float, float]:
    health, armor = max(0.0, health), max(0.0, armor)
    if not math.isfinite(amount) or amount <= 0:
        return health, armor
    absorbed = min(armor, amount)
    return max(0.0, health - (amount - absorbed)), armor - absorbed


def warranted_stars(current: int, severity: int, witnessed: bool) -> int:
    """Bound a witnessed offense's alert increase without side effects."""
    current = max(0, min(5, current))
    return min(5, current + max(0, severity)) if witnessed else current

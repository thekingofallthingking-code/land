"""Witness-gated crime escalation and time-based police search state."""
from math import isfinite

from game.core.config import ROOT, read_json

RULES = read_json(ROOT / "game/data/wanted.json")
OFFENSES = RULES["offenses"]
THRESHOLDS = tuple(RULES["thresholds"])


def valid_point(position):
    return isinstance(position, (tuple, list)) and len(position) == 3 and all(
        isinstance(value, (int, float)) and -10_000 <= value <= 10_000 for value in position
    )


class Wanted:
    def __init__(self):
        self.clear()

    def clear(self):
        self.heat = 0
        self.mode = "clear"
        self.last_seen = (0.0, 0.0, 0.0)
        self.last_seen_time = 0.0
        self.next_cooldown = 0.0
        self.report_times = {}

    @property
    def stars(self):
        return sum(self.heat >= threshold for threshold in THRESHOLDS)

    @property
    def search_radius(self):
        return RULES["search_base_radius"] + self.stars * RULES["search_radius_per_star"]

    def report(self, kind, position, witnesses, elapsed):
        offense = OFFENSES.get(kind)
        if offense is None or not witnesses or not valid_point(tuple(position)):
            return False
        if elapsed - self.report_times.get(kind, -float("inf")) < offense["repeat"]:
            return False
        self.report_times[kind] = elapsed
        self.heat = min(THRESHOLDS[-1], self.heat + offense["heat"])
        self.observe(position, elapsed)
        return True

    def observe(self, position, elapsed):
        self.last_seen = tuple(position)
        self.last_seen_time = elapsed
        self.mode = "pursuit"
        self.next_cooldown = 0.0

    def update(self, elapsed, visible_position=None):
        if not self.stars:
            return
        if visible_position is not None:
            self.observe(visible_position, elapsed)
            return
        unseen = elapsed - self.last_seen_time
        if unseen < RULES["loss_grace"]:
            return
        if unseen < RULES["loss_grace"] + RULES["search_seconds"]:
            self.mode = "search"
            return
        if self.mode != "cooldown":
            self.mode = "cooldown"
            self.next_cooldown = elapsed + RULES["cooldown_seconds"]
        while self.stars and elapsed >= self.next_cooldown:
            self.heat = THRESHOLDS[self.stars - 1] - 1
            self.next_cooldown += RULES["cooldown_seconds"]
        if not self.stars:
            self.clear()

    def snapshot(self, elapsed):
        return {"heat": self.heat, "last_seen": list(self.last_seen),
                "age": max(0.0, elapsed - self.last_seen_time)}

    def restore(self, data, elapsed):
        self.clear()
        if not isinstance(data, dict):
            return
        heat, point, age = data.get("heat"), data.get("last_seen"), data.get("age")
        if type(heat) is int and 0 < heat <= THRESHOLDS[-1] and valid_point(point):
            self.heat = heat
            self.last_seen = tuple(point)
            self.last_seen_time = elapsed - age if isinstance(age, (int, float)) and 0 <= age <= 240 else elapsed
            self.mode = "pursuit"
            self.update(elapsed)

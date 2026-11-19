"""Paths and an atomic local store for the manual save slots."""
from datetime import datetime

from game.core.config import ROOT, project_file, read_json, write_json

SLOT_COUNT = 3


def slot_path(slot):
    if type(slot) is not int or not 1 <= slot <= SLOT_COUNT:
        raise ValueError("Invalid save slot.")
    return ROOT / "saves" / f"slot-{slot}.json"


def store_save(path, state):
    project_file(path.parent).mkdir(exist_ok=True)
    data = dict(state, saved_at=datetime.now().astimezone().isoformat(timespec="seconds"))
    write_json(path, data)


def slot_caption(slot):
    data = read_json(slot_path(slot))
    if not data:
        return None
    saved = data.get("saved_at")
    if isinstance(saved, str):
        try:
            return datetime.fromisoformat(saved).strftime("%d %b %H:%M")
        except ValueError:
            pass
    return "Saved game"

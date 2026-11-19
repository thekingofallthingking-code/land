import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from game.core.config import DEFAULT_BINDINGS, LOGS, ROOT, read_json, rebind
from game.core.savegame import slot_path, store_save


class SaveGameTests(unittest.TestCase):
    def test_slot_round_trip(self):
        LOGS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="save-test-", dir=LOGS) as folder:
            directory = Path(folder).resolve()
            self.assertTrue(directory.is_relative_to(ROOT))
            path = directory / "slot-1.json"
            state = {"schema": 3, "on_foot": [3, 4, 0], "money": 180, "wanted": {"heat": 2}}
            store_save(path, state)
            restored = read_json(path)
        self.assertEqual({key: restored[key] for key in state}, state)
        self.assertIn("saved_at", restored)
        self.assertEqual(slot_path(3).name, "slot-3.json")
        with self.assertRaises(ValueError):
            slot_path(0)

    def test_rebinding_swaps_and_respects_fixed_shortcuts(self):
        keys = DEFAULT_BINDINGS.copy()
        self.assertTrue(rebind(keys, "forward", "a"))
        self.assertEqual(keys["forward"], "a")
        self.assertEqual(keys["left"], "w")
        self.assertFalse(rebind(keys, "fire", "f5"))

    def test_overlapping_writes_leave_one_complete_record(self):
        LOGS.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="save-test-", dir=LOGS) as folder:
            directory = Path(folder).resolve()
            self.assertTrue(directory.is_relative_to(ROOT))
            path = directory / "slot-1.json"
            states = [{"schema": 3, "inventory": [value] * 200} for value in (5, 27)]
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda state: store_save(path, state), states))
            self.assertIn(read_json(path)["inventory"], [state["inventory"] for state in states])

"""Local paths, quality presets and validated versioned persistence."""
from dataclasses import asdict, dataclass, field
import json
import logging
import os
from pathlib import Path
import platform
from tempfile import NamedTemporaryFile

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets_generated"
LOGS = ROOT / "logs"
SCREENSHOTS = ROOT / "screenshots"
PRESETS = {
    "Low": dict(shadow=0, far=420, radius=2, msaa=0),
    "Medium": dict(shadow=1024, far=630, radius=2, msaa=0),
    "High": dict(shadow=2048, far=800, radius=3, msaa=2),
}
WEAPON_KEYS = {slot: str(slot) for slot in range(1, 10)} | {10: "0", 11: "-"}

DEFAULT_BINDINGS = {
    "forward": "w", "back": "s", "left": "a", "right": "d", "sprint": "shift",
    "jump": "space", "interact": "f", "vehicle_view": "c", "talk": "e",
    "aim": "mouse3", "fire": "mouse1", "reload": "r", "cycle_weapon": "q",
}
ACTION_LABELS = {
    "forward": "Forward / accelerate", "back": "Back / brake",
    "left": "Left", "right": "Right", "sprint": "Sprint", "jump": "Jump / handbrake",
    "interact": "Vehicle entry / exit", "vehicle_view": "Vehicle view", "talk": "Interact",
    "aim": "Aim", "fire": "Fire / melee", "reload": "Reload", "cycle_weapon": "Next weapon",
}
EXTRA_KEYS = frozenset(("space", "shift", "control", "alt", "tab", "mouse1", "mouse2",
                        "mouse3", "arrow_up", "arrow_down", "arrow_left", "arrow_right"))


def rebind(bindings, action, key):
    if (action not in DEFAULT_BINDINGS or not isinstance(key, str)
            or not (len(key) == 1 and "a" <= key <= "z" or key in EXTRA_KEYS)):
        return False
    other = next((name for name, binding in bindings.items() if binding == key), None)
    if other and other != action:
        bindings[other] = bindings[action]
    bindings[action] = key
    return True


def project_file(path: Path) -> Path:
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError(f"Path resolves outside Harbor City: {path}")
    return path


def read_json(path: Path) -> dict:
    try:
        value = json.loads(project_file(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:
        logging.warning("Could not read %s: %s", path.name, error)
        return {}


def write_json(path: Path, value: dict) -> None:
    project_file(path)
    parent = project_file(path.parent)
    pending = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=parent, delete=False,
                                prefix=f".{path.name}-", suffix=".tmp") as handle:
            pending = Path(handle.name)
            json.dump(value, handle, indent=2, allow_nan=False)
            handle.write("\n")
        project_file(pending).replace(project_file(path))
    finally:
        if pending is not None:
            project_file(pending).unlink(missing_ok=True)


def memory_gib() -> float:
    if platform.system() == "Windows":
        import ctypes

        values = (ctypes.c_ulonglong * 8)()
        values[0] = ctypes.sizeof(values)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(values)):
            return values[1] / (1024 ** 3)
        return 0.0
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 ** 3)
    except (ValueError, OSError, AttributeError):
        return 0.0


def pick_quality(renderer: str, cores: int, ram: float) -> str:
    renderer = renderer.lower()
    if any(name in renderer for name in ("llvmpipe", "softpipe", "software", "swiftshader", "microsoft basic")):
        return "Low"
    if not renderer or cores < 4 or 0 < ram < 7:
        return "Low"
    if cores >= 8 and ram >= 14 and any(name in renderer for name in ("rtx", "radeon rx", "arc a")):
        return "High"
    return "Medium"


@dataclass
class Settings:
    quality: str = ""
    sensitivity: float = .22
    volume: float = .72
    bindings: dict[str, str] = field(default_factory=DEFAULT_BINDINGS.copy)

    @classmethod
    def load(cls, path: Path):
        data = read_json(path)
        result = cls()
        quality = data.get("quality")
        if isinstance(quality, str) and quality in PRESETS:
            result.quality = quality
        for key, lower, upper in (("sensitivity", .04, .7), ("volume", 0, 1)):
            value = data.get(key)
            if isinstance(value, (float, int)) and lower <= value <= upper:
                setattr(result, key, float(value))
        if isinstance(data.get("bindings"), dict):
            for action, key in data["bindings"].items():
                rebind(result.bindings, action, key)
        return result

    def save(self, path: Path) -> None:
        write_json(path, asdict(self))


def configure_logging() -> None:
    project_file(LOGS).mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(project_file(LOGS / "game.log"), encoding="utf-8"),
                  logging.StreamHandler()],
    )

"""Write local Python, package and offscreen renderer diagnostics."""

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import os
import platform
import sys

from game.core.config import LOGS, ROOT, memory_gib, project_file


def check_packages(report):
    matched = True
    requirements = project_file(ROOT / "requirements.txt").read_text(encoding="utf-8")
    for requirement in requirements.splitlines():
        requirement = requirement.partition("#")[0].strip()
        if not requirement:
            continue
        package, expected = requirement.split("==", 1)
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = "missing"
        report(f"{package}: {installed} (expected {expected})")
        matched &= installed == expected
    return matched


def check_renderer(report):
    from direct.showbase.ShowBase import ShowBase
    import numpy
    from panda3d.bullet import BulletWorld
    from panda3d.core import load_prc_file_data
    from PIL import Image
    import simplepbr

    BulletWorld()
    numpy.zeros((1,), dtype=numpy.float32)
    Image.new("RGB", (1, 1))
    if not callable(simplepbr.init):
        raise RuntimeError("The PBR renderer could not be imported")
    settings = "win-size 640 360\naudio-library-name null\nsync-video false\nnotify-level warning"
    if platform.system() == "Linux":
        settings += "\nload-display p3headlessgl"
    load_prc_file_data("harbor-city-diagnostics", settings)
    app = ShowBase(windowType="offscreen")
    try:
        if not app.win:
            raise RuntimeError("Panda3D could not create an offscreen buffer")
        app.graphicsEngine.render_frame()
        app.graphicsEngine.sync_frame()
        renderer = app.win.get_gsg()
        report(f"Offscreen buffer: {app.win.get_x_size()} x {app.win.get_y_size()}")
        report(f"Renderer: {renderer.get_driver_renderer()}")
        report(f"Driver vendor: {renderer.get_driver_vendor()}")
        report(f"Driver version: {renderer.get_driver_version()}")
    finally:
        app.destroy()


def main():
    try:
        project_file(LOGS).mkdir(exist_ok=True)
        output_path = project_file(LOGS / "diag.log")
        with output_path.open("w", encoding="utf-8", buffering=1) as output:
            def report(message):
                print(message, file=output)
                print(message, flush=True)

            report(f"Harbor City diagnostics | {datetime.now(timezone.utc).isoformat()}")
            report(f"Operating system: {platform.system()} {platform.release()} {platform.version()}")
            report(f"Architecture: {platform.machine()} | {os.cpu_count()} logical processors")
            report(f"Memory: {memory_gib():.1f} GiB")
            report(f"Python: {platform.python_version()} ({sys.executable})")
            try:
                matched = check_packages(report)
                check_renderer(report)
                if not matched:
                    raise RuntimeError("Package versions do not match requirements. Run setup.bat.")
            except Exception as error:
                report(f"FAIL - {type(error).__name__}: {error}")
                return 1
            report("PASS - Package pins, core imports, Bullet and offscreen renderer responded.")
    except (OSError, ValueError) as error:
        print(f"FAIL - Could not write diagnostics: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

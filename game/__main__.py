"""Command line for the game, bounded self-test and offscreen screenshots."""
import argparse
import logging
import math
from pathlib import Path
import platform
import time

from panda3d.core import load_prc_file_data

from game.core.config import PRESETS, SCREENSHOTS, configure_logging, project_file


def arguments():
    parser = argparse.ArgumentParser(prog="Harbor City")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--self-test", action="store_true", help="run the scripted integration test")
    mode.add_argument("--benchmark", action="store_true", help="benchmark a repeatable offscreen drive")
    parser.add_argument("--scenario", choices=("drive", "chaos"), default="drive",
                        help="benchmark normal driving or a three-star chase with a large blast")
    parser.add_argument("--offscreen", action="store_true", help="render without opening a window")
    parser.add_argument("--play", action="store_true", help="skip the title screen")
    parser.add_argument("--quality", choices=PRESETS, help="override the detected graphics preset")
    parser.add_argument("--duration", type=float, default=65., help="self-test duration or benchmark time limit in real seconds")
    parser.add_argument("--frames", type=int, default=90, help="offscreen or benchmark frame count")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--hour", type=float, help="initial local time in the city")
    parser.add_argument("--screenshot", type=Path, help="PNG filename within screenshots/")
    options = parser.parse_args()
    options.offscreen |= options.benchmark
    if options.scenario != "drive" and not options.benchmark:
        parser.error("--scenario chaos requires --benchmark.")
    if not (5 <= options.duration <= 75 and 1 <= options.frames <= 1200):
        parser.error("Duration must be 5–75 seconds and frames must be 1–1200.")
    if not (640 <= options.width <= 3840 and 360 <= options.height <= 2160):
        parser.error("Buffer size must be 640×360 through 3840×2160.")
    if options.hour is not None and not math.isfinite(options.hour):
        parser.error("Initial city time must be finite.")
    if options.screenshot and (not options.offscreen or options.screenshot.name != str(options.screenshot)
                               or options.screenshot.suffix.lower() != ".png"):
        parser.error("Use --offscreen and a plain .png filename for --screenshot.")
    return options


def apply_engine_config(options):
    settings = [
        "window-title Harbor City",
        f"win-size {options.width} {options.height}",
        "fullscreen false",
        "show-frame-rate-meter false",
        "framebuffer-srgb false",
        "textures-power-2 none",
        "notify-level warning",
    ]
    if options.offscreen or options.self_test:
        settings.extend(["sync-video false", "audio-library-name null"])
    else:
        settings.extend(["sync-video true", "audio-library-name p3openal_audio"])
    if options.offscreen and platform.system() == "Linux":
        settings.append("load-display p3headlessgl")
    load_prc_file_data("harbor-city", "\n".join(settings))


def render_frames(app, options):
    from game.app import STEP, Controls

    if options.play:
        app.begin_play()
    for _ in range(4):
        app.advance(STEP, Controls())
        app.task_mgr.step()
    started = time.perf_counter()
    for _ in range(options.frames):
        before = time.perf_counter()
        app.advance(STEP, Controls())
        app.task_mgr.step()
        app.graphicsEngine.sync_frame()
        app.performance.record(time.perf_counter() - before)
    seconds = time.perf_counter() - started
    print(f"OFFSCREEN {options.frames} frames / {seconds:.2f} s = "
          f"{options.frames / max(seconds, .0001):.1f} FPS | "
          f"{len(app.city.loaded_chunks)} chunks | {len(app.vehicles)} vehicles | {app.quality} | "
          f"{options.width}×{options.height}", flush=True)


def main():
    options = arguments()
    apply_engine_config(options)
    configure_logging()
    app = None
    try:
        from game.app import HarborCity
        app = HarborCity(options)
        if options.self_test:
            from game.core.selftest import run_self_test
            run_self_test(app, options.duration)
        elif options.benchmark:
            from game.core.benchmark import run_benchmark
            run_benchmark(app, options.frames, options.duration)
        elif options.offscreen:
            render_frames(app, options)
        else:
            app.run()
        if options.screenshot and not options.self_test:
            project_file(SCREENSHOTS).mkdir(exist_ok=True)
            app.snapshot(SCREENSHOTS / options.screenshot)
        return 0
    except Exception:
        logging.exception("Harbor City stopped")
        return 1
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())

"""Command line for the game, bounded self-test and offscreen screenshots."""
import argparse
import logging
from pathlib import Path
import platform
import time

from panda3d.core import load_prc_file_data

from game.core.config import PRESETS, SCREENSHOTS, configure_logging, project_file


def arguments():
    parser = argparse.ArgumentParser(prog="Harbor City")
    parser.add_argument("--self-test", action="store_true", help="run the scripted integration test")
    parser.add_argument("--offscreen", action="store_true", help="render without opening a window")
    parser.add_argument("--play", action="store_true", help="skip the title screen")
    parser.add_argument("--quality", choices=PRESETS, help="override the detected graphics preset")
    parser.add_argument("--duration", type=float, default=65., help="self-test duration in real seconds")
    parser.add_argument("--frames", type=int, default=90, help="offscreen frame count")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--hour", type=float, help="initial local time in the city")
    parser.add_argument("--screenshot", type=Path, help="PNG filename within screenshots/")
    options = parser.parse_args()
    if not (5 <= options.duration <= 75 and 1 <= options.frames <= 1200):
        parser.error("Duration must be 5–75 seconds and frames must be 1–1200.")
    if not (640 <= options.width <= 3840 and 360 <= options.height <= 2160):
        parser.error("Buffer size must be 640×360 through 3840×2160.")
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
        app.advance(STEP, Controls())
        app.task_mgr.step()
    seconds = time.perf_counter() - started
    if options.screenshot:
        project_file(SCREENSHOTS).mkdir(exist_ok=True)
        app.snapshot(SCREENSHOTS / options.screenshot)
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
        elif options.offscreen:
            render_frames(app, options)
        else:
            app.run()
        return 0
    except Exception:
        logging.exception("Harbor City stopped")
        return 1
    finally:
        if app:
            app.close()


if __name__ == "__main__":
    raise SystemExit(main())

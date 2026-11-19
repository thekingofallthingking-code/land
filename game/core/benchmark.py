"""Repeatable city driving benchmark for Linux and Windows graphics drivers."""
import logging
import time

from game.app import Controls

FRAME_STEP = 1 / 30
WARMUP_FRAMES = 12


def _drive_frame(app):
    app.advance(FRAME_STEP, Controls(forward=1))
    app.task_mgr.step()
    app.graphicsEngine.sync_frame()


def run_benchmark(app, frames, duration):
    app.begin_play()
    app.interact_vehicle()
    if app.occupied is None:
        raise RuntimeError("Benchmark could not enter the starting car.")

    # Place the same compact in the travel lane, clear of the parked fleet.
    app.occupied.node.set_x(3.2)
    app.occupied.node.set_y(32.0)
    app.follow_camera.update(0, app.player, app.occupied, snap=True)
    start = time.perf_counter()
    for _ in range(WARMUP_FRAMES):
        _drive_frame(app)

    for _ in range(frames):
        before = time.perf_counter()
        if before - start >= duration:
            break
        _drive_frame(app)
        app.performance.record(time.perf_counter() - before)
    results = app.performance.summary()
    if not results["count"]:
        raise RuntimeError("Benchmark timed out during warm-up.")

    renderer = app.win.get_gsg().get_driver_renderer()
    logging.info(
        "DRIVE BENCHMARK | %s | %d×%d | %s | %d/%d frames in %.2fs | "
        "%.1f average FPS | %.1fms median | %.1fms p95 | %.1fms p99 | %.0f km/h | %d chunks",
        app.quality, app.win.get_x_size(), app.win.get_y_size(), renderer,
        results["count"], frames, results["timed_seconds"], results["fps"],
        results["median_ms"], results["p95_ms"], results["p99_ms"],
        app.occupied.speed_kph, len(app.city.loaded_chunks),
    )
    if results["count"] < frames:
        raise RuntimeError("Benchmark reached its time limit. Retry with fewer --frames.")

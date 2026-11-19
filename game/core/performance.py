"""Append timestamped render and simulation timing statistics to the local log."""

from datetime import datetime, timezone
import json
import logging
import math
import os
from random import Random
from statistics import median
from time import perf_counter, time_ns

from game.core.config import LOGS, project_file


SAMPLE_LIMIT = 4096
LOG_INTERVAL = 10.0


class FrameTimings:
    """Keep exact throughput totals and a bounded, uniform percentile sample."""

    def __init__(self):
        self.count = 0
        self.seconds = 0.0
        self.longest = 0.0
        self.samples = []
        self.random = Random(0)

    def record(self, seconds):
        self.count += 1
        self.seconds += seconds
        self.longest = max(self.longest, seconds)
        if len(self.samples) < SAMPLE_LIMIT:
            self.samples.append(seconds)
        else:
            index = self.random.randrange(self.count)
            if index < SAMPLE_LIMIT:
                self.samples[index] = seconds

    def summarize(self, rate_name):
        values = sorted(self.samples)
        count = len(values)
        return {
            "count": self.count,
            "timed_seconds": self.seconds,
            "percentile_samples": count,
            rate_name: self.count / self.seconds if self.seconds else None,
            f"min_{rate_name}": 1 / self.longest if self.longest else None,
            "median_ms": median(values) * 1000 if count else None,
            "p95_ms": values[math.ceil(count * .95) - 1] * 1000 if count else None,
            "p99_ms": values[math.ceil(count * .99) - 1] * 1000 if count else None,
        }


class PerformanceLog:
    def __init__(self, *, quality, mode, renderer, width=None, height=None,
                 driver=None, gl=None, gpu_vendor=None, scenario=None, path=LOGS / "perf.log", interval=LOG_INTERVAL):
        self.path = path
        self.interval = interval
        simulation_only = mode == "headless-self-test"
        self.rate_name = "simulation_updates_per_second" if simulation_only else "fps"
        self.metadata = {
            "run_id": f"{os.getpid()}-{time_ns()}",
            "quality": quality,
            "mode": mode,
            "renderer": renderer,
            "driver": driver,
            "gl": gl,
            "gpu_vendor": gpu_vendor,
            "scenario": scenario,
            "width": width,
            "height": height,
            "timing_kind": "simulation_update" if simulation_only else "render_frame",
        }
        self.total = FrameTimings()
        self.window = FrameTimings()
        self.started = self.window_started = perf_counter()
        self.closed = False
        self.writable = True
        self.count_entities = dict
        self._write("start", 0.0)

    @classmethod
    def from_app(cls, app, options):
        if app.headless:
            return cls(quality=app.quality, mode="headless-self-test", renderer="headless")
        if options.self_test:
            mode = "offscreen-self-test"
        elif options.benchmark:
            mode = "benchmark"
        else:
            mode = "offscreen" if options.offscreen else "live"
        graphics = app.win.get_gsg()
        return cls(
            quality=app.quality, mode=mode,
            renderer=graphics.get_driver_renderer() or "unknown",
            width=app.win.get_x_size(), height=app.win.get_y_size(),
            driver=graphics.get_driver_version(),
            gpu_vendor=graphics.get_driver_vendor(),
            gl=f"{graphics.get_driver_version_major()}.{graphics.get_driver_version_minor()}",
            scenario=getattr(options, "scenario", None) if options.benchmark else None,
        )

    def _write(self, event, wall_seconds, stats=None):
        if not self.writable:
            return
        entry = {
            **self.metadata,
            "event": event,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "wall_seconds": wall_seconds,
            "entities": self.count_entities(),
        }
        if stats is not None:
            entry.update(stats)
        try:
            path = project_file(self.path)
            path.parent.mkdir(exist_ok=True)
            with path.open("a", encoding="utf-8") as output:
                output.write(json.dumps(entry, allow_nan=False) + "\n")
        except (OSError, ValueError) as error:
            self.writable = False
            logging.warning("Performance log is unavailable: %s", error)

    def record(self, seconds):
        if self.closed or not math.isfinite(seconds) or seconds <= 0:
            return
        self.total.record(seconds)
        self.window.record(seconds)
        now = perf_counter()
        if now - self.window_started >= self.interval:
            self._write("periodic", now - self.window_started, self.window.summarize(self.rate_name))
            self.window = FrameTimings()
            self.window_started = now

    def summary(self):
        return self.total.summarize(self.rate_name)

    def finish(self):
        if not self.closed:
            self.closed = True
            self._write("final", perf_counter() - self.started, self.summary())

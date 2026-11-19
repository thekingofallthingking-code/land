# Harbor City handoff

## Section 1 — World and Driving

The Section 1 P0 build is playable and tested on Linux in headless and offscreen modes. The Windows launch and Medium hardware frame-rate exit checks are open. Section 2 and Section 3 gameplay have not started. Hold Section 1 P1 gameplay integration until the Windows exit checks pass.

### Implemented and exercised

- Deterministic 2,304 × 2,304 metre city with the Exchange Quarter, Westbank, Foundry Docks, Juniper Park and South Strand. The shared graph covers roads, lanes, crossings, sidewalks and minimap coordinates. Component fixtures exercised district placement, curb and road collision, pavement seams, streaming and body cleanup.
- Fixed-step Bullet simulation with a capsule character, articulated walking and sprinting, jumping and camera collision. The compact, sport, van and cruiser models use raycast suspension, steering that tightens with speed, automatic gearing, drift and impact-based damage. A wall impact fixture took the sport from 100 to 47.54 health. The real city fixture reached 46.28 km/h before its handbrake turn.
- Eight parked cars with entry, low-speed exit and chase and hood views. Inactive cars retain their transforms and health when their chunks are unloaded. The scripted replay enters, drives and exits every car type, checks finite transforms and restores quicksave state.
- Day/night cycle, maritime fog, procedural sky, sun and moon, directional shadows and HDR bloom on Medium/High, night windows, street lamps and vehicle headlights. Offscreen daytime, nighttime, title and HUD frames were inspected. The captured 1080p Medium drive improved from 3.2 to 9.4 FPS on this host's llvmpipe software renderer. The 45 FPS Medium exit threshold remains open on suitable GPU hardware.
- Pause and controls overlays, HUD and north-up minimap, first-run quality selection, local config, logging and F5 quicksave. The headless replay exercises state changes and save reload. An OpenAL null-device fixture confirmed generated engine and tire sounds enter the playback state and stop when the vehicle streams out.
- Project-local setup and pinned Python dependencies. Clean Linux bootstrap and repeat runs passed. The pinned wheels are published for Windows x64 with Python 3.11 and 3.12. `setup.bat`, `run.bat` and `test.bat` were prepared for transfer and remain unverified under Windows.

The initial checkpoint's launcher rerun passed five unit tests and 65.0 seconds of headless gameplay replay (3,348 scripted ticks, 25 peak chunks, eight vehicles, one player). See `logs/section1-final-test.log` and `logs/section1-1080p.log` in the initial snapshot.

### Continuation checkpoint

Session resumed at 2026-11-19 20:20:29 UTC. Section 1 stays open pending native Windows checks. The continuation hardened startup, vehicle interaction and camera focus handling, and profiled the renderer and the chunk builder.

| Measurement | Initial checkpoint | Continuation |
|---|---:|---:|
| 1080p Medium, 60 synchronized driving frames on llvmpipe | 3.2 FPS | 9.4 FPS |
| Median render frame time on the same drive | 299.5 ms | 103.9 ms |
| 99th-percentile render frame time on the same drive | 490.5 ms | 149.9 ms |
| Median world startup mesh build time | 720 ms | 198 ms |
| 95th-percentile streaming chunk build time | 35.5 ms | 10.7 ms |

The baseline was extracted from the initial checkpoint archive, given the new benchmark entry point, and run with the same route and graphics backend. Both drives finished at 33 km/h with 25 streamed chunks. The 900-build streaming comparison used the same city route on both builds. A byte comparison verified identical vertices and indices for 44 meshes.

The renderer now shades static vertex-colored city surfaces directly, draws the sky after opaque geometry and extracts bloom at quarter resolution. Medium kept its native 1920×1080 scene render and shadow map. The sun's shadow map suspends overnight. Windows uses the same shader path. Its drivers remain unverified.

In-car interaction checks now cover walls between the player and the car, overhead exit obstructions and lateral slides. The replay also checks malformed graphics settings and out-of-range save positions. Focus loss now compares graphics-window handles by equality. The Windows launchers isolate inherited Python configuration and suppress installer discovery prompts. The shared launcher passed a Linux test with invalid inherited Python settings and reaped a timed-out child.

The final launcher run passed five unit tests and a 65.0-second replay with 3,257 ticks. Medium rendered a day–night–day transition and restored the sun's shadow map after dawn. High also completed an eight-frame smoke drive with 49 loaded chunks. See the continued verification logs and screenshots bundled in the optimized snapshot.

Approximate elapsed work by area, with overlap: renderer and benchmark 9 min, chunk profiling and packing 4 min, launcher hardening 3 min, input and save hardening 6 min, final verification and handoff 5 min.

### Open work

1. On the target PC, extract to `C:\Projects\HarborCity`, run `setup.bat`, `test.bat` and `run.bat --quality Medium`. Exercise mouse capture, sprint, pause/resume, F5/restart, audibly verify audio, and check F3 render FPS while driving at 1920×1080. Run the offscreen driving benchmark and record the renderer and frame times.
2. Stabilize these Windows checks and add the remaining Section 1 P1 work if budget permits. Timed signal and radio-generation utilities exist as scaffolding. Runtime signal phasing, radio, skid marks, tire smoke and rain are pending.
3. Proceed to Section 2 after the Section 1 exit checks. Build sidewalk pedestrians and lane-following traffic against `RoadGraph`, then dialogue, carjacking, weapons, pickups and death/respawn. Integrate crime dispatch, police, explosions and missions in Section 3.

### Exact commands

| Purpose | Command |
|---|---|
| Windows bootstrap | `setup.bat` |
| Windows launch | `run.bat` |
| Windows test | `test.bat` |
| Windows 1080p rendered drive | `run.bat --quality Medium --width 1920 --height 1080` |
| Windows 1080p driving benchmark | `run.bat --benchmark --quality Medium --width 1920 --height 1080 --frames 240` |
| Linux bootstrap | `timeout 600s python3 game/tools/launch.py setup` |
| Linux unit and 65-second integration suite | `timeout 95s .venv/bin/python game/tools/launch.py test` |
| Linux 1080p offscreen test | `timeout 60s .venv/bin/python game/tools/launch.py run --benchmark --quality Medium --frames 60 --width 1920 --height 1080 --screenshot medium-optimized.png` |

The project is at `/workspace/work/HarborCity` in this cloud session. The portable archive is `_snapshots/HarborCity-Section-1-optimized.zip`. The target Windows path was unavailable. Save files, settings and generated sounds stay inside the project. See `KNOWN_ISSUES.md` for the remaining verification gaps.

### Time and decisions

Session start was 2026-11-19 20:00:43 UTC. Approximate elapsed work by area, with parallel work overlapping: bootstrap and setup 6 min, procedural city/navigation 11 min, player and vehicles 10 min, audio 5 min, app/HUD/lighting integration 11 min, replay/profile and handoff 7 min. Decisions and milestone timestamps are in `PROGRESS.md`.

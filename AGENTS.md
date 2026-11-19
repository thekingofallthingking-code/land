# Harbor City agent instructions

Read `HANDOFF.md` at session start. With no handoff, start Section 1. Complete only the first unfinished section. Record start time, decisions, elapsed milestones, checkpoints and verification in `PROGRESS.md`. Keep each session within ~5 hours, with P0 by ~3h30, P1 by ~4h and the last 45–60 minutes for stabilization. Test all P0 before starting P1. With less than 15% budget left, stabilize, update the handoff and commit. Checkpoint after milestones and every 30–45 minutes. Verify that each checkpoint launches.

On Windows work inside `C:\Projects\HarborCity`. Resolve paths before moves or deletions. Use no elevation, registry, system settings or personal files. Use official PyPI for packages and only official per-user Python installation if required. Keep builds, generated files and logs local. Give every test or launch a timeout and clean up child processes.

Use original procedural art, models and audio. Keep violence arcade-style and non-graphic. Prioritize a playable, stable city. Report test evidence and unverified features separately in the handoff. Log repeated failures in `KNOWN_ISSUES.md` after three attempts.

## Commands

- Windows setup and launch use `setup.bat`, then `run.bat`.
- Windows suite uses `test.bat`, including the 65-second fixed-step integration replay.
- Windows 1080p driving benchmark uses `run.bat --benchmark --quality Medium --width 1920 --height 1080 --frames 240`.
- Offscreen preview uses `run.bat --offscreen --frames 90 --quality Medium --screenshot preview.png`.
- Linux setup uses `timeout 600s python3 game/tools/launch.py setup`. Linux suite uses `timeout 95s .venv/bin/python game/tools/launch.py test`.

## Map

`game/app.py` owns state, simulation order and interaction. `game/core` holds cameras, lighting, configuration, event bus and the replay. `game/world` owns deterministic chunks, the shared road graph and minimap. `game/entities` owns the player and vehicles. `game/ui` holds the menus and HUD. `game/tools` handles setup supervision and procedural assets. `game/data` holds versioned game definitions. See `docs/architecture.md`.

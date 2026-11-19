# Harbor City

A standalone Python driving sandbox set in a procedurally built coastal city. Section 1 establishes the open-world foundation. Explore the Exchange Quarter, Westbank, Foundry Docks, Juniper Park and South Strand on foot or in eight parked cars across four models. The city covers 2.304 km on each side.

## Windows

1. Extract the project to `C:\Projects\HarborCity`.
2. Double-click `setup.bat` with 64-bit Python 3.12 or 3.11 installed. Setup creates a local environment, installs pinned packages from PyPI and synthesizes the audio. It writes `logs\setup.log`.
3. Open `run.bat`, then select **Play** or press Enter.
4. Run `test.bat` for the pure logic unit tests and a bounded 65-second simulation replay.

## Controls

| Input | On foot | Driving |
|---|---|---|
| W / S | Forward / back | Accelerate / brake and reverse |
| A / D | Strafe | Steer |
| Mouse | Orbit camera | Orbit chase camera or look from hood |
| Shift | Sprint | |
| Space | Jump | Handbrake |
| F | Enter nearby car | Exit at low speed |
| C | | Toggle chase / hood |
| Esc | Pause / resume | Pause / resume |
| F1 / F3 | Controls / debug | Controls / debug |
| F5 | Save | Save |

Quicksaves record the player's state, the time and parked vehicles in `save.json`. The title screen restores a valid save when entering the city. The quality choice is written to `settings.json` on first launch. Use `run.bat --quality Low` for a one-run override.

## Development

Run `run.bat --offscreen --play --quality Medium --width 1280 --height 720 --frames 90 --screenshot preview.png` for a bounded offscreen capture. Generated sounds and maps live under `assets_generated`. The game needs no asset downloads.

On Linux, use `timeout 600s python3 game/tools/launch.py setup` followed by `timeout 95s .venv/bin/python game/tools/launch.py test`. Development verification and section status are in `HANDOFF.md` and `KNOWN_ISSUES.md`.

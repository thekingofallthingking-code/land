# Harbor City

Harbor City is an original, low-poly 3D action and driving game in a 2.3 × 2.3 km coastal city. Walk, talk to locals, buy equipment, drive or take over an occupied car, and lose police pursuit. The map, people, vehicles, effects and sounds are generated locally.

## Windows 10 or 11 x64

1. Extract the HarborCity folder to `C:\Projects\HarborCity`.
2. Double-click `setup.bat`. It downloads and checks a project-local Python runtime and installs the pinned packages from official sources. First setup requires network access. Setup writes `logs\setup.log`.
3. Double-click `run.bat` and choose **Play**. Use **Settings** to select Low, Medium or High and remap controls. Restart to apply a graphics preset.
4. Run `test.bat` for unit tests and a bounded 65-second offscreen replay. Run `diag.bat` for environment, dependency and graphics diagnostics in `logs\diag.log`.

## Controls

| Input | Action |
|---|---|
| W / A / S / D | Move, accelerate, steer and brake/reverse |
| Mouse | Look |
| Shift | Sprint |
| Space | Jump on foot or handbrake in a car |
| F | Enter or exit a car. Approach a slow or stopped occupied car to take it over |
| E | Talk, shop, accept a job or close dialogue |
| RMB / LMB | Aim and fire or swing |
| R | Reload |
| 1–5 | Pistol, SMG, shotgun, rifle, melee |
| 6 / 7 | Grenade or rocket launcher once purchased |
| C | Switch vehicle camera |
| Esc | Close a panel or pause |
| F1 / F3 / F5 | Controls, debug readout, quicksave |

Use **Save / Load** for three manual slots. Quick saves are separate. Saves retain inventory, armor, money, parked and stolen cars, job progress, wanted state and damaged explosive props.

## The city

Tideway Supply is north of the starting car. E opens the shop, and number keys buy guns, ammunition or armor there. Cash and dropped weapons are picked up on foot. Defeat returns you to Breakwater Clinic. An arrest clears the pursuit and releases you on Breakwater Avenue after a fine.

Witnessed crimes add wanted stars. Police pursue the reported location, deploy foot officers and set roadblocks. Breaking sight starts a search, followed by cooldown. At four stars tactical vans join. At five stars a helicopter searches with a spotlight. When sight is lost, follow the minimap marker to Lantern Lockup in Foundry Docks and press E inside the bay to lay low. Active objectives and destinations appear on the HUD and minimap.

- **Slipway Escape** begins north of spawn. Get into a pursuit, lose it and deliver the car.
- **Breakwater Bounty** starts near the shop. Find and defeat the marked gang target.
- **Exchange Sprint** starts south of the clinic. Drive through the marked gates in order before time runs out.
- **Dock Run** is the delivery job farther north of the shop.

Lantern Fuel and the barrels near it can trigger a chain of arcade explosions. A damaged car can smoke, catch fire and explode. Leave an overheating vehicle before it fails. Dawn and dusk bring rain, while locals chat in groups and use nearby benches.

## Performance and verification

```bat
run.bat --benchmark --quality Medium --width 1920 --height 1080 --frames 240
run.bat --benchmark --scenario chaos --quality Medium --width 1920 --height 1080 --frames 120
```

Each game run appends timing to `logs\perf.log`. Render entries include renderer, driver, OpenGL version, average and minimum FPS, frame-time percentiles and entity counts. Headless runs report simulation timing. F3 shows live frame rate and local population. See HANDOFF.md for Linux evidence and Windows checks.

### Linux development

```sh
timeout 600s python3 game/tools/launch.py setup
timeout 95s .venv/bin/python game/tools/launch.py test
timeout 98s .venv/bin/python game/tools/launch.py test-rendered
```

Game assets are procedural. `docs/architecture.md` maps the runtime and `docs/SECTION_3.md` records the final-section specification.

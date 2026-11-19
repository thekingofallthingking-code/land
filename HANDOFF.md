SECTION 3 COMPLETE

# Harbor City handoff

## Visual and armory update

- Linux offscreen captures show the revised street materials, storefronts, façades, harbor cranes, coast and five vehicle models. Medium and High add surface grain and rain sheen. High adds softer sun shadows. The bay displays animated waves and sky-colored reflections on all presets.
- Tideway Supply sells the Tideglass Compact (`8`), Iron Buoy (`9`), Riptide Drum (`0`) and Farline Scout (`-`). `Q` cycles owned weapons and is remappable. Offscreen checks covered shop purchases and selection, a complete burst after releasing the trigger, the Scout's aim zoom, and the new sounds through OpenAL's null device. Weapon tests cover save round trips and the new firing modes.
- All 256 chunks retain the same Bullet collision shapes, transforms and bench positions. The five vehicle types passed timed Linux driving and headlight checks. The downtown day sample kept 76 mesh nodes. Added geometry raised the sample from 115,356 to 135,018 triangles and the Linux chunk build p95 from 9.4 to 12.4 ms. Graphics budgets remain unchanged pending real-GPU timing.
- The updated Linux gate passed 24 unit tests and the 65.1-second Low 640×360 offscreen replay. The replay covered both city and chase scenarios, including 2,329 scripted ticks, a peak of 25 streamed chunks and five blasts. See `logs/polish-final-test.log`.
- A 48-frame 1080p Medium three-star chase with a chain blast completed at 5.3 average FPS and 247.8 ms p95 on Linux llvmpipe. The last sample had four cruisers, four foot officers, 38 blast particles and 21 debris. See `logs/polish-chaos-medium.log` and `logs/perf.log`. Windows GPU performance remains open.

## Verified

The previous Section 2 checkpoint was `39d2633`. Section 3 began on Linux at 2026-11-19 20:58:10 UTC. No Windows runtime was available.

- Step 0 passed five unit tests and the existing 65.0-second headless replay. Reviewed and replaced the fresh-PC setup path. The official embeddable CPython and pip downloads matched their pinned SHA-256 values. Isolated package imports, the Linux diagnostic, and the new launcher against the previous stable rendered replay passed. Install and batch execution on Windows remain open.
- P0 checkpoint `92ada3f` passed 17 unit tests and 65.0-second headless and offscreen replays. Scripted controls took a car in sight of a pedestrian, triggered wanted level three, drew moving cruisers, and exercised search, escape, blast chaining, the Exchange Sprint reward and save/reload. A staged foot officer arrested and released the player. Unit and real-city fixtures also covered witness-free events, wanted decay, damage falloff, arrest, save state, all three mission state machines, and shared-graph GPS.
- Police component runs verified a solved Bullet ram, spin and box-in approach, physical roadblocks, dismounting and retirement. A scoped blast fixture used the actual launcher and grenade projectiles, chained fuel, barrels and a car, damaged an occupant at the car, and rolled a Bullet vehicle upside down. Offscreen captures show flame, smoke, rings, pooled debris and scorched wrecks. OpenAL null playback verified siren and blast starts, attenuation and cleanup.
- The 72-frame P0 1080p Medium chase profile on Linux llvmpipe reached 6.1 average FPS, 2.6 minimum FPS, 278.0 ms p95 and 385.0 ms p99. At finish the scene held four cruisers, four foot officers, 40 blast particles and two debris. See `logs/section3-chaos-medium.log` and the runtime `logs/perf.log`.
- P1 fixtures verified four-star SWAT vans, five-star helicopter spotlight and the shared 6/9/12 police caps. The integrated Medium offscreen drive reached five stars with one helicopter, two tactical vans, one cruiser and four foot officers. Lantern Lockup accepted E after loss of sight and shortened cooldown. Day and night captures and Bullet sweeps confirmed a van fits the sheltered bay. Rain, pedestrian chats and autonomous bench use were verified in separate timed fixtures.
- Settings and save UI checks exercised quality selection, 12 key binding actions, three save slots, all seven shop rows, the wanted HUD, BUSTED and the clipped GPS overlay. Save slots and F5 use separate atomic files and preserve schema 1 and 2 compatibility.

Final Linux gate passed 19 unit tests, a 65.0-second headless replay (2,904 sampled ticks), and a 65.0-second Low 640×360 offscreen replay (2,440 sampled frames, 47.9 measured FPS). No windowed smoke was used. The diagnostic imported all five exact pins, constructed Bullet and probed Mesa OpenGL 4.5.

The final 1080p Medium three-star dusk stress captured 72 frames with a large chain blast. llvmpipe reached 7.4 average FPS, 2.1 minimum FPS, 117.1 ms median, 200.2 ms p95 and 470.2 ms p99. The final frame sample counted four cruisers, four foot officers, 40 blast particles and two debris. These are software-renderer observations. Presets and caps remain the hardware-policy choices.

The original Section 3 archive is `_snapshots/HarborCity-Section-3.zip`. Download the `main` branch ZIP from GitHub for the visual and armory update.

## Needs checking on Windows

- **Setup from scratch.** On a clean Windows 10/11 x64 PC, double-click `setup.bat`. Check `logs\setup.log` and run `diag.bat`. Setup uses built-in PowerShell before Python is available, verifies official downloads, and installs the runtime and packages under `.venv\portable`. Check that the bundled runtime launches and the dependency wheels import on that PC.
- **Launch and input.** Run `run.bat` and `test.bat`. Exercise mouse capture, focus, pause, remapping, restart after switching quality, F5, and a manual save/load slot.
- **Audible sound.** Listen to engine, horn, crowd, shot, siren and near/far blast audio through the PC's output. Check the four new weapon reports and the Scout's zoom with the live controls.
- **Real-GPU FPS.** Run the 1080p Medium chase benchmark below, drive with F3 open, and return `logs\perf.log`. It records graphics vendor, renderer, driver/GL, average/minimum FPS, p95/p99, and population/effect counts. Existing 45 FPS Medium target remains to be checked on the target PC.
- **Handling and chase feel.** Verify steering, braking, reversing, drift, hood camera, vehicle exit, PIT response, five-star escape, roadblocks and arrest timing on the intended hardware.

## Partial

P2 motorbikes, interiors and extra districts are deferred. Native Windows verification and hardware-based preset tuning remain open.

## Known bugs

Some shoulder surfaces show minor overlap in the close aiming pose. See KNOWN_ISSUES.md for retained verification gaps.

## Decisions

The simulation remains fixed-step and independent of rendering. Crime reports with supplied witnesses use that evidence. The existing Section 2 reports generally carried actor and position, so scene queries resolve witnesses and occlusion. The police route toward the last observed position and the scripted replay stages escapes and race arrivals to exercise deterministic transitions. No preset or spawn budget was derived from software-renderer FPS. The launcher, effects caps and runtime evidence stay inside the project.

## Next steps by priority

1. Exercise fresh setup, launch, diagnostics and both save paths on Windows.
2. Collect real-GPU chase timing and handling/audio feedback. Use those results for hardware-specific tuning.
3. Consider P2 content if requested.

## Exact commands

| Purpose | Command |
|---|---|
| Clean Windows setup | `setup.bat` |
| Windows game | `run.bat` |
| Windows offscreen suite | `test.bat` |
| Windows diagnostics | `diag.bat` |
| Windows 1080p Medium stress | `run.bat --benchmark --scenario chaos --quality Medium --width 1920 --height 1080 --frames 120` |
| Linux headless | `timeout 95s .venv/bin/python game/tools/launch.py test` |
| Linux offscreen | `timeout 98s .venv/bin/python game/tools/launch.py test-rendered` |
| Linux 1080p stress | `timeout 65s .venv/bin/python -m game --benchmark --scenario chaos --quality Medium --width 1920 --height 1080 --frames 72` |

## Time per area

Start and checkpoint times are in PROGRESS.md. Overlapping work took approximately 5 minutes for Step 0 and launcher/diagnostic review, 7 for wanted and police, 8 for blast and projectile work, 6 for missions, 6 for menu/settings and persistence, 8 for P1 and 8 for staged replays, profiling and release verification.

The follow-up on visual and weapon polish used approximately 8 minutes of overlapping implementation and 6 minutes of regression, previews and documentation.

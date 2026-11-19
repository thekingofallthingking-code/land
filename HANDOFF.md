# Harbor City handoff

## Section 2 — The City Comes Alive

Started 2026-11-19 20:35:50 UTC from `de03a1b`. The user authorized the Linux workspace as the project root and moved development to Section 2 ahead of Windows testing. Section 1 optional skid marks, rain, and radio were skipped. The Section 2 runtime drives the traffic lights.

### P0 build

- Capped pedestrians stream along the existing sidewalks and wait for their crossing phase. Five procedurally dressed archetypes idle, walk and run. Gunfire and threatening cars trigger panic. Actors can flee, hold a grudge, insult the player, fall, recover, and drop cash on defeat. Armed gang characters shoot back when they have line of sight.
- Press E to speak to nearby pedestrians. Tideway Supply sells guns, reserve ammo and body armor. NPC dialogue varies with mood, and hostility fades over time. Active NPC memories live in the streamed simulation.
- Lane-following Bullet traffic follows signals, turns, avoids cars, yields, honks and flees attacks. Press F at a stopped or slow occupied car to draw the driver out and take over its physics body. A displaced driver flees or fights.
- Arcade pistol, SMG, shotgun, rifle and melee share camera aiming, recoil, spread, magazines, reserve ammo, head hits and pooled muzzle, tracer and impact effects. The player starts with a pistol and melee. Buy the other slots at Tideway Supply.
- Armor absorbs damage, and death returns the player to Breakwater Clinic after the WASTED screen. Pick up dropped cash and weapons by walking close. Save schema 2 records inventory, armor and stolen cars. Section 1 schema 1 saves still load.
- `logs/perf.log` appends one JSON object per line. Rendered runs record FPS and median, p95 and p99 frame times, with renderer, preset and resolution. A run records start, ten-second samples and a final entry on normal shutdown. Headless replay records simulation updates per second and timing percentiles.

### Verification

Linux setup reran successfully with all five exact dependency pins and synthesized the new audio. Component fixtures covered crossing phases, vehicle hits, line-of-sight retaliation, stationary and moving traffic, all weapon slots, reloads, head/body hits, cover, and carjacking. OpenAL's null backend confirmed sound playback state and cleanup. Daylight, gunfire HUD, marketplace UI, clinic and hospital UI were rendered and inspected during component and integration checks.

The bounded integrated replay checks commerce, aim and recoil, reload transfer, armed retaliation, cash and weapon pickup, showing the dragged driver, taking over and driving the same car, save reload, defeat and clinic respawn. Section 1 driving and streaming checks remain in the suite.

### Needs checking on Windows

- **Launch and input.** Run `setup.bat`, `test.bat` and `run.bat` on Windows. Exercise focus loss, mouse capture, firing, pause/resume and F5 save followed by restart.
- **Audio.** Listen to engine, tire, crash, horn, weapon and dialogue-area ambience through the PC's actual audio output.
- **Real-GPU FPS.** Run the 1080p Medium benchmark below and drive interactively with F3. Return `logs\perf.log`, including the renderer and completion statistics. The Section 1 target was 45 FPS on Medium. Linux used llvmpipe.
- **Handling feel.** Check steering, brake and reverse transition, handbrake drift, both vehicle cameras, exit clearance and the slow-car carjacking animation with your preferred input and hardware.

### Commands

| Purpose | Command |
|---|---|
| Windows setup and play | `setup.bat` then `run.bat` |
| Windows suite | `test.bat` |
| 1080p Medium drive | `run.bat --benchmark --quality Medium --width 1920 --height 1080 --frames 240` |
| Linux suite | `timeout 95s .venv/bin/python game/tools/launch.py test` |
| Linux rendered integration | `timeout 55s .venv/bin/python -m game --self-test --offscreen --duration 18 --width 720 --height 405 --quality Low` |

### Next work

Finish the Section 2 optional features and stabilization within this session. Section 3 will add witnessed wanted escalation, police pursuit, explosives and further missions after this handoff. No Windows test has been performed in this session.

### Time

Session start and time checks are in PROGRESS.md. Approximate work by area, overlapping in parallel: pedestrians and data 10 min, traffic 10 min, weapons and audio 10 min, landmarks and HUD 5 min, performance logger 3 min, app integration and replay 13 min.

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

### P1 delivered

- Dock Run begins at the gold marker north of Tideway Supply. Accept with E, take a car with a driver, and stop in the marked Foundry Docks bay to earn $240. The objective banner and minimap marker follow the job. Active and completed job state is saved.
- Benches have batched original geometry, collision and streamed seat anchors. Proximity-mixed procedural crowd ambience and capped, fading bullet marks on static scenery are in the build.
- Autonomous group chatting and sitting on benches were deferred when a worker hit the usage limit. The handoff retains the P0 checkpoint and the stabilized P1 work.

### Verification

Linux setup reran successfully with all five exact dependency pins and synthesized the new audio. Component fixtures covered crossing phases, vehicle hits, line-of-sight retaliation, stationary and moving traffic, all weapon slots, reloads, head/body hits, cover, and carjacking. OpenAL's null backend confirmed sound playback state and cleanup. Daylight, gunfire HUD, marketplace UI, clinic and hospital UI were rendered and inspected during component and integration checks.

The final replay passed five unit tests and **65.0 seconds headless** (3,471 sampled ticks). The **20.0-second offscreen** replay passed at 720×405 Low (903 sampled frames). The bounded integrated replay checks commerce, aim and recoil, reload transfer, armed retaliation, cash and weapon pickup, showing the dragged driver, taking over and driving the same car, save reload, Dock Run and its payout, defeat and clinic respawn. The replay stages the delivery arrival with the real stolen car and verifies the reward exactly once. Section 1 driving and streaming checks remain in the suite. A 60-frame 1080p Medium drive measured 8.2 FPS on llvmpipe with 115.3 ms median, 151.0 ms p95 and 202.4 ms p99. Baseline and final checks were run headless or offscreen. Game source parsed with Python 3.11 syntax.

### Needs checking on Windows

- **Launch and input.** Run `setup.bat`, `test.bat` and `run.bat` on Windows. Exercise focus loss, mouse capture, firing, pause/resume and F5 save followed by restart.
- **Audio.** Listen to engine, tire, crash, horn, weapon and crowd ambience through the PC's actual audio output.
- **Real-GPU FPS.** Run the 1080p Medium benchmark below and drive interactively with F3. Return `logs\perf.log`, including the renderer and completion statistics. The Section 1 target was 45 FPS on Medium. Linux used llvmpipe.
- **Handling feel.** Check steering, brake and reverse transition, handbrake drift, both vehicle cameras, exit clearance and the slow-car carjacking animation with your preferred input and hardware.

### Commands

| Purpose | Command |
|---|---|
| Windows setup and play | `setup.bat` then `run.bat` |
| Windows suite | `test.bat` |
| 1080p Medium drive | `run.bat --benchmark --quality Medium --width 1920 --height 1080 --frames 240` |
| Linux suite | `timeout 95s .venv/bin/python game/tools/launch.py test` |
| Linux rendered integration | `timeout 55s .venv/bin/python -m game --self-test --offscreen --duration 20 --width 720 --height 405 --quality Low` |

### Next work

Section 2 P0 is complete. Section 3 is next when requested, starting with witnessed wanted escalation, police pursuit, explosives and further missions. Autonomous NPC group chatting and bench use remain optional Section 2 work. No Windows test has been performed.

The project is at `/workspace/work/HarborCity`. The local transfer package is `_snapshots/HarborCity-Section-2.zip`. The Section 2 P0 checkpoint is `3f50d94`.

### Time

Session start and time checks are in PROGRESS.md. Approximate work by area, overlapping in parallel: pedestrians and data 10 min, traffic 10 min, weapons and audio 10 min, landmarks and HUD 5 min, performance logger 3 min, app integration and replay 13 min.

Optional work and final QA overlapped. Dock Run and its replay took about 4 min. Benches, crowd audio and decals took about 4 min. Final tests, profiling, visual inspection and packaging took about 4 min.

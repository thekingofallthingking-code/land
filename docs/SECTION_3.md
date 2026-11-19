# Section 3 — Chaos, Police and Polish

## Environment and Step 0

Target a fresh Windows 10/11 PC. Running setup.bat alone must install everything, without admin or manual steps. Record the actual host OS. Label Windows checks as unverified unless performed on Windows. Use real-GPU numbers from HANDOFF.md or logs/perf.log to tune quality and entity caps when available. Software-renderer measurements are evidence only.

Stay within the project folder. Use official package sources, timeouts on every run, original assets, no gore, and no admin, registry or PATH changes. Leave no tests or game processes running.

Within the first 20 minutes, rerun the existing unit suite and headless replay and fix regressions. Review setup.bat, run.bat, test.bat and diag.bat for fresh-Windows Python discovery, Microsoft Store stubs, quoting and ASCII CRLF wrappers. Keep the launch logic in tools. Record Windows verification gaps.

## P0

Develop and checkpoint playable slices in order where practical. Start optional work after the P0 gate.

- Wanted stars 1–3. Witnesses determine whether shooting, killing, car theft, hit-and-run, explosions and attacking police count. Consume the event bus evidence, model last known position and search area, and cool down after losing line of sight.
- Cruisers use the shared road graph to pursue, ram or turn the target car, box it in and set ahead roadblocks. Foot officers chase, shoot and arrest. Enforce despawn rules and a maximum of 12 police with a lower cap on Low.
- Cars progress through smoke, fire and explosion. Include explosive barrels and fuel stations, grenades and a rocket launcher, pooled fireball sprites, smoke columns, shockwaves and capped debris. Apply damage falloff, physics impulses, chain reactions, burning wrecks, scorch decals, camera shake and positional audio. Explosions can be witnessed crimes.
- Getaway, target takedown and street race missions use objectives, shared-graph GPS routes and rewards. Integrate money, the shop, F5 quicksave and a proper save slot.
- Finish menus, quality selection, key rebinding, balance, performance, bug sweep and the README.

## P1 and P2

P1 adds stars 4–5, SWAT vans, a helicopter spotlight, weather and a place to shake the cops. NPC group chatting and autonomous bench use are optional if time remains. P2 covers motorbikes, interiors and extra districts.

## Exit and testing

The playthrough must let a player steal a car, commit witnessed crimes, reach a three-star chase, escape or get busted, trigger an explosion, finish a mission and save/reload. Use fixed seeds and keep simulation independent of rendering. Unit-test witness and wanted thresholds and cooldown, damage falloff, arrest, mission states and save/load. test.bat runs a bounded 60–90 second scripted offscreen case exercising the playthrough, validating finite state and caps and reporting frame rates and entity counts. Prefer offscreen. At most one windowed smoke launch, hard-timeout 15 seconds.

Store police, explosion and mission tuning in JSON and communicate through the event bus. Every run appends timestamp, GPU/driver/GL, preset, average/minimum FPS, p95/p99 and entity counts to logs/perf.log. Profile a three-star pursuit with a large explosion and trim effects before removing P0 behavior.

## Budget and handoff

Plan Step 0 by ~0:20, P0 by ~3:30, P1 by ~4:00, then stabilize and document. Record decisions and timing in PROGRESS.md. On a usage warning or under 15% remaining, stop new features and prepare a launching checkpoint with README and handoff. Commit each milestone or use a project snapshot if Git is unavailable.

HANDOFF.md starts with SECTION 3 COMPLETE or SECTION 3 PARTIAL and covers Verified, Needs checking on Windows, partial work, known bugs, decisions, next steps, exact commands and time per area. Use BLOCKED.md only for a complete blocker. Final chat is at most 15 lines.

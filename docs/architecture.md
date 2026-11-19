# Architecture

`game.app.HarborCity` owns engine startup, input, and simulation ordering. The menu and pause states leave the city loaded. The game runs fixed 60 Hz Bullet steps with a bounded catch-up window. Camera and UI update after the simulation.

`game.world.City` owns deterministic chunk geometry and static Bullet bodies. `RoadGraph` owns shared road, crosswalk and lane locations. The minimap is generated from that graph. Coordinates and spawn points use metres, +Y is north and +Z is up.

`game.entities` owns the player controller and Bullet vehicles. `game.core.events.EventBus` is the synchronous gameplay boundary. Publishers use named payloads and callbacks run on the game thread. Vehicle impacts publish `damage`; future systems can publish `gunshot`, `crime` and `explosion`.

Vehicle tuning lives in `game/data/vehicles.json`. Weapons, archetypes, dialogue and missions have their own versioned JSON files. The Section 2 systems load those files at runtime.

`game.tools.assets` synthesizes audio inside the project. `game.tools.launch` supervises Windows game and test processes. Save and configuration JSON are project-local.

## Living city

`game.ai.pedestrians` owns streamed walk routes, reactions and analytic hit regions. `game.ai.traffic` owns active Bullet drivers and route control. Carjacking releases the traffic controller and keeps the same physics vehicle in the app's parked and owned fleet.

`game.entities.weapons` reads the weapon catalogue, owns inventory and resolves hit rays. `game.fx.combat` pools flash, tracer, impact and decal nodes. Weapon, damage, cash and theft events connect the independent systems. `game.missions.delivery` listens for a carjacking and resolves Dock Run against the saved vehicle identity.

`game.core.performance` appends timestamped frame or simulation statistics to `logs/perf.log`. Replay and benchmark modes share the same fixed-step entry point.

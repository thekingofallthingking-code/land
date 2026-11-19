# Architecture

`game.app.HarborCity` owns engine startup, input, and simulation ordering. The menu and pause states leave the city loaded. The game runs fixed 60 Hz Bullet steps with a bounded catch-up window. Camera and UI update after the simulation.

`game.world.City` owns deterministic chunk geometry and static Bullet bodies. `RoadGraph` owns shared road, crosswalk and lane locations. The minimap is generated from that graph. Coordinates and spawn points use metres, +Y is north and +Z is up.

`game.entities` owns the player controller and Bullet vehicles. `game.core.events.EventBus` is the synchronous gameplay boundary. Publishers use named payloads and callbacks run on the game thread. Vehicle impacts publish `damage`; future systems can publish `gunshot`, `crime` and `explosion`.

Vehicle tuning lives in `game/data/vehicles.json`. Weapons, archetypes, dialogue and missions have their own versioned JSON files. The combat and mission data are prepared for the next sections and have no runtime consumers in Section 1.

`game.tools.assets` synthesizes audio inside the project. `game.tools.launch` supervises Windows game and test processes. Save and configuration JSON are project-local.

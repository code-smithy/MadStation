# Phase 4 Split Plan

Phase 4 is started with a deterministic NPC survival core before broader behavior systems.

## Phase 4A (implemented in this iteration)

- Added 10 named persistent NPCs in world state initialization.
- Added deterministic NPC attributes including bounded speed in `[1,4]`.
- Added survival-first NPC movement using diagonal neighbors (8-way candidate evaluation).
- Added suffocation damage and permanent death handling.
- Added automatic `DisposeBody` work-order creation on NPC death.
- Added NPC/death/work-order delta outputs through:
  - `delta_tick.entity_changes` (movement/survival/death markers),
  - `delta_tick.work_order_changes`,
  - `delta_tick.death_log_appends`.

## Phase 4B (next)

- Replace local oxygen-gradient movement with full pathfinding.
- Add needs model and personality modifiers (without overriding survival constraints).
- Add richer death metadata and body lifecycle progression.

## Exit target for Phase 4

- NPC roster persists and updates deterministically.
- NPCs prefer safer oxygen states when available.
- Deaths are permanent, logged, and produce cleanup work orders.

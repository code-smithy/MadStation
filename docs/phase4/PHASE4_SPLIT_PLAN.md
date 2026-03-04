# Phase 4 Split Plan

Phase 4 is started with a deterministic NPC survival core before broader behavior systems.

## Phase 4A (implemented in this iteration)

- Added 10 named persistent NPCs in world state initialization.
- Added deterministic NPC attributes including bounded speed in `[1,4]`.
- Added survival-first NPC movement using diagonal neighbors (8-way evaluation) with deterministic oxygen-aware path search.
- Added suffocation damage and permanent death handling.
- Added automatic `DisposeBody` work-order creation on NPC death.
- Added deterministic `DisposeBody` work-order assignment/execution baseline (assign, progress, complete, requeue on assignee death).
- Added deterministic needs drift (`hunger`, `fatigue`) with `npc_need_state` events.
- Added personality modifier baseline (`diligent` work-progress boost) while preserving survival-first behavior.
- Added NPC/death/work-order delta outputs through:
  - `delta_tick.entity_changes` (movement/survival/death markers),
  - `delta_tick.work_order_changes`,
  - `delta_tick.death_log_appends`.

## Phase 4B (completed in this iteration)

- Upgraded to task-aware pathfinding behavior for `DisposeBody` assignment and execution with deterministic nearest-reachable selection and re-queue on path invalidation. ✅
- Expanded baseline needs/personality model while preserving survival-first constraints. ✅
- Added richer death metadata and body lifecycle progression (`body_created`/`body_disposed`, disposal linkage on completed `DisposeBody`). ✅

## Exit target for Phase 4

- NPC roster persists and updates deterministically.
- NPCs prefer safer oxygen states when available.
- Deaths are permanent, logged, and produce cleanup work orders.
- Active body lifecycle state is observable and deterministic.

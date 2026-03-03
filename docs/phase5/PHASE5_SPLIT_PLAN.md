# Phase 5 Split Plan

Phase 5 is being split into foundational logistics first, then full life-support chain integration.

## Phase 5A (implemented in this iteration)

- Added command-applied `CreateWorkOrder` world mutation path (queued work orders now enter authoritative state).
- Added physical item/state scaffolding:
  - `world.items`,
  - `world.storages` with inventory lists,
  - runtime `item_count` metric.
- Added baseline logistics execution hooks in NPC loop:
  - `MineIce` completion creates physical item records,
  - auto-creates queued `HaulItem` orders to nearest storage,
  - `HaulItem` completion stores items into storage inventories.
- Preserved deterministic ordering for assignment and completion side effects.

## Phase 5B (implemented in this iteration)

- Expanded work-order command schema and validation for item/machine chains (`MineIce`, `HaulItem`, `RefineIce`, `FeedOxygenGenerator`) with required metadata checks. ✅
- Added initial refinement/feed stages with physical item transformation and consumption semantics (`RefineIce` -> `WaterUnit`, `FeedOxygenGenerator` consumes water). ✅
- Added deterministic collision/replan behavior for competing NPCs on the same logistics chain (loser unassigned/requeued; unavailable item orders cancel). ✅

## Exit target for Phase 5

- Work orders drive physical item state transitions (no abstract pool).
- Storage inventories reflect deterministic haul/placement outcomes.
- Core life-support logistics chain can be executed end-to-end.

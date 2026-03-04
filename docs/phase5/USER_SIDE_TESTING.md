# Phase 5 User-Side Testing

This checklist validates Phase 5 end-to-end logistics/work-order behavior on the default map.

## Prerequisites

1. Start the API/server as documented in `README.md`.
2. Open a websocket client to observe `delta_tick` payloads.
3. Keep `/world` responses open for periodic inspection.

## End-to-end chain validation

1. Submit `CreateWorkOrder` for `MineIce` at an interior walkable tile.
2. Confirm queued/assigned order transitions for:
   - `MineIce`,
   - auto `HaulItem`,
   - auto `RefineIce`,
   - auto `HaulItem` for water,
   - auto `FeedOxygenGenerator`.
3. Confirm physical state transitions:
   - `IceChunk` created then consumed by `RefineIce`,
   - `WaterUnit` created then consumed by `FeedOxygenGenerator`,
   - storage inventory reflects hauled items.

## Generator coupling and power gating checks

1. Ensure a feed order targets a generator location (`generator_location`).
2. With generator powered, verify feed order completes and local compartment oxygen rises.
3. Remove power (or disable generator) and verify feed orders requeue with deterministic reason:
   - `generator_unpowered`, or
   - `generator_missing_or_disabled`.

## Determinism and collision checks

1. Create two competing logistics orders for the same item.
2. Verify deterministic winner/loser behavior (loser unassigned/requeued or cancelled per item availability).
3. Repeat same command sequence and verify materially identical order/item outcomes.

## Success criteria

- End-to-end Phase 5 chain executes with physical items and work orders only (no abstract teleport/resource pool shortcuts).
- Feed behavior is tied to powered generator machines.
- Collision handling remains deterministic and observable in `work_order_changes`.

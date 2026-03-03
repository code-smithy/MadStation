# Phase 3 Split Plan

Phase 3 is split into two slices to keep deterministic behavior stable while expanding systemic complexity.

## Phase 3A (completed in this iteration)

- Global power model on top of machine registry.
- Source handling:
  - `SolarPanel` generation,
  - `Reactor` generation,
  - `Battery` deficit discharge and surplus charging.
- Consumer allocation by priority tier with deterministic ordering.
- Power state observability in world snapshot/runtime status:
  - generation/demand,
  - battery discharge/charge,
  - powered/unpowered consumer lists,
  - disabled priority tiers.
- Oxygen generator production now requires power availability.

## Phase 3B (completed in this iteration)

- Added additional consumer classes and configurable tier policy from runtime constants. ✅
- Added topology-aware power-network segmentation by connected compartments with per-network allocation. ✅
- Added richer failure events (brownout/blackout/recovery markers) in protocol `delta_tick.entity_changes`. ✅
- Added deterministic coverage for deficit shedding and recovery ordering. ✅

## Exit target for Phase 3

- Deficits reliably shed lower tiers first.
- Batteries bridge shortfalls and recharge on surplus.
- Life support power dependencies are observable and test-covered.
- Disconnected topology islands do not share generation/storage across networks.


## Phase 3 completion check

- Lower-priority consumers are shed first under deficit and recover deterministically after generation returns. ✅
- Topology-isolated networks do not share generation/storage across disconnected compartments. ✅
- Brownout/blackout/recovery events are emitted in `delta_tick.entity_changes`. ✅

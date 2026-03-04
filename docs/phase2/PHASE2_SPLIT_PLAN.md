# Phase 2 Split Plan

Phase 2 is split into two implementation slices to keep risk low and preserve deterministic behavior while expanding simulation depth.

## Phase 2A (this step)

- 50x50 structural grid represented in authoritative world state.
- Structural command effects wired into tick execution:
  - `Build` mutates target tile type,
  - `Deconstruct` converts target tile to vacuum.
- Compartment flood-fill recomputation on topology change.
- Compartment-level oxygen pressure drift from vacuum exposure (leak model).
- Delta payload now includes tile mutation records for applied structural commands.
- Runtime status now includes `compartment_count` for observability.

## Phase 2B (completed)

- Door state model (`open/closed`) with deterministic auto-open/close baseline rules. ✅
- Explicit diffusion between compartments through open door boundaries. ✅
- Exterior/interior zoning improvements (station grid + asteroid field semantics). ✅
- Machine hooks for oxygen generation into compartment model. ✅
- Additional invariants and replay tests for compartment transitions continue under ongoing regression maintenance (tracked outside Phase 2 completion gate). ✅

## Why split

- Compartment topology and oxygen dynamics are correctness-critical and easier to validate before adding door-state transitions and machine coupling.
- This keeps Phase 2 progress visible while reducing regression risk in core tick determinism.


## Baseline map update (post-Phase-2 validation)

- Default world initialization now uses a large vacuum exterior plus an enclosed square station interior (wall perimeter, floor interior).
- NPCs spawn inside the station interior to improve deterministic decompression/compartment testability.

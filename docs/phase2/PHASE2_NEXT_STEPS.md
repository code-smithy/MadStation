# Phase 2 Remaining Work (After 2B progress)

## Completed in this iteration

- Deterministic door state model with auto-open/auto-close baseline behavior.
- Diffusion between compartments through open-door boundaries.
- Oxygen generation hooks at compartment level via `OxygenGenerator` machine integration.
- Added tests for closed-door split behavior, open-door diffusion, and door auto-state transitions.

## Remaining 2B/Phase-3-facing Tasks

1. **Topology/compartment invariants**
   - Add tests for split/merge transitions and oxygen conservation constraints.

2. **Protocol and UI-support data**
   - Include optional compartment-change summaries in deltas for easier client rendering/debug.

## Suggested test additions

- Compartment split and merge regression tests.
- Door open/close behavior tests.
- Diffusion convergence tests between adjacent compartments.
- Determinism replay test across longer command streams.
- End-to-end websocket lifecycle smoke test in a dependency-complete environment.

## User-side validation target for 2B

- Build a sealed room with a door.
- Toggle/open door and observe oxygen equalization across connected compartments.
- Close door and verify independent pressure behavior.

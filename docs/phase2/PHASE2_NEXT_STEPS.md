# Phase 2 Remaining Work (After 2A)

## 2B Engineering Tasks

1. **Door state system**
   - Track door open/closed state separately from tile type.
   - Introduce deterministic auto-open/auto-close behavior.

2. **Diffusion model**
   - Add oxygen diffusion between connected compartments through open door boundaries.
   - Keep leak-to-vacuum and diffusion as distinct terms in oxygen update.

3. **Environment hooks for life support machines**
   - Define oxygen generation injection points at compartment level.
   - Keep implementation deterministic and tick-order-stable.

4. **Topology/compartment invariants**
   - Add tests for split/merge transitions and oxygen conservation constraints.

5. **Protocol and UI-support data**
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

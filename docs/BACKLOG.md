# MadStation Backlog

This backlog tracks work intentionally deferred after Phase 7 completion.

## Scope

- Source of truth for follow-on implementation work after the Phase 2–7 MVP pass.
- Items are copied from `IMPLEMENTATION_PLAN.md` and expanded with actionable outcomes.

## Prioritized Items

### P1 — Temperature gameplay (heaters/coolers + machine heat)
- **Problem:** Simulation currently has oxygen/power but no thermal gameplay loop.
- **Goal:** Add deterministic compartment temperature simulation with vacuum cooling, machine waste heat, and powered HVAC control.
- **Done when:**
  - Temperature fields and thermal updates are deterministic and observable.
  - Heaters/coolers and machine heat affect compartments with power gating.
  - Tests and user-side thermal checklist are documented in `docs/phase8/TEMPERATURE_GAMEPLAY_PLAN.md`.

### P1 — Door power-loss behavior model
- **Problem:** Door behavior under power loss is still deferred.
- **Goal:** Define deterministic door state transitions when local power is lost/recovered.
- **Done when:**
  - Powered/unpowered door transitions are deterministic across replay.
  - Tests cover power-loss close/open behavior and compartment effects.

### P1 — Enforce placement constraints
- **Problem:** Build placement still allows future-ready invalid placements.
- **Goal:** Reject invalid placements at command validation/apply time.
- **Done when:**
  - Build command fails with explicit reason for invalid tiles/contexts.
  - Tests cover valid/invalid machine and structural placement.

### P1 — Topology-aware storage access
- **Problem:** Storage access remains effectively global and can hide logistics complexity.
- **Goal:** Constrain storage interactions by reachable topology/compartment rules.
- **Done when:**
  - Haul/store/refine/feed flows respect topology constraints.
  - Tests verify inaccessible storage is not selected/used.

### P2 — Deterministic replay/stress harness expansion
- **Problem:** Replay validation for larger command streams is limited.
- **Goal:** Add stress fixtures for long command sequences and deterministic replay checks.
- **Done when:**
  - Large replay streams are executed in CI/local test profile.
  - Deterministic state-hash equivalence is asserted across restart/replay.

### P2 — Phase 7 UI regression tests
- **Problem:** Overlay/filter/inspector interactions are not covered by automated regressions.
- **Goal:** Add frontend regression tests for key operator flows.
- **Done when:**
  - Automated tests validate overlay/filter toggles and inspector updates.
  - Regressions fail on DOM/state drift in these flows.

### P3 — Optional per-tile environment resolution
- **Problem:** Simulation currently uses compartment-level baseline only.
- **Goal:** Add optional per-tile environmental resolution without breaking determinism.
- **Done when:**
  - Feature flag/config gate exists.
  - Per-tile mode has deterministic tests and parity checks.

### P3 — Frontend UX polish (accessibility and compact layouts)
- **Problem:** MVP UI usability can be improved.
- **Goal:** Improve accessibility, readability, and small-screen operator ergonomics.
- **Done when:**
  - Keyboard navigation and contrast checks pass.
  - Compact layout mode is available and documented.

### P3 — Operator presets/scenarios
- **Problem:** Failure-cascade demos require manual setup.
- **Goal:** Add reusable presets/scenarios for demos and testing.
- **Done when:**
  - At least 3 presets (e.g., breach, brownout, logistics failure) are available.
  - Presets are documented and scriptable.

### P3 — Performance profiling for >5 concurrent clients
- **Problem:** Multi-client performance headroom is unknown.
- **Goal:** Profile runtime behavior with multiple websocket clients.
- **Done when:**
  - A repeatable profiling runbook exists.
  - Key bottlenecks and baseline metrics are documented.

### P2 — Release checklist (docs/tests/observability)
- **Problem:** No explicit release gate tying docs/tests/runtime visibility.
- **Goal:** Add release checklist and enforce it in workflow.
- **Done when:**
  - Checklist includes docs, test suite, replay validation, runtime status verification.
  - Checklist is referenced by README/release process docs.

## Tracking Notes

- Keep this file aligned with the "Immediate Backlog" section in `IMPLEMENTATION_PLAN.md`.
- When an item is implemented, update this file and link to the implementing PR/commit.

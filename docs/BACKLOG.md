# MadStation Backlog

This backlog tracks work intentionally deferred after Phase 7 completion.

## Scope

- Source of truth for follow-on implementation work after the Phase 2–7 MVP pass.
- Items are copied from `IMPLEMENTATION_PLAN.md` and expanded with actionable outcomes.

## Prioritized Items

### [x] P1 — Temperature gameplay (heaters/coolers + machine heat)
- **Problem (historical):** Simulation previously had oxygen/power but no thermal gameplay loop.
- **Goal:** Add deterministic **per-tile** temperature simulation with softened vacuum cooling, machine waste heat, and powered on/off HVAC control.
- **Done when:**
  - Temperature fields and thermal updates are deterministic and observable.
  - Heaters/coolers and machine heat affect tiles with power gating.
  - NPCs flee dangerous thermal zones when feasible.
  - Split plan + tasklist + user testing are documented in `docs/phase8/PHASE8_SPLIT_PLAN.md`, `docs/phase8/TASKLIST.md`, and `docs/phase8/USER_SIDE_TESTING.md`.
- **Status:** Completed in Phase 8 (8A/8B/8C).

### [x] P1 — Door power-loss behavior model
- **Problem (historical):** Door behavior under power loss was deferred.
- **Goal:** Define deterministic door state transitions when local power is lost/recovered.
- **Done when:**
  - Powered/unpowered door transitions are deterministic across replay.
  - Tests cover power-loss close/open behavior and compartment effects.
- **Status:** Completed with deterministic local-network power gating in door auto-state logic.

### [x] P1 — Enforce placement constraints
- **Problem (historical):** Build placement allowed future-ready invalid placements.
- **Goal:** Reject invalid placements at command validation/apply time.
- **Done when:**
  - Build command fails with explicit reason for invalid tiles/contexts.
  - Tests cover valid/invalid machine and structural placement.
- **Status:** Completed with machine placement-context validation and explicit rejection reasons (`machine_requires_floor_or_airlock`).

### [x] P1 — Topology-aware storage access
- **Problem (historical):** Storage access was effectively global and could hide logistics complexity.
- **Goal:** Constrain storage interactions by reachable topology/compartment rules.
- **Done when:**
  - Haul/store/refine/feed flows respect topology constraints.
  - Tests verify inaccessible storage is not selected/used.
- **Status:** Completed by path-reachable storage selection in logistics destination routing.

### [x] P1 — NPC equipment and wearable items
- **Problem (historical):** NPCs lacked slot-based wearable/tool equipment and item weight handling.
- **Goal:** Add hands/clothes/backpack equipment slots, weighted items, mining-laser prerequisite, and spacesuit hazard protections.
- **Done when:**
  - NPCs can equip MiningLaser/SpaceSuit/Backpack deterministically.
  - MineIce enforces mining-laser prerequisite.
  - SpaceSuit mitigates oxygen/pressure/thermal hazard damage.
- **Status:** Completed in Phase 9 initial slice.

### [ ] P2 — Deterministic replay/stress harness expansion
- **Problem:** Replay validation for larger command streams is limited.
- **Goal:** Add stress fixtures for long command sequences and deterministic replay checks.
- **Done when:**
  - Large replay streams are executed in CI/local test profile.
  - Deterministic state-hash equivalence is asserted across restart/replay.

### [x] P2 — Phase 7 UI regression tests
- **Problem (historical):** Overlay/filter/inspector interactions were not covered by automated regressions.
- **Goal:** Add frontend regression tests for key operator flows.
- **Done when:**
  - Automated tests validate overlay/filter toggles and inspector updates.
  - Regressions fail on DOM/state drift in these flows.
- **Status:** Completed via frontend route content assertions + phase thermal UX regression coverage in `tests/test_app.py` and `tests/test_engine.py`.

### [ ] P3 — Optional per-tile environment resolution
- **Problem:** Simulation currently uses compartment-level baseline only.
- **Goal:** Add optional per-tile environmental resolution without breaking determinism.
- **Done when:**
  - Feature flag/config gate exists.
  - Per-tile mode has deterministic tests and parity checks.

### [ ] P3 — Frontend UX polish (accessibility and compact layouts)
- **Problem:** MVP UI usability can be improved.
- **Goal:** Improve accessibility, readability, and small-screen operator ergonomics.
- **Done when:**
  - Keyboard navigation and contrast checks pass.
  - Compact layout mode is available and documented.

### [ ] P3 — Operator presets/scenarios
- **Problem:** Failure-cascade demos require manual setup.
- **Goal:** Add reusable presets/scenarios for demos and testing.
- **Done when:**
  - At least 3 presets (e.g., breach, brownout, logistics failure) are available.
  - Presets are documented and scriptable.

### [ ] P3 — Performance profiling for >5 concurrent clients
- **Problem:** Multi-client performance headroom is unknown.
- **Goal:** Profile runtime behavior with multiple websocket clients.
- **Done when:**
  - A repeatable profiling runbook exists.
  - Key bottlenecks and baseline metrics are documented.

### [x] P2 — Release checklist (docs/tests/observability)
- **Problem:** No explicit release gate tying docs/tests/runtime visibility.
- **Goal:** Add release checklist and enforce it in workflow.
- **Done when:**
  - Checklist includes docs, test suite, replay validation, runtime status verification.
  - Checklist is referenced by README/release process docs.
- **Status:** Completed via `docs/RELEASE_CHECKLIST.md` and README linkage.

## Tracking Notes

Status legend for this file:
- `[x]` completed
- `[ ]` open

- Keep this file aligned with the "Immediate Backlog" section in `IMPLEMENTATION_PLAN.md`.
- When an item is implemented, update this file and link to the implementing PR/commit.

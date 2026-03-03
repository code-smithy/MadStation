# Phase 0 Scope: Simulation Contract Lock

Phase 0 should produce **implementation-ready artifacts**, not just a planning paragraph.

## Objective
Lock deterministic rules, command contracts, and baseline constants so Phase 1 can be implemented without semantic ambiguity.

## Required Outputs

1. `docs/phase0/SIMULATION_SPEC.md`
   - Authoritative tick order and sub-step ordering.
   - Determinism constraints (no wall-clock branching in simulation logic).
   - Tie-break rules (`first-write-wins`, deterministic NPC tie-break keys).
   - RNG policy and seed lifecycle.

2. `docs/phase0/COMMAND_CONTRACT.md`
   - Inbound command schema definitions.
   - Validation and rejection rules.
   - Server sequencing and dedup/idempotency behavior.

3. `docs/phase0/DEFAULT_CONSTANTS.md`
   - Placeholder values for oxygen, damage, movement, suit depletion, power priorities.
   - Explicitly marked as tuning baselines.

4. `docs/phase0/DELTA_PROTOCOL.md`
   - Snapshot-on-join model.
   - Tick delta message format and versioning.

5. `docs/phase0/DETERMINISM_TEST_PLAN.md`
   - Replay harness strategy.
   - World hash checkpoints.
   - Acceptance criteria for deterministic equivalence.

## Definition of Done

- All required docs exist and are cross-linked.
- A single example tick trace is documented end-to-end.
- Determinism acceptance criteria are testable and unambiguous.
- At least one backlog ticket references each output file.

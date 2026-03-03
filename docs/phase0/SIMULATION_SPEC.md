# Simulation Spec (Phase 0 Draft)

## 1. Deterministic Tick Order (1Hz)

Each tick executes in this fixed order:

1. Ingest and validate queued commands for this tick window.
2. Apply accepted commands in server sequence order.
3. Recalculate topology-dependent caches when invalidated:
   - compartments,
   - navigation,
   - power graph.
4. Update environment:
   - oxygen diffusion/leaks,
   - pressure/temperature drift (where enabled),
   - radiation baseline/events (when enabled).
5. Update power generation/storage/allocation tiers.
6. Update machine processing.
7. Update NPC decision + movement + task interaction.
8. Apply all damage and death resolution.
9. Emit events/log entries.
10. Broadcast state delta.
11. Persist snapshot if cadence matches.

## 2. Determinism Rules

- No direct wall-clock usage in simulation state transitions.
- No nondeterministic iteration over hash maps/sets.
- All command ordering derives from server sequence IDs.
- Tie-breakers always use stable key ordering (`entity_id`, then `sequence_id`).

## 3. Conflict Rule

- Structural edits use **first-write-wins** at equal contention points.
- Later conflicting commands in the same tick are rejected with reason code `CONFLICT_STALE_TARGET`.

## 4. RNG Policy

- Use a deterministic PRNG seeded by `world_seed`.
- Event/NPC random draws consume RNG in a fixed order each tick.
- Save RNG state in snapshots.

## 5. Tick Trace Requirement

For one sample tick, record:
- incoming commands,
- accepted/rejected list,
- resulting world hash,
- emitted deltas.

(Used by replay harness and regression tests.)

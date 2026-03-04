# MadStation MVP Implementation Plan (Aligned Review)

## Confirmed Decisions (from latest review)

1. **Visitor commands (MVP):** only the minimum set for now (`Build`, `Deconstruct`, `CreateWorkOrder`).
2. **Anti-grief throttling:** `1 action / 10 seconds` per anonymous session.
3. **Identity model:** anonymous users only.
4. **Command conflict rule:** **first write wins**.
5. **Simulation requirement:** strict determinism.
6. **Movement:** diagonal allowed; base speed target `2 tiles/sec`, with per-character speed in `[1,4] tiles/sec`.
7. **Doors:** auto-open/auto-close (power-loss behavior deferred).
8. **Environment resolution:** compartment-level now, per-tile later.
9. **Tuning constants:** placeholder values now; calibrate via playtests.
10. **Work-order collision:** auto-resolve and replan if another NPC completes first.
11. **Trait priority:** personality never overrides survival constraints.
12. **Deaths:** `DisposeBody` work order in MVP; no morale system yet.
13. **Placement constraints:** design for future constraints now, no hard enforcement yet.
14. **Power network:** global connected network (no cabling in MVP).
15. **Storage behavior:** global storage access in MVP (topology-aware later).
16. **Crash recovery:** restore from snapshot (+ optional replay later).
17. **Snapshot cadence:** configurable.
18. **Initial scale target:** 5 concurrent users.
19. **Observability:** yes, include baseline metrics + debugging support.
20. **Frontend stack:** best-practice implementation choice.
21. **State sync:** full snapshot on join + deltas.
22. **Priority:** simulation correctness over visual polish.

---

## Revised Step-by-Step Sequence

## Phase 0 — Simulation Contract Lock (Day 1)

- Produce explicit Phase 0 artifacts under `docs/phase0/`:
  - `PHASE0_SCOPE.md`
  - `SIMULATION_SPEC.md`
  - `COMMAND_CONTRACT.md`
  - `DEFAULT_CONSTANTS.md`
  - `DELTA_PROTOCOL.md`
  - `DETERMINISM_TEST_PLAN.md`
- Lock these decisions in writing:
  - canonical tick order and deterministic sequencing,
  - first-write-wins tie-break rule,
  - throttle policy `1 action / 10 sec / anonymous session`,
  - deterministic RNG/seed lifecycle,
  - snapshot-on-join + delta protocol.

**Exit criteria:** two independent runs with same seed + command stream produce identical hashes for N ticks, and all six phase-0 docs are complete and cross-linked.

## Phase 1 — Engine + Transport Skeleton (Days 2–3) ✅ Completed

- Implement FastAPI + WebSocket server.
- Add simulation clock at 1Hz (authoritative server tick).
- Add command intake queue with server-side sequencing.
- Add state sync model:
  - snapshot on connect,
  - delta each tick.
- Add anonymous session IDs for per-session throttling and attribution.

**Exit criteria:** 5 clients can connect and receive deterministic tick updates. ✅ Met (see `docs/phase1/PHASE1_COMPLETION.md`).

## Phase 2 — World + Core Environment (Days 4–7) ✅ Completed

### Phase 2A (completed in current iteration)
- Implemented 50x50 structural grid and structural edits via `Build`/`Deconstruct`.
- Implemented compartment flood-fill recalculation only on topology change.
- Implemented compartment-level oxygen leak model from vacuum exposure.
- Added tile mutation deltas and `compartment_count` runtime observability.

### Phase 2B (completed)
- Implemented diffusion behavior via explicit open-door boundaries. ✅
- Implemented deterministic door auto-open/close baseline logic. ✅
- Implemented oxygen generation hooks for machine integration. ✅

**Exit criteria:** removing a wall causes visible decompression and oxygen decay in expected compartments. ✅ Met.

## Phase 3 — Power + Priority Load Shedding (Days 8–10) ✅ Completed

### Phase 3A (completed in current iteration)
- Implemented global power model with generation, battery discharge/charge, and tiered allocation.
- Added power-state observability (`generation`, `demand`, `powered/unpowered`, `disabled_priorities`).
- Wired oxygen generator production to power availability.

### Phase 3B (completed in this iteration)
- Added configurable tier policy from runtime constants (`power_priority_tiers`) and deterministic tier allocation. ✅
- Added topology-aware power-network segmentation by connected compartments. ✅
- Added power-failure/recovery markers in protocol deltas. ✅
- Added deterministic test coverage for brownout shedding + recovery ordering. ✅

**Exit criteria:** deficits consistently disable lower tiers first and recover deterministically. ✅ Met.

## Phase 4 — NPC Core + Permanent Death (Days 11–15) ✅ Completed

### Phase 4A (started in current iteration)
- Added 10 named persistent NPCs. ✅
- Added speed attributes bounded to `[1,4]`. ✅
- Added deterministic diagonal survival movement baseline (full pathfinding still pending). ✅
- Added suffocation damage/death handling with permanent death records. ✅
- Added automatic `DisposeBody` work-order creation on death. ✅
- Added deterministic DisposeBody work-order assignment/execution baseline. ✅
- Added baseline needs/personality layer with survival-first enforcement. ✅

### Phase 4B (completed)
- Added deterministic oxygen-aware path search baseline for multi-step routing. ✅
- Upgraded task-aware path selection/execution for `DisposeBody` with deterministic nearest-reachable assignment and re-queue on unreachable paths. ✅
- Expanded baseline needs/personality stack while preserving survival-first constraints. ✅
- Enriched death/body lifecycle metadata and disposal-state integration. ✅

**Exit criteria:** NPCs navigate, prioritize survival, and deaths persist with cause/timestamp. ✅ Met.

## Phase 5 — Work Orders + Physical Logistics Loop (Days 16–21) ✅ Completed

### Phase 5A (started in current iteration)
- Added command-applied work-order creation path into authoritative world state. ✅
- Added physical `items` and `storages` state scaffolding with inventory tracking. ✅
- Added baseline `MineIce` -> auto `HaulItem` to storage foundation loop. ✅

### Phase 5B (implemented in this iteration)
- Expanded work-order command schema and deterministic logistics command validation for `MineIce`, `HaulItem`, `RefineIce`, and `FeedOxygenGenerator`. ✅
- Added initial refinement/feed chain baseline (`RefineIce` + `FeedOxygenGenerator`) with physical item handoff/consumption. ✅
- Added race collision/replan handling for shared logistics orders with deterministic loser requeue/cancel outcomes. ✅

**Exit criteria:** full life-support chain works end-to-end without teleportation. ✅ Met.

### Phase 5C (started in this iteration)
- Coupled `FeedOxygenGenerator` execution to oxygen generator machine/power state. ✅
- Added feed-generator command metadata validation (`generator_location`) and order targeting. ✅
- Added deterministic requeue for blocked feed tasks (`generator_missing_or_disabled`, `generator_unpowered`). ✅

## Phase 6 — Persistence + Recovery + Basic Ops (Days 22–25) ✅ Completed

### Phase 6A (implemented in this iteration)
- Persist world state snapshots on configurable cadence. ✅
- Add configurable snapshot cadence/path runtime settings. ✅
- Implement crash restart bootstrap from latest snapshot. ✅
- Expose snapshot cadence/last-snapshot in runtime status. ✅

### Phase 6B (started in this iteration)
- Added snapshot schema/version integrity guards (`snapshot_schema_version` + `state_hash`). ✅
- Added safe fallback bootstrap when snapshot fails integrity checks. ✅
- Added optional replay window from snapshot forward. ✅
- Added ops metrics (`tick duration`, queue trends, idle NPC ratio over time). ✅

### Phase 6C (started in this iteration)
- Added basic ops runtime metrics (`tick_duration_ms_last`, `tick_duration_ms_ema`, `tick_duration_ms_max`, `command_queue_peak`). ✅
- Added deterministic test coverage for ops metric updates. ✅

### Phase 6D (started in this iteration)
- Added replay-log window for post-snapshot command recovery. ✅
- Added startup replay for commands newer than snapshot sequence. ✅
- Added replay-log compaction on snapshot persist. ✅

### Phase 6E (started in this iteration)
- Added restore observability metrics (`restored_from_snapshot`, `replay_commands_applied_on_restore`). ✅
- Added replay-window bound tests (`command_replay_max_entries`) to keep replay growth controlled. ✅

### Phase 6F (implemented in this iteration)
- Added queue-depth trend metrics (`queue_depth_last/ema/max` + bounded `queue_depth_history`). ✅
- Added idle NPC ratio trend metrics (`idle_npc_ratio_last/ema` + bounded `idle_npc_ratio_history`). ✅
- Added deterministic tests for trend metric updates and bounded histories. ✅

**Exit criteria:** restart resumes world safely within snapshot tolerance. ✅ Met.

## Phase 7 — Frontend MVP (parallel, correctness-first) ✅ Completed

### Phase 7A (implemented in this iteration)
- Added simulation-first web UI entry page (`GET /`). ✅
- Added grid view, edit controls, and basic work-order controls. ✅
- Added live status panel + event log with websocket-driven updates. ✅

### Phase 7B (completed)
- Added tile/NPC inspectors and machine quick-actions. ✅
- Added power/oxygen/compartment overlays plus event filtering ergonomics. ✅
- Added richer work-order metadata forms. ✅

**Exit criteria:** operators can reliably induce and observe failure cascades. ✅ Met.

---

## Immediate Backlog (Post-Phase-7 follow-ons)

1. Door power-loss behavior model (deferred from early phases).
2. Enforce placement constraints currently documented as future-ready.
3. Add topology-aware (non-global) storage access constraints.
4. Expand deterministic replay/stress harness for larger command streams.
5. Add Phase 7 UI regression tests for overlay/filter/inspector interactions.
6. Add optional per-tile environment resolution path (post compartment-level baseline).
7. Add frontend UX polish pass for accessibility and compact layouts.
8. Add operator presets/scenarios for failure-cascade demos.
9. Add performance profiling pass for >5 concurrent clients.
10. Add explicit release checklist tying docs, tests, and runtime observability.

---

## Review Notes / Risks

- **Biggest technical risk:** keeping strict determinism while serving real-time multiplayer commands.
  - Mitigation: sequence all commands server-side and prohibit wall-clock branching inside simulation logic.
- **Biggest design risk:** global storage in MVP can hide logistics complexity.
  - Mitigation: keep APIs topology-ready so adjacency constraints can be introduced without rewriting machine logic.
- **Balancing risk:** placeholder constants may create abrupt collapse loops.
  - Mitigation: add metrics + scripted chaos scenarios for tuning.

This plan is intentionally shaped around your priorities: **simulation integrity first**, then progressive complexity.

---

## Phase 1 Bootstrap Notes (Historical)

Initial Phase 1 scaffold now targets:
- FastAPI transport (`/health`, `/ws`),
- 1Hz loop skeleton,
- anonymous session issuance,
- throttled command enqueue,
- server sequence IDs,
- snapshot-on-connect + delta broadcast.

This is an engine skeleton for Phase 1 integration and does not yet include full world mutation semantics.


## Phase 1 Completion Documentation

Phase 1 closure, verification mapping, and handoff notes are documented in `docs/phase1/PHASE1_COMPLETION.md`.


Phase 2 split details are tracked in `docs/phase2/PHASE2_SPLIT_PLAN.md`.


Phase 3 split details are tracked in `docs/phase3/PHASE3_SPLIT_PLAN.md`.



Phase 4 split details are tracked in `docs/phase4/PHASE4_SPLIT_PLAN.md`.



Phase 5 split details are tracked in `docs/phase5/PHASE5_SPLIT_PLAN.md`.

Phase 6 split details are tracked in `docs/phase6/PHASE6_SPLIT_PLAN.md`.

Phase 7 split details are tracked in `docs/phase7/PHASE7_SPLIT_PLAN.md`.

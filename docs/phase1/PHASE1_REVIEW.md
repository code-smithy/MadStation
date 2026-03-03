# Phase 1 Review (Feedback)

## Overall assessment

Phase 1 is a solid scaffold and successfully proves the core loop shape (server tick, command queue, websocket state streaming).

**Status:** good foundation, but not production-safe yet.

## What is working well

1. **Clear engine boundary** (`SimulationEngine`) with an explicit tick loop.
2. **Anonymous session flow** is present and integrated with websocket connect.
3. **Throttle policy** (`1 action / 10 sec`) is implemented.
4. **First-write-wins conflict behavior** exists for same-target, same-tick contention.
5. **Functional tests exist and pass** for key baseline semantics.

## Gaps / risks to address next

### 1) Duplicate command handling is missing (high priority)
- Phase 0 command contract documents idempotency via `client_command_id`, but engine currently does not deduplicate repeated command IDs.
- Risk: client retries can produce unintended duplicate effects.

### 2) Command acknowledgement semantics are ambiguous (high priority)
- `enqueue_command` returns `ACCEPTED` immediately, and `_execute_tick` sends another `ACCEPTED` ack with `server_sequence_id`.
- Risk: clients may treat pre-tick acceptance as final application and diverge from authoritative state.

### 3) Error handling on websocket send/broadcast is absent (high priority)
- `_broadcast` and `_send_to` do not handle connection send failures.
- Risk: one broken socket can interrupt tick behavior or crash loop depending on exception propagation.

### 4) Determinism caveat: throttle uses wall clock (medium priority)
- The simulation state is deterministic, but admission control uses `time.monotonic()`.
- Acceptable for MVP transport behavior, but this must remain outside simulation-state determinism claims.

### 5) Validation depth is minimal (medium priority)
- Payload validation checks only coordinate shape/range.
- Missing command-type-specific schema checks and consistent rejection taxonomy.

### 6) Test coverage could still miss protocol integration bugs (medium priority)
- Current tests focus engine internals only.
- No websocket roundtrip/integration test for `/ws` message lifecycle.

## Recommended Phase 1.1 backlog (ordered)

1. Add `client_command_id` idempotency cache with replayed ack semantics.
2. Split ack states into:
   - `QUEUED` (accepted for later tick),
   - `APPLIED` or `REJECTED` after tick execution.
3. Wrap websocket sends in resilient error handling; prune dead sessions safely.
4. Add per-command schema validators for `Build`, `Deconstruct`, `CreateWorkOrder`.
5. Add `/ws` integration tests using TestClient websocket support.
6. Add deterministic replay test harness stub and world-hash checkpoint tests.
7. Expose minimal metrics: tick duration, queued command count, connected sessions.

## Exit criteria suggestion before Phase 2

- Duplicate command retries are idempotent.
- Ack contract is single-source-of-truth and documented.
- Broken websocket clients cannot destabilize tick loop.
- Engine + websocket integration tests cover success and failure paths.

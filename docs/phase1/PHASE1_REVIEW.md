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

## Gaps / risks to address next (historical, now resolved)

These Phase 1 review gaps were addressed during subsequent phases and are retained here as a trace log.

### 1) Duplicate command handling was missing (high priority) — ✅ Resolved
- Engine now caches per-session command acknowledgements by `client_command_id` and replays cached responses for retries.

### 2) Command acknowledgement semantics were ambiguous (high priority) — ✅ Resolved
- Ack contract now uses staged results (`QUEUED` then authoritative `APPLIED`/rejection after tick processing) with server sequence attribution.

### 3) Error handling on websocket send/broadcast was absent (high priority) — ✅ Resolved
- Broadcast path now wraps sends safely and disconnects failing sockets without destabilizing tick loop.

### 4) Determinism caveat: throttle uses wall clock (medium priority) — ✅ Clarified
- Throttle remains transport-layer admission control; simulation-state determinism remains tick/sequence based.

### 5) Validation depth was minimal (medium priority) — ✅ Resolved
- Command-type-specific payload validation now covers structural edits, machine payloads, and work-order metadata schemas.

### 6) Test coverage could miss protocol integration bugs (medium priority) — ✅ Resolved
- Added websocket lifecycle integration coverage in app tests in addition to existing engine/failure-path tests.

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

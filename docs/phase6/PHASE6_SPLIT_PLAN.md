# Phase 6 Split Plan

Phase 6 is split into persistence/recovery foundations first, then broader ops observability.

## Phase 6A (implemented in this iteration)

- Added configurable snapshot cadence and snapshot path in runtime settings. ✅
- Added periodic world snapshot persistence from the engine tick loop. ✅
- Added startup restore from latest snapshot when available. ✅
- Added runtime status counters for snapshot cadence/last snapshot tick. ✅

## Phase 6B (started in this iteration)

- Added snapshot integrity/version guards (`snapshot_schema_version` + deterministic `state_hash` verification). ✅
- Added restore fallback behavior for invalid/corrupt snapshots (safe default bootstrap). ✅
- Add optional command replay window after snapshot restore.
- Add richer basic ops metrics (tick duration, queue depth trends, idle NPC ratio timelines).

## Exit target for Phase 6

- Restart resumes world state safely from latest snapshot within configured cadence tolerance.
- Snapshot cadence/restore behavior is deterministic and test-covered.

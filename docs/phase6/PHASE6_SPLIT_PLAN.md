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


## Phase 6C (started in this iteration)

- Added basic ops metrics in runtime status: `tick_duration_ms_last`, `tick_duration_ms_ema`, `tick_duration_ms_max`, and `command_queue_peak`. ✅
- Added deterministic test coverage for queue-peak and tick-duration metric updates. ✅


## Phase 6D (started in this iteration)

- Added replay-log window foundation (`jsonl`) for post-snapshot applied commands. ✅
- Added startup replay of commands newer than snapshot `server_sequence_id`. ✅
- Added replay-log trimming on snapshot persist to bound replay window. ✅


## Phase 6E (started in this iteration)

- Added restore observability metrics: `restored_from_snapshot` and `replay_commands_applied_on_restore`. ✅
- Added replay-window max-entry enforcement tests to bound replay growth. ✅

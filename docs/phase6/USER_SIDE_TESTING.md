# Phase 6 User-Side Testing Guide

Use this checklist to validate persistence/recovery behavior.

## Prerequisites

- Server running (`make run`).
- Access to local filesystem path configured for snapshot file.

## 1) Snapshot cadence behavior

1. Start server and observe `/status` fields `last_snapshot_tick` and `snapshot_cadence_ticks`.
2. Wait until tick reaches a cadence boundary (e.g., every 10 ticks by default).
3. Confirm snapshot file is created/updated on disk.

## 2) Restart recovery behavior

1. With active world state changes (machines/orders/items), stop the server.
2. Restart server with same snapshot path.
3. Confirm `/world` reflects pre-restart state (tick, machines, items, work orders) from latest snapshot.
4. Confirm `/status.last_snapshot_tick` is at or near restored tick.

## 3) Tolerance expectations

- On crash between cadence boundaries, up to `snapshot_cadence_ticks - 1` ticks may be lost by design.
- Replay-window recovery is now available; this tolerance note still applies between snapshot boundaries before replayed commands.


## 4) Snapshot integrity guard checks

1. Stop server and manually edit snapshot file to corrupt `state_hash` (or set unsupported `snapshot_schema_version`).
2. Restart server.
3. Confirm server starts safely using default bootstrap state instead of crashing on invalid snapshot.
4. Confirm `/status.tick` resets and world remains valid/interactive.


## 5) Basic ops metrics checks

1. Observe `/status` fields for tick runtime and queue behavior:
   - `tick_duration_ms_last`
   - `tick_duration_ms_ema`
   - `tick_duration_ms_max`
   - `command_queue_peak`
2. Burst-enqueue several commands quickly and confirm `command_queue_peak` increases.
3. Let simulation run for multiple ticks and confirm duration fields remain populated and stable.


## 6) Replay-window recovery checks

1. Run until a snapshot is persisted.
2. Apply one or more structural/work-order commands after that snapshot point.
3. Stop and restart server.
4. Confirm post-snapshot commands are restored via replay window (no full-state loss back to old snapshot).
5. Confirm replay log shrinks after new snapshot persist (window compaction).


## 7) Restore observability checks

1. Restart the server from a valid snapshot + replay log.
2. Verify `/status.restored_from_snapshot == 1`.
3. Verify `/status.replay_commands_applied_on_restore` reflects replayed command count (>0 when post-snapshot commands existed).
4. Verify `/status.replay_log_entries` stays bounded over time based on replay-window configuration.


## 8) Queue/idle trend metrics checks

1. Observe `/status` fields:
   - `queue_depth_last`, `queue_depth_ema`, `queue_depth_max`, `queue_depth_history`
   - `idle_npc_ratio_last`, `idle_npc_ratio_ema`, `idle_npc_ratio_history`
2. Burst command submissions and verify queue depth metrics respond.
3. Run for many ticks and confirm history arrays remain bounded (windowed).

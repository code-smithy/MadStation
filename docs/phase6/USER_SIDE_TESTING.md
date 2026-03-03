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
- This is expected until replay/logging is added in later Phase 6 slices.


## 4) Snapshot integrity guard checks

1. Stop server and manually edit snapshot file to corrupt `state_hash` (or set unsupported `snapshot_schema_version`).
2. Restart server.
3. Confirm server starts safely using default bootstrap state instead of crashing on invalid snapshot.
4. Confirm `/status.tick` resets and world remains valid/interactive.

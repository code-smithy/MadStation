# State Sync Protocol (Phase 0 Draft)

## Join Flow

1. Client connects via WebSocket.
2. Server issues/returns anonymous `session_id`.
3. Server sends full snapshot with `snapshot_tick`.
4. Client applies incremental deltas where `tick > snapshot_tick`.

## Message Types

- `snapshot_full`
- `delta_tick`
- `command_ack`
- `system_event`

## `delta_tick` Shape (conceptual)

```json
{
  "type": "delta_tick",
  "tick": 1234,
  "world_hash": "...",
  "tile_changes": [],
  "entity_changes": [],
  "work_order_changes": [],
  "death_log_appends": []
}
```

## Versioning

- Include `protocol_version` in all payloads.
- Backward-incompatible protocol changes must bump major version.

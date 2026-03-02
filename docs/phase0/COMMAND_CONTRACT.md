# Command Contract (Phase 0 Draft)

## Supported MVP Commands

1. `Build`
2. `Deconstruct`
3. `CreateWorkOrder`

## Common Envelope

```json
{
  "client_command_id": "uuid",
  "session_id": "anon-session-id",
  "issued_at_ms": 0,
  "type": "Build|Deconstruct|CreateWorkOrder",
  "payload": {}
}
```

## Validation Rules

- Reject unknown command types.
- Enforce per-session throttle: `1 action / 10 seconds`.
- Validate target coordinates in bounds.
- Reject commands that violate immutable tile constraints.
- Reject conflicting same-tick write when target already modified by earlier sequence.

## Sequencing

- All accepted commands get a monotonic `server_sequence_id`.
- Simulation consumes commands strictly by `server_sequence_id`.
- Sequence IDs are included in broadcast acknowledgements.

## Idempotency

- Duplicate `client_command_id` from same session is ignored (ack with prior result).

## Rejection Codes

- `THROTTLED`
- `INVALID_PAYLOAD`
- `OUT_OF_BOUNDS`
- `CONFLICT_STALE_TARGET`
- `UNKNOWN_COMMAND`


## Acknowledgement Lifecycle

- On successful admission, server responds with `QUEUED`.
- After tick execution, server emits final command result (`APPLIED` or rejection such as `CONFLICT_STALE_TARGET`).
- Duplicate `client_command_id` from the same session returns the cached acknowledgement (idempotent behavior).

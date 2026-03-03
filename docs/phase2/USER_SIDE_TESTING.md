# Phase 2 User-Side Testing Guide

Use this checklist to validate Phase 1 + Phase 2A behavior from a player/operator perspective.

## Prerequisites

- Server running locally (`make run`).
- A websocket client (`wscat`) or browser console.

## 1) Basic runtime checks

1. `GET /health` returns `{ "status": "ok" }`.
2. `GET /status` returns:
   - `tick` increasing,
   - `connected_clients`,
   - `queued_commands`,
   - `compartment_count`.
3. `GET /world` returns world snapshot with:
   - `world.grid` (50 rows × 50 columns),
   - `world.compartments`,
   - `world.compartment_index`.

## 2) Websocket connection

Connect:

```bash
wscat -c ws://127.0.0.1:8000/ws
```

Expected first message: `snapshot_full`.

## 3) Structural edit validation

Send a build command:

```json
{"client_command_id":"build-a","type":"Build","payload":{"x":3,"y":3,"tile_type":"Wall"}}
```

Expected:
- immediate `command_ack` (`QUEUED`),
- later `command_ack` (`APPLIED`),
- subsequent `delta_tick` with one `tile_changes` entry showing `before`/`after`.

## 4) Vacuum breach / oxygen drift validation

Send a deconstruct command on edge tile:

```json
{"client_command_id":"breach-a","type":"Deconstruct","payload":{"x":0,"y":0}}
```

Expected:
- `delta_tick.tile_changes` includes `after: "Vacuum"`,
- `GET /world` shows compartment oxygen lower than baseline over ticks.

## 5) Deterministic multi-client quick check

Open 2+ websocket clients and compare incoming `delta_tick` payloads for:
- same `tick`,
- same `world_hash`,
- same `command_count`.

## 6) Throttle check

Send two commands rapidly from the same websocket session.
Expected second ack: `THROTTLED`.

## Known current scope (Phase 2A)

- Compartments and oxygen leak are implemented.
- Door auto-open/close and explicit door diffusion behavior are planned for Phase 2B.


## 7) Door auto-state + diffusion check

1. Create two nearby floor pockets with a door tile between them.
2. Confirm door state appears in `/world.world.door_states`.
3. Observe `door_state` entries inside `delta_tick.tile_changes` when the door auto-opens/closes.
4. With differing oxygen values between pockets, keep door open and confirm values trend toward each other over ticks.

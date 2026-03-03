# MadStation

## Planning docs
- `IMPLEMENTATION_PLAN.md`
- `docs/phase0/PHASE0_SCOPE.md`
- `docs/phase0/SIMULATION_SPEC.md`
- `docs/phase0/COMMAND_CONTRACT.md`
- `docs/phase0/DEFAULT_CONSTANTS.md`
- `docs/phase0/DELTA_PROTOCOL.md`
- `docs/phase0/DETERMINISM_TEST_PLAN.md`
- `docs/phase1/PHASE1_COMPLETION.md`
- `docs/phase1/PHASE1_REVIEW.md`
- `docs/phase2/PHASE2_SPLIT_PLAN.md`
- `docs/phase2/PHASE2_NEXT_STEPS.md`
- `docs/phase2/USER_SIDE_TESTING.md`
- `docs/phase3/PHASE3_SPLIT_PLAN.md`
- `docs/phase3/USER_SIDE_TESTING.md`

## Phase 1 server scaffold (completed)

A minimal Phase 1 implementation is now included:
- FastAPI app with `/health`, `/status`, and `/ws`
- `GET /ws` returns usage help; actual client connection must be a WebSocket upgrade on `ws://.../ws`.
- 1Hz simulation loop
- anonymous session IDs
- command queue with server sequencing
- per-session throttle (`1 action / 10 sec`)
- first-write-wins conflict handling at tile target level
- snapshot on websocket connect + per-tick delta broadcast

## Local setup (Linux/WSL, PEP 668 safe)

If you see `externally-managed-environment`, install inside a virtual environment.

```bash
make install
```

This creates `.venv`, upgrades pip, and installs project + dev dependencies (including WebSocket runtime support and `pytest`).

## Run server

```bash
make run
```

Then open `http://127.0.0.1:8000/health`, `http://127.0.0.1:8000/status`, and `http://127.0.0.1:8000/world`.

## Connect a client (WebSocket)

`connected_clients` increases when a client opens a WebSocket to `/ws` and stays connected.

### Quick browser console test

1. Open `http://127.0.0.1:8000/health` in a browser.
2. Open DevTools Console and run:

```js
const ws = new WebSocket("ws://127.0.0.1:8000/ws");
ws.onmessage = (event) => console.log("WS message:", event.data);
```

3. In another tab, check `http://127.0.0.1:8000/status`.
   - You should see `connected_clients` increase while the socket remains open.

### Quick `wscat` test

```bash
wscat -c ws://127.0.0.1:8000/ws
```

If connected, `/status` should show `connected_clients: 1`.

### Send a command over the same socket

```js
ws.send(JSON.stringify({
  client_command_id: "cmd-1",
  type: "Build",
  payload: { x: 1, y: 1 }
}));
```

You should receive a `command_ack` and subsequent `delta_tick` messages.

## Testing

Run functional tests on every change:

```bash
make test
```

## Troubleshooting

- `ModuleNotFoundError: No module named 'fastapi'`
  - You are likely running system `uvicorn` without project dependencies.
  - Fix by running `make install` and then `make run` so `uvicorn` comes from `.venv`.

- `No supported WebSocket library detected`
  - Your environment is missing `websockets`/`wsproto` for Uvicorn upgrades.
  - Fix with `make install` (this project now installs `websockets` by default).

- `No module named pytest` when running `make test`
  - Your virtualenv was created before test dependencies were added, or install did not complete.
  - Fix by running `make install` again (installs `.[dev]`, including `pytest`).


## Phase 2 progress

Phase 2 is being delivered in slices. Core 2B door auto-state + open-door diffusion + oxygen-generator hooks are now implemented; see `docs/phase2/PHASE2_SPLIT_PLAN.md` for current scope.


## User-side testing (manual)

1. Start server: `make run`.
2. Open `/world` and confirm a 50x50 `grid` exists.
3. Connect websocket: `wscat -c ws://127.0.0.1:8000/ws`.
4. Send a wall build command:

```json
{"client_command_id":"u1","type":"Build","payload":{"x":3,"y":3,"tile_type":"Wall"}}
```

5. Send a decompression command:

```json
{"client_command_id":"u2","type":"Deconstruct","payload":{"x":0,"y":0}}
```

6. Build a door between two floor tiles and watch `delta_tick.tile_changes` for `door_state` transitions.
7. Optionally build a floor with a machine hook using payload `{"machine":{"type":"OxygenGenerator","rate_per_tick":3}}`.
8. Breach then reseal the same tile (`Deconstruct` then `Build Floor`) and verify oxygen/pressure stabilize after reseal.
9. Refresh `/world` to confirm tile mutations + compartment oxygen drift/diffusion/generation.

See `docs/phase2/USER_SIDE_TESTING.md` for a fuller checklist.


## Phase 3 progress

Phase 3A is implemented and Phase 3B is in progress: global power + load-shedding + oxygen-generator power gating are live, and `power_event` markers now appear in `delta_tick.entity_changes`. See `docs/phase3/PHASE3_SPLIT_PLAN.md`.


## Phase 3 manual testing

1. Connect websocket: `wscat -c ws://127.0.0.1:8000/ws`.
2. Build a powered consumer (`OxygenGenerator`) and a lower-priority consumer (`Light`).
3. Build limited generation (`SolarPanel`) and verify `unpowered_consumers`/`disabled_priorities` in `/world.world.power_state`.
4. Add `Battery` and verify `battery_discharge > 0` and battery `stored` decreases when bridging deficit.
5. Add `Reactor` and verify consumers recover and oxygen generation resumes.
6. Observe websocket `delta_tick.entity_changes` for `power_event` entries (`brownout_started`, `blackout_started`, `power_recovered`).

See `docs/phase3/USER_SIDE_TESTING.md` for the full step-by-step command checklist.

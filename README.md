# MadStation

## Planning docs
- `IMPLEMENTATION_PLAN.md`
- `docs/phase0/PHASE0_SCOPE.md`
- `docs/phase0/SIMULATION_SPEC.md`
- `docs/phase0/COMMAND_CONTRACT.md`
- `docs/phase0/DEFAULT_CONSTANTS.md`
- `docs/phase0/DELTA_PROTOCOL.md`
- `docs/phase0/DETERMINISM_TEST_PLAN.md`

## Phase 1 server scaffold

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

This creates `.venv`, upgrades pip, and installs the project dependencies.

## Run server

```bash
make run
```

Then open `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/status`.


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

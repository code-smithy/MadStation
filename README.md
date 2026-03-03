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

## Testing

Run functional tests on every change:

```bash
make test
```

## Troubleshooting

- `ModuleNotFoundError: No module named 'fastapi'`
  - You are likely running system `uvicorn` without project dependencies.
  - Fix by running `make install` and then `make run` so `uvicorn` comes from `.venv`.

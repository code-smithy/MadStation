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
- FastAPI app with `/health` and `/ws`
- 1Hz simulation loop
- anonymous session IDs
- command queue with server sequencing
- per-session throttle (`1 action / 10 sec`)
- first-write-wins conflict handling at tile target level
- snapshot on websocket connect + per-tick delta broadcast

### Run

```bash
pip install -e .
uvicorn madstation.app:app --reload
```

## Testing

Run functional tests on every change:

```bash
make test
```


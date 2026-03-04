# MadStation Release Checklist

Use this checklist before cutting a release tag or announcing a milestone branch.

## 1) Documentation
- [ ] `README.md` reflects current phase status and major operator workflows.
- [ ] `IMPLEMENTATION_PLAN.md` backlog/status aligns with delivered scope.
- [ ] `docs/BACKLOG.md` marks completed items and links to implementation evidence.
- [ ] Phase-specific docs are updated for any behavior changes in this release.

## 2) Automated validation
- [ ] Run `PYTHONPATH=. python -m pytest -q` with all tests passing.
- [ ] Run targeted regression tests for changed subsystems (engine/app/frontend flows).
- [ ] Confirm deterministic/replay-sensitive tests pass when persistence features changed.

## 3) Runtime observability
- [ ] `/health` responds `{"status": "ok"}`.
- [ ] `/status` exposes expected summary metrics for changed subsystems.
- [ ] `/world` includes expected world payload fields for changed subsystems.
- [ ] WebSocket `/ws` snapshot + delta flow still works for core operator actions.

## 4) Persistence and recovery (when applicable)
- [ ] Snapshot write/read path validated.
- [ ] Replay-log bounds/compaction behavior validated.
- [ ] Restore path from snapshot (+ replay) validated in tests.

## 5) Release hygiene
- [ ] Backlog items addressed in this release are marked complete.
- [ ] New deferred work is documented in `docs/BACKLOG.md` with explicit done criteria.
- [ ] PR summary includes exact test commands and outcomes.

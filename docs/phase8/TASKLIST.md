# Phase 8 Tasklist

Execution tasklist for delivering temperature gameplay in staged PRs.

## Status legend
- [ ] Not started
- [~] In progress
- [x] Done

## PR-1 — 8A Engine Thermal Baseline + API Observability

### Engine model
- [x] Add per-tile `temperature_c` initialization for all world tiles.
- [x] Add deterministic thermal update pass to tick execution order.
- [x] Implement softened vacuum cooling coefficients.
- [x] Implement tile-to-tile heat transfer (stable-order, deterministic).
- [x] Add powered on/off `Heater` behavior.
- [x] Add powered on/off `Cooler` behavior.
- [x] Add waste heat contributions for selected heat-producing machines.
- [x] Ensure thermal updates are replay-safe and snapshot-safe.

### API/transport observability
- [x] Add thermal summary fields to `/status` output.
- [x] Add per-tile temperature data to `/world` output.
- [x] Add thermal delta payloads/events to websocket updates.

### Tests (PR-1 gate)
- [x] Determinism test for identical tile temperature field across replay.
- [x] Vacuum cooling trend test.
- [x] Tile transfer convergence test.
- [x] Heater power-gating test (powered vs unpowered).
- [x] Cooler power-gating test (powered vs unpowered).
- [x] Machine waste-heat behavior test.
- [x] `/status` thermal fields test.
- [x] `/world` thermal field test.

## PR-2 — 8B NPC Thermal Hazard + Flee

### NPC simulation
- [x] Add thermal comfort and hazard thresholds to settings.
- [x] Apply deterministic mild penalties outside comfort bounds.
- [x] Apply deterministic health degradation in hazard bounds.
- [x] Add flee behavior: choose safer thermal route when available.
- [x] Preserve deterministic tie-breaking in flee routing.

### Events/observability
- [x] Emit thermal hazard enter/exit events.
- [x] Emit flee-related NPC decision events (or equivalent debug markers).

### Tests (PR-2 gate)
- [x] NPC flees hazardous thermal area when escape path exists.
- [x] NPC degrades deterministically when trapped in hazard.
- [x] Thermal event payload coverage test.

## PR-3 — 8C Frontend Thermal UX

### UI features
- [x] Add Temperature view mode toggle.
- [x] Add temperature color scale/legend.
- [x] Show tile temperature in inspector.
- [x] Add heater/cooler quick actions in control panel.
- [x] Add thermal event visualization/filterability in event log.

### UI tests and manual validation
- [x] Add UI regression coverage for temperature overlay and inspector.
- [~] Validate `docs/phase8/USER_SIDE_TESTING.md` sections 1–8 end-to-end.

## Completion gate
- [~] All PR-1/PR-2/PR-3 gates pass.
- [x] No determinism regressions in full suite.
- [~] Phase 8 docs updated with completion notes and any tuning deltas.

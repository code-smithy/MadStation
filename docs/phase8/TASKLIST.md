# Phase 8 Tasklist

Execution tasklist for delivering temperature gameplay in staged PRs.

## Status legend
- [ ] Not started
- [~] In progress
- [x] Done

## PR-1 — 8A Engine Thermal Baseline + API Observability

### Engine model
- [ ] Add per-tile `temperature_c` initialization for all world tiles.
- [ ] Add deterministic thermal update pass to tick execution order.
- [ ] Implement softened vacuum cooling coefficients.
- [ ] Implement tile-to-tile heat transfer (stable-order, deterministic).
- [ ] Add powered on/off `Heater` behavior.
- [ ] Add powered on/off `Cooler` behavior.
- [ ] Add waste heat contributions for selected heat-producing machines.
- [ ] Ensure thermal updates are replay-safe and snapshot-safe.

### API/transport observability
- [ ] Add thermal summary fields to `/status` output.
- [ ] Add per-tile temperature data to `/world` output.
- [ ] Add thermal delta payloads/events to websocket updates.

### Tests (PR-1 gate)
- [ ] Determinism test for identical tile temperature field across replay.
- [ ] Vacuum cooling trend test.
- [ ] Tile transfer convergence test.
- [ ] Heater power-gating test (powered vs unpowered).
- [ ] Cooler power-gating test (powered vs unpowered).
- [ ] Machine waste-heat behavior test.
- [ ] `/status` thermal fields test.
- [ ] `/world` thermal field test.

## PR-2 — 8B NPC Thermal Hazard + Flee

### NPC simulation
- [ ] Add thermal comfort and hazard thresholds to settings.
- [ ] Apply deterministic mild penalties outside comfort bounds.
- [ ] Apply deterministic health degradation in hazard bounds.
- [ ] Add flee behavior: choose safer thermal route when available.
- [ ] Preserve deterministic tie-breaking in flee routing.

### Events/observability
- [ ] Emit thermal hazard enter/exit events.
- [ ] Emit flee-related NPC decision events (or equivalent debug markers).

### Tests (PR-2 gate)
- [ ] NPC flees hazardous thermal area when escape path exists.
- [ ] NPC degrades deterministically when trapped in hazard.
- [ ] Thermal event payload coverage test.

## PR-3 — 8C Frontend Thermal UX

### UI features
- [ ] Add Temperature view mode toggle.
- [ ] Add temperature color scale/legend.
- [ ] Show tile temperature in inspector.
- [ ] Add heater/cooler quick actions in control panel.
- [ ] Add thermal event visualization/filterability in event log.

### UI tests and manual validation
- [ ] Add UI regression coverage for temperature overlay and inspector.
- [ ] Validate `docs/phase8/USER_SIDE_TESTING.md` sections 1–8 end-to-end.

## Completion gate
- [ ] All PR-1/PR-2/PR-3 gates pass.
- [ ] No determinism regressions in full suite.
- [ ] Phase 8 docs updated with completion notes and any tuning deltas.

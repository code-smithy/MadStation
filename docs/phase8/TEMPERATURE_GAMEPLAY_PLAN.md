# Phase 8 Proposal — Temperature Gameplay (Heaters, Coolers, Machine Heat)

This document captures the agreed Phase 8 direction and implementation constraints for a deterministic thermal gameplay loop.

## Confirmed decisions

1. **Granularity:** implement **per-tile temperature effects** in Phase 8 (not compartment-only).
2. **Tuning:** keep thermal behavior **softened for gameplay** in initial rollout.
3. **NPC behavior:** NPCs should **flee dangerous temperatures** (not only take damage).
4. **HVAC control:** `Heater`/`Cooler` ship as **on/off** machines first.
5. **Machine heat scope:** include machines that naturally generate heat in MVP (Generator/Refiner/Reactors and other high-power producers/processors).
6. **Machine failure from temperature:** **out of scope** for this phase.
7. **Delivery approach:** split implementation into multiple PRs where it reduces risk (engine first, then UI/polish).

## Why this next

Temperature is a strong systems connector:
- **Power**: heaters/coolers become meaningful, non-trivial consumers.
- **Machines**: generators/refiners can produce waste heat.
- **Atmospherics**: vacuum exposure should cool local environments.
- **NPC gameplay**: thermal stress and flee behavior create emergent failure cascades.

## Design principles

1. **Deterministic-first**: no wall-clock branching; tick-based updates in stable order.
2. **Per-tile thermal state**: simulation source of truth is at tile resolution.
3. **Config-driven tuning**: constants in `SETTINGS` with gameplay-soft defaults.
4. **Power-coupled actuation**: heaters/coolers only affect tiles when powered + enabled.
5. **Debuggable state**: clear thermal metrics/events in `/status`, `/world`, websocket deltas, and UI overlays.

## MVP model

### New world state
- `tile.temperature_c` for each tile (authoritative thermal field).
- Optional aggregate telemetry:
  - `thermal_state.avg_temp_c`
  - `thermal_state.min_temp_c`
  - `thermal_state.max_temp_c`
  - `thermal_state.danger_tile_count`

### Heat sources/sinks
- **Passive vacuum cooling**: tiles exposed to vacuum lose heat each tick (softened coefficients).
- **Tile-to-tile transfer**: neighboring traversable/open boundaries exchange heat deterministically.
- **Machine waste heat**: selected powered machines contribute local positive heat.
- **Active HVAC machines**:
  - `Heater`: raises nearby tile temps while powered.
  - `Cooler`: lowers nearby tile temps while powered.

### NPC thermal effects
- Add comfort/hazard thresholds:
  - `temp_comfort_min_c`, `temp_comfort_max_c`
  - `temp_hazard_min_c`, `temp_hazard_max_c`
- Outside comfort: mild penalties.
- In hazard: deterministic health loss + flee routing preference toward safer tiles.

### Command/model updates
- `Build` supports machine types: `Heater`, `Cooler`.
- Machine payload remains on/off-oriented (`enabled`); no target setpoint in this phase.

## Split plan (execution)

### 8A — Engine thermal baseline (per-tile) + API observability

- Add per-tile temperature field and thermal tick pass.
- Implement softened vacuum cooling and tile transfer.
- Add machine waste heat contributions for selected machine types.
- Add powered `Heater`/`Cooler` behavior (on/off).
- Expose thermal summaries in `/status` and tile temperatures in `/world`.

**Exit criteria**
- Thermal evolution is deterministic across replay.
- Vacuum breaches cool nearby tiles in expected trend.
- Heaters/coolers and machine heat only apply when powered.

### 8B — NPC thermal gameplay behavior

- Add hazard-aware NPC penalties and flee behavior.
- Emit thermal-related NPC/events in deltas for observability.

**Exit criteria**
- NPCs leave hazardous thermal zones when possible.
- Extreme temperatures still produce deterministic degradation when escape is impossible.

### 8C — Frontend thermal UX and validation

- Add Temperature view mode/overlay and legend.
- Show tile temperature in inspector.
- Add quick actions for placing heaters/coolers.
- Extend event feed for thermal state transitions.

**Exit criteria**
- Operator can induce and observe thermal effects from UI without manual JSON.

## Testing plan

### Automated tests (engine)
1. **Determinism:** same seed/commands => same tile temperature field over N ticks.
2. **Vacuum cooling:** breached/open tiles trend cooler at configured rates.
3. **Local transfer:** adjacent tile temperatures converge over time.
4. **HVAC power gating:** heater/cooler inert when unpowered, effective when powered.
5. **Machine heat:** configured hot machines raise local temperatures.
6. **NPC flee:** NPC in hazard chooses route toward safer temperature zone.

### Automated tests (API/frontend integration)
1. `/status` includes thermal summary fields.
2. `/world` includes tile temperature values.
3. Websocket deltas include thermal change/event payloads.
4. Frontend temperature overlay renders values/legend correctly.

### User-side checklist (manual)
1. Place powered heater in enclosed space; verify local warming.
2. Remove power; verify warming stops.
3. Create vacuum exposure; verify cooling trend near breach.
4. Place powered cooler; verify local cooling.
5. Observe NPC entering thermal hazard and fleeing when path exists.

## Out-of-scope explicitly

- Temperature-based machine breakage/reliability failures.
- Closed-loop thermostat/setpoint control.

## Suggested PR order

1. PR-1: 8A engine + tests + API thermal fields.
2. PR-2: 8B NPC flee + hazard events + tests.
3. PR-3: 8C frontend overlay/inspector/controls + UI tests + updated user testing doc.

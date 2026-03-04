# Phase 8 Proposal — Temperature Gameplay (Heaters, Coolers, Machine Heat)

This document proposes a deterministic temperature simulation layer that builds on the current compartment/oxygen/power model.

## Why this next

Temperature is a strong systems connector:
- **Power**: heaters/coolers become meaningful, non-trivial consumers.
- **Machines**: generators/refiners can produce waste heat.
- **Atmospherics**: vacuum exposure should rapidly cool local environments.
- **NPC gameplay**: thermal stress can shape priorities, routing, and failure cascades.

## Design principles

1. **Deterministic-first**: no wall-clock branching; all updates are tick-based and stable-order.
2. **Compartment-first baseline**: start with per-compartment temperature, optional per-tile later.
3. **Config-driven tuning**: all constants in `SETTINGS` with conservative defaults.
4. **Power-coupled actuation**: heaters/coolers only apply effects when powered and enabled.
5. **Debuggable state**: expose clear metrics/events in `/status`, `/world`, and websocket deltas.

## MVP model (Phase 8A)

### New world state (compartment-level)
- `compartment.temperature_c` (float, default e.g. `21.0`).
- Optional runtime aggregates:
  - `thermal_state.avg_temp_c`
  - `thermal_state.min_temp_c`
  - `thermal_state.max_temp_c`

### Heat sources/sinks
- **Passive sink**: vacuum-adjacent compartments lose heat each tick.
- **Door/open-boundary transfer**: neighboring compartments exchange heat.
- **Machine heat**: selected powered machines contribute `waste_heat_kw` (or `heat_delta_per_tick`).
- **Active HVAC machines**:
  - `Heater` raises local compartment temp when powered.
  - `Cooler` lowers local compartment temp when powered.

### NPC thermal effects (minimal)
- Add soft bounds:
  - `temp_comfort_min_c`, `temp_comfort_max_c`
  - `temp_hazard_min_c`, `temp_hazard_max_c`
- Outside comfort: gradual stamina/health penalties.
- Outside hazard: stronger deterministic damage (parallel to oxygen suffocation model).

### Suggested command extensions
- `Build` accepts machine types: `Heater`, `Cooler`.
- Existing machine payload may include:
  - `target_temp_c` (for future closed-loop control)
  - `enabled`.

## Split plan

## 8A — Thermal baseline + HVAC machines

- Add compartment temperature field and tick update pass.
- Add heat transfer between compartments and vacuum sink behavior.
- Add `Heater` and `Cooler` machine types with powered gating.
- Add machine waste-heat hooks for existing machines.
- Expose temperature in `/world` and summary in `/status`.

**Exit criteria**
- Compartments trend toward expected temperatures deterministically.
- Heaters/coolers visibly affect temperature only when powered.
- Breach/open-to-vacuum causes cooling trend.

## 8B — NPC thermal gameplay integration

- Add NPC thermal stress model and health penalties.
- Extend work-order/NPC decision hints (optional): prefer safer thermal routes.
- Emit thermal-related events in deltas (e.g. `thermal_hazard_entered`).

**Exit criteria**
- NPCs reliably degrade in extreme temperatures.
- Telemetry/events make thermal failures diagnosable.

## 8C — UI + operator workflows

- Add temperature overlay/view mode in frontend.
- Add inspector fields for tile/compartment temperature.
- Add quick-actions/forms for placing/configuring heaters/coolers.
- Add event-log entries for notable thermal transitions.

**Exit criteria**
- Operator can induce and observe thermal failures via UI only.

## Testing plan

### Automated tests (engine)
1. **Determinism**
   - Same seed + command stream => identical compartment temps over N ticks.
2. **Vacuum cooling**
   - Breached compartment temperature decreases at configured rate.
3. **Transfer**
   - Two connected compartments converge toward each other.
4. **HVAC powered gating**
   - Heater/cooler has no effect when unpowered, works when powered.
5. **Machine waste heat**
   - Running power producer/refiner increases local temp by configured amount.
6. **NPC thermal hazard**
   - NPC health declines in hazard zone according to deterministic constants.

### Automated tests (API/frontend integration)
1. `/status` includes thermal summary fields.
2. `/world` includes per-compartment temperature.
3. Websocket deltas include thermal-relevant change payloads.
4. Frontend temperature overlay renders expected legend/value mapping.

### User-side testing checklist (manual)
1. Place heater in sealed powered compartment; verify warming trend.
2. Disable power; verify warming stops.
3. Create breach to vacuum; verify cooling trend accelerates.
4. Place cooler; verify temperature drops while powered.
5. Observe NPC in thermal hazard and verify health decline/event feed.

## Open product questions (needs your decisions)

1. **Simulation granularity**: keep compartment-only for Phase 8, or include any per-tile thermal effects now?
2. **Realism vs gameplay**: should vacuum cooling be physically steep (fast lethal) or softened for playability?
3. **NPC behavior**: should NPCs proactively flee thermal hazards in 8B, or only take damage first?
4. **HVAC control**: do you want simple on/off machines first, or target-temperature control in first pass?
5. **Machine heat scope**: which machines should emit heat initially (Generator, Refiner, all powered consumers)?
6. **Failure policy**: can extreme temps disable machines, or should machine reliability remain out-of-scope?
7. **UI priority**: should temperature overlay ship in same PR as engine baseline, or immediately after in 8C?

## Suggested implementation order

1. 8A engine-only baseline + tests.
2. Minimal `/status` + `/world` thermal observability.
3. 8C frontend overlay + controls.
4. 8B NPC thermal consequences and balancing pass.

This order minimizes coupling risk while quickly making thermal behavior visible and testable.

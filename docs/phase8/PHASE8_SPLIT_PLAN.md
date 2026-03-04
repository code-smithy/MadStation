# Phase 8 Split Plan

Phase 8 adds deterministic temperature gameplay and thermal operator workflows.

## 8A — Engine thermal baseline (per-tile) + API observability

- Add per-tile thermal state and deterministic thermal tick update.
- Add softened vacuum cooling and local tile transfer.
- Add waste heat for selected machine types.
- Add powered on/off `Heater` and `Cooler` machines.
- Expose thermal summaries in `/status` and tile temps in `/world`.

**Exit criteria**
- Deterministic thermal state across replay.
- Observable, test-covered cooling/heating behavior.

## 8B — NPC thermal hazard and flee behavior

- Add hazard thresholds and deterministic health penalties.
- Add flee behavior when NPC occupies dangerous thermal tiles.
- Emit thermal hazard/flee events for debugging.

**Exit criteria**
- NPCs attempt escape from dangerous temperatures when feasible.
- Deterministic degradation path when escape unavailable.

## 8C — Frontend thermal UX

- Temperature overlay view mode + legend.
- Tile inspector temperature detail.
- Heater/cooler quick actions.
- Thermal event visibility in event feed.

**Exit criteria**
- Operators can run temperature scenarios entirely from UI.

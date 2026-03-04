# Phase 7 Split Plan

Phase 7 focuses on a minimal operator-facing frontend first, then richer UX polish.

## Phase 7A (implemented in this iteration)

- Added a server-rendered frontend entry page (`GET /`) with a lightweight simulation UI. ✅
- Added basic grid rendering, status panel, event log, and command controls (Build/Deconstruct/CreateWorkOrder). ✅
- Wired websocket snapshot/delta refresh flow into the UI for near-real-time updates. ✅
- Added WebSocket fallback endpoint cycling (`location.host`, `127.0.0.1`, `localhost`) with visible connection target. ✅
- Added color-coded tile rendering and NPC overlay markers plus legend for immediate map readability. ✅

## Phase 7B (planned)

- Improve command ergonomics (tile inspector, machine quick-actions, work-order metadata forms).
- Added Machine Quick Actions panel for one-click machine placement at selected coordinates. ✅
- Added View Mode selector (Tile/Compartment/Oxygen) and click-to-inspect tile detail panel. ✅
- Add focused visualization layers (power overlays, oxygen/compartment overlays, npc/work-order highlights).
- Added Power Network view mode and compact world stats panel (power gen/demand/networks). ✅
- Added compartment and oxygen visualization modes in the main grid. ✅
- Add frontend-side deterministic event feed filtering and severity tags.
- Added event log severity tags plus severity/text filters in the UI. ✅

## Exit target for Phase 7

- Operators can reliably induce and observe failure cascades through the UI.
- Frontend exposes core simulation controls and key runtime observability without requiring manual JSON typing.

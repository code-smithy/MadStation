# Phase 7 Split Plan

Phase 7 focuses on a minimal operator-facing frontend first, then richer UX polish.

## Phase 7A (implemented in this iteration)

- Added a server-rendered frontend entry page (`GET /`) with a lightweight simulation UI. ✅
- Added basic grid rendering, status panel, event log, and command controls (Build/Deconstruct/CreateWorkOrder). ✅
- Wired websocket snapshot/delta refresh flow into the UI for near-real-time updates. ✅
- Added WebSocket fallback endpoint cycling (`location.host`, `127.0.0.1`, `localhost`) with visible connection target. ✅
- Added color-coded tile rendering and NPC overlay markers plus legend for immediate map readability. ✅

## Phase 7B (implemented)

- Completed command ergonomics: tile inspector, machine quick-actions, and work-order metadata forms. ✅
- Added work-order metadata form controls (item id, destination, generator location) and payload builder. ✅
- Added Machine Quick Actions panel for one-click machine placement at selected coordinates. ✅
- Added View Mode selector (Tile/Compartment/Oxygen) and click-to-inspect tile detail panel. ✅
- Completed focused visualization layers: power overlays, oxygen/compartment overlays, and NPC/work-order highlights. ✅
- Added NPC/work-order highlight overlays with toggles and tile inspector work-order details. ✅
- Added Power Network view mode and compact world stats panel (power gen/demand/networks). ✅
- Added compartment and oxygen visualization modes in the main grid. ✅
- Completed frontend event feed filtering and severity tags. ✅
- Added event log severity tags plus severity/text filters in the UI. ✅

## Phase 7B closeout

- All previously open 7B bullets are now implemented and covered by the user-side testing guide sections 6–10. ✅

## Exit target for Phase 7

- Operators can reliably induce and observe failure cascades through the UI.
- Frontend exposes core simulation controls and key runtime observability without requiring manual JSON typing.

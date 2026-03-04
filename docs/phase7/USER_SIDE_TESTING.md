# Phase 7 User-Side Testing Guide

Use this checklist to validate the frontend MVP.

## Prerequisites

- Server running (`make run`).
- Browser open at `http://127.0.0.1:8000/`.

## 1) Load + connection

1. Open `/` and confirm the page renders with grid, status, controls, event log, and tile legend.
2. Confirm websocket connection indicator transitions to connected.
3. Confirm tick/status values refresh over time.

## 2) Structural command controls

1. Set coordinates and click **Send Build**.
2. Verify event log shows queued/applied acks.
3. Verify grid updates at chosen coordinates.
4. Click **Send Deconstruct** and verify reverse mutation.

## 3) Work-order command control

1. Select work type and click **Send CreateWorkOrder**.
2. Verify command ack in event log.
3. Verify `/world` includes new queued work-order state.

## 4) Status observability spot-check

1. Confirm status block includes key fields such as tick, queue depth, alive NPC count, and replay entries.
2. Trigger a few commands and confirm numbers react as expected.

## 5) Delta refresh behavior

1. Leave page open while simulation runs.
2. Confirm websocket deltas continue refreshing grid/status without manual reload.



## 6) View mode + tile inspector

1. Switch **View Mode** between Tile Type, Compartment ID, Oxygen Heat, and Power Network.
2. Confirm the map recolors immediately for each mode.
3. Click a few cells and verify inspector details include tile + coordinates and, when applicable, compartment oxygen/pressure and power state.
4. Confirm **World Stats** updates with power generation/demand/network counts.

## Troubleshooting

- If WS remains disconnected, check the displayed `ws:` target in the header.
- Retry using query override: `/?ws=ws://127.0.0.1:8000/ws` (or your explicit host/port).
- Ensure server logs show websocket upgrade attempts on `/ws`.


## Visual readability checks

1. Confirm tile colors are distinct for Vacuum/Floor/Wall/Door/Airlock/Window.
2. Confirm NPCs appear as red markers over tiles.
3. Hover tiles and verify coordinate/type tooltip appears.


## 7) Event log filtering

1. Generate mixed log entries (connect/disconnect, command send, errors).
2. Set **Severity** to `error` and verify only error-tagged lines remain visible.
3. Use **Filter text** to narrow entries by substring (for example `ws_connected` or `invalid`).
4. Return severity to `All` and clear filter text to restore full feed.


## 8) Machine quick actions

1. Set coordinates in Build panel and choose a machine type in **Machine Quick Actions**.
2. Click **Place Machine at X/Y** and confirm command acks in the event log.
3. Click the same tile in the map inspector and verify machine type appears in inspector details.
4. If using `Power Network` mode, verify placement can affect world stats/power behavior over subsequent ticks.


## 9) Work-order metadata controls

1. Select `HaulItem`, set `Item ID` and `Destination X/Y`, then submit and confirm ack is not INVALID_PAYLOAD.
2. Select `RefineIce`, set `Item ID`, submit, and verify queued/apply acknowledgment.
3. Select `FeedOxygenGenerator`, set `Item ID` and `Generator X/Y`, then submit and confirm ack.
4. Select `MineIce` and ensure `Mine Item Type` defaults to `IceChunk`.


## 10) NPC/work-order highlights

1. Ensure **Highlight NPCs** and **Highlight Work Orders** are enabled in View/Inspect panel.
2. Confirm NPC tiles show red dots and work-order target tiles show queued/active border highlights.
3. Toggle each highlight off and verify the corresponding overlay disappears while base tile view remains.
4. Click a highlighted work-order tile and confirm inspector includes `work_orders:` with status labels.

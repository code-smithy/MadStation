# Phase 7 User-Side Testing Guide

Use this checklist to validate the frontend MVP.

## Prerequisites

- Server running (`make run`).
- Browser open at `http://127.0.0.1:8000/`.

## 1) Load + connection

1. Open `/` and confirm the page renders with grid, status, controls, and event log.
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

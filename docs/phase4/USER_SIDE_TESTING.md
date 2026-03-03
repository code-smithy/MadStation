# Phase 4 User-Side Testing Guide

Use this checklist to validate initial NPC/death behavior.

## Prerequisites

- Server running (`make run`).
- WebSocket client (`wscat`) connected to `ws://127.0.0.1:8000/ws`.

## 1) Baseline runtime checks

- `GET /status` should include:
  - `alive_npc_count`
  - `work_order_count`
  - `death_log_count`
- `GET /world` should include:
  - `world.npcs`
  - `world.work_orders`
  - `world.death_log`

## 2) NPC roster checks

- Confirm `world.npcs` initially contains 10 named NPCs.
- Confirm each NPC has:
  - persistent `id`,
  - `speed` in range `[1,4]`,
  - `alive=true`.

## 3) Suffocation/death and work-order checks

- Create a vacuum breach path that depressurizes a compartment with NPC presence.
- Observe over ticks:
  - NPC `npc_survival_state` events when oxygen falls low,
  - eventual `npc_death` event at zero-oxygen damage threshold.
- Verify in `GET /world`:
  - death entry appended to `world.death_log`,
  - matching `DisposeBody` work order in `world.work_orders`.

## 4) Delta stream checks

Watch `delta_tick` payloads for:

- `entity_changes` entries with `type` in:
  - `npc_move`,
  - `npc_survival_state`,
  - `npc_death`.
- `work_order_changes` entries for auto-created `DisposeBody` orders.
- `death_log_appends` entries for newly recorded deaths.

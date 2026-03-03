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
  - `world.bodies`

## 2) NPC roster checks

- Confirm `world.npcs` initially contains 10 named NPCs.
- Confirm each NPC has:
  - persistent `id`,
  - `speed` in range `[1,4]`,
  - `alive=true`.

## 3) Suffocation/death and work-order checks

- Create a vacuum breach path that depressurizes a compartment with NPC presence.
- Observe over ticks:
  - NPC movement toward safer oxygen, including traversal through open doors when needed,
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


## 5) DisposeBody lifecycle checks

- After an NPC death, watch `delta_tick.work_order_changes` for:
  - `work_order_created`,
  - `work_order_assigned`,
  - `work_order_progress`,
  - `work_order_completed`.
- If an assignee dies before completion, verify `work_order_unassigned` and re-queue behavior.


## 6) Need/personality checks

- Observe `delta_tick.entity_changes` for `npc_need_state` when hunger/fatigue cross threshold.
- Confirm in low oxygen conditions NPCs still prioritize oxygen-safe movement over assigned work targets.
- In oxygen-safe conditions, compare diligent vs baseline NPC work-order progress rates (diligent should progress faster).


## 7) Body lifecycle metadata checks

- On death, verify `death_log_appends` includes extended fields (oxygen at death, compartment, personality, needs snapshot).
- Verify `entity_changes` includes `body_created` after death.
- After `DisposeBody` completion, verify `entity_changes` includes `body_disposed` and corresponding body record is marked disposed.

# Phase 9 Split Plan

Phase 9 introduces item equipment gameplay for NPCs.

## 9A — Inventory/equipment model

- Add item weight field and baseline weights for key item types.
- Add NPC equipment schema: two hand slots, one clothes slot, one backpack slot.
- Add backpack slot expansion (4 inventory slots) and carry-weight checks.

**Exit criteria**
- NPC state exposes deterministic equipment and inventory fields.
- Item weight is present on generated gameplay items.

## 9B — Core equipment behavior

- NPCs can pick up/equip MiningLaser into hand slots.
- NPCs can wear SpaceSuit in clothes slot.
- NPCs can equip Backpack to enable extra inventory slots.

**Exit criteria**
- Equip events are emitted and deterministic across ticks/replay.

## 9C — Gameplay coupling

- MineIce requires MiningLaser equipped.
- SpaceSuit protects against oxygen/pressure/temperature hazard damage.

**Exit criteria**
- Mine work orders are unassigned/requeued when no MiningLaser is equipped.
- Spacesuit-wearing NPCs avoid hazard damage under matching scenarios.

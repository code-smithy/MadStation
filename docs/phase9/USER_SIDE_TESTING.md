# Phase 9 User-Side Testing

## 1) Equipment defaults
1. Open `/world` and inspect at least one NPC object.
2. Confirm `equipment.hands` (2 entries), `equipment.clothes`, `equipment.backpack`, and `inventory` are present.

## 2) Auto-equip behavior
1. Place item records at an NPC tile (`MiningLaser`, `SpaceSuit`, `Backpack`).
2. Advance ticks and confirm websocket `entity_changes` include `npc_item_equipped`.

## 3) Mining prerequisite
1. Queue `MineIce` without MiningLaser equipped.
2. Confirm work-order unassign event with `reason=missing_mining_laser`.
3. Provide MiningLaser and confirm mining can complete.

## 4) Spacesuit protection
1. Put NPC in thermal/low-oxygen/low-pressure hazard.
2. Without spacesuit: health drops.
3. With spacesuit: hazard damage is prevented.

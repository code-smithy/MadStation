# Phase 9 Tasklist

## Status legend
- [ ] Not started
- [~] In progress
- [x] Done

## PR-1 — 9A model foundation
- [x] Add NPC equipment slots (hands x2, clothes x1, backpack x1).
- [x] Add backpack inventory slot budget (+4) and carry-weight config hooks.
- [x] Add item weight field for generated logistics items.

## PR-2 — 9B equip behavior
- [x] Add deterministic auto-equip pickup for MiningLaser, SpaceSuit, Backpack from tile items.
- [x] Emit equip/stow NPC events.

## PR-3 — 9C gameplay coupling
- [x] Require MiningLaser for `MineIce` completion path.
- [x] Add spacesuit protection for oxygen/pressure/thermal hazard damage.

## Test gate
- [x] Equipment slot defaults + auto-equip test.
- [x] MineIce prerequisite (MiningLaser required) test.
- [x] SpaceSuit hazard protection test.

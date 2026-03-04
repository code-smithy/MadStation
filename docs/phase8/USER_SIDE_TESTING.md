# Phase 8 User-Side Testing Guide

Use this checklist once Phase 8 implementation starts landing.

## Prerequisites

- Server running (`make run`).
- Browser open at `http://127.0.0.1:8000/`.

## 1) Thermal observability baseline

1. Open `/status` and verify thermal summary fields exist.
2. Open `/world` and verify per-tile temperature values are present.
3. Confirm websocket deltas continue while thermal scenarios run.

## 2) Heater behavior (powered)

1. Place a `Heater` on a powered tile.
2. Let simulation run for multiple ticks.
3. Verify local temperature near heater rises.

## 3) Heater behavior (unpowered)

1. Remove power or disable heater power path.
2. Verify heater no longer increases temperature.

## 4) Cooler behavior (powered)

1. Place a `Cooler` on a powered tile.
2. Verify local temperature decreases over subsequent ticks.

## 5) Vacuum cooling

1. Create a breach/open path to vacuum near a warm tile region.
2. Verify affected area cools faster than sealed interior.

## 6) Machine waste heat

1. Run a heat-producing machine (e.g., generator/refiner).
2. Verify nearby temperature increases compared to baseline.

## 7) NPC thermal flee behavior

1. Move/observe an NPC in a dangerous thermal region.
2. Verify NPC attempts to route toward safer temperatures.
3. If trapped, verify deterministic health decline.

## 8) Frontend thermal UX

1. Switch to Temperature view mode and verify heatmap/legend.
2. Click tiles and verify inspector shows temperature.
3. Place heater/cooler from UI quick actions and verify map changes.

## Completion gate

Mark Phase 8 complete only after sections 1–8 pass in one run.

# Determinism Test Plan (Phase 0)

## Goal
Ensure identical simulation outputs for identical seed + identical command stream.

## Test Strategy

1. Initialize world with fixed `world_seed`.
2. Feed predefined command log for N ticks.
3. Capture world hash every tick.
4. Repeat run on clean process.
5. Compare hash sequences and event logs.

## Required Assertions

- Hash sequence A == Hash sequence B for all ticks.
- Accepted/rejected command lists match exactly.
- Death log entries are byte-identical.

## Core Scenarios

1. Simultaneous conflicting builds (first-write-wins check).
2. Work-order race where one NPC completes before another arrives.
3. Topology edits triggering compartment recalculation.
4. Snapshot-save and restart replay equivalence.

## Acceptance Criteria

- 100% match across at least 1,000 ticks in baseline scenario suite.

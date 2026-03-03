# Default Constants (Initial Tuning Baseline)

> These are placeholders to unblock implementation. Balance iteratively after instrumentation.

## Simulation

- `TICK_RATE_HZ = 1`
- `WORLD_WIDTH = 50`
- `WORLD_HEIGHT = 50`

## NPC Movement

- `NPC_SPEED_MIN_TILES_PER_SEC = 1`
- `NPC_SPEED_DEFAULT_TILES_PER_SEC = 2`
- `NPC_SPEED_MAX_TILES_PER_SEC = 4`
- `DIAGONAL_MOVEMENT_ALLOWED = true`

## Oxygen / Suffocation

- `OXYGEN_SAFE_MIN_PERCENT = 15`
- `OXYGEN_FATAL_PERCENT = 0`
- `SUFFOCATION_DAMAGE_PER_TICK_AT_0_O2 = 8`

## Temperature (future-enabled)

- `INTERIOR_TARGET_C = 21`
- `VACUUM_BASELINE_C = -150`

## Radiation (future-enabled)

- `RADIATION_BASELINE = 1`
- `RADIATION_DAMAGE_THRESHOLD = 100`

## Throttle

- `SESSION_ACTION_COOLDOWN_SEC = 10`

## Persistence

- `SNAPSHOT_INTERVAL_TICKS = 60` (configurable)

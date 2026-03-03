# Phase 3 User-Side Testing Guide

Use this checklist to validate completed Phase 3 power behavior from an operator perspective.

## Prerequisites

- Server running (`make run`).
- WebSocket client available (`wscat`) or browser console.

## 1) Baseline runtime checks

1. `GET /status` should include:
   - `tick`
   - `machine_count`
   - `powered_consumer_count`
   - `unpowered_consumer_count`
2. `GET /world` should include:
   - `world.power_state`
   - `world.power_state.networks`
   - `world.machines`

## 2) Build machines via websocket

Connect:

```bash
wscat -c ws://127.0.0.1:8000/ws
```

Send commands (wait >10s between commands for throttle, or use a new websocket):

### Build oxygen generator consumer
```json
{"client_command_id":"p1","type":"Build","payload":{"x":20,"y":20,"tile_type":"Floor","machine":{"type":"OxygenGenerator","rate_per_tick":3,"consume_kw":2}}}
```

### Build low-priority light consumer
```json
{"client_command_id":"p2","type":"Build","payload":{"x":21,"y":20,"tile_type":"Floor","machine":{"type":"Light","consume_kw":1}}}
```

### Build insufficient generation source (for shedding test)
```json
{"client_command_id":"p3","type":"Build","payload":{"x":22,"y":20,"tile_type":"Floor","machine":{"type":"SolarPanel","generation_kw":2}}}
```

## 3) Validate load shedding

Refresh `GET /world` and inspect `world.power_state`:

- `demand` > `generation`
- `unpowered_consumers` should include lower priority entries before higher priority entries
- `disabled_priorities` should include lower-tier values when deficit exists

Expected for the setup above: oxygen generator remains powered while light is shed first.

## 4) Validate battery bridging

Add battery:

```json
{"client_command_id":"p4","type":"Build","payload":{"x":23,"y":20,"tile_type":"Floor","machine":{"type":"Battery","capacity":20,"stored":10,"discharge_kw":4,"charge_kw":2}}}
```

Refresh `/world`:

- `power_state.battery_discharge` should become > 0 when deficit exists.
- `world.machines["23,20"].stored` should decrease while discharging.

## 5) Validate oxygen generator power gating

- In deficit state with no enough generation/battery, oxygen generator should stop increasing oxygen.
- Add reactor generation:

```json
{"client_command_id":"p5","type":"Build","payload":{"x":24,"y":20,"tile_type":"Floor","machine":{"type":"Reactor","generation_kw":10}}}
```

- Refresh `/world` over a few ticks:
  - generator should re-enter `powered_consumers`
  - compartment oxygen near generator should trend upward.

## 6) Delta stream checks

Watch websocket `delta_tick` messages:

- `command_count` increments on applied command ticks.
- `tile_changes` include structural changes.
- `entity_changes` include compartment updates when oxygen/pressure changes.


## 7) Validate topology-aware networks

Create two disconnected sealed rooms and place generation in one, consumer in the other.

Expected:
- Consumer in the non-powered room remains in `unpowered_consumers`.
- `world.power_state.networks` shows separate `network_id` entries with independent generation/demand.
- No cross-network battery discharge/charge effects.


## 8) Deterministic recovery ordering check

1. Create a deficit setup with one life-support consumer and two lower-priority consumers.
2. Confirm lower-priority consumers are shed first (`unpowered_consumers` + `disabled_priorities`).
3. Add generation back (e.g., reactor) and confirm all consumers recover and `disabled_priorities` becomes empty.
4. Repeat the same command sequence and compare resulting `powered_consumers`/`unpowered_consumers` order; results should match.

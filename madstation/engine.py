from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from madstation.config import SETTINGS
from madstation.protocol import ClientCommand, CommandAck, CommandResult, CommandType, DeltaTick, SnapshotFull

TILE_VACUUM = "Vacuum"
TILE_FLOOR = "Floor"
TILE_WALL = "Wall"
TILE_DOOR = "Door"
TILE_AIRLOCK = "Airlock"
TILE_WINDOW = "Window"

ALL_TILE_TYPES = {TILE_VACUUM, TILE_FLOOR, TILE_WALL, TILE_DOOR, TILE_AIRLOCK, TILE_WINDOW}
WALKABLE_TILES = {TILE_FLOOR, TILE_DOOR, TILE_AIRLOCK}
COMPARTMENT_FILL_TILES = {TILE_FLOOR, TILE_AIRLOCK}

MACHINE_OXYGEN_GENERATOR = "OxygenGenerator"
MACHINE_SOLAR_PANEL = "SolarPanel"
MACHINE_REACTOR = "Reactor"
MACHINE_BATTERY = "Battery"
MACHINE_HEATER = "Heater"
MACHINE_LIGHT = "Light"

POWER_PRIORITY = dict(SETTINGS.power_priority_tiers)


@dataclass
class PendingCommand:
    session_id: str
    command: ClientCommand
    enqueued_at_tick: int


class SocketLike(Protocol):
    async def accept(self) -> None: ...
    async def send_json(self, payload: dict) -> None: ...


class SimulationEngine:
    def __init__(self) -> None:
        width, height = 50, 50
        self.tick: int = 0
        self.server_sequence_id: int = 0
        self.world_state: dict = {
            "world": {"width": width, "height": height},
            "power": {"mode": "topology_aware_networks"},
            "power_state": {
                "generation": 0.0,
                "demand": 0.0,
                "battery_discharge": 0.0,
                "battery_charge": 0.0,
                "powered_consumers": [],
                "unpowered_consumers": [],
                "disabled_priorities": [],
                "networks": [],
            },
            "population": 0,
            "grid": [[TILE_FLOOR for _ in range(width)] for _ in range(height)],
            "door_states": {},
            "machines": {},
            "compartments": [],
            "compartment_index": {},
        }
        self.connections: dict[str, SocketLike] = {}
        self.command_queue: asyncio.Queue[PendingCommand] = asyncio.Queue()
        self.last_action_at: dict[str, float] = {}
        self.command_ack_cache: dict[str, dict[str, CommandAck]] = {}
        self._running = False
        self._recompute_compartments()

    def next_session_id(self) -> str:
        return f"anon-{uuid4().hex}"

    async def connect(self, websocket: SocketLike) -> str:
        await websocket.accept()
        session_id = self.next_session_id()
        self.connections[session_id] = websocket
        self.command_ack_cache.setdefault(session_id, {})
        snapshot = SnapshotFull(session_id=session_id, snapshot_tick=self.tick, state=self.world_state)
        await self._safe_send(session_id, snapshot.model_dump())
        return session_id

    def disconnect(self, session_id: str) -> None:
        self.connections.pop(session_id, None)

    async def enqueue_command(self, session_id: str, command: ClientCommand) -> CommandAck:
        cached_ack = self.command_ack_cache.setdefault(session_id, {}).get(command.client_command_id)
        if cached_ack is not None:
            return cached_ack

        if not self._allowed_by_throttle(session_id):
            ack = CommandAck(client_command_id=command.client_command_id, result=CommandResult.THROTTLED, tick=self.tick)
            self.command_ack_cache[session_id][command.client_command_id] = ack
            return ack

        if not self._validate_command_payload(command):
            ack = CommandAck(client_command_id=command.client_command_id, result=CommandResult.INVALID_PAYLOAD, tick=self.tick)
            self.command_ack_cache[session_id][command.client_command_id] = ack
            return ack

        await self.command_queue.put(PendingCommand(session_id=session_id, command=command, enqueued_at_tick=self.tick))
        self.last_action_at[session_id] = time.monotonic()
        ack = CommandAck(client_command_id=command.client_command_id, result=CommandResult.QUEUED, tick=self.tick)
        self.command_ack_cache[session_id][command.client_command_id] = ack
        return ack

    def world_snapshot(self) -> dict:
        return {"tick": self.tick, "world": self.world_state}

    def runtime_status(self) -> dict[str, int]:
        open_door_count = sum(
            1 for value in self.world_state["door_states"].values() if isinstance(value, dict) and value.get("open", False)
        )
        return {
            "tick": self.tick,
            "server_sequence_id": self.server_sequence_id,
            "connected_clients": len(self.connections),
            "queued_commands": self.command_queue.qsize(),
            "compartment_count": len(self.world_state["compartments"]),
            "open_door_count": open_door_count,
            "machine_count": len(self.world_state["machines"]),
            "powered_consumer_count": len(self.world_state["power_state"].get("powered_consumers", [])),
            "unpowered_consumer_count": len(self.world_state["power_state"].get("unpowered_consumers", [])),
        }

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        if self._running:
            return

        self._running = True
        tick_interval = 1 / SETTINGS.tick_rate_hz
        while self._running:
            tick_start = time.monotonic()
            await self._execute_tick()
            elapsed = time.monotonic() - tick_start
            await asyncio.sleep(max(0.0, tick_interval - elapsed))

    async def _execute_tick(self) -> None:
        self.tick += 1
        drained: list[PendingCommand] = []
        while not self.command_queue.empty():
            drained.append(self.command_queue.get_nowait())

        claimed_targets: set[str] = set()
        applied = 0
        tile_changes: list[dict] = []
        topology_changed = False

        for pending in drained:
            target_key = self._target_key(pending.command)
            if target_key in claimed_targets:
                ack = CommandAck(
                    client_command_id=pending.command.client_command_id,
                    result=CommandResult.CONFLICT_STALE_TARGET,
                    tick=self.tick,
                )
                self.command_ack_cache[pending.session_id][pending.command.client_command_id] = ack
                await self._safe_send(pending.session_id, ack.model_dump())
                continue

            claimed_targets.add(target_key)
            self.server_sequence_id += 1
            applied += 1

            if pending.command.type in {CommandType.BUILD, CommandType.DECONSTRUCT}:
                tile_change, did_change = self._apply_structural_command(pending.command)
                if tile_change is not None:
                    tile_changes.append(tile_change)
                topology_changed = topology_changed or did_change

            ack = CommandAck(
                client_command_id=pending.command.client_command_id,
                result=CommandResult.APPLIED,
                server_sequence_id=self.server_sequence_id,
                tick=self.tick,
            )
            self.command_ack_cache[pending.session_id][pending.command.client_command_id] = ack
            await self._safe_send(pending.session_id, ack.model_dump())

        door_changes = self._auto_update_doors()
        if door_changes:
            tile_changes.extend(door_changes)
            topology_changed = True

        before_compartments = self._compartment_snapshot_map()
        before_power = self._power_snapshot()
        if topology_changed:
            self._recompute_compartments()

        self._update_power()
        self._update_oxygen()

        after_compartments = self._compartment_snapshot_map()
        after_power = self._power_snapshot()
        compartment_changes = self._compartment_changes(before_compartments, after_compartments)
        power_events = self._power_events(before_power, after_power)

        delta = DeltaTick(
            tick=self.tick,
            world_hash=self._world_hash(),
            command_count=applied,
            tile_changes=tile_changes,
            entity_changes=compartment_changes + power_events,
        )
        await self._broadcast(delta.model_dump())

    async def _broadcast(self, payload: dict) -> None:
        for session_id in list(self.connections.keys()):
            await self._safe_send(session_id, payload)

    async def _safe_send(self, session_id: str, payload: dict) -> None:
        websocket = self.connections.get(session_id)
        if websocket is None:
            return
        try:
            await websocket.send_json(payload)
        except Exception:
            self.disconnect(session_id)

    def _target_key(self, command: ClientCommand) -> str:
        if command.type in {CommandType.BUILD, CommandType.DECONSTRUCT}:
            return f"tile:{command.payload['x']}:{command.payload['y']}"
        if command.type is CommandType.CREATE_WORK_ORDER:
            location = command.payload["location"]
            return f"workorder:{location['x']}:{location['y']}:{command.payload['work_type']}"
        return f"generic:{command.client_command_id}"

    @staticmethod
    def _validate_xy(x: object, y: object) -> bool:
        return isinstance(x, int) and isinstance(y, int) and (0 <= x < 50) and (0 <= y < 50)

    def _validate_command_payload(self, command: ClientCommand) -> bool:
        payload = command.payload
        if command.type in {CommandType.BUILD, CommandType.DECONSTRUCT}:
            if not self._validate_xy(payload.get("x"), payload.get("y")):
                return False
            if command.type is CommandType.BUILD and "tile_type" in payload:
                tile_type = payload.get("tile_type")
                if not (isinstance(tile_type, str) and tile_type in (ALL_TILE_TYPES - {TILE_VACUUM})):
                    return False
            machine = payload.get("machine")
            if machine is None:
                return True
            return self._validate_machine_payload(machine)

        if command.type is CommandType.CREATE_WORK_ORDER:
            work_type = payload.get("work_type")
            location = payload.get("location")
            if not isinstance(work_type, str) or not work_type:
                return False
            if not isinstance(location, dict):
                return False
            return self._validate_xy(location.get("x"), location.get("y"))

        return False

    def _validate_machine_payload(self, machine: object) -> bool:
        if not isinstance(machine, dict):
            return False
        machine_type = machine.get("type")
        if machine_type == MACHINE_OXYGEN_GENERATOR:
            rate = machine.get("rate_per_tick", 2.0)
            consume = machine.get("consume_kw", 2.0)
            return self._valid_positive(rate, 25.0) and self._valid_positive(consume, 25.0)
        if machine_type == MACHINE_SOLAR_PANEL:
            return self._valid_positive(machine.get("generation_kw", 4.0), 100.0)
        if machine_type == MACHINE_REACTOR:
            return self._valid_positive(machine.get("generation_kw", 12.0), 200.0)
        if machine_type == MACHINE_BATTERY:
            return (
                self._valid_positive(machine.get("capacity", 50.0), 10000.0)
                and self._valid_positive(machine.get("discharge_kw", 5.0), 200.0)
                and self._valid_non_negative(machine.get("stored", 0.0), 10000.0)
            )
        if machine_type in {MACHINE_HEATER, MACHINE_LIGHT}:
            return self._valid_positive(machine.get("consume_kw", 1.0), 100.0)
        return False

    @staticmethod
    def _valid_positive(value: object, max_value: float) -> bool:
        return isinstance(value, (int, float)) and 0 < float(value) <= max_value

    @staticmethod
    def _valid_non_negative(value: object, max_value: float) -> bool:
        return isinstance(value, (int, float)) and 0 <= float(value) <= max_value

    def _allowed_by_throttle(self, session_id: str) -> bool:
        prev = self.last_action_at.get(session_id)
        if prev is None:
            return True
        return (time.monotonic() - prev) >= SETTINGS.action_cooldown_sec

    def _world_hash(self) -> str:
        value = {
            "tick": self.tick,
            "server_sequence_id": self.server_sequence_id,
            "world_state": self.world_state,
        }
        encoded = json.dumps(value, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _apply_structural_command(self, command: ClientCommand) -> tuple[dict | None, bool]:
        x = command.payload["x"]
        y = command.payload["y"]
        key = self._xy_key(x, y)
        before = self.world_state["grid"][y][x]
        after = command.payload.get("tile_type", TILE_WALL) if command.type is CommandType.BUILD else TILE_VACUUM

        changed_tile = before != after
        if changed_tile:
            self.world_state["grid"][y][x] = after
            if after == TILE_DOOR:
                self.world_state["door_states"][key] = {"open": False}
            else:
                self.world_state["door_states"].pop(key, None)

        machine_payload = command.payload.get("machine") if command.type is CommandType.BUILD else None
        machine_changed = False
        if isinstance(machine_payload, dict):
            self.world_state["machines"][key] = self._normalize_machine(machine_payload)
            machine_changed = True
        elif key in self.world_state["machines"] and (command.type is CommandType.DECONSTRUCT or changed_tile):
            self.world_state["machines"].pop(key, None)
            machine_changed = True

        if not changed_tile and not machine_changed:
            return None, False
        if changed_tile:
            return {"x": x, "y": y, "before": before, "after": after}, True
        return {"x": x, "y": y, "type": "machine_change", "machine_key": key}, True

    def _normalize_machine(self, machine: dict) -> dict:
        machine_type = machine.get("type")
        if machine_type == MACHINE_OXYGEN_GENERATOR:
            return {
                "type": MACHINE_OXYGEN_GENERATOR,
                "enabled": bool(machine.get("enabled", True)),
                "rate_per_tick": float(machine.get("rate_per_tick", 2.0)),
                "consume_kw": float(machine.get("consume_kw", 2.0)),
            }
        if machine_type == MACHINE_SOLAR_PANEL:
            return {
                "type": MACHINE_SOLAR_PANEL,
                "enabled": bool(machine.get("enabled", True)),
                "generation_kw": float(machine.get("generation_kw", 4.0)),
            }
        if machine_type == MACHINE_REACTOR:
            return {
                "type": MACHINE_REACTOR,
                "enabled": bool(machine.get("enabled", True)),
                "generation_kw": float(machine.get("generation_kw", 12.0)),
            }
        if machine_type == MACHINE_BATTERY:
            capacity = float(machine.get("capacity", 50.0))
            stored = float(machine.get("stored", capacity / 2))
            return {
                "type": MACHINE_BATTERY,
                "enabled": bool(machine.get("enabled", True)),
                "capacity": capacity,
                "stored": max(0.0, min(capacity, stored)),
                "discharge_kw": float(machine.get("discharge_kw", 5.0)),
                "charge_kw": float(machine.get("charge_kw", 5.0)),
            }
        if machine_type == MACHINE_HEATER:
            return {
                "type": MACHINE_HEATER,
                "enabled": bool(machine.get("enabled", True)),
                "consume_kw": float(machine.get("consume_kw", 2.0)),
            }
        if machine_type == MACHINE_LIGHT:
            return {
                "type": MACHINE_LIGHT,
                "enabled": bool(machine.get("enabled", True)),
                "consume_kw": float(machine.get("consume_kw", 1.0)),
            }
        return {"type": str(machine_type), "enabled": False}

    def _auto_update_doors(self) -> list[dict]:
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        door_changes: list[dict] = []

        for key, state in list(self.world_state["door_states"].items()):
            x_str, y_str = key.split(",")
            x, y = int(x_str), int(y_str)
            if not (0 <= x < width and 0 <= y < height):
                continue
            if self.world_state["grid"][y][x] != TILE_DOOR:
                self.world_state["door_states"].pop(key, None)
                continue

            before_open = bool(state.get("open", False))
            should_open = self._door_should_open(x, y)
            if before_open != should_open:
                self.world_state["door_states"][key] = {"open": should_open}
                door_changes.append(
                    {
                        "x": x,
                        "y": y,
                        "type": "door_state",
                        "door_open_before": before_open,
                        "door_open_after": should_open,
                    }
                )

        return door_changes

    def _door_should_open(self, x: int, y: int) -> bool:
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        interior_neighbors = 0
        for nx, ny in self._neighbors4(x, y, width, height):
            tile = self.world_state["grid"][ny][nx]
            if tile in COMPARTMENT_FILL_TILES:
                interior_neighbors += 1
        return interior_neighbors >= 2

    def _recompute_compartments(self) -> None:
        grid = self.world_state["grid"]
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        visited: set[tuple[int, int]] = set()
        compartment_index: dict[str, int] = {}
        compartments: list[dict] = []

        old_map = {int(c["id"]): float(c.get("oxygen_percent", 100.0)) for c in self.world_state.get("compartments", [])}
        old_index = self.world_state.get("compartment_index", {})

        def oxygen_for_tile(tx: int, ty: int) -> float:
            old_id = old_index.get(self._xy_key(tx, ty))
            if old_id is None:
                return 100.0
            return old_map.get(int(old_id), 100.0)

        comp_id = 1
        for y in range(height):
            for x in range(width):
                if (x, y) in visited or grid[y][x] not in COMPARTMENT_FILL_TILES:
                    continue

                queue = [(x, y)]
                visited.add((x, y))
                tiles: list[tuple[int, int]] = []
                oxygen_total = 0.0

                while queue:
                    cx, cy = queue.pop()
                    tiles.append((cx, cy))
                    oxygen_total += oxygen_for_tile(cx, cy)
                    for nx, ny in self._neighbors4(cx, cy, width, height):
                        if (nx, ny) in visited or grid[ny][nx] not in COMPARTMENT_FILL_TILES:
                            continue
                        visited.add((nx, ny))
                        queue.append((nx, ny))

                oxygen = oxygen_total / max(1, len(tiles))
                compartments.append(
                    {
                        "id": comp_id,
                        "oxygen_percent": round(oxygen, 2),
                        "pressure": round(oxygen / 100, 3),
                        "temperature": 21.0,
                        "radiation": 0.1,
                        "contamination": 0.0,
                        "tile_count": len(tiles),
                    }
                )
                for tx, ty in tiles:
                    compartment_index[self._xy_key(tx, ty)] = comp_id
                comp_id += 1

        self.world_state["compartments"] = compartments
        self.world_state["compartment_index"] = compartment_index

    def _update_power(self) -> None:
        machines = self.world_state["machines"]
        machines_by_network: dict[str, list[str]] = {}
        for key in sorted(machines.keys()):
            network_id = self._power_network_id(key)
            machines_by_network.setdefault(network_id, []).append(key)

        generation = 0.0
        demand = 0.0
        battery_discharge = 0.0
        battery_charge = 0.0
        powered_consumers: list[str] = []
        unpowered_consumers: list[str] = []
        disabled_priorities: set[int] = set()
        network_states: list[dict] = []

        for network_id in sorted(machines_by_network.keys()):
            network_machine_keys = machines_by_network[network_id]
            result = self._update_power_for_network(network_id, network_machine_keys)
            generation += result["generation"]
            demand += result["demand"]
            battery_discharge += result["battery_discharge"]
            battery_charge += result["battery_charge"]
            powered_consumers.extend(result["powered_consumers"])
            unpowered_consumers.extend(result["unpowered_consumers"])
            disabled_priorities.update(result["disabled_priorities"])
            network_states.append(result)

        self.world_state["power_state"] = {
            "generation": round(generation, 3),
            "demand": round(demand, 3),
            "battery_discharge": round(battery_discharge, 3),
            "battery_charge": round(battery_charge, 3),
            "powered_consumers": sorted(powered_consumers),
            "unpowered_consumers": sorted(unpowered_consumers),
            "disabled_priorities": sorted(disabled_priorities),
            "networks": network_states,
        }

    def _power_network_id(self, machine_key: str) -> str:
        comp_id = self.world_state.get("compartment_index", {}).get(machine_key)
        if comp_id is not None:
            return f"compartment:{int(comp_id)}"
        return f"isolated:{machine_key}"

    def _update_power_for_network(self, network_id: str, machine_keys: list[str]) -> dict:
        machines = self.world_state["machines"]
        generation = 0.0
        demand = 0.0
        consumers: list[tuple[str, int, float]] = []
        battery_keys: list[str] = []

        for key in machine_keys:
            machine = machines[key]
            if not isinstance(machine, dict) or not machine.get("enabled", True):
                continue
            mtype = machine.get("type")
            if mtype in {MACHINE_SOLAR_PANEL, MACHINE_REACTOR}:
                generation += float(machine.get("generation_kw", 0.0))
            elif mtype == MACHINE_BATTERY:
                battery_keys.append(key)
            elif mtype in POWER_PRIORITY:
                consume = float(machine.get("consume_kw", 0.0))
                demand += consume
                consumers.append((key, POWER_PRIORITY[mtype], consume))

        deficit = max(0.0, demand - generation)
        battery_discharge = 0.0
        for key in battery_keys:
            if deficit <= 0:
                break
            battery = machines[key]
            available = min(float(battery.get("stored", 0.0)), float(battery.get("discharge_kw", 0.0)))
            draw = min(deficit, available)
            if draw <= 0:
                continue
            battery["stored"] = max(0.0, float(battery.get("stored", 0.0)) - draw)
            battery_discharge += draw
            deficit -= draw

        total_available = generation + battery_discharge
        powered_consumers: list[str] = []
        unpowered_consumers: list[str] = []
        disabled_priorities: set[int] = set()

        for key, priority, consume in sorted(consumers, key=lambda item: (item[1], item[0])):
            if total_available >= consume:
                total_available -= consume
                powered_consumers.append(key)
            else:
                unpowered_consumers.append(key)
                disabled_priorities.add(priority)

        battery_charge = 0.0
        for key in battery_keys:
            if total_available <= 0:
                break
            battery = machines[key]
            capacity = float(battery.get("capacity", 0.0))
            stored = float(battery.get("stored", 0.0))
            room = max(0.0, capacity - stored)
            charge_rate = float(battery.get("charge_kw", 0.0))
            gain = min(total_available, room, charge_rate)
            if gain <= 0:
                continue
            battery["stored"] = stored + gain
            battery_charge += gain
            total_available -= gain

        return {
            "network_id": network_id,
            "generation": round(generation, 3),
            "demand": round(demand, 3),
            "battery_discharge": round(battery_discharge, 3),
            "battery_charge": round(battery_charge, 3),
            "powered_consumers": sorted(powered_consumers),
            "unpowered_consumers": sorted(unpowered_consumers),
            "disabled_priorities": sorted(disabled_priorities),
        }

    def _update_oxygen(self) -> None:
        grid = self.world_state["grid"]
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        index = self.world_state["compartment_index"]
        compartments = self.world_state["compartments"]

        leak_counts: dict[int, int] = {int(c["id"]): 0 for c in compartments}
        tile_counts: dict[int, int] = {int(c["id"]): int(c["tile_count"]) for c in compartments}
        oxygen_values: dict[int, float] = {int(c["id"]): float(c["oxygen_percent"]) for c in compartments}
        oxygen_delta: dict[int, float] = {int(c["id"]): 0.0 for c in compartments}

        for key, comp_id in index.items():
            x_str, y_str = key.split(",")
            x, y = int(x_str), int(y_str)
            for nx, ny in self._neighbors4(x, y, width, height):
                if grid[ny][nx] == TILE_VACUUM:
                    leak_counts[int(comp_id)] += 1

        powered = set(self.world_state.get("power_state", {}).get("powered_consumers", []))
        for key, machine in self.world_state["machines"].items():
            if not isinstance(machine, dict) or not machine.get("enabled", True):
                continue
            if machine.get("type") != MACHINE_OXYGEN_GENERATOR:
                continue
            if key not in powered:
                continue
            comp_id = index.get(key)
            if comp_id is None:
                continue
            oxygen_delta[int(comp_id)] += float(machine.get("rate_per_tick", 2.0))

        for key, state in self.world_state["door_states"].items():
            if not state.get("open", False):
                continue
            x_str, y_str = key.split(",")
            x, y = int(x_str), int(y_str)
            adjacent_comp_ids: list[int] = []
            has_vacuum_neighbor = False

            for nx, ny in self._neighbors4(x, y, width, height):
                neighbor_tile = grid[ny][nx]
                if neighbor_tile == TILE_VACUUM:
                    has_vacuum_neighbor = True
                comp = index.get(self._xy_key(nx, ny))
                if comp is not None:
                    adjacent_comp_ids.append(int(comp))

            unique_adjacent = sorted(set(adjacent_comp_ids))
            if len(unique_adjacent) >= 2:
                left, right = unique_adjacent[0], unique_adjacent[1]
                gradient = oxygen_values[left] - oxygen_values[right]
                transfer = max(-3.0, min(3.0, gradient * 0.15))
                oxygen_delta[left] -= transfer
                oxygen_delta[right] += transfer

            if has_vacuum_neighbor and len(unique_adjacent) == 1:
                leak_counts[unique_adjacent[0]] += 1

        for compartment in compartments:
            comp_id = int(compartment["id"])
            tile_count = max(1, tile_counts[comp_id])
            exposure_ratio = leak_counts[comp_id] / tile_count
            leak_rate = min(10.0, exposure_ratio * 200.0)
            next_oxygen = oxygen_values[comp_id] + oxygen_delta[comp_id] - leak_rate
            next_oxygen = max(0.0, min(100.0, next_oxygen))
            compartment["oxygen_percent"] = round(next_oxygen, 2)
            compartment["pressure"] = round(next_oxygen / 100, 3)

    def _compartment_snapshot_map(self) -> dict[int, dict]:
        snapshot: dict[int, dict] = {}
        for compartment in self.world_state["compartments"]:
            cid = int(compartment["id"])
            snapshot[cid] = {
                "oxygen_percent": float(compartment.get("oxygen_percent", 0.0)),
                "pressure": float(compartment.get("pressure", 0.0)),
                "tile_count": int(compartment.get("tile_count", 0)),
            }
        return snapshot

    @staticmethod
    def _compartment_changes(before: dict[int, dict], after: dict[int, dict]) -> list[dict]:
        changes: list[dict] = []
        for cid, current in after.items():
            previous = before.get(cid)
            if previous is None:
                changes.append({"type": "compartment_change", "compartment_id": cid, "reason": "created", "current": current})
                continue
            if (
                current["oxygen_percent"] != previous["oxygen_percent"]
                or current["pressure"] != previous["pressure"]
                or current["tile_count"] != previous["tile_count"]
            ):
                changes.append(
                    {
                        "type": "compartment_change",
                        "compartment_id": cid,
                        "reason": "updated",
                        "previous": previous,
                        "current": current,
                    }
                )

        for cid in before.keys() - after.keys():
            changes.append({"type": "compartment_change", "compartment_id": cid, "reason": "removed", "previous": before[cid]})
        return changes

    def _power_snapshot(self) -> dict:
        state = self.world_state.get("power_state", {})
        return {
            "generation": float(state.get("generation", 0.0)),
            "demand": float(state.get("demand", 0.0)),
            "powered": list(state.get("powered_consumers", [])),
            "unpowered": list(state.get("unpowered_consumers", [])),
            "disabled": list(state.get("disabled_priorities", [])),
        }

    @staticmethod
    def _power_events(before: dict, after: dict) -> list[dict]:
        events: list[dict] = []
        before_unpowered = len(before.get("unpowered", []))
        after_unpowered = len(after.get("unpowered", []))
        before_powered = len(before.get("powered", []))
        after_powered = len(after.get("powered", []))

        if before_unpowered == 0 and after_unpowered > 0:
            event_type = "blackout_started" if after_powered == 0 else "brownout_started"
            events.append(
                {
                    "type": "power_event",
                    "event": event_type,
                    "unpowered_count": after_unpowered,
                    "powered_count": after_powered,
                }
            )

        if before_unpowered > 0 and after_unpowered == 0:
            events.append(
                {
                    "type": "power_event",
                    "event": "power_recovered",
                    "unpowered_count": after_unpowered,
                    "powered_count": after_powered,
                }
            )

        if before_unpowered != after_unpowered and after_unpowered > 0:
            events.append(
                {
                    "type": "power_event",
                    "event": "brownout_changed",
                    "unpowered_count": after_unpowered,
                    "powered_count": after_powered,
                    "delta_unpowered": after_unpowered - before_unpowered,
                }
            )

        if before_powered != after_powered:
            events.append(
                {
                    "type": "power_event",
                    "event": "powered_consumers_changed",
                    "powered_count": after_powered,
                    "delta_powered": after_powered - before_powered,
                }
            )

        return events

    @staticmethod
    def _neighbors4(x: int, y: int, width: int, height: int) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                points.append((nx, ny))
        return points

    @staticmethod
    def _xy_key(x: int, y: int) -> str:
        return f"{x},{y}"

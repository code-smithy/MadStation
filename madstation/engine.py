from __future__ import annotations

import asyncio
from copy import deepcopy
from collections import deque
import hashlib
import json
from pathlib import Path
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

DEFAULT_STATION_MIN_X = 14
DEFAULT_STATION_MAX_X = 35
DEFAULT_STATION_MIN_Y = 14
DEFAULT_STATION_MAX_Y = 35

MACHINE_OXYGEN_GENERATOR = "OxygenGenerator"
MACHINE_SOLAR_PANEL = "SolarPanel"
MACHINE_REACTOR = "Reactor"
MACHINE_BATTERY = "Battery"
MACHINE_HEATER = "Heater"
MACHINE_COOLER = "Cooler"
MACHINE_LIGHT = "Light"

POWER_PRIORITY = dict(SETTINGS.power_priority_tiers)
SUPPORTED_COMMAND_WORK_TYPES = {"MineIce", "HaulItem", "RefineIce", "FeedOxygenGenerator"}
WORK_TYPES_WITH_ITEM = {"HaulItem", "RefineIce", "FeedOxygenGenerator"}

ITEM_MINING_LASER = "MiningLaser"
ITEM_SPACE_SUIT = "SpaceSuit"
ITEM_BACKPACK = "Backpack"
ITEM_WEIGHT_BY_TYPE = {
    "IceChunk": 3.0,
    "WaterUnit": 2.0,
    ITEM_MINING_LASER: 5.0,
    ITEM_SPACE_SUIT: 8.0,
    ITEM_BACKPACK: 2.0,
}


@dataclass
class PendingCommand:
    session_id: str
    command: ClientCommand
    enqueued_at_tick: int


class SocketLike(Protocol):
    async def accept(self) -> None: ...
    async def send_json(self, payload: dict) -> None: ...


class SimulationEngine:
    def __init__(
        self,
        snapshot_path: str | None = None,
        snapshot_cadence_ticks: int | None = None,
        replay_log_path: str | None = None,
        replay_max_entries: int | None = None,
        load_snapshot: bool = False,
    ) -> None:
        width, height = 50, 50
        self.tick: int = 0
        self.server_sequence_id: int = 0
        grid = self._build_default_grid(width, height)
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
            "npcs": [],
            "work_orders": [],
            "death_log": [],
            "bodies": [],
            "items": [],
            "storages": [
                {
                    "id": "storage-main",
                    "location": {"x": 19, "y": 19},
                    "inventory": [],
                }
            ],
            "grid": grid,
            "door_states": {},
            "machines": {},
            "compartments": [],
            "compartment_index": {},
            "temperature_grid": self._build_default_temperature_grid(grid),
            "thermal_state": {
                "avg_temp_c": SETTINGS.thermal_default_temp_c,
                "min_temp_c": SETTINGS.thermal_default_temp_c,
                "max_temp_c": SETTINGS.thermal_default_temp_c,
                "danger_tile_count": 0,
            },
        }
        self.connections: dict[str, SocketLike] = {}
        self.command_queue: asyncio.Queue[PendingCommand] = asyncio.Queue()
        self.last_action_at: dict[str, float] = {}
        self.command_ack_cache: dict[str, dict[str, CommandAck]] = {}
        self._running = False
        self.snapshot_path = Path(snapshot_path or SETTINGS.snapshot_file_path)
        cadence = snapshot_cadence_ticks if snapshot_cadence_ticks is not None else SETTINGS.snapshot_cadence_ticks
        self.snapshot_cadence_ticks = max(1, int(cadence))
        self.replay_log_path = Path(replay_log_path or SETTINGS.command_replay_log_path)
        replay_limit = replay_max_entries if replay_max_entries is not None else SETTINGS.command_replay_max_entries
        self.replay_max_entries = max(1, int(replay_limit))
        self.last_snapshot_tick: int = 0
        self.tick_duration_ms_last: float = 0.0
        self.tick_duration_ms_ema: float = 0.0
        self.tick_duration_ms_max: float = 0.0
        self.command_queue_peak: int = 0
        self.queue_depth_last: int = 0
        self.queue_depth_ema: float = 0.0
        self.queue_depth_max: int = 0
        self.queue_depth_history: list[int] = []
        self.idle_npc_ratio_last: float = 0.0
        self.idle_npc_ratio_ema: float = 0.0
        self.idle_npc_ratio_history: list[float] = []
        self.replay_commands_applied_on_restore: int = 0
        self.restored_from_snapshot: bool = False

        restored = load_snapshot and self._load_snapshot_if_available()
        self.restored_from_snapshot = bool(restored)
        if restored:
            self._replay_commands_since_snapshot()
        self._ensure_world_defaults()
        if not restored:
            self._recompute_compartments()
            self._initialize_npcs()


    @staticmethod
    def _build_default_grid(width: int, height: int) -> list[list[str]]:
        grid = [[TILE_VACUUM for _ in range(width)] for _ in range(height)]
        for y in range(DEFAULT_STATION_MIN_Y, DEFAULT_STATION_MAX_Y + 1):
            for x in range(DEFAULT_STATION_MIN_X, DEFAULT_STATION_MAX_X + 1):
                is_border = (
                    x in {DEFAULT_STATION_MIN_X, DEFAULT_STATION_MAX_X}
                    or y in {DEFAULT_STATION_MIN_Y, DEFAULT_STATION_MAX_Y}
                )
                grid[y][x] = TILE_WALL if is_border else TILE_FLOOR
        return grid

    @staticmethod
    def _build_default_temperature_grid(grid: list[list[str]]) -> list[list[float]]:
        base = float(SETTINGS.thermal_default_temp_c)
        space = float(SETTINGS.thermal_space_temp_c)
        return [[space if tile == TILE_VACUUM else base for tile in row] for row in grid]

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

        is_valid, invalid_reason = self._validate_command_payload(command)
        if not is_valid:
            ack = CommandAck(
                client_command_id=command.client_command_id,
                result=CommandResult.INVALID_PAYLOAD,
                tick=self.tick,
                rejection_reason=invalid_reason or "invalid_payload",
            )
            self.command_ack_cache[session_id][command.client_command_id] = ack
            return ack

        await self.command_queue.put(PendingCommand(session_id=session_id, command=command, enqueued_at_tick=self.tick))
        self.command_queue_peak = max(self.command_queue_peak, self.command_queue.qsize())
        self.last_action_at[session_id] = time.monotonic()
        ack = CommandAck(client_command_id=command.client_command_id, result=CommandResult.QUEUED, tick=self.tick)
        self.command_ack_cache[session_id][command.client_command_id] = ack
        return ack

    def world_snapshot(self) -> dict:
        return {"tick": self.tick, "world": self.world_state}

    def runtime_status(self) -> dict[str, int | float | str | list[int] | list[float]]:
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
            "alive_npc_count": sum(1 for npc in self.world_state.get("npcs", []) if npc.get("alive", True)),
            "work_order_count": len(self.world_state.get("work_orders", [])),
            "death_log_count": len(self.world_state.get("death_log", [])),
            "active_body_count": sum(1 for body in self.world_state.get("bodies", []) if not body.get("disposed", False)),
            "item_count": len(self.world_state.get("items", [])),
            "last_snapshot_tick": self.last_snapshot_tick,
            "snapshot_cadence_ticks": self.snapshot_cadence_ticks,
            "snapshot_schema_version": SETTINGS.snapshot_schema_version,
            "tick_duration_ms_last": round(self.tick_duration_ms_last, 3),
            "tick_duration_ms_ema": round(self.tick_duration_ms_ema, 3),
            "tick_duration_ms_max": round(self.tick_duration_ms_max, 3),
            "command_queue_peak": self.command_queue_peak,
            "queue_depth_last": self.queue_depth_last,
            "queue_depth_ema": round(self.queue_depth_ema, 3),
            "queue_depth_max": self.queue_depth_max,
            "queue_depth_history": list(self.queue_depth_history),
            "idle_npc_ratio_last": round(self.idle_npc_ratio_last, 4),
            "idle_npc_ratio_ema": round(self.idle_npc_ratio_ema, 4),
            "idle_npc_ratio_history": list(self.idle_npc_ratio_history),
            "replay_log_entries": self._replay_log_entry_count(),
            "replay_log_path": str(self.replay_log_path),
            "restored_from_snapshot": int(self.restored_from_snapshot),
            "replay_commands_applied_on_restore": self.replay_commands_applied_on_restore,
            "thermal_avg_temp_c": float(self.world_state.get("thermal_state", {}).get("avg_temp_c", SETTINGS.thermal_default_temp_c)),
            "thermal_min_temp_c": float(self.world_state.get("thermal_state", {}).get("min_temp_c", SETTINGS.thermal_default_temp_c)),
            "thermal_max_temp_c": float(self.world_state.get("thermal_state", {}).get("max_temp_c", SETTINGS.thermal_default_temp_c)),
            "thermal_danger_tile_count": int(self.world_state.get("thermal_state", {}).get("danger_tile_count", 0)),
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
        tick_started_at = time.monotonic()
        self.tick += 1
        queue_depth_before_drain = self.command_queue.qsize()
        drained: list[PendingCommand] = []
        while not self.command_queue.empty():
            drained.append(self.command_queue.get_nowait())

        claimed_targets: set[str] = set()
        applied = 0
        tile_changes: list[dict] = []
        command_work_order_changes: list[dict] = []
        applied_commands_for_replay: list[dict] = []
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
            elif pending.command.type is CommandType.CREATE_WORK_ORDER:
                created_order = self._apply_create_work_order(pending.command, self.server_sequence_id)
                command_work_order_changes.append({"type": "work_order_created_by_command", "work_order": self._snapshot_work_order(created_order)})

            applied_commands_for_replay.append(
                {
                    "tick": self.tick,
                    "server_sequence_id": self.server_sequence_id,
                    "command": pending.command.model_dump(),
                }
            )

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
        before_thermal_state = dict(self.world_state.get("thermal_state", {}))
        if topology_changed:
            self._recompute_compartments()

        self._update_power()
        self._update_oxygen()
        self._update_temperature()
        npc_changes, work_order_changes, death_log_appends = self._update_npcs()

        after_compartments = self._compartment_snapshot_map()
        after_power = self._power_snapshot()
        after_thermal_state = dict(self.world_state.get("thermal_state", {}))
        compartment_changes = self._compartment_changes(before_compartments, after_compartments)
        power_events = self._power_events(before_power, after_power)
        thermal_events = self._thermal_events(before_thermal_state, after_thermal_state)

        delta = DeltaTick(
            tick=self.tick,
            world_hash=self._world_hash(),
            command_count=applied,
            tile_changes=tile_changes,
            entity_changes=compartment_changes + power_events + thermal_events + npc_changes,
            work_order_changes=command_work_order_changes + work_order_changes,
            death_log_appends=death_log_appends,
        )
        if applied_commands_for_replay:
            self._append_replay_entries(applied_commands_for_replay)
        self._maybe_persist_snapshot()

        self.queue_depth_last = queue_depth_before_drain
        if self.tick <= 1:
            self.queue_depth_ema = float(queue_depth_before_drain)
        else:
            self.queue_depth_ema = (0.8 * self.queue_depth_ema) + (0.2 * float(queue_depth_before_drain))
        self.queue_depth_max = max(self.queue_depth_max, queue_depth_before_drain)
        self.queue_depth_history.append(int(queue_depth_before_drain))
        if len(self.queue_depth_history) > 120:
            self.queue_depth_history = self.queue_depth_history[-120:]

        alive_npcs = [npc for npc in self.world_state.get("npcs", []) if npc.get("alive", True)]
        if alive_npcs:
            idle_npcs = [npc for npc in alive_npcs if not npc.get("current_work_order_id")]
            idle_ratio = len(idle_npcs) / len(alive_npcs)
        else:
            idle_ratio = 0.0
        self.idle_npc_ratio_last = idle_ratio
        if self.tick <= 1:
            self.idle_npc_ratio_ema = idle_ratio
        else:
            self.idle_npc_ratio_ema = (0.8 * self.idle_npc_ratio_ema) + (0.2 * idle_ratio)
        self.idle_npc_ratio_history.append(round(idle_ratio, 4))
        if len(self.idle_npc_ratio_history) > 120:
            self.idle_npc_ratio_history = self.idle_npc_ratio_history[-120:]

        elapsed_ms = (time.monotonic() - tick_started_at) * 1000.0
        self.tick_duration_ms_last = elapsed_ms
        if self.tick <= 1:
            self.tick_duration_ms_ema = elapsed_ms
        else:
            self.tick_duration_ms_ema = (0.8 * self.tick_duration_ms_ema) + (0.2 * elapsed_ms)
        self.tick_duration_ms_max = max(self.tick_duration_ms_max, elapsed_ms)
        await self._broadcast(delta.model_dump())

    def _ensure_world_defaults(self) -> None:
        self.world_state.setdefault("power", {"mode": "topology_aware_networks"})
        self.world_state.setdefault("power_state", {})
        self.world_state["power_state"].setdefault("generation", 0.0)
        self.world_state["power_state"].setdefault("demand", 0.0)
        self.world_state["power_state"].setdefault("battery_discharge", 0.0)
        self.world_state["power_state"].setdefault("battery_charge", 0.0)
        self.world_state["power_state"].setdefault("powered_consumers", [])
        self.world_state["power_state"].setdefault("unpowered_consumers", [])
        self.world_state["power_state"].setdefault("disabled_priorities", [])
        self.world_state["power_state"].setdefault("networks", [])
        self.world_state.setdefault("population", 0)
        self.world_state.setdefault("npcs", [])
        self.world_state.setdefault("work_orders", [])
        self.world_state.setdefault("death_log", [])
        self.world_state.setdefault("bodies", [])
        self.world_state.setdefault("items", [])
        self.world_state.setdefault("storages", [{"id": "storage-main", "location": {"x": 19, "y": 19}, "inventory": []}])
        self.world_state.setdefault("door_states", {})
        self.world_state.setdefault("machines", {})
        self.world_state.setdefault("compartments", [])
        self.world_state.setdefault("compartment_index", {})
        self.world_state.setdefault("temperature_grid", self._build_default_temperature_grid(self.world_state.get("grid", [])))
        self._ensure_temperature_grid_dimensions()
        self._refresh_thermal_state_summary()
        if not self.world_state.get("npcs"):
            self._initialize_npcs()

    def _ensure_temperature_grid_dimensions(self) -> None:
        grid = self.world_state.get("grid", [])
        temp_grid = self.world_state.get("temperature_grid", [])
        if not isinstance(grid, list) or not grid:
            self.world_state["temperature_grid"] = []
            return
        height = len(grid)
        width = len(grid[0])
        if (
            not isinstance(temp_grid, list)
            or len(temp_grid) != height
            or any(not isinstance(row, list) or len(row) != width for row in temp_grid)
        ):
            self.world_state["temperature_grid"] = self._build_default_temperature_grid(grid)

    def _sync_temperature_grid_with_tiles(self) -> None:
        self._ensure_temperature_grid_dimensions()
        grid = self.world_state.get("grid", [])
        temp_grid = self.world_state.get("temperature_grid", [])
        if not grid or not temp_grid:
            return
        base = float(SETTINGS.thermal_default_temp_c)
        space = float(SETTINGS.thermal_space_temp_c)
        for y, row in enumerate(grid):
            for x, tile in enumerate(row):
                value = temp_grid[y][x]
                current = float(value) if isinstance(value, (int, float)) else base
                if tile == TILE_VACUUM:
                    temp_grid[y][x] = space
                elif current <= space:
                    temp_grid[y][x] = base

    def _refresh_thermal_state_summary(self) -> None:
        temp_grid = self.world_state.get("temperature_grid", [])
        values = [float(v) for row in temp_grid if isinstance(row, list) for v in row if isinstance(v, (int, float))]
        if not values:
            default_temp = float(SETTINGS.thermal_default_temp_c)
            summary = {
                "avg_temp_c": default_temp,
                "min_temp_c": default_temp,
                "max_temp_c": default_temp,
                "danger_tile_count": 0,
            }
        else:
            hazard_min = 5.0
            hazard_max = 45.0
            summary = {
                "avg_temp_c": round(sum(values) / len(values), 2),
                "min_temp_c": round(min(values), 2),
                "max_temp_c": round(max(values), 2),
                "danger_tile_count": sum(1 for value in values if value < hazard_min or value > hazard_max),
            }
        self.world_state["thermal_state"] = summary

    def _load_snapshot_if_available(self) -> bool:
        if not self.snapshot_path.exists():
            return False
        try:
            payload = json.loads(self.snapshot_path.read_text())
        except Exception:
            return False
        if not isinstance(payload, dict):
            return False

        schema_version = int(payload.get("snapshot_schema_version", -1))
        if schema_version != SETTINGS.snapshot_schema_version:
            return False

        state = payload.get("world_state")
        if not isinstance(state, dict):
            return False

        tick = int(payload.get("tick", 0))
        server_sequence_id = int(payload.get("server_sequence_id", 0))
        stored_hash = payload.get("state_hash")
        expected_hash = self._snapshot_state_hash(tick, server_sequence_id, state)
        if not isinstance(stored_hash, str) or stored_hash != expected_hash:
            return False

        self.tick = tick
        self.server_sequence_id = server_sequence_id
        self.world_state = state
        self.last_snapshot_tick = self.tick
        return True

    def _snapshot_payload(self) -> dict:
        return {
            "snapshot_schema_version": SETTINGS.snapshot_schema_version,
            "tick": self.tick,
            "server_sequence_id": self.server_sequence_id,
            "state_hash": self._snapshot_state_hash(self.tick, self.server_sequence_id, self.world_state),
            "world_state": self.world_state,
            "saved_at_unix_ms": int(time.time() * 1000),
        }

    @staticmethod
    def _snapshot_state_hash(tick: int, server_sequence_id: int, world_state: dict) -> str:
        value = {
            "tick": tick,
            "server_sequence_id": server_sequence_id,
            "world_state": world_state,
        }
        encoded = json.dumps(value, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _persist_snapshot(self) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.snapshot_path.with_suffix(self.snapshot_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(self._snapshot_payload(), sort_keys=True))
        temp_path.replace(self.snapshot_path)
        self.last_snapshot_tick = self.tick
        self._trim_replay_log(min_server_sequence_id_exclusive=self.server_sequence_id)

    def _maybe_persist_snapshot(self) -> None:
        if self.tick % self.snapshot_cadence_ticks != 0:
            return
        self._persist_snapshot()

    def _append_replay_entries(self, entries: list[dict]) -> None:
        if not entries:
            return
        self.replay_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.replay_log_path.open("a", encoding="utf-8") as fp:
            for entry in entries:
                fp.write(json.dumps(entry, sort_keys=True) + "\n")
        self._trim_replay_log(min_server_sequence_id_exclusive=self.server_sequence_id - self.replay_max_entries)

    def _trim_replay_log(self, min_server_sequence_id_exclusive: int) -> None:
        if not self.replay_log_path.exists():
            return
        kept: list[str] = []
        for line in self.replay_log_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except Exception:
                continue
            seq = int(entry.get("server_sequence_id", -1))
            if seq > min_server_sequence_id_exclusive:
                kept.append(json.dumps(entry, sort_keys=True))
        temp_path = self.replay_log_path.with_suffix(self.replay_log_path.suffix + ".tmp")
        temp_path.write_text("\n".join(kept) + ("\n" if kept else ""))
        temp_path.replace(self.replay_log_path)

    def _replay_commands_since_snapshot(self) -> None:
        if not self.replay_log_path.exists():
            return
        replayed_topology_change = False
        replayed_count = 0
        for line in self.replay_log_path.read_text().splitlines():
            try:
                entry = json.loads(line)
            except Exception:
                continue
            seq = int(entry.get("server_sequence_id", -1))
            if seq <= self.server_sequence_id:
                continue
            command_payload = entry.get("command")
            if not isinstance(command_payload, dict):
                continue
            try:
                command = ClientCommand.model_validate(command_payload)
            except Exception:
                continue
            if command.type in {CommandType.BUILD, CommandType.DECONSTRUCT}:
                _, did_change = self._apply_structural_command(command)
                replayed_topology_change = replayed_topology_change or did_change
            elif command.type is CommandType.CREATE_WORK_ORDER:
                self._apply_create_work_order(command, seq)
            replayed_count += 1
            self.server_sequence_id = max(self.server_sequence_id, seq)
            self.tick = max(self.tick, int(entry.get("tick", self.tick)))

        if replayed_topology_change:
            self._recompute_compartments()
        self.replay_commands_applied_on_restore = replayed_count
        self._update_power()

    def _replay_log_entry_count(self) -> int:
        if not self.replay_log_path.exists():
            return 0
        return sum(1 for _ in self.replay_log_path.open("r", encoding="utf-8"))

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

    def _validate_command_payload(self, command: ClientCommand) -> tuple[bool, str | None]:
        payload = command.payload
        if command.type in {CommandType.BUILD, CommandType.DECONSTRUCT}:
            x, y = payload.get("x"), payload.get("y")
            if not self._validate_xy(x, y):
                return False, "invalid_xy"

            if command.type is CommandType.BUILD and "tile_type" in payload:
                tile_type = payload.get("tile_type")
                if not (isinstance(tile_type, str) and tile_type in (ALL_TILE_TYPES - {TILE_VACUUM})):
                    return False, "invalid_tile_type"

            machine = payload.get("machine")
            if machine is None:
                return True, None
            if command.type is not CommandType.BUILD:
                return False, "machine_not_allowed_for_command"
            if not self._validate_machine_payload(machine):
                return False, "invalid_machine_payload"

            tx, ty = int(x), int(y)
            target_tile = payload.get("tile_type")
            if not isinstance(target_tile, str):
                target_tile = self.world_state["grid"][ty][tx]
            if target_tile not in {TILE_FLOOR, TILE_AIRLOCK}:
                return False, "machine_requires_floor_or_airlock"

            return True, None

        if command.type is CommandType.CREATE_WORK_ORDER:
            return (True, None) if self._validate_work_order_payload(payload) else (False, "invalid_work_order_payload")

        return False, "unsupported_command_type"

    def _validate_work_order_payload(self, payload: dict) -> bool:
        work_type = payload.get("work_type")
        location = payload.get("location")
        if not isinstance(work_type, str) or work_type not in SUPPORTED_COMMAND_WORK_TYPES:
            return False
        if not isinstance(location, dict) or not self._validate_xy(location.get("x"), location.get("y")):
            return False

        metadata = payload.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            return False

        if work_type == "MineIce":
            item_type = metadata.get("item_type", "IceChunk")
            return isinstance(item_type, str) and item_type == "IceChunk"

        if work_type == "HaulItem":
            item_id = metadata.get("item_id")
            destination = metadata.get("destination")
            if not isinstance(item_id, str) or not item_id:
                return False
            if not isinstance(destination, dict):
                return False
            return self._validate_xy(destination.get("x"), destination.get("y"))

        if work_type == "RefineIce":
            item_id = metadata.get("item_id")
            return isinstance(item_id, str) and bool(item_id)

        if work_type == "FeedOxygenGenerator":
            item_id = metadata.get("item_id")
            generator_location = metadata.get("generator_location")
            if not isinstance(item_id, str) or not item_id:
                return False
            if not isinstance(generator_location, dict):
                return False
            return self._validate_xy(generator_location.get("x"), generator_location.get("y"))

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
        if machine_type in {MACHINE_HEATER, MACHINE_COOLER, MACHINE_LIGHT}:
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

    @staticmethod
    def _snapshot_work_order(order: dict) -> dict:
        return deepcopy(order)

    def _apply_structural_command(self, command: ClientCommand) -> tuple[dict | None, bool]:
        x = command.payload["x"]
        y = command.payload["y"]
        key = self._xy_key(x, y)
        before = self.world_state["grid"][y][x]
        after = command.payload.get("tile_type", TILE_WALL) if command.type is CommandType.BUILD else TILE_VACUUM

        changed_tile = before != after
        if changed_tile:
            self.world_state["grid"][y][x] = after
            self._ensure_temperature_grid_dimensions()
            if after == TILE_VACUUM:
                self.world_state["temperature_grid"][y][x] = float(SETTINGS.thermal_space_temp_c)
            elif before == TILE_VACUUM:
                self.world_state["temperature_grid"][y][x] = float(SETTINGS.thermal_default_temp_c)
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

    def _apply_create_work_order(self, command: ClientCommand, sequence_id: int) -> dict:
        payload = command.payload
        location = payload.get("location", {})
        work_type = str(payload.get("work_type"))
        order = {
            "id": f"wo-cmd-{sequence_id}",
            "work_type": work_type,
            "status": "Queued",
            "location": {"x": int(location["x"]), "y": int(location["y"])},
            "created_tick": self.tick,
            "progress": 0,
            "required_progress": 1 if work_type == "FeedOxygenGenerator" else 2,
        }
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        if work_type == "MineIce":
            order["item_type"] = str(metadata.get("item_type", "IceChunk"))
        elif work_type in WORK_TYPES_WITH_ITEM:
            order["item_id"] = str(metadata.get("item_id"))
            if work_type == "HaulItem":
                destination = metadata.get("destination", {})
                order["destination"] = {"x": int(destination["x"]), "y": int(destination["y"])}
            if work_type == "FeedOxygenGenerator":
                generator_location = metadata.get("generator_location", {})
                order["generator_location"] = {"x": int(generator_location["x"]), "y": int(generator_location["y"])}

        self.world_state.setdefault("work_orders", []).append(order)
        return order

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
        if machine_type == MACHINE_COOLER:
            return {
                "type": MACHINE_COOLER,
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

        if interior_neighbors < 2:
            return False

        if bool(getattr(SETTINGS, "door_requires_local_power", False)):
            has_power, has_power_network = self._door_local_power_state(x, y)
            if has_power_network and not has_power:
                return False

        return True

    def _door_local_power_state(self, x: int, y: int) -> tuple[bool, bool]:
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        index = self.world_state.get("compartment_index", {})
        adjacent_compartments: set[int] = set()

        for nx, ny in self._neighbors4(x, y, width, height):
            tile = self.world_state["grid"][ny][nx]
            if tile not in COMPARTMENT_FILL_TILES:
                continue
            comp_id = index.get(self._xy_key(nx, ny))
            if comp_id is None:
                continue
            adjacent_compartments.add(int(comp_id))

        if not adjacent_compartments:
            return False, False

        networks = self.world_state.get("power_state", {}).get("networks", [])
        if not isinstance(networks, list):
            return False, False

        network_map: dict[str, dict] = {}
        for network in networks:
            if not isinstance(network, dict):
                continue
            network_id = network.get("network_id")
            if isinstance(network_id, str):
                network_map[network_id] = network

        has_known_network = False
        for compartment_id in sorted(adjacent_compartments):
            network = network_map.get(f"compartment:{compartment_id}")
            if network is None:
                continue
            has_known_network = True
            supply_kw = float(network.get("generation", 0.0)) + float(network.get("battery_discharge", 0.0))
            if supply_kw > 0.0:
                return True, True

        return False, has_known_network


    def _ensure_npc_defaults(self) -> None:
        for npc in self.world_state.get("npcs", []):
            equipment = npc.get("equipment")
            if not isinstance(equipment, dict):
                equipment = {"hands": [None, None], "clothes": None, "backpack": None}
                npc["equipment"] = equipment
            hands = equipment.get("hands")
            if not isinstance(hands, list) or len(hands) != 2:
                equipment["hands"] = [None, None]
            else:
                equipment["hands"] = [self._normalize_equipped_item(v) for v in hands]
            equipment["clothes"] = self._normalize_equipped_item(equipment.get("clothes"))
            equipment["backpack"] = self._normalize_equipped_item(equipment.get("backpack"))

            inv = npc.get("inventory")
            if not isinstance(inv, list):
                npc["inventory"] = []
            else:
                npc["inventory"] = [str(v) for v in inv if isinstance(v, str)]

    @staticmethod
    def _normalize_equipped_item(value: object) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    def _npc_has_equipped_item(self, npc: dict, item_type: str) -> bool:
        equipment = npc.get("equipment", {})
        if not isinstance(equipment, dict):
            return False
        hands = equipment.get("hands", [])
        if isinstance(hands, list) and any(v == item_type for v in hands):
            return True
        return equipment.get("clothes") == item_type or equipment.get("backpack") == item_type

    def _npc_has_spacesuit(self, npc: dict) -> bool:
        return self._npc_has_equipped_item(npc, ITEM_SPACE_SUIT)

    def _npc_backpack_slots(self, npc: dict) -> int:
        return int(SETTINGS.npc_backpack_slot_count) if self._npc_has_equipped_item(npc, ITEM_BACKPACK) else 0

    def _npc_carry_capacity_weight(self, npc: dict) -> float:
        base = float(SETTINGS.npc_base_carry_weight)
        if self._npc_has_equipped_item(npc, ITEM_BACKPACK):
            base += float(SETTINGS.npc_backpack_bonus_carry_weight)
        return base

    def _npc_inventory_weight(self, npc: dict) -> float:
        total = 0.0
        item_map: dict[str, dict] = {}
        for item in self.world_state.get("items", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                item_map[str(item["id"])] = item
        for item_id in npc.get("inventory", []):
            item = item_map.get(str(item_id))
            if item is None:
                continue
            total += float(item.get("weight", self._item_weight(str(item.get("item_type", "")))))
        return total

    def _item_weight(self, item_type: str) -> float:
        return float(ITEM_WEIGHT_BY_TYPE.get(item_type, 1.0))

    def _auto_equip_npc_from_tile_items(self, npc: dict, npc_changes: list[dict]) -> None:
        nx = int(npc.get("x", 0))
        ny = int(npc.get("y", 0))
        equipment = npc.setdefault("equipment", {"hands": [None, None], "clothes": None, "backpack": None})
        hands = equipment.setdefault("hands", [None, None])
        if not isinstance(hands, list) or len(hands) != 2:
            hands = [None, None]
            equipment["hands"] = hands
        inventory = npc.setdefault("inventory", [])
        if not isinstance(inventory, list):
            inventory = []
            npc["inventory"] = inventory

        for item in self.world_state.get("items", []):
            if not isinstance(item, dict):
                continue
            if bool(item.get("consumed", False)):
                continue
            if item.get("holder_npc_id") is not None:
                continue
            loc = item.get("location", {})
            if int(loc.get("x", -1)) != nx or int(loc.get("y", -1)) != ny:
                continue
            item_type = str(item.get("item_type", ""))
            if item_type == ITEM_MINING_LASER:
                for idx in range(2):
                    if hands[idx] is None:
                        hands[idx] = ITEM_MINING_LASER
                        item["holder_npc_id"] = npc.get("id")
                        item["equipped_by_npc_id"] = npc.get("id")
                        item["equipped_slot"] = f"hand:{idx}"
                        npc_changes.append({"type": "npc_item_equipped", "npc_id": npc.get("id"), "item_id": item.get("id"), "slot": f"hand:{idx}", "item_type": item_type})
                        break
            elif item_type == ITEM_SPACE_SUIT and equipment.get("clothes") is None:
                equipment["clothes"] = ITEM_SPACE_SUIT
                item["holder_npc_id"] = npc.get("id")
                item["equipped_by_npc_id"] = npc.get("id")
                item["equipped_slot"] = "clothes"
                npc_changes.append({"type": "npc_item_equipped", "npc_id": npc.get("id"), "item_id": item.get("id"), "slot": "clothes", "item_type": item_type})
            elif item_type == ITEM_BACKPACK and equipment.get("backpack") is None:
                equipment["backpack"] = ITEM_BACKPACK
                item["holder_npc_id"] = npc.get("id")
                item["equipped_by_npc_id"] = npc.get("id")
                item["equipped_slot"] = "backpack"
                npc_changes.append({"type": "npc_item_equipped", "npc_id": npc.get("id"), "item_id": item.get("id"), "slot": "backpack", "item_type": item_type})
            else:
                slots = self._npc_backpack_slots(npc)
                if slots <= 0 or len(inventory) >= slots:
                    continue
                capacity = self._npc_carry_capacity_weight(npc)
                current_weight = self._npc_inventory_weight(npc)
                item_weight = float(item.get("weight", self._item_weight(item_type)))
                if current_weight + item_weight > capacity:
                    continue
                item_id = item.get("id")
                if not isinstance(item_id, str):
                    continue
                inventory.append(item_id)
                item["holder_npc_id"] = npc.get("id")
                item["equipped_by_npc_id"] = npc.get("id")
                item["equipped_slot"] = f"inventory:{len(inventory)-1}"
                npc_changes.append({"type": "npc_item_stowed", "npc_id": npc.get("id"), "item_id": item_id, "slot": item["equipped_slot"]})

    def _pressure_at_tile(self, x: int, y: int, index: dict, compartments: dict[int, dict]) -> float:
        comp_id = index.get(self._xy_key(x, y))
        if comp_id is None:
            return 0.0
        compartment = compartments.get(int(comp_id))
        if compartment is None:
            return 0.0
        return float(compartment.get("pressure", 0.0))

    def _recompute_compartments(self) -> None:
        grid = self.world_state["grid"]
        self._sync_temperature_grid_with_tiles()
        temp_grid = self.world_state.get("temperature_grid", [])
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        visited: set[tuple[int, int]] = set()
        compartment_index: dict[str, int] = {}
        compartments: list[dict] = []

        old_map = {int(c["id"]): float(c.get("oxygen_percent", 100.0)) for c in self.world_state.get("compartments", [])}
        old_temp_map = {int(c["id"]): float(c.get("temperature", SETTINGS.thermal_default_temp_c)) for c in self.world_state.get("compartments", [])}
        old_index = self.world_state.get("compartment_index", {})

        def oxygen_for_tile(tx: int, ty: int) -> float:
            old_id = old_index.get(self._xy_key(tx, ty))
            if old_id is None:
                return 100.0
            return old_map.get(int(old_id), 100.0)

        def temp_for_tile(tx: int, ty: int) -> float:
            if 0 <= ty < len(temp_grid) and 0 <= tx < len(temp_grid[ty]):
                value = temp_grid[ty][tx]
                if isinstance(value, (int, float)):
                    return float(value)
            old_id = old_index.get(self._xy_key(tx, ty))
            if old_id is None:
                return float(SETTINGS.thermal_default_temp_c)
            return old_temp_map.get(int(old_id), float(SETTINGS.thermal_default_temp_c))

        comp_id = 1
        for y in range(height):
            for x in range(width):
                if (x, y) in visited or grid[y][x] not in COMPARTMENT_FILL_TILES:
                    continue

                queue = [(x, y)]
                visited.add((x, y))
                tiles: list[tuple[int, int]] = []
                oxygen_total = 0.0
                temp_total = 0.0

                while queue:
                    cx, cy = queue.pop()
                    tiles.append((cx, cy))
                    oxygen_total += oxygen_for_tile(cx, cy)
                    temp_total += temp_for_tile(cx, cy)
                    for nx, ny in self._neighbors4(cx, cy, width, height):
                        if (nx, ny) in visited or grid[ny][nx] not in COMPARTMENT_FILL_TILES:
                            continue
                        visited.add((nx, ny))
                        queue.append((nx, ny))

                oxygen = oxygen_total / max(1, len(tiles))
                temperature = temp_total / max(1, len(tiles))
                compartments.append(
                    {
                        "id": comp_id,
                        "oxygen_percent": round(oxygen, 2),
                        "pressure": round(oxygen / 100, 3),
                        "temperature": round(temperature, 2),
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
        self._refresh_thermal_state_summary()
        self._ensure_npc_defaults()

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
        # Non-compartment machines (e.g. exterior placements) share a common fallback network
        # instead of being isolated per-machine key.
        return "non_compartment"

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

    def _update_temperature(self) -> None:
        self._sync_temperature_grid_with_tiles()
        grid = self.world_state.get("grid", [])
        temp_grid = self.world_state.get("temperature_grid", [])
        if not grid or not temp_grid:
            self._refresh_thermal_state_summary()
            return

        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        space_temp = float(SETTINGS.thermal_space_temp_c)
        transfer_rate = float(SETTINGS.thermal_transfer_rate)
        max_transfer = float(SETTINGS.thermal_max_transfer_delta_c_per_tick)
        vacuum_cooling_per_edge = float(SETTINGS.thermal_vacuum_cooling_per_edge_c_per_tick)
        powered = set(self.world_state.get("power_state", {}).get("powered_consumers", []))

        machine_heat_delta: dict[str, float] = {
            MACHINE_REACTOR: 0.45,
            MACHINE_OXYGEN_GENERATOR: 0.18,
            MACHINE_HEATER: float(SETTINGS.thermal_heater_delta_c_per_tick),
            MACHINE_COOLER: -float(SETTINGS.thermal_cooler_delta_c_per_tick),
            MACHINE_LIGHT: 0.05,
        }

        next_grid = [row[:] for row in temp_grid]
        for y in range(height):
            for x in range(width):
                current = float(temp_grid[y][x])
                tile = grid[y][x]
                if tile == TILE_VACUUM:
                    next_grid[y][x] = space_temp
                    continue

                delta = 0.0
                vacuum_edges = 0
                for nx, ny in self._neighbors4(x, y, width, height):
                    neighbor_tile = grid[ny][nx]
                    neighbor_temp = float(temp_grid[ny][nx])
                    gradient = (neighbor_temp - current) * transfer_rate
                    delta += max(-max_transfer, min(max_transfer, gradient))
                    if neighbor_tile == TILE_VACUUM:
                        vacuum_edges += 1

                if vacuum_edges > 0:
                    target_delta = (space_temp - current) * 0.02 * float(vacuum_edges)
                    delta += max(-vacuum_cooling_per_edge * vacuum_edges, min(0.0, target_delta))

                key = self._xy_key(x, y)
                machine = self.world_state.get("machines", {}).get(key)
                if isinstance(machine, dict) and machine.get("enabled", True):
                    machine_type = machine.get("type")
                    heat = machine_heat_delta.get(str(machine_type))
                    requires_power = str(machine_type) in POWER_PRIORITY
                    if heat is not None and (not requires_power or key in powered):
                        delta += heat

                next_grid[y][x] = round(max(space_temp, min(80.0, current + delta)), 2)

        self.world_state["temperature_grid"] = next_grid

        index = self.world_state.get("compartment_index", {})
        if index:
            comp_totals: dict[int, float] = {}
            comp_counts: dict[int, int] = {}
            for y in range(height):
                for x in range(width):
                    comp_id = index.get(self._xy_key(x, y))
                    if comp_id is None:
                        continue
                    cid = int(comp_id)
                    comp_totals[cid] = comp_totals.get(cid, 0.0) + float(next_grid[y][x])
                    comp_counts[cid] = comp_counts.get(cid, 0) + 1
            for compartment in self.world_state.get("compartments", []):
                cid = int(compartment.get("id", -1))
                if cid in comp_totals and comp_counts[cid] > 0:
                    compartment["temperature"] = round(comp_totals[cid] / comp_counts[cid], 2)

        self._refresh_thermal_state_summary()
        self._ensure_npc_defaults()

    def _initialize_npcs(self) -> None:
        names = [
            "Ari",
            "Beck",
            "Cyra",
            "Dax",
            "Esme",
            "Finn",
            "Gala",
            "Hale",
            "Ivo",
            "Juno",
        ]
        default_speed = SETTINGS.npc_speed_default_tiles_per_sec
        min_speed = SETTINGS.npc_speed_min_tiles_per_sec
        max_speed = SETTINGS.npc_speed_max_tiles_per_sec
        roster: list[dict] = []
        for i, name in enumerate(names):
            speed = min(max_speed, max(min_speed, default_speed + ((i % 3) - 1)))
            x = 18 + (i % 5)
            y = 18 + (i // 5)
            roster.append(
                {
                    "id": f"npc-{i + 1}",
                    "name": name,
                    "x": x,
                    "y": y,
                    "speed": speed,
                    "move_accumulator": 0.0,
                    "health": 100.0,
                    "alive": True,
                    "personality": ["baseline", "diligent", "cautious"][i % 3],
                    "current_work_order_id": None,
                    "equipment": {"hands": [None, None], "clothes": None, "backpack": None},
                    "inventory": [],
                    "needs": {
                        "hunger": 0.0,
                        "fatigue": 0.0,
                    },
                }
            )
        self.world_state["npcs"] = roster
        self.world_state["population"] = len(roster)

    def _update_npcs(self) -> tuple[list[dict], list[dict], list[dict]]:
        npc_changes: list[dict] = []
        work_order_changes: list[dict] = []
        death_log_appends: list[dict] = []
        grid = self.world_state["grid"]
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        index = self.world_state.get("compartment_index", {})
        compartments = {int(c["id"]): c for c in self.world_state.get("compartments", [])}

        for npc in self.world_state.get("npcs", []):
            if not npc.get("alive", True):
                continue

            self._ensure_npc_defaults()
            self._auto_equip_npc_from_tile_items(npc, npc_changes)
            has_spacesuit = self._npc_has_spacesuit(npc)

            before_temp = self._temperature_at_tile(int(npc["x"]), int(npc["y"]))
            was_in_thermal_hazard = bool(npc.get("in_thermal_hazard", False))
            thermal_flee_step_taken = False

            active_order = self._npc_active_work_order(npc)
            if active_order is None:
                assigned = self._assign_next_work_order(npc)
                if assigned is not None:
                    active_order = assigned
                    work_order_changes.append(
                        {
                            "type": "work_order_assigned",
                            "work_order_id": assigned["id"],
                            "assignee_npc_id": npc["id"],
                            "status": assigned["status"],
                        }
                    )

            before_x, before_y = int(npc["x"]), int(npc["y"])
            per_tick_speed = float(npc.get("speed", SETTINGS.npc_speed_default_tiles_per_sec)) / max(float(SETTINGS.tick_rate_hz), 1.0)
            move_budget = float(npc.get("move_accumulator", 0.0)) + per_tick_speed
            steps = int(move_budget)
            npc["move_accumulator"] = round(move_budget - steps, 3)

            for _ in range(steps):
                next_pos: tuple[int, int] | None
                oxygen_here = self._oxygen_at_tile(int(npc["x"]), int(npc["y"]), index, compartments)
                temp_here = self._temperature_at_tile(int(npc["x"]), int(npc["y"]))
                # Survival constraints always dominate personality/task behavior.
                if (not has_spacesuit) and (temp_here < SETTINGS.thermal_hazard_min_c or temp_here > SETTINGS.thermal_hazard_max_c):
                    next_pos = self._next_npc_position_for_thermal_safety(int(npc["x"]), int(npc["y"]), grid, width, height)
                    if next_pos is not None:
                        thermal_flee_step_taken = True
                elif (not has_spacesuit) and oxygen_here <= SETTINGS.oxygen_safe_min_percent:
                    next_pos = self._next_npc_position(int(npc["x"]), int(npc["y"]), grid, width, height, index, compartments)
                elif active_order is not None:
                    target = self._work_order_target(active_order, npc)
                    tx = target[0] if target is not None else None
                    ty = target[1] if target is not None else None
                    if isinstance(tx, int) and isinstance(ty, int):
                        next_pos = self._step_toward_target(int(npc["x"]), int(npc["y"]), tx, ty, grid, width, height)
                        if next_pos is None and (int(npc["x"]), int(npc["y"])) != (tx, ty):
                            # Dynamic topology may invalidate the assignment path; deterministically re-queue.
                            active_order["status"] = "Queued"
                            active_order.pop("assignee_npc_id", None)
                            active_order.pop("assigned_tick", None)
                            npc["current_work_order_id"] = None
                            work_order_changes.append(
                                {
                                    "type": "work_order_unassigned",
                                    "work_order_id": active_order["id"],
                                    "reason": "path_unreachable",
                                }
                            )
                            active_order = None
                            next_pos = self._next_npc_position(int(npc["x"]), int(npc["y"]), grid, width, height, index, compartments)
                    else:
                        next_pos = self._next_npc_position(int(npc["x"]), int(npc["y"]), grid, width, height, index, compartments)
                else:
                    next_pos = self._next_npc_position(int(npc["x"]), int(npc["y"]), grid, width, height, index, compartments)
                if next_pos is None:
                    break
                npc["x"], npc["y"] = next_pos

            oxygen = self._oxygen_at_tile(int(npc["x"]), int(npc["y"]), index, compartments)
            pressure = self._pressure_at_tile(int(npc["x"]), int(npc["y"]), index, compartments)
            temperature = self._temperature_at_tile(int(npc["x"]), int(npc["y"]))
            if (not has_spacesuit) and oxygen <= 0.0:
                npc["health"] = round(float(npc.get("health", 100.0)) - SETTINGS.suffocation_damage_per_tick_at_zero_o2, 2)
            if (not has_spacesuit) and (temperature < SETTINGS.thermal_hazard_min_c or temperature > SETTINGS.thermal_hazard_max_c):
                npc["health"] = round(float(npc.get("health", 100.0)) - SETTINGS.thermal_hazard_damage_per_tick, 2)
            if (not has_spacesuit) and pressure < 0.2:
                pressure_factor = max(0.0, min(1.0, (0.2 - pressure) / 0.2))
                npc["health"] = round(float(npc.get("health", 100.0)) - (SETTINGS.npc_pressure_damage_per_tick_at_zero * pressure_factor), 2)

            needs = npc.setdefault("needs", {"hunger": 0.0, "fatigue": 0.0})
            # Deterministic baseline need drift.
            needs["hunger"] = round(min(100.0, float(needs.get("hunger", 0.0)) + 0.2), 2)
            needs["fatigue"] = round(min(100.0, float(needs.get("fatigue", 0.0)) + 0.15), 2)
            if temperature < SETTINGS.thermal_comfort_min_c or temperature > SETTINGS.thermal_comfort_max_c:
                needs["fatigue"] = round(min(100.0, float(needs.get("fatigue", 0.0)) + 0.1), 2)
            if needs["hunger"] >= 75.0 or needs["fatigue"] >= 75.0:
                npc_changes.append(
                    {
                        "type": "npc_need_state",
                        "npc_id": npc["id"],
                        "hunger": needs["hunger"],
                        "fatigue": needs["fatigue"],
                    }
                )

            if int(npc["x"]) != before_x or int(npc["y"]) != before_y:
                npc_changes.append(
                    {
                        "type": "npc_move",
                        "npc_id": npc["id"],
                        "from": {"x": before_x, "y": before_y},
                        "to": {"x": int(npc["x"]), "y": int(npc["y"])},
                    }
                )

            if (not has_spacesuit) and oxygen <= SETTINGS.oxygen_safe_min_percent:
                npc_changes.append(
                    {
                        "type": "npc_survival_state",
                        "npc_id": npc["id"],
                        "oxygen_percent": round(oxygen, 2),
                        "health": round(float(npc.get("health", 100.0)), 2),
                    }
                )
            if (not has_spacesuit) and (temperature < SETTINGS.thermal_hazard_min_c or temperature > SETTINGS.thermal_hazard_max_c):
                npc_changes.append(
                    {
                        "type": "npc_thermal_hazard",
                        "npc_id": npc["id"],
                        "temperature_c": round(temperature, 2),
                        "health": round(float(npc.get("health", 100.0)), 2),
                    }
                )
            in_thermal_hazard = (not has_spacesuit) and (temperature < SETTINGS.thermal_hazard_min_c or temperature > SETTINGS.thermal_hazard_max_c)
            if in_thermal_hazard and not was_in_thermal_hazard:
                npc_changes.append({
                    "type": "npc_thermal_hazard_enter",
                    "npc_id": npc["id"],
                    "temperature_c": round(temperature, 2),
                })
            if not in_thermal_hazard and was_in_thermal_hazard:
                npc_changes.append({
                    "type": "npc_thermal_hazard_exit",
                    "npc_id": npc["id"],
                    "temperature_c": round(temperature, 2),
                })
            if thermal_flee_step_taken:
                npc_changes.append({
                    "type": "npc_thermal_flee",
                    "npc_id": npc["id"],
                    "temperature_before_c": round(before_temp, 2),
                    "temperature_after_c": round(temperature, 2),
                })
            npc["in_thermal_hazard"] = in_thermal_hazard

            if float(npc.get("health", 0.0)) <= 0.0:
                npc["alive"] = False
                npc["health"] = 0.0
                comp_id = index.get(self._xy_key(int(npc["x"]), int(npc["y"])))
                death_cause = "suffocation" if oxygen <= 0.0 else "thermal_hazard"
                death_entry = {
                    "npc_id": npc["id"],
                    "name": npc.get("name", npc["id"]),
                    "tick": self.tick,
                    "cause": death_cause,
                    "x": int(npc["x"]),
                    "y": int(npc["y"]),
                    "oxygen_percent_at_death": round(oxygen, 2),
                    "temperature_c_at_death": round(temperature, 2),
                    "compartment_id": int(comp_id) if comp_id is not None else None,
                    "personality": str(npc.get("personality", "baseline")),
                    "hunger": round(float(npc.get("needs", {}).get("hunger", 0.0)), 2),
                    "fatigue": round(float(npc.get("needs", {}).get("fatigue", 0.0)), 2),
                }
                self.world_state.setdefault("death_log", []).append(death_entry)
                death_log_appends.append(death_entry)
                npc_changes.append({"type": "npc_death", **death_entry})

                body = {
                    "id": f"body-{npc['id']}-{self.tick}",
                    "npc_id": npc["id"],
                    "name": npc.get("name", npc["id"]),
                    "location": {"x": int(npc["x"]), "y": int(npc["y"])},
                    "created_tick": self.tick,
                    "disposed": False,
                    "disposed_tick": None,
                    "disposed_by_npc_id": None,
                }
                self.world_state.setdefault("bodies", []).append(body)
                npc_changes.append({"type": "body_created", "body_id": body["id"], "location": body["location"], "npc_id": npc["id"]})

                if active_order is not None and active_order.get("status") == "Assigned":
                    active_order["status"] = "Queued"
                    active_order.pop("assignee_npc_id", None)
                    active_order.pop("assigned_tick", None)
                    npc["current_work_order_id"] = None
                    work_order_changes.append(
                        {
                            "type": "work_order_unassigned",
                            "work_order_id": active_order["id"],
                            "reason": "assignee_died",
                        }
                    )

                work_order = {
                    "id": f"wo-dispose-{npc['id']}-{self.tick}",
                    "work_type": "DisposeBody",
                    "status": "Queued",
                    "location": {"x": int(npc["x"]), "y": int(npc["y"])},
                    "source_npc_id": npc["id"],
                    "body_id": body["id"],
                    "created_tick": self.tick,
                    "progress": 0,
                    "required_progress": 2,
                }
                self.world_state.setdefault("work_orders", []).append(work_order)
                work_order_changes.append({"type": "work_order_created", "work_order": self._snapshot_work_order(work_order)})
                continue

            if active_order is not None:
                item_conflict = self._active_order_item_conflict_reason(active_order, npc)
                if item_conflict == "item_unavailable":
                    active_order["status"] = "Cancelled"
                    active_order["cancelled_tick"] = self.tick
                    active_order["cancel_reason"] = item_conflict
                    active_order.pop("assignee_npc_id", None)
                    active_order.pop("assigned_tick", None)
                    npc["current_work_order_id"] = None
                    work_order_changes.append(
                        {
                            "type": "work_order_cancelled",
                            "work_order_id": active_order["id"],
                            "reason": item_conflict,
                        }
                    )
                    active_order = None
                elif item_conflict == "claimed_by_other_order":
                    active_order["status"] = "Queued"
                    active_order["progress"] = 0
                    active_order.pop("assignee_npc_id", None)
                    active_order.pop("assigned_tick", None)
                    npc["current_work_order_id"] = None
                    work_order_changes.append(
                        {
                            "type": "work_order_unassigned",
                            "work_order_id": active_order["id"],
                            "reason": item_conflict,
                        }
                    )
                    active_order = None

            if active_order is not None and self._npc_at_active_order_target(npc, active_order):
                self._process_active_work_order(npc, active_order, oxygen, npc_changes, work_order_changes)

        self.world_state["population"] = sum(1 for npc in self.world_state.get("npcs", []) if npc.get("alive", True))
        return npc_changes, work_order_changes, death_log_appends

    def _process_active_work_order(
        self,
        npc: dict,
        active_order: dict,
        oxygen: float,
        npc_changes: list[dict],
        work_order_changes: list[dict],
    ) -> None:
        progress_gain = 1
        personality = str(npc.get("personality", "baseline"))
        if personality == "diligent" and oxygen > SETTINGS.oxygen_safe_min_percent:
            progress_gain = 2

        work_type = str(active_order.get("work_type", ""))
        if work_type == "MineIce" and not self._npc_has_equipped_item(npc, ITEM_MINING_LASER):
            active_order["status"] = "Queued"
            active_order["progress"] = 0
            active_order.pop("assignee_npc_id", None)
            active_order.pop("assigned_tick", None)
            npc["current_work_order_id"] = None
            work_order_changes.append({"type": "work_order_unassigned", "work_order_id": active_order["id"], "reason": "missing_mining_laser"})
            return

        if work_type == "HaulItem":
            item = self._item_for_haul_order(active_order)
            if item is not None:
                holder = item.get("holder_npc_id")
                if holder is None:
                    item["holder_npc_id"] = npc["id"]
                    work_order_changes.append({"type": "item_picked_up", "item_id": item["id"], "npc_id": npc["id"]})
                elif holder == npc.get("id"):
                    item["location"] = {"x": int(npc["x"]), "y": int(npc["y"])}

        active_order["progress"] = int(active_order.get("progress", 0)) + progress_gain
        work_order_changes.append(
            {
                "type": "work_order_progress",
                "work_order_id": active_order["id"],
                "progress": int(active_order["progress"]),
                "required_progress": int(active_order.get("required_progress", 2)),
                "assignee_npc_id": npc["id"],
            }
        )
        if int(active_order["progress"]) < int(active_order.get("required_progress", 2)):
            return

        work_type = str(active_order.get("work_type", ""))
        disposed_body_id = active_order.get("body_id")
        if work_type == "DisposeBody" and isinstance(disposed_body_id, str):
            for body in self.world_state.get("bodies", []):
                if body.get("id") != disposed_body_id:
                    continue
                if not body.get("disposed", False):
                    body["disposed"] = True
                    body["disposed_tick"] = self.tick
                    body["disposed_by_npc_id"] = npc["id"]
                    npc_changes.append(
                        {
                            "type": "body_disposed",
                            "body_id": disposed_body_id,
                            "disposed_by_npc_id": npc["id"],
                            "tick": self.tick,
                        }
                    )
                break
        elif work_type == "MineIce":
            item_id = f"item-ice-{active_order['id']}-{self.tick}"
            item = {
                "id": item_id,
                "item_type": str(active_order.get("item_type", "IceChunk")),
                "location": {"x": int(npc["x"]), "y": int(npc["y"])},
                "holder_npc_id": None,
                "created_tick": self.tick,
                "weight": self._item_weight(str(active_order.get("item_type", "IceChunk"))),
            }
            self.world_state.setdefault("items", []).append(item)
            npc_changes.append({"type": "item_created", "item_id": item_id, "item_type": item["item_type"], "location": item["location"]})

            destination = self._nearest_storage_location(int(npc["x"]), int(npc["y"]))
            if destination is not None:
                haul_order = {
                    "id": f"wo-haul-{item_id}",
                    "work_type": "HaulItem",
                    "status": "Queued",
                    "location": {"x": int(npc["x"]), "y": int(npc["y"])},
                    "destination": destination,
                    "item_id": item_id,
                    "created_tick": self.tick,
                    "progress": 0,
                    "required_progress": 2,
                }
                self.world_state.setdefault("work_orders", []).append(haul_order)
                work_order_changes.append({"type": "work_order_created_auto", "work_order": self._snapshot_work_order(haul_order)})
        elif work_type == "HaulItem":
            item = self._item_for_haul_order(active_order)
            destination = active_order.get("destination")
            if item is not None and isinstance(destination, dict):
                item["holder_npc_id"] = None
                item["location"] = {"x": int(destination.get("x", npc["x"])), "y": int(destination.get("y", npc["y"]))}
                self._store_item_at_location(item)
                work_order_changes.append({"type": "item_stored", "item_id": item["id"], "location": item["location"]})

                # phase 5b chain hooks
                if str(item.get("item_type")) == "IceChunk":
                    refine_order = {
                        "id": f"wo-refine-{item['id']}",
                        "work_type": "RefineIce",
                        "status": "Queued",
                        "location": {"x": int(item["location"]["x"]), "y": int(item["location"]["y"] )},
                        "item_id": item["id"],
                        "created_tick": self.tick,
                        "progress": 0,
                        "required_progress": 2,
                    }
                    self.world_state.setdefault("work_orders", []).append(refine_order)
                    work_order_changes.append({"type": "work_order_created_auto", "work_order": self._snapshot_work_order(refine_order)})
                elif str(item.get("item_type")) == "WaterUnit":
                    generator_location = self._nearest_oxygen_generator_location(int(item["location"]["x"]), int(item["location"]["y"]))
                    if generator_location is not None:
                        feed_order = {
                            "id": f"wo-feed-{item['id']}",
                            "work_type": "FeedOxygenGenerator",
                            "status": "Queued",
                            "location": {"x": int(item["location"]["x"]), "y": int(item["location"]["y"])},
                            "item_id": item["id"],
                            "generator_location": {"x": int(generator_location["x"]), "y": int(generator_location["y"])},
                            "created_tick": self.tick,
                            "progress": 0,
                            "required_progress": 1,
                        }
                        self.world_state.setdefault("work_orders", []).append(feed_order)
                        work_order_changes.append({"type": "work_order_created_auto", "work_order": self._snapshot_work_order(feed_order)})
        elif work_type == "RefineIce":
            source_item = self._item_for_order_item(active_order)
            if source_item is not None and not source_item.get("consumed", False):
                source_item["consumed"] = True
                source_item["consumed_tick"] = self.tick
                water_id = f"item-water-{source_item['id']}-{self.tick}"
                water_item = {
                    "id": water_id,
                    "item_type": "WaterUnit",
                    "location": {"x": int(npc["x"]), "y": int(npc["y"])},
                    "holder_npc_id": None,
                    "created_tick": self.tick,
                    "consumed": False,
                    "weight": self._item_weight("WaterUnit"),
                }
                self.world_state.setdefault("items", []).append(water_item)
                npc_changes.append({"type": "item_created", "item_id": water_id, "item_type": "WaterUnit", "location": water_item["location"]})

                destination = self._nearest_oxygen_generator_location(int(npc["x"]), int(npc["y"])) or self._nearest_storage_location(int(npc["x"]), int(npc["y"]))
                if destination is not None:
                    haul_order = {
                        "id": f"wo-haul-{water_id}",
                        "work_type": "HaulItem",
                        "status": "Queued",
                        "location": {"x": int(water_item["location"]["x"]), "y": int(water_item["location"]["y"])},
                        "destination": destination,
                        "item_id": water_id,
                        "created_tick": self.tick,
                        "progress": 0,
                        "required_progress": 2,
                    }
                    self.world_state.setdefault("work_orders", []).append(haul_order)
                    work_order_changes.append({"type": "work_order_created_auto", "work_order": self._snapshot_work_order(haul_order)})
        elif work_type == "FeedOxygenGenerator":
            water_item = self._item_for_order_item(active_order)
            gx = int(npc["x"])
            gy = int(npc["y"])
            machine = self.world_state.get("machines", {}).get(self._xy_key(gx, gy))
            if not isinstance(machine, dict) or machine.get("type") != MACHINE_OXYGEN_GENERATOR or not bool(machine.get("enabled", True)):
                active_order["status"] = "Queued"
                active_order["progress"] = 0
                active_order.pop("assignee_npc_id", None)
                active_order.pop("assigned_tick", None)
                active_order.pop("completed_tick", None)
                active_order.pop("completed_by_npc_id", None)
                npc["current_work_order_id"] = None
                work_order_changes.append({
                    "type": "work_order_unassigned",
                    "work_order_id": active_order["id"],
                    "reason": "generator_missing_or_disabled",
                })
                return
            if not self._consumer_is_powered(self._xy_key(gx, gy)):
                active_order["status"] = "Queued"
                active_order["progress"] = 0
                active_order.pop("assignee_npc_id", None)
                active_order.pop("assigned_tick", None)
                active_order.pop("completed_tick", None)
                active_order.pop("completed_by_npc_id", None)
                npc["current_work_order_id"] = None
                work_order_changes.append({
                    "type": "work_order_unassigned",
                    "work_order_id": active_order["id"],
                    "reason": "generator_unpowered",
                })
                return
            if water_item is not None and not water_item.get("consumed", False):
                water_item["consumed"] = True
                water_item["consumed_tick"] = self.tick
                comp_id = self.world_state.get("compartment_index", {}).get(self._xy_key(gx, gy))
                if comp_id is not None:
                    for comp in self.world_state.get("compartments", []):
                        if int(comp.get("id", -1)) != int(comp_id):
                            continue
                        boost = float(machine.get("rate_per_tick", 2.0))
                        comp["oxygen_percent"] = round(min(100.0, float(comp.get("oxygen_percent", 0.0)) + boost), 2)
                        comp["pressure"] = round(float(comp["oxygen_percent"]) / 100, 3)
                        break
                npc_changes.append({"type": "item_consumed", "item_id": water_item["id"], "reason": "feed_oxygen_generator"})

        active_order["status"] = "Completed"
        active_order["completed_tick"] = self.tick
        active_order["completed_by_npc_id"] = npc["id"]
        npc["current_work_order_id"] = None

        work_order_changes.append(
            {
                "type": "work_order_completed",
                "work_order_id": active_order["id"],
                "completed_by_npc_id": npc["id"],
                "disposed_body_id": disposed_body_id,
            }
        )

    def _work_order_target(self, order: dict, npc: dict) -> tuple[int, int] | None:
        work_type = str(order.get("work_type", ""))
        if work_type not in {"HaulItem", "FeedOxygenGenerator"}:
            loc = order.get("location", {})
            if isinstance(loc.get("x"), int) and isinstance(loc.get("y"), int):
                return int(loc["x"]), int(loc["y"])
            return None

        if work_type == "FeedOxygenGenerator":
            item = self._item_for_order_item(order)
            if item is None:
                return None
            holder = item.get("holder_npc_id")
            if holder == npc.get("id"):
                destination = order.get("generator_location")
                if isinstance(destination, dict) and isinstance(destination.get("x"), int) and isinstance(destination.get("y"), int):
                    return int(destination["x"]), int(destination["y"])
                destination = self._nearest_oxygen_generator_location(int(npc.get("x", 0)), int(npc.get("y", 0)))
                if destination is not None:
                    return int(destination["x"]), int(destination["y"])
            loc = item.get("location", {})
            if isinstance(loc.get("x"), int) and isinstance(loc.get("y"), int):
                return int(loc["x"]), int(loc["y"])
            return None

        item = self._item_for_haul_order(order)
        if item is None:
            return None
        holder = item.get("holder_npc_id")
        if holder == npc.get("id"):
            destination = order.get("destination")
            if isinstance(destination, dict) and isinstance(destination.get("x"), int) and isinstance(destination.get("y"), int):
                return int(destination["x"]), int(destination["y"])
            return None
        loc = item.get("location", {})
        if isinstance(loc.get("x"), int) and isinstance(loc.get("y"), int):
            return int(loc["x"]), int(loc["y"])
        return None

    def _npc_at_active_order_target(self, npc: dict, order: dict) -> bool:
        target = self._work_order_target(order, npc)
        if target is None:
            return False
        return int(npc.get("x", -1)) == target[0] and int(npc.get("y", -1)) == target[1]

    def _item_for_haul_order(self, order: dict) -> dict | None:
        item_id = order.get("item_id")
        if not isinstance(item_id, str):
            return None
        for item in self.world_state.get("items", []):
            if item.get("id") == item_id:
                return item
        return None

    def _npc_active_work_order(self, npc: dict) -> dict | None:
        work_order_id = npc.get("current_work_order_id")
        if not isinstance(work_order_id, str) or not work_order_id:
            return None
        for order in self.world_state.get("work_orders", []):
            if order.get("id") != work_order_id:
                continue
            if order.get("status") != "Assigned":
                return None
            if order.get("assignee_npc_id") != npc.get("id"):
                return None
            return order
        return None

    def _assign_next_work_order(self, npc: dict) -> dict | None:
        npc_id = npc.get("id")
        if not isinstance(npc_id, str):
            return None

        grid = self.world_state["grid"]
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        sx, sy = int(npc.get("x", 0)), int(npc.get("y", 0))

        ranked: list[tuple[int, int, str, dict]] = []
        for order in self.world_state.get("work_orders", []):
            if order.get("status") != "Queued":
                continue
            if order.get("work_type") not in ({"DisposeBody"} | SUPPORTED_COMMAND_WORK_TYPES):
                continue
            location = order.get("location", {})
            tx = location.get("x")
            ty = location.get("y")
            if not isinstance(tx, int) or not isinstance(ty, int):
                continue
            if self._work_order_item_claimed(order):
                continue
            distance = self._path_distance(sx, sy, tx, ty, grid, width, height)
            if distance is None:
                continue
            ranked.append((distance, int(order.get("created_tick", 0)), str(order.get("id", "")), order))

        if not ranked:
            return None

        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        chosen = ranked[0][3]
        chosen["status"] = "Assigned"
        chosen["assignee_npc_id"] = npc_id
        chosen["assigned_tick"] = self.tick
        chosen.setdefault("progress", 0)
        chosen.setdefault("required_progress", 2)
        chosen["path_distance_assigned"] = ranked[0][0]
        npc["current_work_order_id"] = chosen["id"]
        return chosen

    def _work_order_item_claimed(self, order: dict) -> bool:
        if str(order.get("work_type")) not in WORK_TYPES_WITH_ITEM:
            return False
        item_id = order.get("item_id")
        if not isinstance(item_id, str) or not item_id:
            return False
        for other in self.world_state.get("work_orders", []):
            if other is order:
                continue
            if other.get("status") != "Assigned":
                continue
            if other.get("item_id") != item_id:
                continue
            if self._order_priority_key(other) <= self._order_priority_key(order):
                return True
        return False

    @staticmethod
    def _order_priority_key(order: dict) -> tuple[int, str]:
        return int(order.get("created_tick", 0)), str(order.get("id", ""))

    def _is_alive_npc_id(self, npc_id: object) -> bool:
        if not isinstance(npc_id, str):
            return False
        for npc in self.world_state.get("npcs", []):
            if npc.get("id") != npc_id:
                continue
            return bool(npc.get("alive", True))
        return False

    def _active_order_item_conflict_reason(self, order: dict, npc: dict) -> str | None:
        if str(order.get("work_type")) not in WORK_TYPES_WITH_ITEM:
            return None
        item = self._item_for_order_item(order)
        if item is None or bool(item.get("consumed", False)):
            return "item_unavailable"
        item_id = order.get("item_id")
        if isinstance(item_id, str):
            for other in self.world_state.get("work_orders", []):
                if other is order:
                    continue
                if other.get("item_id") != item_id:
                    continue
                if other.get("status") != "Completed":
                    continue
                if other.get("work_type") != order.get("work_type"):
                    continue
                if self._order_priority_key(other) <= self._order_priority_key(order):
                    return "item_unavailable"
        if self._work_order_item_claimed(order):
            return "claimed_by_other_order"
        holder = item.get("holder_npc_id")
        npc_id = npc.get("id")
        if holder is not None and holder != npc_id:
            # Dead/missing holders should not permanently lock the item.
            if self._is_alive_npc_id(holder):
                return "claimed_by_other_order"
            item["holder_npc_id"] = None
        return None

    def _path_distance(
        self,
        sx: int,
        sy: int,
        tx: int,
        ty: int,
        grid: list[list[str]],
        width: int,
        height: int,
    ) -> int | None:
        start = (sx, sy)
        target = (tx, ty)
        if start == target:
            return 0

        visited: set[tuple[int, int]] = {start}
        frontier: deque[tuple[int, int, int]] = deque([(sx, sy, 0)])
        while frontier:
            cx, cy, dist = frontier.popleft()
            for nx, ny in self._neighbors8(cx, cy, width, height):
                if (nx, ny) in visited:
                    continue
                if grid[ny][nx] not in WALKABLE_TILES:
                    continue
                if (nx, ny) == target:
                    return dist + 1
                visited.add((nx, ny))
                frontier.append((nx, ny, dist + 1))
        return None

    def _step_toward_target(
        self,
        x: int,
        y: int,
        target_x: int,
        target_y: int,
        grid: list[list[str]],
        width: int,
        height: int,
    ) -> tuple[int, int] | None:
        start = (x, y)
        target = (target_x, target_y)
        if start == target:
            return None

        visited: set[tuple[int, int]] = {start}
        parents: dict[tuple[int, int], tuple[int, int]] = {}
        frontier: deque[tuple[int, int]] = deque([start])

        found = False
        while frontier:
            cx, cy = frontier.popleft()
            for nx, ny in self._neighbors8(cx, cy, width, height):
                if (nx, ny) in visited:
                    continue
                if grid[ny][nx] not in WALKABLE_TILES:
                    continue
                visited.add((nx, ny))
                parents[(nx, ny)] = (cx, cy)
                if (nx, ny) == target:
                    found = True
                    frontier.clear()
                    break
                frontier.append((nx, ny))

        if not found:
            return None

        step = target
        while parents.get(step) != start:
            parent = parents.get(step)
            if parent is None:
                return None
            step = parent
        return step

    def _next_npc_position(
        self,
        x: int,
        y: int,
        grid: list[list[str]],
        width: int,
        height: int,
        index: dict[str, int],
        compartments: dict[int, dict],
    ) -> tuple[int, int] | None:
        current = (x, y)
        current_oxygen = self._oxygen_at_tile(x, y, index, compartments)

        visited: set[tuple[int, int]] = {current}
        parents: dict[tuple[int, int], tuple[int, int]] = {}
        distances: dict[tuple[int, int], int] = {current: 0}
        frontier: deque[tuple[int, int]] = deque([current])

        best_target = current
        best_rank = (current_oxygen >= SETTINGS.oxygen_safe_min_percent, current_oxygen, 0, -x, -y)

        while frontier:
            cx, cy = frontier.popleft()
            for nx, ny in self._neighbors8(cx, cy, width, height):
                if (nx, ny) in visited:
                    continue
                if grid[ny][nx] not in WALKABLE_TILES:
                    continue

                visited.add((nx, ny))
                parents[(nx, ny)] = (cx, cy)
                distances[(nx, ny)] = distances[(cx, cy)] + 1
                frontier.append((nx, ny))

                oxygen = self._oxygen_at_tile(nx, ny, index, compartments)
                rank = (
                    oxygen >= SETTINGS.oxygen_safe_min_percent,
                    oxygen,
                    -distances[(nx, ny)],
                    -nx,
                    -ny,
                )
                if rank > best_rank:
                    best_rank = rank
                    best_target = (nx, ny)

        if best_target == current:
            return None

        step = best_target
        while parents.get(step) != current:
            parent = parents.get(step)
            if parent is None:
                return None
            step = parent
        return step

    def _next_npc_position_for_thermal_safety(
        self,
        x: int,
        y: int,
        grid: list[list[str]],
        width: int,
        height: int,
    ) -> tuple[int, int] | None:
        current = (x, y)
        current_temp = self._temperature_at_tile(x, y)

        visited: set[tuple[int, int]] = {current}
        parents: dict[tuple[int, int], tuple[int, int]] = {}
        distances: dict[tuple[int, int], int] = {current: 0}
        frontier: deque[tuple[int, int]] = deque([current])

        best_target = current
        best_rank = self._thermal_safety_rank(current_temp, 0, x, y)

        while frontier:
            cx, cy = frontier.popleft()
            for nx, ny in self._neighbors8(cx, cy, width, height):
                if (nx, ny) in visited:
                    continue
                if grid[ny][nx] not in WALKABLE_TILES:
                    continue

                visited.add((nx, ny))
                parents[(nx, ny)] = (cx, cy)
                distances[(nx, ny)] = distances[(cx, cy)] + 1
                frontier.append((nx, ny))

                temp = self._temperature_at_tile(nx, ny)
                rank = self._thermal_safety_rank(temp, distances[(nx, ny)], nx, ny)
                if rank > best_rank:
                    best_rank = rank
                    best_target = (nx, ny)

        if best_target == current:
            return None

        step = best_target
        while parents.get(step) != current:
            parent = parents.get(step)
            if parent is None:
                return None
            step = parent
        return step

    @staticmethod
    def _thermal_safety_rank(temp_c: float, distance: int, x: int, y: int) -> tuple[bool, float, int, int, int]:
        comfort_min = float(SETTINGS.thermal_comfort_min_c)
        comfort_max = float(SETTINGS.thermal_comfort_max_c)
        if comfort_min <= temp_c <= comfort_max:
            comfort_score = 0.0
            in_comfort = True
        elif temp_c < comfort_min:
            comfort_score = temp_c - comfort_min
            in_comfort = False
        else:
            comfort_score = comfort_max - temp_c
            in_comfort = False
        return (
            in_comfort,
            comfort_score,
            -distance,
            -x,
            -y,
        )

    def _temperature_at_tile(self, x: int, y: int) -> float:
        temp_grid = self.world_state.get("temperature_grid", [])
        if not isinstance(temp_grid, list):
            return float(SETTINGS.thermal_default_temp_c)
        if 0 <= y < len(temp_grid) and isinstance(temp_grid[y], list) and 0 <= x < len(temp_grid[y]):
            value = temp_grid[y][x]
            if isinstance(value, (int, float)):
                return float(value)
        return float(SETTINGS.thermal_default_temp_c)

    def _oxygen_at_tile(self, x: int, y: int, index: dict[str, int], compartments: dict[int, dict]) -> float:
        comp_id = index.get(self._xy_key(x, y))
        if comp_id is not None:
            compartment = compartments.get(int(comp_id))
            if compartment is not None:
                return float(compartment.get("oxygen_percent", 0.0))

        # Door tiles are walkable but not part of compartments; infer local oxygen from adjacent compartments.
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]
        adjacent_values: list[float] = []
        for nx, ny in self._neighbors4(x, y, width, height):
            neighbor_comp = index.get(self._xy_key(nx, ny))
            if neighbor_comp is None:
                continue
            compartment = compartments.get(int(neighbor_comp))
            if compartment is None:
                continue
            adjacent_values.append(float(compartment.get("oxygen_percent", 0.0)))
        if adjacent_values:
            return max(adjacent_values)
        return 0.0

    def _compartment_snapshot_map(self) -> dict[int, dict]:
        snapshot: dict[int, dict] = {}
        for compartment in self.world_state["compartments"]:
            cid = int(compartment["id"])
            snapshot[cid] = {
                "oxygen_percent": float(compartment.get("oxygen_percent", 0.0)),
                "pressure": float(compartment.get("pressure", 0.0)),
                "temperature": float(compartment.get("temperature", SETTINGS.thermal_default_temp_c)),
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
                or current["temperature"] != previous["temperature"]
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

    def _item_for_order_item(self, order: dict) -> dict | None:
        item_id = order.get("item_id")
        if not isinstance(item_id, str):
            return None
        for item in self.world_state.get("items", []):
            if item.get("id") == item_id:
                return item
        return None

    def _consumer_is_powered(self, machine_key: str) -> bool:
        for consumer in self.world_state.get("power_state", {}).get("powered_consumers", []):
            if str(consumer) == machine_key:
                return True
        return False

    def _nearest_oxygen_generator_location(self, x: int, y: int) -> dict | None:
        ranked: list[tuple[int, str, dict]] = []
        for key, machine in self.world_state.get("machines", {}).items():
            if not isinstance(machine, dict):
                continue
            if machine.get("type") != MACHINE_OXYGEN_GENERATOR:
                continue
            try:
                sx_str, sy_str = key.split(",")
                sx, sy = int(sx_str), int(sy_str)
            except Exception:
                continue
            dist = abs(sx - x) + abs(sy - y)
            ranked.append((dist, key, {"x": sx, "y": sy}))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]))
        return ranked[0][2]

    def _nearest_storage_location(self, x: int, y: int) -> dict | None:
        storages = self.world_state.get("storages", [])
        grid = self.world_state["grid"]
        width = self.world_state["world"]["width"]
        height = self.world_state["world"]["height"]

        ranked: list[tuple[int, str, dict]] = []
        for storage in storages:
            loc = storage.get("location", {})
            sx, sy = loc.get("x"), loc.get("y")
            if not isinstance(sx, int) or not isinstance(sy, int):
                continue
            distance = self._path_distance(int(x), int(y), sx, sy, grid, width, height)
            if distance is None:
                continue
            ranked.append((distance, str(storage.get("id", "")), storage))
        if not ranked:
            return None
        ranked.sort(key=lambda item: (item[0], item[1]))
        loc = ranked[0][2]["location"]
        return {"x": int(loc["x"]), "y": int(loc["y"])}

    def _store_item_at_location(self, item: dict) -> None:
        loc = item.get("location", {})
        ix, iy = loc.get("x"), loc.get("y")
        if not isinstance(ix, int) or not isinstance(iy, int):
            return
        for storage in self.world_state.get("storages", []):
            s_loc = storage.get("location", {})
            if s_loc.get("x") == ix and s_loc.get("y") == iy:
                inventory = storage.setdefault("inventory", [])
                if item.get("id") not in inventory:
                    inventory.append(item.get("id"))
                break

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
    def _thermal_events(before: dict, after: dict) -> list[dict]:
        if before == after:
            return []
        return [
            {
                "type": "thermal_state_change",
                "previous": before,
                "current": after,
            }
        ]

    @staticmethod
    def _neighbors8(x: int, y: int, width: int, height: int) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        for dx, dy in ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                points.append((nx, ny))
        return points

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

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
            "power": {"mode": "global_network"},
            "population": 0,
            "grid": [[TILE_FLOOR for _ in range(width)] for _ in range(height)],
            "door_states": {},
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
            ack = CommandAck(
                client_command_id=command.client_command_id,
                result=CommandResult.THROTTLED,
                tick=self.tick,
            )
            self.command_ack_cache[session_id][command.client_command_id] = ack
            return ack

        if not self._validate_command_payload(command):
            ack = CommandAck(
                client_command_id=command.client_command_id,
                result=CommandResult.INVALID_PAYLOAD,
                tick=self.tick,
            )
            self.command_ack_cache[session_id][command.client_command_id] = ack
            return ack

        await self.command_queue.put(PendingCommand(session_id=session_id, command=command, enqueued_at_tick=self.tick))
        self.last_action_at[session_id] = time.monotonic()
        ack = CommandAck(
            client_command_id=command.client_command_id,
            result=CommandResult.QUEUED,
            tick=self.tick,
        )
        self.command_ack_cache[session_id][command.client_command_id] = ack
        return ack

    def world_snapshot(self) -> dict:
        return {
            "tick": self.tick,
            "world": self.world_state,
        }

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

        if topology_changed:
            self._recompute_compartments()

        self._update_oxygen()
        world_hash = self._world_hash()
        delta = DeltaTick(tick=self.tick, world_hash=world_hash, command_count=applied, tile_changes=tile_changes)
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
                return isinstance(tile_type, str) and tile_type in (ALL_TILE_TYPES - {TILE_VACUUM})
            return True

        if command.type is CommandType.CREATE_WORK_ORDER:
            work_type = payload.get("work_type")
            location = payload.get("location")
            if not isinstance(work_type, str) or not work_type:
                return False
            if not isinstance(location, dict):
                return False
            return self._validate_xy(location.get("x"), location.get("y"))

        return False

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

        if command.type is CommandType.BUILD:
            after = command.payload.get("tile_type", TILE_WALL)
        else:
            after = TILE_VACUUM

        if before == after:
            return None, False

        self.world_state["grid"][y][x] = after
        if after == TILE_DOOR:
            self.world_state["door_states"][key] = {"open": False}
        elif key in self.world_state["door_states"]:
            self.world_state["door_states"].pop(key, None)

        return {"x": x, "y": y, "before": before, "after": after}, True

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

        old_map = {
            int(c["id"]): float(c.get("oxygen_percent", 100.0)) for c in self.world_state.get("compartments", [])
        }
        old_index = self.world_state.get("compartment_index", {})

        def oxygen_for_tile(tx: int, ty: int) -> float:
            old_id = old_index.get(self._xy_key(tx, ty))
            if old_id is None:
                return 100.0
            return old_map.get(int(old_id), 100.0)

        comp_id = 1
        for y in range(height):
            for x in range(width):
                if (x, y) in visited:
                    continue
                if grid[y][x] not in COMPARTMENT_FILL_TILES:
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
                        if (nx, ny) in visited:
                            continue
                        if grid[ny][nx] not in COMPARTMENT_FILL_TILES:
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

        # direct leak to vacuum from compartment tiles
        for key, comp_id in index.items():
            x_str, y_str = key.split(",")
            x, y = int(x_str), int(y_str)
            for nx, ny in self._neighbors4(x, y, width, height):
                if grid[ny][nx] == TILE_VACUUM:
                    leak_counts[int(comp_id)] += 1

        # door-driven diffusion/leak
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
                left = unique_adjacent[0]
                right = unique_adjacent[1]
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

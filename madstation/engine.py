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
        self.tick: int = 0
        self.server_sequence_id: int = 0
        self.world_state: dict = {
            "world": {"width": 50, "height": 50},
            "power": {"mode": "global_network"},
            "population": 0,
        }
        self.connections: dict[str, SocketLike] = {}
        self.command_queue: asyncio.Queue[PendingCommand] = asyncio.Queue()
        self.last_action_at: dict[str, float] = {}
        self.command_ack_cache: dict[str, dict[str, CommandAck]] = {}
        self._running = False

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
            ack = CommandAck(
                client_command_id=pending.command.client_command_id,
                result=CommandResult.APPLIED,
                server_sequence_id=self.server_sequence_id,
                tick=self.tick,
            )
            self.command_ack_cache[pending.session_id][pending.command.client_command_id] = ack
            await self._safe_send(pending.session_id, ack.model_dump())

        world_hash = self._world_hash()
        delta = DeltaTick(tick=self.tick, world_hash=world_hash, command_count=applied)
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
            return self._validate_xy(payload.get("x"), payload.get("y"))

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

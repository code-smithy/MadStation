from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class CommandType(str, Enum):
    BUILD = "Build"
    DECONSTRUCT = "Deconstruct"
    CREATE_WORK_ORDER = "CreateWorkOrder"


class CommandResult(str, Enum):
    ACCEPTED = "ACCEPTED"
    THROTTLED = "THROTTLED"
    CONFLICT_STALE_TARGET = "CONFLICT_STALE_TARGET"
    INVALID_PAYLOAD = "INVALID_PAYLOAD"


@dataclass
class ClientCommand:
    client_command_id: str
    type: CommandType
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def model_validate(cls, payload: dict[str, Any]) -> "ClientCommand":
        if not isinstance(payload, dict):
            raise ValueError("command payload must be an object")

        command_type = payload.get("type")
        return cls(
            client_command_id=str(payload.get("client_command_id", "")),
            type=CommandType(command_type),
            payload=payload.get("payload") or {},
        )

    def model_dump(self) -> dict[str, Any]:
        dumped = asdict(self)
        dumped["type"] = self.type.value
        return dumped


@dataclass
class CommandAck:
    client_command_id: str
    result: CommandResult
    tick: int
    server_sequence_id: int | None = None
    type: str = "command_ack"

    def model_dump(self) -> dict[str, Any]:
        dumped = asdict(self)
        dumped["result"] = self.result.value
        return dumped


@dataclass
class SnapshotFull:
    session_id: str
    snapshot_tick: int
    state: dict[str, Any]
    type: str = "snapshot_full"
    protocol_version: str = "1.0"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeltaTick:
    tick: int
    world_hash: str
    command_count: int
    tile_changes: list[dict[str, Any]] = field(default_factory=list)
    entity_changes: list[dict[str, Any]] = field(default_factory=list)
    work_order_changes: list[dict[str, Any]] = field(default_factory=list)
    death_log_appends: list[dict[str, Any]] = field(default_factory=list)
    type: str = "delta_tick"
    protocol_version: str = "1.0"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

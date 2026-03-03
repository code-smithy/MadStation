import asyncio

from madstation.engine import SimulationEngine, TILE_VACUUM, TILE_WALL
from madstation.protocol import ClientCommand, CommandResult, CommandType


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


class FailingWebSocket(FakeWebSocket):
    async def send_json(self, payload: dict) -> None:
        raise RuntimeError("socket failed")


def build_command(command_id: str, x: int, y: int, tile_type: str | None = None) -> ClientCommand:
    payload = {"x": x, "y": y}
    if tile_type is not None:
        payload["tile_type"] = tile_type
    return ClientCommand(client_command_id=command_id, type=CommandType.BUILD, payload=payload)


def test_connect_sends_snapshot_full() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session_id = await engine.connect(ws)

        assert ws.accepted is True
        assert session_id.startswith("anon-")
        assert ws.messages[0]["type"] == "snapshot_full"
        assert ws.messages[0]["session_id"] == session_id
        assert ws.messages[0]["snapshot_tick"] == 0

    asyncio.run(run())


def test_enqueue_command_rejects_invalid_payload() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ack = await engine.enqueue_command(
            "anon-test",
            ClientCommand(client_command_id="c1", type=CommandType.BUILD, payload={"x": "bad", "y": 1}),
        )
        assert ack.result == CommandResult.INVALID_PAYLOAD

    asyncio.run(run())


def test_build_rejects_invalid_tile_type() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ack = await engine.enqueue_command(
            "anon-test",
            ClientCommand(
                client_command_id="c1",
                type=CommandType.BUILD,
                payload={"x": 1, "y": 1, "tile_type": "NotATile"},
            ),
        )
        assert ack.result == CommandResult.INVALID_PAYLOAD

    asyncio.run(run())


def test_enqueue_command_enforces_throttle() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        first = await engine.enqueue_command("anon-test", build_command("c1", 1, 1))
        second = await engine.enqueue_command("anon-test", build_command("c2", 2, 2))

        assert first.result == CommandResult.QUEUED
        assert second.result == CommandResult.THROTTLED

    asyncio.run(run())


def test_enqueue_command_is_idempotent_per_client_command_id() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        first = await engine.enqueue_command("anon-test", build_command("same-id", 1, 1))
        second = await engine.enqueue_command("anon-test", build_command("same-id", 1, 1))

        assert first.result == CommandResult.QUEUED
        assert second.result == CommandResult.QUEUED
        assert first.tick == second.tick
        assert engine.command_queue.qsize() == 1

    asyncio.run(run())


def test_execute_tick_applies_first_write_wins_for_conflicts() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        ws_a = FakeWebSocket()
        ws_b = FakeWebSocket()
        await engine.connect(ws_a)
        await engine.connect(ws_b)
        session_ids = list(engine.connections.keys())
        session_a, session_b = session_ids[0], session_ids[1]

        engine.last_action_at.pop(session_a, None)
        engine.last_action_at.pop(session_b, None)

        await engine.enqueue_command(session_a, build_command("a1", 5, 5))
        await engine.enqueue_command(session_b, build_command("b1", 5, 5))

        await engine._execute_tick()

        acks_a = [m for m in ws_a.messages if m.get("type") == "command_ack"]
        acks_b = [m for m in ws_b.messages if m.get("type") == "command_ack"]

        assert any(m["result"] == CommandResult.APPLIED.value for m in acks_a)
        assert any(m["result"] == CommandResult.CONFLICT_STALE_TARGET.value for m in acks_b)

        delta_messages = [m for m in ws_a.messages if m.get("type") == "delta_tick"]
        assert delta_messages[-1]["command_count"] == 1

    asyncio.run(run())


def test_build_and_deconstruct_emit_tile_changes() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session_id = await engine.connect(ws)

        await engine.enqueue_command(session_id, build_command("wall-1", 2, 2, TILE_WALL))
        await engine._execute_tick()

        engine.last_action_at.pop(session_id, None)
        await engine.enqueue_command(
            session_id,
            ClientCommand(client_command_id="decon-1", type=CommandType.DECONSTRUCT, payload={"x": 2, "y": 2}),
        )
        await engine._execute_tick()

        deltas = [m for m in ws.messages if m.get("type") == "delta_tick"]
        assert len(deltas) >= 2
        first_changes = deltas[-2]["tile_changes"]
        second_changes = deltas[-1]["tile_changes"]
        assert len(first_changes) == 1
        assert len(second_changes) == 1
        assert first_changes[0]["after"] == TILE_WALL
        assert second_changes[0]["after"] == TILE_VACUUM
        assert engine.world_state["grid"][2][2] == TILE_VACUUM

    asyncio.run(run())


def test_oxygen_drops_after_vacuum_breach() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session_id = await engine.connect(ws)

        before = engine.world_state["compartments"][0]["oxygen_percent"]
        await engine.enqueue_command(
            session_id,
            ClientCommand(client_command_id="breach", type=CommandType.DECONSTRUCT, payload={"x": 0, "y": 0}),
        )
        await engine._execute_tick()
        after = engine.world_state["compartments"][0]["oxygen_percent"]

        assert after < before

    asyncio.run(run())


def test_broadcast_disconnects_failing_socket() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws_ok = FakeWebSocket()
        ws_bad = FailingWebSocket()

        session_ok = await engine.connect(ws_ok)
        session_bad = await engine.connect(ws_bad)

        await engine._broadcast({"type": "delta_tick"})

        assert session_ok in engine.connections
        assert session_bad not in engine.connections

    asyncio.run(run())


def test_create_work_order_payload_validation() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        invalid = ClientCommand(
            client_command_id="wo-1",
            type=CommandType.CREATE_WORK_ORDER,
            payload={"location": {"x": 2, "y": 2}},
        )
        valid = ClientCommand(
            client_command_id="wo-2",
            type=CommandType.CREATE_WORK_ORDER,
            payload={"work_type": "Mine", "location": {"x": 2, "y": 2}},
        )

        invalid_ack = await engine.enqueue_command("anon-test", invalid)
        engine.last_action_at.pop("anon-test", None)
        valid_ack = await engine.enqueue_command("anon-test", valid)

        assert invalid_ack.result == CommandResult.INVALID_PAYLOAD
        assert valid_ack.result == CommandResult.QUEUED

    asyncio.run(run())


def test_runtime_status_exposes_tick_and_queue_metrics() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        await engine.connect(ws)
        await engine.enqueue_command("anon-a", build_command("c1", 1, 1))

        status_before = engine.runtime_status()
        assert status_before["tick"] == 0
        assert status_before["connected_clients"] == 1
        assert status_before["queued_commands"] == 1
        assert status_before["compartment_count"] >= 1

        await engine._execute_tick()
        status_after = engine.runtime_status()
        assert status_after["tick"] == 1
        assert status_after["queued_commands"] == 0

    asyncio.run(run())


def test_five_clients_receive_same_deterministic_tick_delta() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        sockets = [FakeWebSocket() for _ in range(5)]
        for ws in sockets:
            await engine.connect(ws)

        await engine._execute_tick()

        deltas = []
        for ws in sockets:
            msgs = [m for m in ws.messages if m.get("type") == "delta_tick"]
            assert msgs, "expected at least one delta_tick"
            deltas.append(msgs[-1])

        ticks = {d["tick"] for d in deltas}
        hashes = {d["world_hash"] for d in deltas}
        command_counts = {d["command_count"] for d in deltas}

        assert ticks == {1}
        assert hashes and len(hashes) == 1
        assert command_counts == {0}

    asyncio.run(run())

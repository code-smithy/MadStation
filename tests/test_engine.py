import asyncio

from madstation.engine import SimulationEngine
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


def build_command(command_id: str, x: int, y: int) -> ClientCommand:
    return ClientCommand(client_command_id=command_id, type=CommandType.BUILD, payload={"x": x, "y": y})


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

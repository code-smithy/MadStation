import asyncio

from madstation.engine import SimulationEngine
from madstation.protocol import ClientCommand, CommandResult


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        self.messages.append(payload)


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
            ClientCommand(client_command_id="c1", type="Build", payload={"x": "bad", "y": 1}),
        )
        assert ack.result == CommandResult.INVALID_PAYLOAD

    asyncio.run(run())


def test_enqueue_command_enforces_throttle() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        command = ClientCommand(client_command_id="c1", type="Build", payload={"x": 1, "y": 1})

        first = await engine.enqueue_command("anon-test", command)
        second = await engine.enqueue_command(
            "anon-test",
            ClientCommand(client_command_id="c2", type="Build", payload={"x": 2, "y": 2}),
        )

        assert first.result == CommandResult.ACCEPTED
        assert second.result == CommandResult.THROTTLED

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

        await engine.enqueue_command(
            session_a,
            ClientCommand(client_command_id="a1", type="Build", payload={"x": 5, "y": 5}),
        )
        await engine.enqueue_command(
            session_b,
            ClientCommand(client_command_id="b1", type="Build", payload={"x": 5, "y": 5}),
        )

        await engine._execute_tick()

        # Last message for each websocket is delta broadcast; inspect all messages for command acks.
        acks_a = [m for m in ws_a.messages if m.get("type") == "command_ack"]
        acks_b = [m for m in ws_b.messages if m.get("type") == "command_ack"]

        assert any(m["result"] == CommandResult.ACCEPTED.value for m in acks_a)
        assert any(m["result"] == CommandResult.CONFLICT_STALE_TARGET.value for m in acks_b)

        delta_messages = [m for m in ws_a.messages if m.get("type") == "delta_tick"]
        assert delta_messages[-1]["command_count"] == 1

    asyncio.run(run())

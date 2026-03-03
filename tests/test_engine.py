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
            ClientCommand(client_command_id="breach", type=CommandType.DECONSTRUCT, payload={"x": 14, "y": 20}),
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


def test_closed_door_splits_compartments() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        # carve tiny deterministic setup
        for y in range(50):
            for x in range(50):
                engine.world_state["grid"][y][x] = "Wall"

        engine.world_state["grid"][1][1] = "Floor"
        engine.world_state["grid"][1][3] = "Floor"
        engine.world_state["grid"][1][2] = "Door"
        engine.world_state["door_states"]["2,1"] = {"open": False}

        engine._recompute_compartments()

        assert len(engine.world_state["compartments"]) == 2

    asyncio.run(run())


def test_open_door_diffuses_oxygen_between_compartments() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        for y in range(50):
            for x in range(50):
                engine.world_state["grid"][y][x] = "Wall"

        engine.world_state["grid"][1][1] = "Floor"
        engine.world_state["grid"][1][3] = "Floor"
        engine.world_state["grid"][1][2] = "Door"
        engine.world_state["door_states"]["2,1"] = {"open": True}

        engine._recompute_compartments()
        left_id = int(engine.world_state["compartment_index"]["1,1"])
        right_id = int(engine.world_state["compartment_index"]["3,1"])
        assert left_id != right_id

        for comp in engine.world_state["compartments"]:
            if int(comp["id"]) == left_id:
                comp["oxygen_percent"] = 100.0
            if int(comp["id"]) == right_id:
                comp["oxygen_percent"] = 0.0

        engine._update_oxygen()

        left_after = next(c["oxygen_percent"] for c in engine.world_state["compartments"] if int(c["id"]) == left_id)
        right_after = next(c["oxygen_percent"] for c in engine.world_state["compartments"] if int(c["id"]) == right_id)

        assert left_after < 100.0
        assert right_after > 0.0

    asyncio.run(run())


def test_door_auto_open_close_generates_tile_changes() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session_id = await engine.connect(ws)

        # build interior floor pair around a door location
        await engine.enqueue_command(session_id, build_command("f-left", 9, 10, "Floor"))
        await engine._execute_tick()
        engine.last_action_at.pop(session_id, None)
        await engine.enqueue_command(session_id, build_command("f-right", 11, 10, "Floor"))
        await engine._execute_tick()
        engine.last_action_at.pop(session_id, None)
        await engine.enqueue_command(session_id, build_command("door", 10, 10, "Door"))
        await engine._execute_tick()

        door_state = engine.world_state["door_states"].get("10,10", {})
        assert door_state.get("open") is True

        deltas = [m for m in ws.messages if m.get("type") == "delta_tick"]
        assert any(any(change.get("type") == "door_state" for change in d.get("tile_changes", [])) for d in deltas)

    asyncio.run(run())


def test_delta_includes_compartment_changes_after_breach() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session_id = await engine.connect(ws)

        await engine.enqueue_command(
            session_id,
            ClientCommand(client_command_id="breach-comp", type=CommandType.DECONSTRUCT, payload={"x": 14, "y": 20}),
        )
        await engine._execute_tick()

        deltas = [m for m in ws.messages if m.get("type") == "delta_tick"]
        assert deltas
        entity_changes = deltas[-1].get("entity_changes", [])
        assert any(change.get("type") == "compartment_change" for change in entity_changes)

    asyncio.run(run())



def test_oxygen_generator_machine_increases_compartment_oxygen() -> None:
    async def run() -> None:
        engine = SimulationEngine()

        # set deterministic closed room with one floor tile compartment
        for y in range(50):
            for x in range(50):
                engine.world_state["grid"][y][x] = "Wall"
        engine.world_state["grid"][10][10] = "Floor"
        engine.world_state["grid"][10][11] = "Floor"
        engine._recompute_compartments()

        only_compartment = engine.world_state["compartments"][0]
        only_compartment["oxygen_percent"] = 20.0

        engine.world_state["machines"]["10,10"] = {
            "type": "OxygenGenerator",
            "enabled": True,
            "rate_per_tick": 5.0,
            "consume_kw": 2.0,
        }
        engine.world_state["machines"]["11,10"] = {
            "type": "Reactor",
            "enabled": True,
            "generation_kw": 8.0,
        }

        engine._update_power()
        engine._update_oxygen()
        assert engine.world_state["compartments"][0]["oxygen_percent"] > 20.0

    asyncio.run(run())


def test_build_with_machine_registers_and_deconstruct_removes_machine() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session_id = await engine.connect(ws)

        build_with_machine = ClientCommand(
            client_command_id="m1",
            type=CommandType.BUILD,
            payload={
                "x": 4,
                "y": 4,
                "tile_type": "Floor",
                "machine": {"type": "OxygenGenerator", "rate_per_tick": 3.0},
            },
        )
        ack = await engine.enqueue_command(session_id, build_with_machine)
        assert ack.result == CommandResult.QUEUED
        await engine._execute_tick()

        assert "4,4" in engine.world_state["machines"]
        assert engine.world_state["machines"]["4,4"]["type"] == "OxygenGenerator"

        engine.last_action_at.pop(session_id, None)
        decon = ClientCommand(client_command_id="m2", type=CommandType.DECONSTRUCT, payload={"x": 4, "y": 4})
        await engine.enqueue_command(session_id, decon)
        await engine._execute_tick()

        assert "4,4" not in engine.world_state["machines"]

    asyncio.run(run())


def test_build_rejects_invalid_machine_payload() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        invalid_machine = ClientCommand(
            client_command_id="bad-machine",
            type=CommandType.BUILD,
            payload={
                "x": 1,
                "y": 1,
                "tile_type": "Floor",
                "machine": {"type": "UnknownMachine", "rate_per_tick": 5},
            },
        )
        ack = await engine.enqueue_command("anon-test", invalid_machine)
        assert ack.result == CommandResult.INVALID_PAYLOAD

    asyncio.run(run())


def test_power_load_shedding_disables_low_priority_consumers() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        engine.world_state["machines"] = {
            "20,20": {"type": "SolarPanel", "enabled": True, "generation_kw": 2.0},
            "21,20": {"type": "OxygenGenerator", "enabled": True, "rate_per_tick": 2.0, "consume_kw": 2.0},
            "22,20": {"type": "Light", "enabled": True, "consume_kw": 1.0},
        }

        engine._update_power()
        state = engine.world_state["power_state"]

        assert "21,20" in state["powered_consumers"]
        assert "22,20" in state["unpowered_consumers"]
        assert 7 in state["disabled_priorities"]

    asyncio.run(run())


def test_battery_bridges_power_deficit_for_oxygen_generator() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        engine.world_state["machines"] = {
            "23,20": {
                "type": "Battery",
                "enabled": True,
                "capacity": 20.0,
                "stored": 10.0,
                "discharge_kw": 4.0,
                "charge_kw": 2.0,
            },
            "21,20": {"type": "OxygenGenerator", "enabled": True, "rate_per_tick": 2.0, "consume_kw": 2.0},
        }
        engine._update_power()
        state = engine.world_state["power_state"]

        assert "21,20" in state["powered_consumers"]
        assert state["battery_discharge"] > 0
        assert engine.world_state["machines"]["23,20"]["stored"] < 10.0

    asyncio.run(run())


def test_oxygen_generator_needs_power_to_produce_oxygen() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        for y in range(50):
            for x in range(50):
                engine.world_state["grid"][y][x] = "Wall"
        engine.world_state["grid"][10][10] = "Floor"
        engine.world_state["grid"][10][11] = "Floor"
        engine._recompute_compartments()
        engine.world_state["compartments"][0]["oxygen_percent"] = 40.0

        engine.world_state["machines"] = {
            "10,10": {"type": "OxygenGenerator", "enabled": True, "rate_per_tick": 5.0, "consume_kw": 3.0}
        }

        engine._update_power()
        engine._update_oxygen()
        without_power = engine.world_state["compartments"][0]["oxygen_percent"]

        engine.world_state["machines"]["11,10"] = {"type": "Reactor", "enabled": True, "generation_kw": 10.0}
        engine._update_power()
        engine._update_oxygen()
        with_power = engine.world_state["compartments"][0]["oxygen_percent"]

        assert without_power == 40.0
        assert with_power > without_power

    asyncio.run(run())


def test_reseal_after_breach_stabilizes_oxygen() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session_id = await engine.connect(ws)

        # 1) breach
        await engine.enqueue_command(
            session_id,
            ClientCommand(client_command_id="reseal-breach", type=CommandType.DECONSTRUCT, payload={"x": 14, "y": 20}),
        )
        await engine._execute_tick()

        oxygen_after_breach = engine.world_state["compartments"][0]["oxygen_percent"]
        await engine._execute_tick()
        oxygen_after_second_tick = engine.world_state["compartments"][0]["oxygen_percent"]
        assert oxygen_after_second_tick < oxygen_after_breach

        # 2) reseal with wall
        engine.last_action_at.pop(session_id, None)
        await engine.enqueue_command(
            session_id,
            ClientCommand(
                client_command_id="reseal-close",
                type=CommandType.BUILD,
                payload={"x": 14, "y": 20, "tile_type": "Wall"},
            ),
        )
        await engine._execute_tick()
        oxygen_after_reseal = engine.world_state["compartments"][0]["oxygen_percent"]

        # 3) with no generators, oxygen should stabilize (not keep leaking)
        await engine._execute_tick()
        oxygen_stable_1 = engine.world_state["compartments"][0]["oxygen_percent"]
        await engine._execute_tick()
        oxygen_stable_2 = engine.world_state["compartments"][0]["oxygen_percent"]

        assert oxygen_stable_1 == oxygen_after_reseal
        assert oxygen_stable_2 == oxygen_after_reseal

        # delta should include the reseal tile change
        deltas = [m for m in ws.messages if m.get("type") == "delta_tick"]
        assert any(
            any(change.get("x") == 14 and change.get("y") == 20 and change.get("after") == "Wall" for change in d["tile_changes"])
            for d in deltas
        )

    asyncio.run(run())



def test_power_topology_does_not_share_between_disconnected_compartments() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        for y in range(50):
            for x in range(50):
                engine.world_state["grid"][y][x] = "Wall"

        engine.world_state["grid"][10][10] = "Floor"
        engine.world_state["grid"][10][11] = "Floor"
        engine.world_state["grid"][20][20] = "Floor"
        engine.world_state["grid"][20][21] = "Floor"
        engine._recompute_compartments()

        engine.world_state["machines"] = {
            "10,10": {"type": "OxygenGenerator", "enabled": True, "rate_per_tick": 3.0, "consume_kw": 2.0},
            "11,10": {"type": "Reactor", "enabled": True, "generation_kw": 6.0},
            "20,20": {"type": "Light", "enabled": True, "consume_kw": 1.0},
        }

        engine._update_power()
        state = engine.world_state["power_state"]

        assert "10,10" in state["powered_consumers"]
        assert "20,20" in state["unpowered_consumers"]
        assert any(n["network_id"].startswith("compartment:") for n in state["networks"])

    asyncio.run(run())

def test_power_events_emitted_for_brownout_and_recovery() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        await engine.connect(ws)

        # force brownout: one consumer, no generation
        engine.world_state["machines"] = {
            "21,20": {"type": "Light", "enabled": True, "consume_kw": 1.0}
        }
        await engine._execute_tick()
        first_delta = [m for m in ws.messages if m.get("type") == "delta_tick"][-1]
        first_events = [e for e in first_delta.get("entity_changes", []) if e.get("type") == "power_event"]
        assert any(e.get("event") in {"brownout_started", "blackout_started"} for e in first_events)

        # recover power with solar
        engine.world_state["machines"]["20,20"] = {"type": "SolarPanel", "enabled": True, "generation_kw": 5.0}
        await engine._execute_tick()
        second_delta = [m for m in ws.messages if m.get("type") == "delta_tick"][-1]
        second_events = [e for e in second_delta.get("entity_changes", []) if e.get("type") == "power_event"]
        assert any(e.get("event") == "power_recovered" for e in second_events)

    asyncio.run(run())


def test_phase4_initializes_persistent_npc_roster() -> None:
    engine = SimulationEngine()
    npcs = engine.world_state.get("npcs", [])
    assert len(npcs) == 10
    assert engine.world_state.get("population") == 10
    assert all(1 <= int(npc.get("speed", 0)) <= 4 for npc in npcs)


def test_npc_moves_diagonally_toward_higher_oxygen() -> None:
    engine = SimulationEngine()
    # Keep one NPC only for deterministic assertion
    engine.world_state["npcs"] = [
        {
            "id": "npc-test",
            "name": "Test",
            "x": 5,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
        }
    ]

    # Seal world and create 2x2 room so (6,6) can be the best tile.
    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][5][5] = "Floor"
    engine.world_state["grid"][5][6] = "Floor"
    engine.world_state["grid"][6][5] = "Floor"
    engine.world_state["grid"][6][6] = "Floor"
    engine._recompute_compartments()

    cid = int(engine.world_state["compartment_index"]["5,5"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == cid:
            comp["oxygen_percent"] = 10.0

    # Build a second compartment on diagonal with better oxygen by splitting walls
    engine.world_state["grid"][6][6] = "Floor"
    # force oxygen preference at destination using same compartment by local tweak through helper-compatible map
    for comp in engine.world_state["compartments"]:
        comp["oxygen_percent"] = 10.0

    # Use direct method to choose diagonal by making one candidate's compartment richer.
    # Create isolated richer tile by recalculating with separation.
    engine.world_state["grid"][5][6] = "Wall"
    engine.world_state["grid"][6][5] = "Wall"
    engine._recompute_compartments()
    low = int(engine.world_state["compartment_index"]["5,5"])
    high = int(engine.world_state["compartment_index"]["6,6"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == low:
            comp["oxygen_percent"] = 10.0
        if int(comp["id"]) == high:
            comp["oxygen_percent"] = 90.0

    npc_changes, _, _ = engine._update_npcs()
    npc = engine.world_state["npcs"][0]
    assert (npc["x"], npc["y"]) == (6, 6)
    assert any(change.get("type") == "npc_move" for change in npc_changes)


def test_npc_death_appends_log_and_dispose_body_work_order() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-doom",
            "name": "Doom",
            "x": 8,
            "y": 8,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 8.0,
            "alive": True,
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][8][8] = "Floor"
    engine._recompute_compartments()
    comp_id = int(engine.world_state["compartment_index"]["8,8"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == comp_id:
            comp["oxygen_percent"] = 0.0

    engine.tick = 42
    npc_changes, work_order_changes, death_appends = engine._update_npcs()

    assert engine.world_state["npcs"][0]["alive"] is False
    assert engine.world_state["population"] == 0
    assert len(death_appends) == 1
    assert death_appends[0]["cause"] == "suffocation"
    assert "oxygen_percent_at_death" in death_appends[0]
    assert "compartment_id" in death_appends[0]
    assert len(work_order_changes) == 1
    assert work_order_changes[0]["work_order"]["work_type"] == "DisposeBody"
    assert "body_id" in work_order_changes[0]["work_order"]
    assert any(change.get("type") == "npc_death" for change in npc_changes)
    assert any(change.get("type") == "body_created" for change in npc_changes)


def test_npc_path_search_can_route_through_door_to_safer_compartment() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-route",
            "name": "Route",
            "x": 5,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][5][5] = "Floor"
    engine.world_state["grid"][5][6] = "Door"
    engine.world_state["door_states"]["6,5"] = {"open": True}
    engine.world_state["grid"][5][7] = "Floor"
    engine._recompute_compartments()

    left = int(engine.world_state["compartment_index"]["5,5"])
    right = int(engine.world_state["compartment_index"]["7,5"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == left:
            comp["oxygen_percent"] = 5.0
        if int(comp["id"]) == right:
            comp["oxygen_percent"] = 85.0

    engine._update_npcs()
    npc = engine.world_state["npcs"][0]
    assert (npc["x"], npc["y"]) == (6, 5)


def test_door_tile_oxygen_uses_adjacent_compartment_values() -> None:
    engine = SimulationEngine()
    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][5][5] = "Floor"
    engine.world_state["grid"][5][6] = "Door"
    engine.world_state["grid"][5][7] = "Floor"
    engine._recompute_compartments()

    left = int(engine.world_state["compartment_index"]["5,5"])
    right = int(engine.world_state["compartment_index"]["7,5"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == left:
            comp["oxygen_percent"] = 11.0
        if int(comp["id"]) == right:
            comp["oxygen_percent"] = 73.0

    oxygen = engine._oxygen_at_tile(6, 5, engine.world_state["compartment_index"], {int(c["id"]): c for c in engine.world_state["compartments"]})
    assert oxygen == 73.0


def test_dispose_body_work_order_gets_assigned_and_completed() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-worker",
            "name": "Worker",
            "x": 5,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "current_work_order_id": None,
        }
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-1",
            "work_type": "DisposeBody",
            "status": "Queued",
            "location": {"x": 7, "y": 5},
            "created_tick": 1,
            "progress": 0,
            "required_progress": 2,
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][5][5] = "Floor"
    engine.world_state["grid"][5][6] = "Floor"
    engine.world_state["grid"][5][7] = "Floor"
    engine._recompute_compartments()

    engine.tick = 10
    _, work_changes_1, _ = engine._update_npcs()
    order = engine.world_state["work_orders"][0]
    npc = engine.world_state["npcs"][0]
    assert order["status"] == "Assigned"
    assert npc["current_work_order_id"] == "wo-1"
    assert any(c.get("type") == "work_order_assigned" for c in work_changes_1)

    engine.tick = 11
    _, work_changes_2, _ = engine._update_npcs()
    order = engine.world_state["work_orders"][0]
    assert int(order["progress"]) >= 1
    assert any(c.get("type") == "work_order_progress" for c in work_changes_2)

    engine.tick = 12
    _, work_changes_3, _ = engine._update_npcs()
    order = engine.world_state["work_orders"][0]
    npc = engine.world_state["npcs"][0]
    assert order["status"] == "Completed"
    assert npc.get("current_work_order_id") is None
    assert any(c.get("type") == "work_order_completed" for c in work_changes_3)


def test_assigned_work_order_returns_to_queue_if_assignee_dies() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-fragile",
            "name": "Fragile",
            "x": 8,
            "y": 8,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 8.0,
            "alive": True,
            "current_work_order_id": "wo-dead",
        }
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-dead",
            "work_type": "DisposeBody",
            "status": "Assigned",
            "location": {"x": 8, "y": 8},
            "created_tick": 5,
            "progress": 0,
            "required_progress": 2,
            "assignee_npc_id": "npc-fragile",
            "assigned_tick": 9,
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][8][8] = "Floor"
    engine._recompute_compartments()
    cid = int(engine.world_state["compartment_index"]["8,8"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == cid:
            comp["oxygen_percent"] = 0.0

    engine.tick = 20
    _, work_changes, death_log = engine._update_npcs()

    order = engine.world_state["work_orders"][0]
    assert len(death_log) == 1
    assert order["status"] == "Queued"
    assert "assignee_npc_id" not in order
    assert any(c.get("type") == "work_order_unassigned" for c in work_changes)


def test_personality_does_not_override_survival_when_low_oxygen() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-safe-first",
            "name": "SafeFirst",
            "x": 5,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "diligent",
            "current_work_order_id": "wo-far",
            "needs": {"hunger": 0.0, "fatigue": 0.0},
        }
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-far",
            "work_type": "DisposeBody",
            "status": "Assigned",
            "location": {"x": 10, "y": 5},
            "created_tick": 1,
            "progress": 0,
            "required_progress": 2,
            "assignee_npc_id": "npc-safe-first",
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    # low-oxygen start + safe zone one step away through a door (opposite of work target direction)
    engine.world_state["grid"][5][5] = "Floor"
    engine.world_state["grid"][5][4] = "Door"
    engine.world_state["door_states"]["4,5"] = {"open": True}
    engine.world_state["grid"][5][3] = "Floor"
    engine.world_state["grid"][5][6] = "Floor"
    engine._recompute_compartments()

    start_comp = int(engine.world_state["compartment_index"]["5,5"])
    safe_comp = int(engine.world_state["compartment_index"]["3,5"])
    for comp in engine.world_state["compartments"]:
        cid = int(comp["id"])
        if cid == start_comp:
            comp["oxygen_percent"] = 5.0
        elif cid == safe_comp:
            comp["oxygen_percent"] = 90.0

    engine._update_npcs()
    npc = engine.world_state["npcs"][0]
    assert (npc["x"], npc["y"]) == (4, 5)


def test_diligent_personality_increases_work_progress_when_safe() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-diligent",
            "name": "Diligent",
            "x": 7,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "diligent",
            "current_work_order_id": "wo-d",
            "needs": {"hunger": 0.0, "fatigue": 0.0},
        }
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-d",
            "work_type": "DisposeBody",
            "status": "Assigned",
            "location": {"x": 7, "y": 5},
            "created_tick": 1,
            "progress": 0,
            "required_progress": 4,
            "assignee_npc_id": "npc-diligent",
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][5][7] = "Floor"
    engine._recompute_compartments()
    cid = int(engine.world_state["compartment_index"]["7,5"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == cid:
            comp["oxygen_percent"] = 90.0

    _, work_changes, _ = engine._update_npcs()
    order = engine.world_state["work_orders"][0]
    assert order["progress"] == 2
    assert any(c.get("type") == "work_order_progress" for c in work_changes)


def test_npc_needs_drift_and_emit_need_state() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-needs",
            "name": "Needs",
            "x": 4,
            "y": 4,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "baseline",
            "current_work_order_id": None,
            "needs": {"hunger": 74.9, "fatigue": 74.9},
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][4][4] = "Floor"
    engine._recompute_compartments()

    npc_changes, _, _ = engine._update_npcs()
    npc = engine.world_state["npcs"][0]
    assert npc["needs"]["hunger"] > 74.9
    assert npc["needs"]["fatigue"] > 74.9
    assert any(c.get("type") == "npc_need_state" for c in npc_changes)


def test_body_lifecycle_updates_on_dispose_work_completion() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-cleaner",
            "name": "Cleaner",
            "x": 7,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "baseline",
            "current_work_order_id": "wo-clean",
            "needs": {"hunger": 0.0, "fatigue": 0.0},
        }
    ]
    engine.world_state["bodies"] = [
        {
            "id": "body-1",
            "npc_id": "npc-dead",
            "name": "Dead",
            "location": {"x": 7, "y": 5},
            "created_tick": 1,
            "disposed": False,
            "disposed_tick": None,
            "disposed_by_npc_id": None,
        }
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-clean",
            "work_type": "DisposeBody",
            "status": "Assigned",
            "location": {"x": 7, "y": 5},
            "body_id": "body-1",
            "created_tick": 1,
            "progress": 1,
            "required_progress": 2,
            "assignee_npc_id": "npc-cleaner",
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][5][7] = "Floor"
    engine._recompute_compartments()
    cid = int(engine.world_state["compartment_index"]["7,5"])
    for comp in engine.world_state["compartments"]:
        if int(comp["id"]) == cid:
            comp["oxygen_percent"] = 90.0

    engine.tick = 50
    npc_changes, work_changes, _ = engine._update_npcs()

    body = engine.world_state["bodies"][0]
    order = engine.world_state["work_orders"][0]
    assert body["disposed"] is True
    assert body["disposed_tick"] == 50
    assert body["disposed_by_npc_id"] == "npc-cleaner"
    assert order["status"] == "Completed"
    assert any(c.get("type") == "body_disposed" for c in npc_changes)
    assert any(c.get("type") == "work_order_completed" and c.get("disposed_body_id") == "body-1" for c in work_changes)


def test_runtime_status_reports_active_body_count() -> None:
    engine = SimulationEngine()
    engine.world_state["bodies"] = [
        {"id": "b1", "disposed": False},
        {"id": "b2", "disposed": True},
        {"id": "b3", "disposed": False},
    ]
    status = engine.runtime_status()
    assert status["active_body_count"] == 2


def test_task_aware_assignment_prefers_nearest_reachable_dispose_order() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-assign",
            "name": "Assign",
            "x": 5,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "baseline",
            "current_work_order_id": None,
            "needs": {"hunger": 0.0, "fatigue": 0.0},
        }
    ]
    engine.world_state["work_orders"] = [
        {"id": "wo-far", "work_type": "DisposeBody", "status": "Queued", "location": {"x": 15, "y": 5}, "created_tick": 1, "progress": 0, "required_progress": 2},
        {"id": "wo-near", "work_type": "DisposeBody", "status": "Queued", "location": {"x": 7, "y": 5}, "created_tick": 2, "progress": 0, "required_progress": 2},
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    for x in range(5, 16):
        engine.world_state["grid"][5][x] = "Floor"
    engine._recompute_compartments()

    engine.tick = 30
    _, work_changes, _ = engine._update_npcs()
    npc = engine.world_state["npcs"][0]
    assert npc["current_work_order_id"] == "wo-near"
    assert any(c.get("type") == "work_order_assigned" and c.get("work_order_id") == "wo-near" for c in work_changes)


def test_assigned_order_requeues_when_target_becomes_unreachable() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-path",
            "name": "Path",
            "x": 5,
            "y": 5,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "baseline",
            "current_work_order_id": "wo-blocked",
            "needs": {"hunger": 0.0, "fatigue": 0.0},
        }
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-blocked",
            "work_type": "DisposeBody",
            "status": "Assigned",
            "location": {"x": 7, "y": 5},
            "body_id": "body-b",
            "created_tick": 1,
            "progress": 0,
            "required_progress": 2,
            "assignee_npc_id": "npc-path",
        }
    ]

    for y in range(50):
        for x in range(50):
            engine.world_state["grid"][y][x] = "Wall"
    engine.world_state["grid"][5][5] = "Floor"
    engine.world_state["grid"][5][7] = "Floor"
    # no connecting walkable tile between (5,5) and (7,5) => unreachable
    engine._recompute_compartments()

    _, work_changes, _ = engine._update_npcs()
    order = engine.world_state["work_orders"][0]
    npc = engine.world_state["npcs"][0]
    assert order["status"] == "Queued"
    assert npc.get("current_work_order_id") is None
    assert any(c.get("type") == "work_order_unassigned" and c.get("reason") == "path_unreachable" for c in work_changes)


def test_default_world_has_enclosed_station_and_vacuum_exterior() -> None:
    engine = SimulationEngine()
    grid = engine.world_state["grid"]

    assert grid[0][0] == "Vacuum"
    assert grid[14][14] == "Wall"
    assert grid[20][20] == "Floor"
    assert grid[35][35] == "Wall"


def test_default_npc_spawns_are_inside_station_walkable_tiles() -> None:
    engine = SimulationEngine()
    grid = engine.world_state["grid"]
    for npc in engine.world_state.get("npcs", []):
        x, y = int(npc["x"]), int(npc["y"])
        assert grid[y][x] in {"Floor", "Door", "Airlock"}
        assert 14 < x < 35
        assert 14 < y < 35


def test_create_work_order_command_creates_order_and_delta_change() -> None:
    async def run() -> None:
        engine = SimulationEngine()
        ws = FakeWebSocket()
        session = await engine.connect(ws)

        cmd = ClientCommand(
            client_command_id="wo-cmd-1",
            type=CommandType.CREATE_WORK_ORDER,
            payload={
                "work_type": "MineIce",
                "location": {"x": 20, "y": 20},
                "metadata": {"item_type": "IceChunk", "destination": {"x": 19, "y": 19}},
            },
        )
        ack = await engine.enqueue_command(session, cmd)
        assert ack.result == CommandResult.QUEUED

        await engine._execute_tick()
        assert any(order.get("work_type") == "MineIce" for order in engine.world_state.get("work_orders", []))

        last_delta = [m for m in ws.messages if m.get("type") == "delta_tick"][-1]
        assert any(change.get("type") == "work_order_created_by_command" for change in last_delta.get("work_order_changes", []))

    asyncio.run(run())


def test_phase5_foundation_mine_ice_creates_item_and_haul_order() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-miner",
            "name": "Miner",
            "x": 20,
            "y": 20,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "baseline",
            "current_work_order_id": "wo-mine-1",
            "needs": {"hunger": 0.0, "fatigue": 0.0},
        }
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-mine-1",
            "work_type": "MineIce",
https://github.com/code-smithy/MadStation/pull/27/conflict?name=tests%252Ftest_engine.py&ancestor_oid=d30e8e0eaedfd7af19a1aa0c54fbdfddd3c27d36&base_oid=59108e43729f19dd5793b6609c7a7e4446d09da3&head_oid=b97944e5c6cb643df8a1a7b70ceb2d23046c7268            "status": "Assigned",
            "location": {"x": 20, "y": 20},
            "created_tick": 1,
            "progress": 1,
            "required_progress": 2,
            "assignee_npc_id": "npc-miner",
            "item_type": "IceChunk",
        }
    ]

    npc_changes, work_changes, _ = engine._update_npcs()

    assert any(change.get("type") == "item_created" for change in npc_changes)
    assert any(order.get("work_type") == "HaulItem" for order in engine.world_state.get("work_orders", []))
    assert any(change.get("type") == "work_order_created_auto" for change in work_changes)


def test_phase5_foundation_haul_item_stores_into_storage_inventory() -> None:
    engine = SimulationEngine()
    engine.world_state["npcs"] = [
        {
            "id": "npc-hauler",
            "name": "Hauler",
            "x": 19,
            "y": 19,
            "speed": 1,
            "move_accumulator": 0.0,
            "health": 100.0,
            "alive": True,
            "personality": "baseline",
            "current_work_order_id": "wo-haul-1",
            "needs": {"hunger": 0.0, "fatigue": 0.0},
        }
    ]
    engine.world_state["items"] = [
        {
            "id": "item-1",
            "item_type": "IceChunk",
            "location": {"x": 19, "y": 19},
            "holder_npc_id": "npc-hauler",
            "created_tick": 1,
        }
    ]
    engine.world_state["storages"] = [
        {"id": "storage-main", "location": {"x": 19, "y": 19}, "inventory": []}
    ]
    engine.world_state["work_orders"] = [
        {
            "id": "wo-haul-1",
            "work_type": "HaulItem",
            "status": "Assigned",
            "location": {"x": 19, "y": 19},
            "destination": {"x": 19, "y": 19},
            "item_id": "item-1",
            "created_tick": 1,
            "progress": 1,
            "required_progress": 2,
            "assignee_npc_id": "npc-hauler",
        }
    ]

    _, work_changes, _ = engine._update_npcs()

    order = engine.world_state["work_orders"][0]
    item = engine.world_state["items"][0]
    storage = engine.world_state["storages"][0]
    assert order["status"] == "Completed"
    assert item["holder_npc_id"] is None
    assert "item-1" in storage["inventory"]
    assert any(change.get("type") == "item_stored" for change in work_changes)

import asyncio

import pytest

from madstation.app import app, frontend_index, health, status, websocket_usage, world


def test_health_status_world_and_ws_usage_handlers() -> None:
    async def run() -> None:
        page = await frontend_index()
        assert page.status_code == 200
        body = page.body.decode('utf-8')
        assert 'MadStation Frontend MVP' in body
        assert 'Send Build' in body
        assert 'ws://127.0.0.1:8000/ws' in body
        assert 'NPC' in body
        assert 'View Mode' in body
        assert 'Click a tile to inspect.' in body
        assert 'Power Network' in body
        assert 'Temperature Heat' in body
        assert 'Temp Cold' in body
        assert 'Temp Hot' in body
        assert 'World Stats' in body
        assert 'thermal_avg=' in body
        assert 'temperature=' in body
        assert 'Severity' in body
        assert 'Filter text' in body
        assert 'Machine Quick Actions' in body
        assert 'Place Machine at X/Y' in body
        assert 'Cooler' in body
        assert 'Item ID (for Haul/Refine/Feed)' in body
        assert 'Destination X/Y (Haul)' in body
        assert 'Generator X/Y (Feed)' in body
        assert 'Highlight NPCs' in body
        assert 'Highlight Work Orders' in body
        assert 'WO Queued' in body
        assert 'WO Active' in body

        health_payload = await health()
        assert health_payload == {'status': 'ok'}

        status_payload = await status()
        assert 'tick' in status_payload
        assert 'compartment_count' in status_payload
        assert 'machine_count' in status_payload
        assert 'thermal_avg_temp_c' in status_payload

        world_payload = await world()
        assert 'tick' in world_payload
        assert 'world' in world_payload
        assert 'grid' in world_payload['world']
        assert 'temperature_grid' in world_payload['world']

        ws_usage = await websocket_usage()
        assert 'detail' in ws_usage
        assert 'example' in ws_usage

    asyncio.run(run())


def test_ws_snapshot_and_invalid_payload_ack() -> None:
    pytest.importorskip('httpx')
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        with client.websocket_connect('/ws') as ws:
            first = ws.receive_json()
            assert first.get('type') == 'snapshot_full'

            ws.send_json({
                'client_command_id': 'invalid-build-1',
                'type': 'Build',
                'payload': {'x': 'bad', 'y': 1},
            })

            ack = None
            for _ in range(6):
                message = ws.receive_json()
                if message.get('client_command_id') == 'invalid-build-1':
                    ack = message
                    break

            assert ack is not None
            assert ack['result'] == 'INVALID_PAYLOAD'

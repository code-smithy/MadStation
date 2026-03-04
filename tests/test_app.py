import asyncio

from madstation.app import frontend_index, health, status, websocket_usage, world


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
        assert 'World Stats' in body
        assert 'Severity' in body
        assert 'Filter text' in body
        assert 'Machine Quick Actions' in body
        assert 'Place Machine at X/Y' in body
        assert 'Item ID (for Haul/Refine/Feed)' in body
        assert 'Destination X/Y (Haul)' in body
        assert 'Generator X/Y (Feed)' in body

        health_payload = await health()
        assert health_payload == {'status': 'ok'}

        status_payload = await status()
        assert 'tick' in status_payload
        assert 'compartment_count' in status_payload
        assert 'machine_count' in status_payload

        world_payload = await world()
        assert 'tick' in world_payload
        assert 'world' in world_payload
        assert 'grid' in world_payload['world']

        ws_usage = await websocket_usage()
        assert 'detail' in ws_usage
        assert 'example' in ws_usage

    asyncio.run(run())

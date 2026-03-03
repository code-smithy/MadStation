import asyncio

from madstation.app import health, status, websocket_usage, world


def test_health_status_world_and_ws_usage_handlers() -> None:
    async def run() -> None:
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

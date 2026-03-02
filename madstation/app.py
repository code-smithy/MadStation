from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from madstation.engine import SimulationEngine
from madstation.protocol import ClientCommand

engine = SimulationEngine()


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio

    task = asyncio.create_task(engine.run())
    yield
    engine.stop()
    await task


app = FastAPI(title="MadStation", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    session_id = await engine.connect(websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            command = ClientCommand.model_validate(payload)
            ack = await engine.enqueue_command(session_id, command)
            await websocket.send_json(ack.model_dump())
    except WebSocketDisconnect:
        engine.disconnect(session_id)

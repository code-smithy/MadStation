from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from madstation.engine import SimulationEngine
from madstation.protocol import ClientCommand, CommandAck, CommandResult

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


@app.get("/status")
async def status() -> dict[str, int]:
    return engine.runtime_status()




@app.get("/ws")
async def websocket_usage() -> dict[str, str]:
    return {
        "detail": "Use WebSocket upgrade on /ws (ws://...), not HTTP GET.",
        "example": "new WebSocket(\"ws://127.0.0.1:8000/ws\")",
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    session_id = await engine.connect(websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            try:
                command = ClientCommand.model_validate(payload)
            except Exception:
                invalid_ack = CommandAck(
                    client_command_id=str(payload.get("client_command_id", "")),
                    result=CommandResult.INVALID_PAYLOAD,
                    tick=engine.tick,
                )
                await websocket.send_json(invalid_ack.model_dump())
                continue

            ack = await engine.enqueue_command(session_id, command)
            await websocket.send_json(ack.model_dump())
    except WebSocketDisconnect:
        engine.disconnect(session_id)

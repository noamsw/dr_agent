from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from app.agent import run_agent_stream
from starlette.websockets import WebSocketDisconnect
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True}

@app.websocket("/ws")
async def ws_chat(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            async for event in run_agent_stream(msg):
                await ws.send_json(event)
    except WebSocketDisconnect:
        # client closed the connection
        return
    except Exception as e:
        # IMPORTANT: show the real error instead of silent close
        print("WS ERROR:", repr(e))
        try:
            await ws.send_json({"type": "error", "message": f"Server error: {repr(e)}"})
        except Exception:
            pass
        await ws.close(code=1011)

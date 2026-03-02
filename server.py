from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import json
import asyncio
import os
import uuid
from runner import ProcessRunner

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECTS_DIR = os.path.join(os.path.dirname(__file__), "projects")
if not os.path.exists(PROJECTS_DIR):
    os.makedirs(PROJECTS_DIR)

active_runners = {}

@app.websocket("/ws/run")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    project_id = str(uuid.uuid4())
    runner = ProcessRunner(project_id, PROJECTS_DIR)
    active_runners[project_id] = runner
    
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            files = payload.get("files", [])
            
            if not files:
                await websocket.send_text(json.dumps({"type": "error", "message": "No files provided"}))
                continue

            async def log_callback(msg: str):
                await websocket.send_text(json.dumps({"type": "log", "content": msg}))

            await log_callback(f"✦ Preparing environment for project {project_id}...\n")
            await runner.setup(files)
            
            await log_callback("✦ Synchronizing dependencies...\n")
            await runner.install_dependencies(log_callback)
            
            await log_callback("🚀 Launching application...\n")
            await runner.run(log_callback)
            
            # Keep connection open and monitor for timeout or closure
            # In a real production app, we'd have more complex process management here
            try:
                # Wait for disconnect or some signal from client
                while True:
                    await asyncio.wait_for(websocket.receive_text(), timeout=3600)
            except asyncio.TimeoutError:
                await log_callback("\n[System] Session heartbeat timeout (1 hour).\n")

    except WebSocketDisconnect:
        print(f"Client disconnected: {project_id}")
    except Exception as e:
        print(f"Error: {e}")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except:
            pass
    finally:
        await runner.stop()
        # runner.cleanup() # Optional: keep files for debugging or clean them up
        if project_id in active_runners:
            del active_runners[project_id]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

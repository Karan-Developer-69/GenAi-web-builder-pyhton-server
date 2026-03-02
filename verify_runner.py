import asyncio
import websockets
import json

async def test_runner():
    uri = "ws://localhost:8001/ws/run"
    async with websockets.connect(uri) as websocket:
        code = """
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return "Hello from Backend Python Runner!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
"""
        payload = {
            "code": code,
            "requirements": "flask"
        }
        
        print("Sending payload...")
        await websocket.send(json.dumps(payload))
        
        print("Waiting for logs...")
        try:
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                
                if data["type"] == "log":
                    print(f"LOG: {data['content']}", end="")
                    # Check if Flask started
                    if "Running on http" in data["content"]:
                        print("\n[SUCCESS] Flask is running!")
                        break
                elif data["type"] == "error":
                    print(f"ERROR: {data['message']}")
                    break
        except Exception as e:
            print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_runner())

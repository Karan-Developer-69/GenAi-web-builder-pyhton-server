import asyncio
import os
import subprocess
import sys
import uuid
import venv
import shutil
from typing import Callable, Optional, Awaitable

class ProcessRunner:
    def __init__(self, project_id: str, base_dir: str):
        self.project_id = project_id
        self.project_path = os.path.join(base_dir, project_id)
        self.venv_path = os.path.join(self.project_path, "venv")
        self.process: Optional[asyncio.subprocess.Process] = None
        self.is_running = False

    async def setup(self, files: list[dict]):
        if not os.path.exists(self.project_path):
            os.makedirs(self.project_path)

        for file_info in files:
            file_path = file_info.get("path")
            content = file_info.get("content", "")
            
            if not file_path:
                continue

            full_path = os.path.join(self.project_path, file_path)
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, "w") as f:
                f.write(content)

        # Create venv if not exists
        if not os.path.exists(self.venv_path):
            venv.create(self.venv_path, with_pip=True)

    async def install_dependencies(self, log_callback: Callable[[str], Awaitable[None]]):
        req_file = os.path.join(self.project_path, "requirements.txt")
        if not os.path.exists(req_file):
            return

        pip_path = os.path.join(self.venv_path, "bin", "pip")
        if sys.platform == "win32":
            pip_path = os.path.join(self.venv_path, "Scripts", "pip.exe")

        cmd = [pip_path, "install", "-r", req_file]
        await log_callback(f"Running: {' '.join(cmd)}\n")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        async def stream_output(stream, prefix=""):
            while True:
                line = await stream.readline()
                if not line:
                    break
                await log_callback(line.decode())

        await asyncio.gather(
            stream_output(process.stdout),
            stream_output(process.stderr)
        )
        await process.wait()

    def detect_command(self):
        # Look for entry points in the project path
        python_path = os.path.join(self.venv_path, "bin", "python")
        if sys.platform == "win32":
            python_path = os.path.join(self.venv_path, "Scripts", "python.exe")

        entry_point = "app.py"
        if os.path.exists(os.path.join(self.project_path, "main.py")):
            entry_point = "main.py"
        
        with open(os.path.join(self.project_path, entry_point), "r") as f:
            code = f.read()

        if "FastAPI" in code:
            uvicorn_path = os.path.join(self.venv_path, "bin", "uvicorn")
            if sys.platform == "win32":
                uvicorn_path = os.path.join(self.venv_path, "Scripts", "uvicorn.exe")
            # Handle main vs app module
            module = entry_point.replace(".py", "")
            return [uvicorn_path, f"{module}:app", "--host", "0.0.0.0", "--port", "8000"]
        
        if "Flask(" in code:
            return [python_path, entry_point]
        
        if "django" in code.lower():
            return [python_path, "manage.py", "runserver", "0.0.0.0:8000"]

        return [python_path, entry_point]

    async def run(self, log_callback: Callable[[str], Awaitable[None]]):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except:
                pass

        cmd = self.detect_command()
        await log_callback(f"Starting process: {' '.join(cmd)}\n")

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.project_path
        )
        self.is_running = True

        async def stream_output(stream):
            while True:
                line = await stream.readline()
                if not line:
                    break
                await log_callback(line.decode())

        # Run streams in background
        asyncio.create_task(stream_output(self.process.stdout))
        asyncio.create_task(stream_output(self.process.stderr))

    async def stop(self):
        if self.process:
            try:
                self.process.terminate()
                await self.process.wait()
            except ProcessLookupError:
                pass
            except Exception as e:
                print(f"Error stopping process: {e}")
            self.process = None
        self.is_running = False

    def cleanup(self):
        if os.path.exists(self.project_path):
            shutil.rmtree(self.project_path)

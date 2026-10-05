"""
Radar EW Facility Workshop Inventory System - Process Supervisor / Watchdog Handler
This handler ensures the FastAPI / Uvicorn server runs continuously ("forever").
If the server crashes or exits unexpectedly, it automatically restarts it.
"""
import sys
import os
import time
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
PYTHON_EXE = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
HOST = os.environ.get("APP_HOST", "127.0.0.1")
PORT = os.environ.get("APP_PORT", "8000")
LOG_FILE = os.path.join(BASE_DIR, "server_supervisor.log")

def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] [Handler] {msg}"
    print(formatted, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass

def run_server_forever():
    log("==========================================================")
    log("Radar EW Inventory System - Auto-Restart Supervisor Active")
    log(f"Target: http://{HOST}:{PORT}")
    log(f"Python: {PYTHON_EXE}")
    log("Press Ctrl+C in this console to gracefully stop.")
    log("==========================================================")

    restart_count = 0
    cmd = [
        PYTHON_EXE,
        "-m", "uvicorn",
        "app:app",
        "--host", HOST,
        "--port", PORT,
        "--reload"
    ]

    while True:
        log(f"Launching server process (Session #{restart_count + 1})...")
        start_time = time.time()
        process = None

        try:
            process = subprocess.Popen(cmd, cwd=BASE_DIR)
            process.wait()
            exit_code = process.returncode
        except KeyboardInterrupt:
            log("Received shutdown request (Ctrl+C). Terminating server...")
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            log("Supervisor stopped by user. Goodbye!")
            break
        except Exception as e:
            log(f"Supervisor error: {e}")
            exit_code = -1

        uptime = time.time() - start_time
        log(f"Server exited with code {exit_code} (uptime: {int(uptime)}s).")

        # Throttling if crash happens too quickly to avoid high CPU loop
        if uptime < 3:
            log("Short uptime detected. Pausing 3 seconds before restart...")
            time.sleep(3)
        else:
            time.sleep(1)

        restart_count += 1
        log(f"Restarting server automatically (total restarts: {restart_count})...")

if __name__ == "__main__":
    run_server_forever()

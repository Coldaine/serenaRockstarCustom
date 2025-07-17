# Serena Workspace Isolation: The Instance Manager Pattern

## 1. Objective

This document outlines a simple and robust architecture to provide workspace isolation for multiple concurrent Serena clients. The goal is to replace a complex, stateful "Isolation Bridge" with a lightweight, stateless **Instance Manager**.

This pattern avoids the complexity of proxying network traffic. Instead, the manager's sole responsibility is to launch and terminate dedicated `serena-mcp-server` processes, one for each client session.

## 2. Core Concept

The fundamental flaw of a proxy-based bridge is that it sits in the middle of the communication, adding complexity and a central point of failure.

**The Instance Manager pattern is different:**

1.  A client requests a new session from the Instance Manager.
2.  The Manager starts a brand-new, independent `serena-mcp-server` process that listens on a unique, OS-assigned network port.
3.  The Manager returns the `host:port` of the new process to the client.
4.  The client disconnects from the Manager and connects **directly** to its dedicated Serena process.

This provides perfect OS-level process isolation with minimal architectural complexity.

## 3. Implementation Plan & Task List

### Task 1: Modify `serena-mcp-server` to Report its Port

The most robust way for the manager to know which port a new process is using is for the process to write it to a file. This is more reliable than parsing `stdout`.

**File to Edit:** `src/serena/mcp.py`

**Logic:**
1.  Add a new `--port-file` command-line option.
2.  After the server starts, if this option was provided, write the actual port number to the specified file.

```python
# In src/serena/mcp.py, find the start_mcp_server function and add the new option:

@click.command()
@click.option(
    "--port-file",
    "port_file",
    type=click.Path(),
    default=None,
    help="If specified, write the chosen port to this file after the server starts.",
)
# ... (add this near the other click.option decorators)
def start_mcp_server(
    project: str | None,
    project_file_arg: str | None,
    context: str = DEFAULT_CONTEXT,
    modes: tuple[str, ...] = DEFAULT_MODES,
    transport: Literal["stdio", "sse"] = "stdio",
    host: str = "0.0.0.0",
    port: int = 8000,
    port_file: str | None = None, # Add the new parameter here
    # ... other parameters
) -> None:
    # ... (existing code)

    mcp_server = mcp_factory.create_mcp_server(
        host=host,
        port=port,
        # ... other parameters
    )

    # --- ADD THIS LOGIC ---
    # After the server is created but before it runs, we can get the final port.
    # The server object will have the actual port if 'port=0' was used.
    actual_port = mcp_server.settings.port
    if port_file:
        try:
            Path(port_file).write_text(str(actual_port))
            log.info(f"Wrote server port {actual_port} to {port_file}")
        except Exception as e:
            log.error(f"Failed to write port to {port_file}: {e}")
    # --- END OF ADDED LOGIC ---

    log.info(f"Starting MCP server on port {actual_port}...")
    mcp_server.run(transport=transport)

```

### Task 2: Create the `instance_manager.py`

This is the core of the new architecture. It's a standalone service that exposes a simple API to start and stop Serena sessions. We'll use Flask for the API and `psutil` for robust process management.

**New File:** `scripts/instance_manager.py`

```python
# scripts/instance_manager.py
import atexit
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict

import psutil
from flask import Flask, jsonify, request

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app = Flask(__name__)

# --- State Management ---
# Dictionary to store active sessions: {session_id (pid): process_object}
active_sessions: Dict[int, psutil.Process] = {}

def cleanup_all_sessions():
    """Gracefully terminate all managed Serena processes on exit."""
    logging.info(f"Shutting down {len(active_sessions)} active session(s)...")
    for pid, process in list(active_sessions.items()):
        try:
            logging.info(f"Terminating process tree for session {pid}...")
            # Kill all children of the process first, then the process itself
            for child in process.children(recursive=True):
                child.kill()
            process.kill()
            logging.info(f"Session {pid} terminated.")
        except psutil.NoSuchProcess:
            logging.warning(f"Session {pid} was already gone.")
        except Exception as e:
            logging.error(f"Error terminating session {pid}: {e}")
    active_sessions.clear()

# Register cleanup to run when the manager script is terminated
atexit.register(cleanup_all_sessions)


# --- API Endpoints ---
@app.route("/request-session", methods=["POST"])
def request_session():
    """
    Starts a new serena-mcp-server process for a given project.
    JSON Body: {"project_path": "/path/to/project"}
    Returns: {"session_id": int, "host": str, "port": int}
    """
    data = request.get_json()
    project_path = data.get("project_path")
    if not project_path or not Path(project_path).is_dir():
        return jsonify({"error": "Invalid or missing 'project_path'"}), 400

    # Create a temporary file to get the port number back from the child process
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".port") as tmp_port_file:
        port_file_path = tmp_port_file.name

    try:
        cmd = [
            "serena-mcp-server",
            "--project", project_path,
            "--transport", "sse",
            "--port", "0",  # Let the OS choose a free port
            "--port-file", port_file_path,
        ]

        # Launch the process. Note: We don't use Popen's text=True or pipes here,
        # letting it run fully detached from the manager's stdio.
        proc = subprocess.Popen(cmd)
        psutil_proc = psutil.Process(proc.pid)
        logging.info(f"Launched new Serena session for '{project_path}' with PID {proc.pid}")

        # Wait for the port file to be created and read the port
        port = None
        for _ in range(100):  # Timeout after 10 seconds
            if Path(port_file_path).exists() and Path(port_file_path).stat().st_size > 0:
                port = int(Path(port_file_path).read_text())
                break
            time.sleep(0.1)

        if port is None:
            raise RuntimeError("Server process failed to report its port in time.")

        # Success! Store the session and return the details.
        active_sessions[proc.pid] = psutil_proc
        logging.info(f"Session {proc.pid} is active on port {port}")
        return jsonify({
            "session_id": proc.pid,
            "host": "127.0.0.1",
            "port": port
        }), 201

    except Exception as e:
        logging.error(f"Failed to start Serena session: {e}")
        # Ensure cleanup if something went wrong
        if 'proc' in locals() and psutil.pid_exists(proc.pid):
            psutil_proc.kill()
        return jsonify({"error": str(e)}), 500
    finally:
        # Clean up the temporary port file
        Path(port_file_path).unlink(missing_ok=True)


@app.route("/release-session", methods=["POST"])
def release_session():
    """
    Terminates a Serena process by its session_id (PID).
    JSON Body: {"session_id": 12345}
    """
    data = request.get_json()
    session_id = data.get("session_id")
    if not session_id or session_id not in active_sessions:
        return jsonify({"error": "Invalid or missing 'session_id'"}), 404

    try:
        process = active_sessions.pop(session_id)
        logging.info(f"Received request to terminate session {session_id}...")
        for child in process.children(recursive=True):
            child.kill()
        process.kill()
        logging.info(f"Session {session_id} terminated successfully.")
        return jsonify({"status": "terminated", "session_id": session_id}), 200
    except psutil.NoSuchProcess:
        logging.warning(f"Release request for session {session_id}, but it was already gone.")
        return jsonify({"status": "already_gone", "session_id": session_id}), 200
    except Exception as e:
        logging.error(f"Error terminating session {session_id}: {e}")
        # Put it back in the dict if termination failed
        active_sessions[session_id] = process
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Add dependencies: pip install Flask psutil
    app.run(host="127.0.0.1", port=8888)

```

### Task 3: Update Client-Side Logic

Your client application (e.g., the VS Code extension) needs to be updated to use the new manager.

1.  **On Startup/New Workspace:**
    *   Instead of connecting directly, the client makes a `POST` request to the Instance Manager's `/request-session` endpoint (e.g., `http://127.0.0.1:8888/request-session`) with the project's absolute path.
    *   It receives a `session_id` and `port` in the response.
    *   It then establishes its MCP connection directly to `127.0.0.1:{port}`.
2.  **On Shutdown/Workspace Close:**
    *   The client makes a `POST` request to `/release-session` with the `session_id` it received earlier. This gracefully cleans up the server process.

## 4. Detailed Test Plan

### Can a client be simulated adequately?

**Yes, absolutely.** The MCP server (with SSE transport) communicates over standard HTTP. You can use simple command-line tools like `curl` or a Python script with the `requests` library to perfectly simulate a client for testing purposes.

### Test Plan

#### Level 1: Unit Tests (for `instance_manager.py`)

**Goal:** Test the manager's logic in isolation without actually starting processes.
**Tools:** `pytest`, `unittest.mock`

1.  **Test `request_session` Success:**
    *   Mock `subprocess.Popen`, `psutil.Process`, and `tempfile.NamedTemporaryFile`.
    *   Make the mocked `Popen` object have a specific `pid`.
    *   Simulate the port file being created by mocking `pathlib.Path`.
    *   Assert that the function returns the correct `session_id` and `port`.
    *   Assert that the new process PID is added to the `active_sessions` dictionary.
2.  **Test `request_session` Failure:**
    *   Simulate the server process failing to start (e.g., `subprocess.Popen` raises an exception).
    *   Simulate the process never writing its port file (timeout).
    *   Assert that a 500 error is returned and that no new session is left in `active_sessions`.
3.  **Test `release_session`:**
    *   Add a mock process to `active_sessions`.
    *   Call `/release-session` with the correct `session_id`.
    *   Assert that the mock process's `kill()` method was called.
    *   Assert that the `session_id` is removed from `active_sessions`.

#### Level 2: Integration Tests (Manager + Real Serena Process)

**Goal:** Verify that the manager can correctly launch and communicate with a real `serena-mcp-server` process.

**Test Script (`test_manager_integration.py`):**

```python
import requests
import time
import os

MANAGER_URL = "http://127.0.0.1:8888"
# Use the current project as the test subject
PROJECT_PATH = os.path.abspath(".") 

def test_full_session_lifecycle():
    # 1. Request a new session
    response = requests.post(f"{MANAGER_URL}/request-session", json={"project_path": PROJECT_PATH})
    assert response.status_code == 201
    data = response.json()
    session_id = data["session_id"]
    host = data["host"]
    port = data["port"]
    print(f"Obtained session {session_id} on {host}:{port}")

    # 2. Verify the Serena process is actually running and listening
    # Give it a moment to fully initialize
    time.sleep(2)
    serena_url = f"http://{host}:{port}"
    
    # This is the key: simulate a real tool call with curl or requests
    # We'll call the 'get_current_config' tool, which requires no arguments.
    mcp_tool_call = {
        "tool_name": "get_current_config",
        "arguments": {}
    }
    
    try:
        # The MCP server expects a POST to /tool with the tool call payload
        tool_response = requests.post(f"{serena_url}/tool", json=mcp_tool_call, timeout=10)
        assert tool_response.status_code == 200
        tool_result = tool_response.json()
        assert "Current configuration:" in tool_result["stdout"]
        print("Successfully called a tool on the dedicated Serena instance.")
    except requests.RequestException as e:
        assert False, f"Failed to connect to or call tool on the new Serena instance: {e}"

    # 3. Release the session
    response = requests.post(f"{MANAGER_URL}/release-session", json={"session_id": session_id})
    assert response.status_code == 200
    print(f"Successfully released session {session_id}")

    # 4. Verify the process is gone
    time.sleep(1)
    try:
        # This connection should now fail
        requests.get(serena_url, timeout=2)
        assert False, "Serena process should be terminated, but it is still responding."
    except requests.ConnectionError:
        print("Verified that the Serena process is no longer listening.")
        pass # This is the expected outcome
```

**Using `curl` for manual testing:**

You can perform the same tool call from your command line to verify a running instance:

```bash
# Step 1: Request the session
curl -X POST -H "Content-Type: application/json" -d '{"project_path": "E:\\_ProjectBroadside\\serena"}' http://127.0.0.1:8888/request-session
# This will return something like: {"host":"127.0.0.1","port":54321,"session_id":12345}

# Step 2: Use the port to call a tool
PORT=54321 # Use the port from the previous command
curl -X POST -H "Content-Type: application/json" \
     -d '{"tool_name": "get_current_config", "arguments": {}}' \
     http://127.0.0.1:$PORT/tool

# Step 3: Release the session
SESSION_ID=12345 # Use the session_id from the first command
curl -X POST -H "Content-Type: application/json" -d '{"session_id": '$SESSION_ID'}' http://127.0.0.1:8888/release-session
```

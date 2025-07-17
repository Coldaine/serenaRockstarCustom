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

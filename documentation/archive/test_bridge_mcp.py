import subprocess
import json
import sys
import time

# Start the bridge
process = subprocess.Popen(
    ["uv", "run", "serena-workspace-isolation-bridge", "--debug"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=0
)

# Give it time to start
time.sleep(2)

# Send initialize message
init_msg = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"}
    }
}

print("Sending initialize message...")
process.stdin.write(json.dumps(init_msg) + "\n")
process.stdin.flush()

# Try to read response
try:
    response = process.stdout.readline()
    print(f"Response: {response}")
except Exception as e:
    print(f"Error reading response: {e}")

# Clean up
process.terminate()
process.wait()
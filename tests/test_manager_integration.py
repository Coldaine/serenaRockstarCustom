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

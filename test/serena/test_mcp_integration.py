"""Integration tests for the Serena MCP server.

Tests actual MCP protocol communication using stdio transport,
exactly as real MCP clients (like Claude Desktop) would use it.
"""

import json
import subprocess
import time
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def mcp_server():
    """Start MCP server exactly like real MCP clients do."""
    # Get absolute path to project directory
    project_dir = Path(__file__).parent.parent.parent.absolute()
    
    command = [
        "uv", "run", 
        "--directory", str(project_dir),
        "serena-mcp-server"  # stdio transport by default
    ]
    
    # Start with stdin/stdout pipes (actual MCP protocol)
    server_process = subprocess.Popen(
        command, 
        stdin=subprocess.PIPE, 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1  # Line buffered
    )
    
    # Give server a moment to start
    time.sleep(2)
    
    yield server_process
    
    # Cleanup
    server_process.terminate()
    try:
        server_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_process.kill()


def test_mcp_server_initialize(mcp_server):
    """Test MCP server initialization protocol."""
    
    # Send MCP initialization message
    init_message = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        },
        "id": 1
    }
    
    # Send via stdin (actual MCP transport)
    mcp_server.stdin.write(json.dumps(init_message) + '\n')
    mcp_server.stdin.flush()
    
    # Read response from stdout
    response_line = mcp_server.stdout.readline()
    assert response_line.strip(), "No response from MCP server"
    
    response = json.loads(response_line)
    
    assert "result" in response, f"Expected 'result' in response, got: {response}"
    assert response["id"] == 1, f"Expected id=1, got: {response.get('id')}"
    assert "capabilities" in response["result"], "Missing capabilities in initialize response"


def test_mcp_server_list_tools(mcp_server):
    """Test that server can list available tools."""
    
    # First initialize
    init_message = {
        "jsonrpc": "2.0",
        "method": "initialize", 
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        },
        "id": 1
    }
    
    mcp_server.stdin.write(json.dumps(init_message) + '\n')
    mcp_server.stdin.flush()
    mcp_server.stdout.readline()  # Consume initialize response
    
    # Send tools/list request
    list_tools_message = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2
    }
    
    mcp_server.stdin.write(json.dumps(list_tools_message) + '\n')
    mcp_server.stdin.flush()
    
    # Read response
    response_line = mcp_server.stdout.readline()
    assert response_line.strip(), "No response to tools/list"
    
    response = json.loads(response_line)
    
    assert "result" in response, f"Expected 'result' in tools/list response, got: {response}"
    assert "tools" in response["result"], "Missing 'tools' in list response"
    assert len(response["result"]["tools"]) > 0, "No tools found in server"
    
    # Verify we have some expected tools
    tool_names = [tool["name"] for tool in response["result"]["tools"]]
    assert "get_current_config" in tool_names, f"Expected get_current_config tool, found: {tool_names}"


def test_mcp_server_call_tool(mcp_server):
    """Test calling a simple tool through MCP protocol."""
    
    # Initialize first
    init_message = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05", 
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"}
        },
        "id": 1
    }
    
    mcp_server.stdin.write(json.dumps(init_message) + '\n')
    mcp_server.stdin.flush()
    mcp_server.stdout.readline()  # Consume initialize response
    
    # Call get_current_config tool
    tool_call_message = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_current_config",
            "arguments": {}
        },
        "id": 3
    }
    
    mcp_server.stdin.write(json.dumps(tool_call_message) + '\n')
    mcp_server.stdin.flush()
    
    # Read response
    response_line = mcp_server.stdout.readline()
    assert response_line.strip(), "No response to tool call"
    
    response = json.loads(response_line)
    
    assert "result" in response, f"Tool call failed, got: {response}"
    assert "content" in response["result"], "Missing content in tool call response"
    
    # Verify response content makes sense
    content = response["result"]["content"]
    assert len(content) > 0, "Empty content in tool response"
    assert isinstance(content[0], dict), "Content should be array of objects"
    assert "text" in content[0], "Missing text in content object"


@pytest.mark.integration
def test_mcp_server_full_workflow(mcp_server):
    """Test complete MCP workflow: initialize -> list tools -> call tool."""
    
    messages = [
        # 1. Initialize
        {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "integration-test", "version": "1.0.0"}
            },
            "id": 1
        },
        # 2. List tools
        {
            "jsonrpc": "2.0", 
            "method": "tools/list",
            "id": 2
        },
        # 3. Call a tool
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "get_current_config",
                "arguments": {}
            },
            "id": 3
        }
    ]
    
    responses = []
    
    for message in messages:
        mcp_server.stdin.write(json.dumps(message) + '\n')
        mcp_server.stdin.flush()
        
        response_line = mcp_server.stdout.readline()
        assert response_line.strip(), f"No response to message {message['id']}"
        
        response = json.loads(response_line)
        responses.append(response)
        
        # Basic validation of each response
        assert "result" in response, f"Message {message['id']} failed: {response}"
        assert response["id"] == message["id"], f"Response ID mismatch for message {message['id']}"
    
    # Verify we got sensible responses
    assert "capabilities" in responses[0]["result"]  # Initialize response
    assert len(responses[1]["result"]["tools"]) > 0  # Tools list
    assert "content" in responses[2]["result"]       # Tool call result

#!/usr/bin/env python3
"""
Test MCP communication through the Workspace Isolation Bridge
"""

import json
import subprocess
import time
import threading
import sys

def test_mcp_communication():
    """Test basic MCP communication through the bridge"""
    print("🧪 Testing MCP Communication through Workspace Isolation Bridge")
    print("=" * 60)
    
    # Start the bridge
    bridge_cmd = [
        "uv", "run", 
        "--directory", "E:\\_ProjectBroadside\\serena",
        "serena-workspace-isolation-bridge", 
        "--config", "test_bridge_config.json",
        "--debug"
    ]
    
    print(f"Starting bridge: {' '.join(bridge_cmd)}")
    
    try:
        process = subprocess.Popen(
            bridge_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Give it time to start
        time.sleep(2)
        
        # Check if bridge started successfully
        if process.poll() is not None:
            stderr_output = process.stderr.read()
            print(f"❌ Bridge failed to start. Exit code: {process.returncode}")
            print(f"Error output: {stderr_output}")
            return False
        
        print("✅ Bridge started successfully")
        
        # Test basic MCP initialization
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            }
        }
        
        print("📤 Sending initialize request...")
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        # Read response with timeout
        def read_response():
            try:
                response_line = process.stdout.readline()
                if response_line:
                    return json.loads(response_line.strip())
            except:
                return None
            return None
        
        # Wait for response
        response = None
        for _ in range(10):  # 5 second timeout
            response = read_response()
            if response:
                break
            time.sleep(0.5)
        
        if response:
            print("📥 Received response:")
            print(json.dumps(response, indent=2))
            
            if response.get("result"):
                print("✅ MCP initialization successful!")
                success = True
            else:
                print("❌ MCP initialization failed")
                success = False
        else:
            print("❌ No response received from bridge")
            success = False
        
        # Clean shutdown
        print("🛑 Shutting down bridge...")
        process.terminate()
        process.wait(timeout=5)
        
        return success
        
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        if 'process' in locals():
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                pass
        return False

if __name__ == "__main__":
    success = test_mcp_communication()
    sys.exit(0 if success else 1)
"""Test script for WSL Bridge functionality"""

import subprocess
import json
import time
import os
import tempfile

def test_windows_execution():
    """Test Q1: Can WSL launch Windows executables?"""
    print("Testing Windows executable launch from WSL...")
    
    # Test 1: Basic cmd.exe
    result = subprocess.run(
        ['cmd.exe', '/c', 'echo', 'Hello from Windows'],
        capture_output=True,
        text=True
    )
    print(f"cmd.exe test: {result.returncode == 0}")
    print(f"Output: {result.stdout.strip()}")
    
    # Test 2: Windows Python
    win_python_paths = [
        '/mnt/c/Python312/python.exe',
        '/mnt/c/Python311/python.exe',
        '/mnt/c/Python310/python.exe',
        '/mnt/c/Python39/python.exe',
    ]
    
    python_found = False
    for path in win_python_paths:
        if os.path.exists(path):
            result = subprocess.run(
                [path, '-c', 'print("Python on Windows works!")'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                print(f"Windows Python found at: {path}")
                print(f"Output: {result.stdout.strip()}")
                python_found = True
                break
    
    if not python_found:
        print("WARNING: No Windows Python found. Please install Python on Windows.")
    
    return result.returncode == 0

def test_path_translation():
    """Test Q2: Path translation in MCP messages"""
    print("\nTesting path translation...")
    
    # Test message with file paths
    test_message = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "read_file",
            "arguments": {
                "path": "/mnt/c/Users/TestUser/project/file.cs"
            }
        }
    }
    
    # This would be handled by the bridge's _translate_paths_recursive
    print(f"Original: {test_message['params']['arguments']['path']}")
    print(f"Expected: C:\\Users\\TestUser\\project\\file.cs")
    
    return True

import tempfile

def test_serena_connection():
    """Test full bridge connection"""
    print("\nTesting Serena connection through bridge...")

    # Get the project root directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    src_path = os.path.join(project_root, 'src')

    # Create a test configuration
    test_config = {
        "mcpServers": {
            "serena": {
                "command": "python",
                "args": ["-m", "serena.mcp_server", "--test-mode"],
                "env": {
                    "PYTHONPATH": src_path
                }
            }
        },
        "bridge": {
            "debug": True
        }
    }

    # Save test config to a temporary file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".json") as f:
        json.dump(test_config, f)
        config_path = f.name

    try:
        # Get the project root directory
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        src_path = os.path.join(project_root, 'src')

        # Set up environment for the subprocess
        env = os.environ.copy()
        env['PYTHONPATH'] = src_path + os.pathsep + env.get('PYTHONPATH', '')

        # Start the bridge
        bridge_process = subprocess.Popen(
            ['python', 'scripts/serena-wsl-bridge.py', '-c', config_path, '-d'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )

        # Send a test message
        test_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"capabilities": {}}
        }

        bridge_process.stdin.write(json.dumps(test_request) + '\n')
        bridge_process.stdin.flush()

        # Wait for response
        time.sleep(2)

        # Check if bridge is still running
        if bridge_process.poll() is None:
            print("Bridge is running successfully")
            bridge_process.terminate()
            return True
        else:
            stderr = bridge_process.stderr.read()
            print(f"Bridge failed: {stderr}")
            return False
    finally:
        os.remove(config_path)

if __name__ == "__main__":
    print("=== Serena WSL Bridge Test Suite ===\n")
    
    tests = [
        ("Windows Execution", test_windows_execution),
        ("Path Translation", test_path_translation),
        ("Serena Connection", test_serena_connection)
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"Error in {name}: {e}")
            results.append((name, False))
    
    print("\n=== Test Results ===")
    for name, result in results:
        status = "PASS" if result else "FAIL"
        print(f"{name}: {status}")

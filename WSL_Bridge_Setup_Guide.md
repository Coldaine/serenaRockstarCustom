# Comprehensive Serena WSL Bridge Setup Guide

## Context & Objective

I need to set up the Serena WSL Bridge to enable fast file access from Claude Code (running in WSL) to the Serena codebase (stored on Windows). This bridge provides 10-20x faster file access compared to direct WSL-to-Windows filesystem access.

## System Architecture Overview

**Current Setup:**
- **Windows Host**: Serena repository at `E:\_ProjectBroadside\serena`
- **Windows Python**: Standard Python virtual environment (venv) at `E:\_ProjectBroadside\serena\.venv\Scripts\python.exe` (Python 3.11.13)
- **WSL2 Ubuntu**: Claude Code running here, needs fast access to Windows files
- **WSL Mount Point**: Windows files accessible at `/mnt/e/_ProjectBroadside/serena`

**Target Architecture:**
```
Claude Code (WSL) → WSL Bridge Proxy (WSL) → Serena MCP Server (Windows)
```

The bridge:
1. Runs as a proxy in WSL
2. Launches the actual Serena MCP server on Windows using native Python
3. Translates WSL paths (`/mnt/e/`) to Windows paths (`E:\`)
4. Forwards all MCP protocol messages transparently
5. Provides native Windows file access speed

## Why This Is Needed

When Claude Code runs in WSL and tries to access Windows files directly through `/mnt/c/` or `/mnt/e/`, each file operation goes through WSL's filesystem translation layer, which is extremely slow (50-200ms per file). The bridge bypasses this by running the actual file operations on Windows natively.

**Performance Comparison:**
- **Direct WSL access**: 50-200ms per file read
- **Bridge access**: 5-15ms per file read
- **Improvement**: 10-20x faster

## Pre-Setup Verification

Before starting, please verify:

### 1. Check WSL Access to Windows Files
```bash
# Verify you can access the Serena repository from WSL
ls -la /mnt/e/_ProjectBroadside/serena
# Should show the Serena codebase files

# Verify Windows Python is accessible
/mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe --version
# Should show: Python 3.11.13
```

### 2. Check Current Working Directory
```bash
# Navigate to the Serena repository in WSL
cd /mnt/e/_ProjectBroadside/serena
pwd
# Should show: /mnt/e/_ProjectBroadside/serena
```

### 3. Verify WSL Bridge Components Exist
```bash
# Check that bridge scripts exist
ls -la scripts/setup-wsl-bridge.sh
ls -la scripts/serena-wsl-bridge.py
ls -la scripts/validate-wsl-setup.sh
```

## Main Setup Process

### Step 1: Install Serena with WSL Bridge Support
```bash
# Ensure we're in the right directory
cd /mnt/e/_ProjectBroadside/serena

# Install Serena in development mode with WSL bridge components
pip install -e ".[wsl]"

# Verify the WSL bridge command is available
which serena-wsl-bridge
serena-wsl-bridge --version
```

**Expected Output:**
- pip should install successfully
- `which serena-wsl-bridge` should show a path
- `--version` should show version information

### Step 2: Run the WSL Bridge Setup Script
```bash
# Execute the setup script (already configured with correct Python path)
bash scripts/setup-wsl-bridge.sh
```

**Expected Output:**
```
Setting up Serena WSL Bridge...
Found Windows Python at: /mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe
Configuration created at ~/.config/serena/server_config.json
Testing Windows Python execution...
Python execution test successful
Setup complete! You can now use 'serena-wsl-bridge' command.
To test: serena-wsl-bridge --help
```

### Step 3: Verify Configuration Created
```bash
# Check that configuration was created correctly
cat ~/.config/serena/server_config.json
```

**Expected Configuration:**
```json
{
  "mcpServers": {
    "serena": {
      "command": "/mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe",
      "args": ["-m", "serena.mcp_server", "--project", "E:\\_ProjectBroadside\\serena"],
      "env": {
        "PYTHONPATH": "E:\\_ProjectBroadside\\serena\\src",
        "SERENA_LOG_LEVEL": "INFO"
      },
      "cwd": "E:\\_ProjectBroadside\\serena"
    }
  }
}
```

### Step 4: Validate the Setup
```bash
# Run comprehensive validation
bash scripts/validate-wsl-setup.sh
```

**This should verify:**
- WSL bridge command availability
- Configuration file existence and validity
- Windows Python accessibility
- Path translation functionality

### Step 5: Test the Bridge Functionality
```bash
# Test basic bridge functionality
python tests/test_wsl_bridge.py
```

**Expected Output:**
```
=== Serena WSL Bridge Test Suite ===

Testing Windows executable launch from WSL...
cmd.exe test: True
Output: Hello from Windows
Windows Python found at: /mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe
Output: Python on Windows works!

Testing path translation...
Original: /mnt/c/Users/TestUser/project/file.cs
Expected: C:\Users\TestUser\project\file.cs

Testing Serena connection through bridge...
Bridge is running successfully

=== Test Results ===
Windows Execution: PASS
Path Translation: PASS
Serena Connection: PASS
```

### Step 6: Generate Claude Code MCP Configuration
```bash
# Generate the MCP server configuration for Claude Code
bash scripts/configure-claude-code.sh
```

**Expected Output:**
Will generate a configuration file and display the JSON you need to add to Claude Code's MCP settings.

## Claude Code Integration

After running the setup scripts, you'll need to configure Claude Code to use the bridge:

### Configuration Format
The bridge setup will provide a configuration like:
```json
{
  "servers": {
    "serena": {
      "command": "serena-wsl-bridge",
      "args": []
    }
  }
}
```

### Where to Add This Configuration
1. In Claude Code, go to Settings → MCP Servers
2. Add the generated configuration
3. Restart Claude Code

## Advanced Testing & Verification

### Test 1: Bridge Command Availability
```bash
serena-wsl-bridge --help
# Should show help text for the bridge
```

### Test 2: Configuration Validation
```bash
# Verify config file exists and is valid JSON
python -m json.tool ~/.config/serena/server_config.json
```

### Test 3: Windows Python Execution Test
```bash
# Test that Windows Python can be executed from WSL
/mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe -c "print('Windows Python works from WSL!')"
```

### Test 4: Path Translation Test
```bash
# Test path translation functionality
echo '{"path": "/mnt/e/_ProjectBroadside/serena/test.py"}' | python3 -c "
import json, sys
data = json.load(sys.stdin)
wsl_path = data['path']
# Convert /mnt/e/ to E:\
if wsl_path.startswith('/mnt/e/'):
    win_path = 'E:' + chr(92) + chr(92) + wsl_path[7:].replace('/', chr(92))
    print(f'WSL: {wsl_path} -> Windows: {win_path}')
else:
    print(f'No translation needed: {wsl_path}')
"
```

### Test 5: End-to-End Bridge Test
```bash
# Start the bridge in background and test it
serena-wsl-bridge --debug &
BRIDGE_PID=$!

# Give it time to start
sleep 2

# Test with a simple MCP message
echo '{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}}' | nc localhost 8000

# Clean up
kill $BRIDGE_PID
```

## Troubleshooting Guide

### Common Issues & Solutions

**Issue 1: "serena-wsl-bridge command not found"**
```bash
# Solution: Ensure pip install completed and refresh shell
pip install -e ".[wsl]"
hash -r  # Refresh command cache
which serena-wsl-bridge
```

**Issue 2: "Windows Python not found"**
```bash
# Solution: Verify Python path exists
ls -la /mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe
# If missing, the virtual environment may not be properly set up
```

**Issue 3: "Permission denied accessing Windows files"**
```bash
# Solution: Check WSL file permissions
# May need to adjust Windows folder permissions or WSL mount options
sudo mount -t drvfs E: /mnt/e -o metadata
```

**Issue 4: Bridge starts but fails to connect**
```bash
# Solution: Check bridge logs
tail -f /tmp/serena_bridge_*.log
# Look for connection errors or path issues
```

**Issue 5: "Configuration file not found"**
```bash
# Solution: Ensure config directory exists
mkdir -p ~/.config/serena
# Re-run setup script
bash scripts/setup-wsl-bridge.sh
```

## Performance Verification

After setup, you can benchmark the performance improvement:

```bash
# Run performance benchmark
python tests/benchmark_wsl_bridge.py
```

**Expected Results:**
```
Benchmarking file access performance...

Direct WSL access (/mnt/e/):
  mean: 125.45ms
  median: 120.30ms
  stdev: 25.67ms
  min: 95.20ms
  max: 180.45ms

Windows native access (Bridge):
  mean: 8.90ms
  median: 7.50ms
  stdev: 3.20ms
  min: 5.10ms
  max: 15.30ms

Speedup: 14.1x
```

## Success Criteria

Setup is complete when all of these work:

- [ ] `serena-wsl-bridge --help` displays help text
- [ ] Configuration file exists at `~/.config/serena/server_config.json`
- [ ] Windows Python path is correctly detected and accessible
- [ ] WSL bridge validation script passes all tests
- [ ] Bridge test suite runs successfully
- [ ] Path translation works correctly
- [ ] Claude Code can connect to Serena via the bridge
- [ ] File access shows significant performance improvement (10x+)

## Advanced Configuration Options

### Environment Variables (Optional)
```bash
# Enable debug logging for troubleshooting
export SERENA_BRIDGE_DEBUG=1

# Adjust restart behavior
export SERENA_BRIDGE_MAX_RESTARTS=5
export SERENA_BRIDGE_RESTART_COOLDOWN=10

# Disable path translation (if needed for testing)
export SERENA_BRIDGE_TRANSLATE_PATHS=0
```

### Manual Configuration Editing
If needed, you can manually edit `~/.config/serena/server_config.json` to:
- Adjust Python paths
- Modify environment variables  
- Change working directories
- Add additional MCP servers

Example manual configuration:
```json
{
  "mcpServers": {
    "serena": {
      "command": "/mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe",
      "args": ["-m", "serena.mcp_server", "--project", "E:\\_ProjectBroadside\\serena", "--context", "ide-assistant"],
      "env": {
        "PYTHONPATH": "E:\\_ProjectBroadside\\serena\\src",
        "SERENA_LOG_LEVEL": "DEBUG"
      },
      "cwd": "E:\\_ProjectBroadside\\serena"
    }
  }
}
```

## What This Enables

Once setup is complete, Claude Code will be able to:

1. **Fast File Access**: Read/write Serena source files at native Windows speed
2. **Symbol Navigation**: Quickly traverse code symbols and references across the entire codebase
3. **Project Analysis**: Rapidly scan and analyze the complete Serena project
4. **Code Editing**: Make changes with minimal latency
5. **Real-time Feedback**: Get immediate responses to code queries and operations
6. **Memory Access**: Read and write to Serena's memory system efficiently
7. **Tool Execution**: Run Serena's 80+ tools at full speed

The bridge makes working with Windows-hosted code from WSL feel like working with native WSL files, but with much better performance.

## Architecture Details

### How the Bridge Works

1. **Startup**: Claude Code connects to `serena-wsl-bridge` running in WSL
2. **Server Launch**: Bridge launches `serena.mcp_server` on Windows using native Python
3. **Message Forwarding**: All MCP JSON-RPC messages are forwarded between Claude and Serena
4. **Path Translation**: File paths in messages are automatically translated:
   - WSL → Windows: `/mnt/e/_ProjectBroadside/` → `E:\_ProjectBroadside\`
   - Windows → WSL: `E:\_ProjectBroadside\` → `/mnt/e/_ProjectBroadside/`
5. **Native Operations**: All actual file operations happen on Windows at native speed

### Bridge Components

- **`serena-wsl-bridge`**: Main executable that runs in WSL
- **`scripts/serena-wsl-bridge.py`**: The bridge implementation
- **`~/.config/serena/server_config.json`**: Configuration file
- **`src/serena/wsl_bridge/`**: Bridge modules (wrapper, config, metrics)

---

## Instructions for Execution

Please execute these steps in order and report:

1. **Any error messages** you encounter
2. **Unexpected outputs** that don't match the expected results
3. **Performance numbers** from the benchmark
4. **Whether Claude Code can successfully connect** after configuration

The setup scripts are already configured with your specific system paths (`E:\_ProjectBroadside\serena` and the Python virtual environment), so they should work directly without modification.

**Important**: Make sure you're running all commands from the WSL Ubuntu environment, not from Windows Command Prompt or PowerShell.

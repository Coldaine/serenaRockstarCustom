# WSL MCP Server Troubleshooting Briefing

## Current Problem Status
The user has a **Windows-based Serena project** at `E:\_ProjectBroadside\serena` and is trying to connect **Claude Code (running in WSL)** to the Serena MCP server. The current VSCode MCP configuration is failing.

## User's Current Setup

### Windows Side
- **Project Location**: `E:\_ProjectBroadside\serena`
- **Python**: `E:\_ProjectBroadside\serena\.venv\Scripts\python.exe` (Python 3.11.13)
- **UV**: Available and working on Windows
- **Entry Points**: Both `serena-mcp-server` and `rockstar-serena-mcp-server` available

### WSL Side  
- **Claude Code**: Running in WSL2 Ubuntu
- **Mount Point**: Project accessible at `/mnt/e/_ProjectBroadside/serena`
- **Current MCP Config**: `.vscode/mcp.json` (see details below)

### Current MCP Configuration (FAILING)
```jsonc
{
  "servers": {
    "serena": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "${workspaceFolder}",
        "serena-mcp-server",        // OLD ENTRY POINT
        "--port",
        "8347",
        "--context",
        "ide-assistant"
      ],
      "env": {
        "SERENA_CONFIG": "${workspaceFolder}/serena_config.yml"
      }
    }
  }
}
```

## Key Issues Identified

### 1. **Entry Point Issue**
- Config uses `serena-mcp-server` but current version uses `rockstar-serena-mcp-server`
- Both are available for backward compatibility, but may not be working correctly

### 2. **UV Availability in WSL**
- WSL may not have `uv` installed or available in PATH
- Even if available, it may not be able to run the Windows Python environment

### 3. **Path Resolution**
- `${workspaceFolder}` resolves to WSL path, but Python environment is on Windows
- Cross-platform path issues between WSL and Windows

### 4. **Port Argument**
- `--port 8347` may not be a valid argument for the MCP server
- MCP servers typically use stdio transport, not network ports

## Available Solutions

### Option 1: WSL Bridge (RECOMMENDED)
The project has a **WSL Bridge** system designed exactly for this scenario:

**Architecture**: `Claude Code (WSL) → WSL Bridge (WSL) → Serena MCP Server (Windows)`

**Setup Steps**:
1. Run `/mnt/e/_ProjectBroadside/serena/scripts/setup-wsl-bridge.sh`
2. Configure Claude Code to use `serena-wsl-bridge` command
3. The bridge handles all path translation and Windows Python execution

**Benefits**:
- 10-20x faster file access
- Proper path translation
- Handles Windows Python environment correctly

### Option 2: Direct WSL Configuration
Fix the current `.vscode/mcp.json` configuration:

**Issues to Fix**:
- Update entry point to `rockstar-serena-mcp-server`
- Remove `--port` argument (not valid for stdio transport)
- Ensure `uv` is available in WSL PATH
- Fix path resolution issues

### Option 3: Native WSL Installation
Install Serena directly in WSL environment:
- Clone/link the project in WSL
- Set up Python environment in WSL
- Run MCP server natively in WSL

## Recommended Troubleshooting Steps

### Step 1: Check WSL Bridge Availability
```bash
cd /mnt/e/_ProjectBroadside/serena
ls -la scripts/setup-wsl-bridge.sh
```

### Step 2: Test UV in WSL
```bash
which uv
uv --version
```

### Step 3: Test Windows Python Access
```bash
/mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe --version
```

### Step 4: Check Entry Points
```bash
cd /mnt/e/_ProjectBroadside/serena
uv run rockstar-serena-mcp-server --help
```

### Step 5: Validate MCP Server Arguments
The `--port` argument is likely invalid. Test without it:
```bash
uv run --directory /mnt/e/_ProjectBroadside/serena rockstar-serena-mcp-server --context ide-assistant
```

## Next Actions Required

1. **Choose approach**: WSL Bridge (recommended) vs Direct fix vs Native installation
2. **Test components**: UV availability, Python access, entry points
3. **Update configuration**: Fix the `.vscode/mcp.json` based on findings
4. **Validate connection**: Test MCP server startup and Claude Code connection

## Expected Outcome

After fixing the configuration, Claude Code should be able to:
- Connect to Serena MCP server successfully
- Access all Serena tools and capabilities
- Work with the Windows-based project files seamlessly
- Provide 10-20x better performance than direct WSL file access

## Configuration Templates

### WSL Bridge Configuration
```json
{
  "servers": {
    "serena": {
      "type": "stdio",
      "command": "serena-wsl-bridge",
      "args": ["--context", "ide-assistant"]
    }
  }
}
```

### Direct Fix Configuration
```json
{
  "servers": {
    "serena": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/mnt/e/_ProjectBroadside/serena",
        "rockstar-serena-mcp-server",
        "--context",
        "ide-assistant"
      ],
      "env": {
        "SERENA_CONFIG": "/mnt/e/_ProjectBroadside/serena/serena_config.yml"
      }
    }
  }
}
```

## Quick Fix Commands

If you want to try the direct fix approach immediately:

### Update Entry Point
```bash
cd /mnt/e/_ProjectBroadside/serena
# Edit .vscode/mcp.json to change:
# "serena-mcp-server" → "rockstar-serena-mcp-server"
# Remove the "--port", "8347" lines
```

### Test the Connection
```bash
# Test if the MCP server starts correctly
uv run --directory /mnt/e/_ProjectBroadside/serena rockstar-serena-mcp-server --context ide-assistant
# Should show MCP server startup messages, not errors
```

## WSL Bridge Setup (Recommended)

If you choose the WSL Bridge approach:

### 1. Run the Setup Script
```bash
cd /mnt/e/_ProjectBroadside/serena
./scripts/setup-wsl-bridge.sh
```

### 2. Update MCP Configuration
Replace the entire `.vscode/mcp.json` with:
```json
{
  "servers": {
    "serena": {
      "type": "stdio",
      "command": "serena-wsl-bridge",
      "args": ["--context", "ide-assistant"]
    }
  }
}
```

### 3. Test the Bridge
```bash
# Test the bridge connection
serena-wsl-bridge --context ide-assistant
# Should show Serena MCP server starting via the bridge
```

## Troubleshooting Common Issues

### "uv command not found"
```bash
# Install uv in WSL
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### "Python not found"
```bash
# Test Windows Python access
ls -la /mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe
# If missing, the Windows Python environment may not be set up correctly
```

### "serena-wsl-bridge command not found"
```bash
# The WSL bridge setup script may not have run successfully
# Check if the bridge was installed:
which serena-wsl-bridge
# If not found, run the setup script again
```

### "MCP server fails to start"
```bash
# Check for detailed error messages
uv run --directory /mnt/e/_ProjectBroadside/serena rockstar-serena-mcp-server --context ide-assistant --verbose
```

---

**Instructions for WSL Agent**: 
1. Read this entire briefing
2. Follow the troubleshooting steps systematically
3. Choose either the WSL Bridge approach (recommended) or direct fix
4. Test each component before proceeding
5. Update the MCP configuration based on your findings
6. Validate the connection works before completing the task

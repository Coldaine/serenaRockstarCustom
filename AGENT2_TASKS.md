# WSL Bridge Phase 3.2 & 4 - Setup Scripts and Configuration

## Overview
You are responsible for creating the setup scripts and configuration tools for the Serena WSL Bridge. The main agent has completed Phase 3.1 (core implementation and package integration). Your work will enable users to easily install and configure the WSL Bridge.

## Current State
- ✅ WSL Bridge core implementation completed (`src/serena/wsl_bridge/wrapper.py`)
- ✅ Package integration completed (`pyproject.toml` updated with entry points)
- ✅ Entry point script created (`scripts/serena-wsl-bridge`)
- ✅ Branch: `feature/wsl-bridge` (commit: 49468f6)

## Your Tasks

### Phase 3.2: Setup Script Creation

#### Task 1: WSL Environment Setup Script
**File**: `scripts/setup-wsl-bridge.sh`

**Requirements**:
```bash
#!/bin/bash
# Setup script for Serena WSL Bridge
# This script configures the WSL environment for optimal bridge performance

echo "Setting up Serena WSL Bridge..."

# Create config directory
mkdir -p ~/.config/serena

# Detect Windows Python installations
PYTHON_FOUND=false
PYTHON_PATH=""

# Check common Python installation paths
WIN_PYTHON_PATHS=(
    "/mnt/c/Python312/python.exe"
    "/mnt/c/Python311/python.exe" 
    "/mnt/c/Python310/python.exe"
    "/mnt/c/Python39/python.exe"
    "/mnt/c/Users/$USER/AppData/Local/Programs/Python/Python312/python.exe"
    "/mnt/c/Users/$USER/AppData/Local/Programs/Python/Python311/python.exe"
    "/mnt/c/Program Files/Python312/python.exe"
    "/mnt/c/Program Files/Python311/python.exe"
)

for path in "${WIN_PYTHON_PATHS[@]}"; do
    if [ -f "$path" ]; then
        echo "Found Windows Python at: $path"
        # Test if it works
        if "$path" --version >/dev/null 2>&1; then
            PYTHON_PATH="$path"
            PYTHON_FOUND=true
            break
        fi
    fi
done

if [ "$PYTHON_FOUND" = false ]; then
    echo "❌ No working Windows Python installation found!"
    echo "Please install Python on Windows first."
    echo "Recommended: Download from https://python.org and install to C:\\Python312"
    exit 1
fi

# Get Windows username
WIN_USERNAME=$(cmd.exe /c "echo %USERNAME%" 2>/dev/null | tr -d '\r')
if [ -z "$WIN_USERNAME" ]; then
    WIN_USERNAME="$USER"
fi

# Convert WSL path to Windows path for PYTHONPATH
WSL_SERENA_PATH=$(pwd)
WIN_SERENA_PATH=$(echo "$WSL_SERENA_PATH" | sed 's|/mnt/\([a-z]\)/|\1:/|g' | sed 's|/|\\|g')

# Create initial configuration
cat > ~/.config/serena/wsl_bridge.json << EOF
{
  "mcpServers": {
    "serena": {
      "command": "$PYTHON_PATH",
      "args": ["-m", "serena.mcp_server"],
      "env": {
        "PYTHONPATH": "$WIN_SERENA_PATH",
        "SERENA_LOG_LEVEL": "INFO"
      },
      "cwd": "$WIN_SERENA_PATH"
    }
  },
  "bridge": {
    "debug": false,
    "max_restarts": 3,
    "restart_cooldown": 10,
    "translate_paths": true
  }
}
EOF

echo "✅ Configuration created at ~/.config/serena/wsl_bridge.json"
echo ""
echo "Testing Windows Python execution..."
if "$PYTHON_PATH" -c "print('Python execution test successful')" 2>/dev/null; then
    echo "✅ Windows Python is working correctly"
else
    echo "❌ Windows Python execution failed"
    echo "Please check your Windows Python installation"
fi

echo ""
echo "Setup complete! You can now use 'serena-wsl-bridge' command."
echo "To test: serena-wsl-bridge --help"
```

#### Task 2: Configuration Validation Script
**File**: `scripts/validate-wsl-setup.sh`

Create a script that validates the WSL Bridge setup:
- Tests Windows Python execution
- Validates configuration file
- Tests path translation
- Checks for common issues

### Phase 4: Claude Code Integration

#### Task 3: Claude Code Configuration Script
**File**: `scripts/configure-claude-code.sh`

**Requirements**:
```bash
#!/bin/bash
# Configure Claude Code to use Serena WSL Bridge

CLAUDE_CONFIG_LOCATIONS=(
    "$HOME/.claude.json"
    "$HOME/.config/claude/config.json"
    "$HOME/AppData/Roaming/Claude/config.json"
)

echo "Configuring Claude Code to use Serena WSL Bridge..."

# Find Claude Code configuration
CLAUDE_CONFIG=""
for config_path in "${CLAUDE_CONFIG_LOCATIONS[@]}"; do
    if [ -f "$config_path" ]; then
        CLAUDE_CONFIG="$config_path"
        break
    fi
done

if [ -z "$CLAUDE_CONFIG" ]; then
    echo "Claude Code configuration not found."
    echo "Creating new configuration at ~/.claude.json"
    CLAUDE_CONFIG="$HOME/.claude.json"
fi

# Backup existing config
if [ -f "$CLAUDE_CONFIG" ]; then
    cp "$CLAUDE_CONFIG" "${CLAUDE_CONFIG}.backup"
    echo "✅ Backed up existing config to ${CLAUDE_CONFIG}.backup"
fi

# Create or update MCP servers configuration
cat > /tmp/serena_mcp_config.json << EOF
{
  "mcpServers": {
    "serena": {
      "command": "serena-wsl-bridge",
      "args": []
    }
  }
}
EOF

echo ""
echo "Add this configuration to your Claude Code MCP servers:"
echo "----------------------------------------"
cat /tmp/serena_mcp_config.json
echo "----------------------------------------"
echo ""
echo "Manual steps:"
echo "1. Open Claude Code"
echo "2. Go to Settings > MCP Servers"
echo "3. Add the above configuration"
echo "4. Restart Claude Code"
echo ""
echo "Configuration file saved to: /tmp/serena_mcp_config.json"
```

#### Task 4: Installation Instructions
**File**: `docs/wsl-bridge-installation.md`

Create comprehensive installation documentation with:
- Prerequisites (WSL2, Windows Python, Claude Code)
- Step-by-step installation process
- Troubleshooting common issues
- Performance optimization tips

### Interface Specifications

#### Configuration File Format
The bridge expects `~/.config/serena/wsl_bridge.json` with this structure:
```json
{
  "mcpServers": {
    "serena": {
      "command": "/mnt/c/Python312/python.exe",
      "args": ["-m", "serena.mcp_server"],
      "env": {
        "PYTHONPATH": "C:\\path\\to\\serena",
        "SERENA_LOG_LEVEL": "INFO"
      },
      "cwd": "C:\\path\\to\\serena"
    }
  },
  "bridge": {
    "debug": false,
    "max_restarts": 3,
    "restart_cooldown": 10,
    "translate_paths": true
  }
}
```

#### Command Line Interface
The bridge supports these arguments:
- `-c, --config`: Path to configuration file
- `-d, --debug`: Enable debug logging
- `--version`: Show version information

#### Environment Variables
Optional environment overrides:
- `SERENA_BRIDGE_DEBUG=1`: Enable debug mode
- `SERENA_BRIDGE_CONFIG`: Override config file path
- `SERENA_BRIDGE_MAX_RESTARTS`: Override restart limit

## Quality Requirements

### Scripts Must:
1. **Be robust**: Handle missing files, permissions, path issues
2. **Be informative**: Provide clear success/error messages
3. **Be testable**: Include validation and test modes
4. **Be cross-platform**: Work in different WSL distributions

### Documentation Must:
1. **Be comprehensive**: Cover all installation scenarios
2. **Include examples**: Provide copy-paste commands
3. **Address common issues**: Include troubleshooting section
4. **Be beginner-friendly**: Assume no prior WSL experience

## Testing Your Work

### Test Scripts:
```bash
# Test the setup script
./scripts/setup-wsl-bridge.sh

# Test the validation script  
./scripts/validate-wsl-setup.sh

# Test Claude Code configuration
./scripts/configure-claude-code.sh
```

### Validation Checklist:
- [ ] Scripts handle missing Windows Python gracefully
- [ ] Configuration files are created with correct permissions
- [ ] Path translation works for common scenarios
- [ ] Error messages are clear and actionable
- [ ] Documentation includes all necessary steps

## Completion Criteria

Your work is complete when:
1. All scripts execute without errors
2. WSL Bridge can be installed from scratch using your scripts
3. Claude Code can be configured to use the bridge
4. Documentation covers installation and troubleshooting
5. Common edge cases are handled gracefully

## Coordination

- **Branch**: Continue working on `feature/wsl-bridge`
- **Commit Pattern**: Use `feat: Phase 3.2/4 - [description]` for commits
- **File Locations**: Follow the exact paths specified above
- **Interface**: The main agent has defined the bridge interface - don't modify core wrapper code

## Timeline

Estimated work: 20-30 minutes
- Scripts creation: 15 minutes
- Documentation: 10 minutes  
- Testing: 5 minutes

Good luck! The main agent will handle integration testing once your work is complete.

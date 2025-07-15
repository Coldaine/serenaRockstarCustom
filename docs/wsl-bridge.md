# Serena Workspace Isolation Bridge

The Workspace Isolation Bridge provides dedicated Serena server instances for multiple workspaces to prevent connection conflicts.

## Problem

When multiple Claude Code workspaces (or other MCP clients) try to connect to the same Serena MCP server, connection conflicts and resource contention occur. Each workspace needs its own isolated server instance.

## Solution

The Workspace Isolation Bridge acts as a transparent proxy:
- Each workspace connects to the bridge with a unique workspace ID.
- The bridge launches a dedicated Serena server instance for each workspace.
- All MCP communication is forwarded to the appropriate server instance.
- The bridge manages server lifecycle and prevents resource conflicts.

## Installation

1.  **Clone the Serena Repository**
    ```bash
    git clone https://github.com/your-org/serena.git
    cd serena
    ```

2.  **Run the Setup Script**
    This script will detect your Windows Python installation and create a configuration file.
    ```bash
    bash scripts/setup-wsl-bridge.sh
    ```

3.  **Verify the Setup**
    Run the validation script to ensure everything is configured correctly.
    ```bash
    bash scripts/validate-wsl-setup.sh
    ```

4.  **Configure Claude Code**
    Update your Claude Code configuration to use the `serena-workspace-isolation-bridge` command. The `configure-claude-code.sh` script can help with this.

## Configuration

The bridge is configured via `~/.config/serena/server_config.json`. The setup script creates this file for you, but you can edit it to change the Python path or other settings.

You can also use environment variables to override the settings:
- `SERENA_BRIDGE_DEBUG=1`: Enable debug logging.
- `SERENA_BRIDGE_MAX_RESTARTS=5`: Maximum server restart attempts.
- `SERENA_BRIDGE_RESTART_COOLDOWN=10`: Cooldown in seconds between restarts.
- `SERENA_BRIDGE_TRANSLATE_PATHS=0`: Disable path translation.

## Benefits

Key advantages:
- **Workspace Isolation**: Each workspace gets its own dedicated server instance
- **No Connection Conflicts**: Multiple workspaces can run simultaneously without interference
- **Resource Management**: Proper server lifecycle management and cleanup
- **Scalability**: Support for unlimited concurrent workspaces

## Troubleshooting

**Check Bridge Logs**
The bridge creates detailed logs that are essential for troubleshooting.
```bash
tail -f /tmp/serena_bridge_*.log
```

**Run the Functional Tests**
The test suite can help diagnose issues with your setup.
```bash
python tests/test_wsl_bridge.py
```
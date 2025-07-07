# Serena WSL Bridge

The WSL Bridge enables fast file access for Serena when running with Claude Code on Windows via WSL.

## Problem

When Claude Code (running in WSL) uses Serena to read Unity project files stored on Windows, file access is 10-20x slower due to the WSL filesystem translation layer.

## Solution

The WSL Bridge acts as a transparent proxy:
- Claude Code connects to the bridge (running in WSL).
- The bridge launches Serena on Windows for native file speed.
- All MCP communication is forwarded transparently.
- The bridge monitors the Serena process and restarts it if it crashes.

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
    Update your Claude Code configuration to use the `serena-wsl-bridge` command. The `configure-claude-code.sh` script can help with this.

## Configuration

The bridge is configured via `~/.config/serena/server_config.json`. The setup script creates this file for you, but you can edit it to change the Python path or other settings.

You can also use environment variables to override the settings:
- `SERENA_BRIDGE_DEBUG=1`: Enable debug logging.
- `SERENA_BRIDGE_MAX_RESTARTS=5`: Maximum server restart attempts.
- `SERENA_BRIDGE_RESTART_COOLDOWN=10`: Cooldown in seconds between restarts.
- `SERENA_BRIDGE_TRANSLATE_PATHS=0`: Disable path translation.

## Performance

Typical improvements:
- Unity .cs file reads: 50ms → 5ms (10x faster)
- Large YAML files: 200ms → 15ms (13x faster)
- Project scanning: 30s → 3s (10x faster)

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
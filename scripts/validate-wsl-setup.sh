#!/bin/bash
# Validation script for Serena WSL Bridge setup

echo "Validating Serena WSL Bridge setup..."

# 1. Test Windows Python execution
echo "--- 1. Testing Windows Python execution ---"
PYTHON_PATH_IN_CONFIG=$(jq -r '.mcpServers.serena.command' ~/.config/serena/server_config.json)

if [ -z "$PYTHON_PATH_IN_CONFIG" ] || [ "$PYTHON_PATH_IN_CONFIG" == "null" ]; then
    echo "❌ Python path not found in configuration."
    exit 1
fi

if "$PYTHON_PATH_IN_CONFIG" -c "import sys; print(f'Python {sys.version} test successful')" 2>/dev/null; then
    echo "✅ Windows Python is working correctly."
else
    echo "❌ Windows Python execution failed. Check the path in your config."
    exit 1
fi

# 2. Validate configuration file
echo ""
echo "--- 2. Validating configuration file ---"
CONFIG_FILE=~/.config/serena/server_config.json
if [ -f "$CONFIG_FILE" ]; then
    echo "✅ Configuration file found at $CONFIG_FILE"
else
    echo "❌ Configuration file not found!"
    exit 1
fi

# Check for key sections
if jq -e '.mcpServers.serena' "$CONFIG_FILE" >/dev/null; then
    echo "✅ Configuration file contains 'mcpServers' section."
else
    echo "❌ Configuration file is missing required 'mcpServers' section."
    exit 1
fi

# 3. Test path translation
echo ""
echo "--- 3. Testing path translation ---"
# This is a conceptual test. The real test is running the bridge.
WSL_PATH="/mnt/c/Users"
WIN_PATH_EXPECTED="C:\\Users"

# Use the same sed command from the setup script for consistency
WIN_PATH_ACTUAL=$(echo "$WSL_PATH" | sed 's|/mnt/\([a-z]\)/|\1:/|g' | sed 's|/|\\|g')

if [ "$WIN_PATH_ACTUAL" == "$WIN_PATH_EXPECTED" ]; then
    echo "✅ Path translation logic appears correct."
    echo "   WSL: $WSL_PATH -> WIN: $WIN_PATH_ACTUAL"
else
    echo "❌ Path translation logic failed."
    echo "   Expected: $WIN_PATH_EXPECTED"
    echo "   Actual:   $WIN_PATH_ACTUAL"
fi

# 4. Check for common issues
echo ""
echo "--- 4. Checking for common issues ---"
# Check if serena-wsl-bridge is in the PATH
if command -v serena-wsl-bridge >/dev/null 2>&1; then
    echo "✅ 'serena-wsl-bridge' command is available in your PATH."
else
    echo "⚠️ 'serena-wsl-bridge' command not found. Make sure you have sourced your shell profile or run 'pip install -e .''"
fi


echo ""
echo "Validation complete. If all checks passed, your setup is likely correct."
echo "The final test is to run the bridge itself: serena-wsl-bridge --help"

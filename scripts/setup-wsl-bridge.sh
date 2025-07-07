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
    "/mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe"
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
    echo "Recommended: Download from https://python.org and install to C:\Python312"
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
cat > ~/.config/serena/server_config.json << EOF
{
  "mcpServers": {
    "serena": {
      "command": "$PYTHON_PATH",
      "args": ["-m", "serena.mcp_server", "--project", "$WIN_SERENA_PATH"],
      "env": {
        "PYTHONPATH": "$WIN_SERENA_PATH\src",
        "SERENA_LOG_LEVEL": "INFO"
      },
      "cwd": "$WIN_SERENA_PATH"
    }
  }
}
EOF

echo "✅ Configuration created at ~/.config/serena/server_config.json"
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

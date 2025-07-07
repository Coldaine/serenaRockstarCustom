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
  "servers": {
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

#!/bin/bash
# Test the Serena MCP server setup

echo "Testing Serena MCP Server..."

# Test 1: Check if uv is available
if command -v uv &> /dev/null; then
    echo "✅ uv is available"
else
    echo "❌ uv is not available - please install uv first"
    exit 1
fi

# Test 2: Check if we can run the MCP server
echo "Testing MCP server startup..."
cd "e:\_ProjectBroadside\serena"

# Try to start the server with --help to verify it works
if uv run rockstar-serena-mcp-server --help &> /dev/null; then
    echo "✅ MCP server can be started"
else
    echo "❌ MCP server failed to start"
    echo "Trying with backward compatibility command..."
    if uv run serena-mcp-server --help &> /dev/null; then
        echo "✅ MCP server works with backward compatibility command"
    else
        echo "❌ Both commands failed"
        exit 1
    fi
fi

echo "✅ All tests passed! MCP server should work."

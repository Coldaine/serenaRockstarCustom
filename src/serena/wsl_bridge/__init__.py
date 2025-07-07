"""
Serena WSL Bridge

A transparent stdio bridge that connects VS Code to pooled MCP servers,
enabling fast file access when Claude Code runs in WSL but projects are on Windows.
"""

__version__ = "0.1.0"

from .wrapper import MCPWSLBridge

__all__ = ["MCPWSLBridge"]

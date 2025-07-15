"""
Serena Workspace Isolation Bridge

A transparent stdio bridge that provides isolated MCP server instances
per workspace, preventing connection conflicts and resource contention.
"""

__version__ = "0.1.0"

from .wrapper import MCPWorkspaceIsolationBridge

__all__ = ["MCPWorkspaceIsolationBridge"]

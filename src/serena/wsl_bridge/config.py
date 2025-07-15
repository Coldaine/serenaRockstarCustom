#!/usr/bin/env python3
"""
Workspace Isolation Bridge Configuration Management

Handles loading, saving, and validating configuration for the Workspace Isolation Bridge.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging


class WorkspaceIsolationBridgeConfig:
    """Configuration manager for Workspace Isolation Bridge"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config_data = {}
        self.logger = logging.getLogger(__name__)
    
    def _get_default_config_path(self) -> Path:
        """Get the default configuration file path"""
        config_dir = Path.home() / ".config" / "serena"
        return config_dir / "workspace_isolation_bridge.json"
    
    def load(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            with open(self.config_path, 'r') as f:
                self.config_data = json.load(f)
                self.logger.info(f"Loaded config from {self.config_path}")
                return self.config_data
        except FileNotFoundError:
            self.logger.warning(f"Config file not found at {self.config_path}, using defaults")
            self.config_data = self._get_default_config()
            return self.config_data
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in config file {self.config_path}: {e}")
            raise ValueError(f"Configuration file contains invalid JSON: {e}")
        except Exception as e:
            self.logger.error(f"Failed to load config from {self.config_path}: {e}")
            raise
    
    def save(self, config: Dict[str, Any]) -> None:
        """Save configuration to file"""
        try:
            # Ensure config directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            self.config_data = config
            self.logger.info(f"Saved config to {self.config_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to save config to {self.config_path}: {e}")
            raise
    
    def get_server_config(self, server_name: str = "serena") -> Dict[str, Any]:
        """Get configuration for a specific MCP server"""
        servers = self.config_data.get("mcpServers", {})
        if server_name not in servers:
            raise ValueError(f"Server '{server_name}' not found in configuration")
        
        return servers[server_name]
    
    def get_bridge_config(self) -> Dict[str, Any]:
        """Get bridge-specific configuration"""
        return self.config_data.get("bridge", {})
    
    def validate(self) -> bool:
        """Validate the current configuration"""
        try:
            # Check required top-level keys
            required_keys = ["mcpServers", "bridge"]
            for key in required_keys:
                if key not in self.config_data:
                    self.logger.error(f"Missing required configuration key: {key}")
                    return False
            
            # Validate MCP servers
            servers = self.config_data["mcpServers"]
            if not isinstance(servers, dict) or not servers:
                self.logger.error("mcpServers must be a non-empty dictionary")
                return False
            
            for server_name, server_config in servers.items():
                if not self._validate_server_config(server_name, server_config):
                    return False
            
            # Validate bridge config
            bridge_config = self.config_data["bridge"]
            if not self._validate_bridge_config(bridge_config):
                return False
            
            self.logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            self.logger.error(f"Configuration validation failed: {e}")
            return False
    
    def _validate_server_config(self, server_name: str, config: Dict[str, Any]) -> bool:
        """Validate individual server configuration"""
        required_fields = ["command", "args"]
        
        for field in required_fields:
            if field not in config:
                self.logger.error(f"Server '{server_name}' missing required field: {field}")
                return False
        
        # Validate command exists (if it's a file path)
        command = config["command"]
        if command.startswith("/") or "\\" in command:
            # It's a path, check if it exists
            if not os.path.exists(command):
                self.logger.warning(f"Server '{server_name}' command path does not exist: {command}")
                # Don't fail validation, just warn - path might be valid in different context
        
        return True
    
    def _validate_bridge_config(self, config: Dict[str, Any]) -> bool:
        """Validate bridge configuration"""
        # All bridge config fields are optional with defaults
        # Just check types if present
        
        if "debug" in config and not isinstance(config["debug"], bool):
            self.logger.error("bridge.debug must be a boolean")
            return False
        
        if "max_restarts" in config and not isinstance(config["max_restarts"], int):
            self.logger.error("bridge.max_restarts must be an integer")
            return False
        
        if "restart_cooldown" in config and not isinstance(config["restart_cooldown"], (int, float)):
            self.logger.error("bridge.restart_cooldown must be a number")
            return False
        
        if "translate_paths" in config and not isinstance(config["translate_paths"], bool):
            self.logger.error("bridge.translate_paths must be a boolean")
            return False
        
        return True
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "mcpServers": {
                "serena": {
                    "command": "/mnt/c/Python/Python312/python.exe",
                    "args": ["-m", "serena.mcp_server"],
                    "env": {
                        "PYTHONPATH": "C:\\\\Users\\\\%USERNAME%\\\\projects\\\\serena",
                        "SERENA_LOG_LEVEL": "INFO"
                    }
                }
            },
            "bridge": {
                "debug": False,
                "max_restarts": 3,
                "restart_cooldown": 10,
                "translate_paths": True
            }
        }
    
    def get_effective_config(self) -> Dict[str, Any]:
        """Get the current effective configuration (loaded + defaults)"""
        if not self.config_data:
            self.load()
        
        return self.config_data
    
    def update_server_config(self, server_name: str, updates: Dict[str, Any]) -> None:
        """Update configuration for a specific server"""
        if "mcpServers" not in self.config_data:
            self.config_data["mcpServers"] = {}
        
        if server_name not in self.config_data["mcpServers"]:
            self.config_data["mcpServers"][server_name] = {}
        
        self.config_data["mcpServers"][server_name].update(updates)
        self.logger.info(f"Updated config for server '{server_name}'")
    
    def update_bridge_config(self, updates: Dict[str, Any]) -> None:
        """Update bridge configuration"""
        if "bridge" not in self.config_data:
            self.config_data["bridge"] = {}
        
        self.config_data["bridge"].update(updates)
        self.logger.info("Updated bridge configuration")

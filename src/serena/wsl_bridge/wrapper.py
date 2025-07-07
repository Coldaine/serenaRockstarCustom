#!/usr/bin/env python3
"""
MCP WSL Bridge Wrapper

A transparent stdio bridge that connects Claude Code (in WSL) to Serena (on Windows)
for optimal file access performance.
"""

import sys
import os
import json
import threading
import subprocess
import time
import signal
import uuid
from pathlib import Path
from typing import Dict, Any, Optional
import logging


class MCPWSLBridge:
    """WSL Bridge that forwards MCP communication between Claude Code and Windows Serena"""
    
    def __init__(self, config_path: Optional[str] = None, debug: bool = False):
        self.workspace_id = self._generate_workspace_id()
        self.server_process = None
        self.shutdown_event = threading.Event()
        self.debug = debug
        
        # Setup logging first
        self._setup_logging()
        
        # Load configuration
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _generate_workspace_id(self):
        """Generate unique ID for this workspace/VS Code instance"""
        return f"wsl_bridge_{os.getpid()}_{int(time.time())}"
    
    def _get_default_config_path(self):
        """Get the default configuration file path"""
        config_dir = Path.home() / ".config" / "serena"
        return config_dir / "wsl_bridge.json"
    
    def _load_config(self):
        """Load WSL Bridge configuration"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                self._log(f"Loaded config from {self.config_path}")
                return config
        except FileNotFoundError:
            self._log(f"Config file not found at {self.config_path}, using defaults")
            return self._get_default_config()
        except Exception as e:
            self._log(f"Failed to load config from {self.config_path}: {e}")
            sys.exit(1)
    
    def _get_default_config(self):
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
    
    def _setup_logging(self):
        """Setup logging for the bridge"""
        log_level = logging.DEBUG if self.debug else logging.INFO
        
        # Use Windows-compatible temp directory
        import tempfile
        log_file = os.path.join(tempfile.gettempdir(), f'serena_bridge_{self.workspace_id}.log')
        
        logging.basicConfig(
            level=log_level,
            format=f'[WSL-Bridge-{self.workspace_id}] %(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stderr),
                logging.FileHandler(log_file)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _log(self, message):
        """Log to stderr and file (VS Code can see this in MCP server output)"""
        self.logger.info(message)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self._log(f"Received signal {signum}, shutting down...")
        self.shutdown()
    
    def _translate_paths_recursive(self, obj):
        """Recursively translate WSL paths to Windows paths in MCP messages"""
        if not self.config.get("bridge", {}).get("translate_paths", True):
            return obj
            
        if isinstance(obj, dict):
            return {k: self._translate_paths_recursive(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._translate_paths_recursive(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith("/mnt/"):
            # Convert /mnt/c/path/to/file to C:\path\to\file
            parts = obj.split('/')
            if len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1:
                drive = parts[2].upper()
                windows_path = drive + ":\\" + "\\".join(parts[3:])
                self._log(f"Path translation: {obj} -> {windows_path}")
                return windows_path
        
        return obj
    
    def _start_dedicated_server(self):
        """Start a dedicated Serena MCP server on Windows"""
        try:
            # Get the first (and likely only) server config
            server_name = next(iter(self.config['mcpServers'].keys()))
            server_config = self.config['mcpServers'][server_name]
            
            self._log(f"Starting dedicated {server_name} server for workspace {self.workspace_id}")
            
            # Prepare environment variables
            env = os.environ.copy()
            if 'env' in server_config:
                env.update(server_config['env'])
            
            # Start the MCP server process on Windows
            self.server_process = subprocess.Popen(
                [server_config['command']] + server_config['args'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=server_config.get('cwd', '.'),
                env=env
            )
            
            # Give it a moment to start
            time.sleep(0.5)
            
            # Check if it started successfully
            if self.server_process.poll() is not None:
                stderr_output = self.server_process.stderr.read() if self.server_process.stderr else "No error output"
                self._log(f"Server failed to start. Exit code: {self.server_process.returncode}")
                self._log(f"Server stderr: {stderr_output}")
                return False
            
            self._log(f"Successfully started {server_name} server (PID: {self.server_process.pid})")
            return True
            
        except Exception as e:
            self._log(f"Error starting server: {e}")
            return False
    
    def _forward_stdin_to_server(self):
        """Forward stdin from Claude Code to the Serena MCP server with path translation"""
        try:
            while not self.shutdown_event.is_set() and self.server_process and self.server_process.poll() is None:
                try:
                    # Read line from Claude Code
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        break
                    
                    # Parse and translate paths in MCP messages
                    try:
                        message = json.loads(line.strip())
                        translated_message = self._translate_paths_recursive(message)
                        translated_line = json.dumps(translated_message) + '\n'
                        
                        if self.debug and message != translated_message:
                            self._log(f"Translated message: {line.strip()} -> {translated_line.strip()}")
                    except json.JSONDecodeError:
                        # Not a JSON message, pass through as-is
                        translated_line = line
                    
                    # Check if server is still alive before writing
                    if self.server_process and self.server_process.poll() is None and self.server_process.stdin:
                        self.server_process.stdin.write(translated_line)
                        self.server_process.stdin.flush()
                        
                except (BrokenPipeError, OSError) as e:
                    self._log(f"Stdin forwarding error: {e}")
                    break
                    
        except Exception as e:
            self._log(f"Error in stdin forwarding: {e}")
        finally:
            self._log("Stdin forwarding stopped")
    
    def _forward_server_to_stdout(self):
        """Forward output from Serena MCP server to Claude Code"""
        try:
            while not self.shutdown_event.is_set() and self.server_process and self.server_process.poll() is None:
                try:
                    # Check if server is still alive before reading
                    if self.server_process and self.server_process.poll() is None and self.server_process.stdout:
                        line = self.server_process.stdout.readline()
                        if not line:  # EOF
                            break
                        
                        # Forward to Claude Code
                        sys.stdout.write(line)
                        sys.stdout.flush()
                        
                except (BrokenPipeError, OSError) as e:
                    self._log(f"Stdout forwarding error: {e}")
                    break
                    
        except Exception as e:
            self._log(f"Error in stdout forwarding: {e}")
        finally:
            self._log("Stdout forwarding stopped")
    
    def _monitor_server_stderr(self):
        """Monitor server stderr for debugging"""
        try:
            while not self.shutdown_event.is_set() and self.server_process and self.server_process.poll() is None:
                try:
                    # Check if server is still alive before reading
                    if self.server_process and self.server_process.poll() is None and self.server_process.stderr:
                        line = self.server_process.stderr.readline()
                        if not line:
                            break
                        
                        # Log server errors to our stderr
                        self._log(f"Server stderr: {line.strip()}")
                        
                except Exception as e:
                    self._log(f"Error monitoring server stderr: {e}")
                    break
                    
        except Exception as e:
            self._log(f"Error in stderr monitoring: {e}")
    
    def run(self):
        """Main execution loop"""
        self._log("Starting MCP WSL Bridge...")
        
        # Start the dedicated MCP server
        if not self._start_dedicated_server():
            self._log("Failed to start MCP server, exiting")
            sys.exit(1)
        
        # Start forwarding threads
        stdin_thread = threading.Thread(
            target=self._forward_stdin_to_server,
            daemon=True,
            name=f"stdin-forward-{self.workspace_id}"
        )
        
        stdout_thread = threading.Thread(
            target=self._forward_server_to_stdout,
            daemon=True,
            name=f"stdout-forward-{self.workspace_id}"
        )
        
        stderr_thread = threading.Thread(
            target=self._monitor_server_stderr,
            daemon=True,
            name=f"stderr-monitor-{self.workspace_id}"
        )
        
        # Start all threads
        stdin_thread.start()
        stdout_thread.start()
        stderr_thread.start()
        
        self._log("MCP bridge active, forwarding communications...")
        
        try:
            # Wait for server process to end or shutdown signal
            while not self.shutdown_event.is_set():
                if self.server_process.poll() is not None:
                    self._log(f"MCP server process ended with code: {self.server_process.returncode}")
                    break
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            self._log("Received keyboard interrupt")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown of wrapper and server"""
        if self.shutdown_event.is_set():
            return  # Already shutting down
            
        self._log("Shutting down MCP WSL Bridge...")
        self.shutdown_event.set()
        
        # Terminate the MCP server
        if self.server_process and self.server_process.poll() is None:
            try:
                self._log("Terminating MCP server...")
                self.server_process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.server_process.wait(timeout=5)
                    self._log("MCP server terminated gracefully")
                except subprocess.TimeoutExpired:
                    self._log("MCP server didn't terminate gracefully, killing...")
                    self.server_process.kill()
                    self.server_process.wait()
                    
            except Exception as e:
                self._log(f"Error terminating server: {e}")
        
        self._log("MCP WSL Bridge shutdown complete")


def main():
    """Entry point for serena-wsl-bridge command"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Serena WSL Bridge - Fast file access for Claude Code")
    parser.add_argument("-c", "--config", help="Path to configuration file")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--version", action="version", version="0.1.0")
    
    args = parser.parse_args()
    
    try:
        bridge = MCPWSLBridge(config_path=args.config, debug=args.debug)
        bridge.run()
    except Exception as e:
        print(f"[WSL-Bridge] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

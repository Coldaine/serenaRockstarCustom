#!/usr/bin/env python3
"""
MCP Stdio Wrapper

A transparent stdio bridge that connects VS Code to pooled MCP servers.
Each VS Code workspace gets its own dedicated Serena server instance.
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


class MCPStdioWrapper:
    """Stdio wrapper that bridges VS Code to a pooled MCP server"""
    
    def __init__(self):
        self.workspace_id = self._generate_workspace_id()
        self.server_process = None
        self.pool_manager = None
        self.shutdown_event = threading.Event()
        
        # Load server configuration
        self.config_path = Path(__file__).parent / "server_config.json"
        self.config = self._load_config()
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _generate_workspace_id(self):
        """Generate unique ID for this workspace/VS Code instance"""
        # Use combination of PID and timestamp for uniqueness
        return f"vscode_{os.getpid()}_{int(time.time())}"
    
    def _load_config(self):
        """Load MCP server configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            self._log(f"Failed to load config from {self.config_path}: {e}")
            sys.exit(1)
    
    def _log(self, message):
        """Log to stderr (VS Code can see this in MCP server output)"""
        print(f"[MCP-Wrapper-{self.workspace_id}] {message}", file=sys.stderr, flush=True)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self._log(f"Received signal {signum}, shutting down...")
        self.shutdown()
    
    def _start_dedicated_server(self):
        """Start a dedicated MCP server for this workspace"""
        try:
            # Get the first (and likely only) server config
            server_name = next(iter(self.config['mcpServers'].keys()))
            server_config = self.config['mcpServers'][server_name]
            
            self._log(f"Starting dedicated {server_name} server for workspace {self.workspace_id}")
            
            # Start the MCP server process
            self.server_process = subprocess.Popen(
                [server_config['command']] + server_config['args'],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=server_config.get('cwd', '.'),
                env=os.environ.copy()
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
        """Forward stdin from VS Code to the MCP server"""
        try:
            while not self.shutdown_event.is_set() and self.server_process and self.server_process.poll() is None:
                try:
                    # Read line from VS Code
                    line = sys.stdin.readline()
                    if not line:  # EOF
                        break
                    
                    # Check if server is still alive before writing
                    if self.server_process and self.server_process.poll() is None and self.server_process.stdin:
                        self.server_process.stdin.write(line)
                        self.server_process.stdin.flush()
                        
                except (BrokenPipeError, OSError) as e:
                    self._log(f"Stdin forwarding error: {e}")
                    break
                    
        except Exception as e:
            self._log(f"Error in stdin forwarding: {e}")
        finally:
            self._log("Stdin forwarding stopped")
    
    def _forward_server_to_stdout(self):
        """Forward output from MCP server to VS Code"""
        try:
            while not self.shutdown_event.is_set() and self.server_process and self.server_process.poll() is None:
                try:
                    # Check if server is still alive before reading
                    if self.server_process and self.server_process.poll() is None and self.server_process.stdout:
                        line = self.server_process.stdout.readline()
                        if not line:  # EOF
                            break
                        
                        # Forward to VS Code
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
        self._log("Starting MCP Stdio Wrapper...")
        
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
            
        self._log("Shutting down MCP wrapper...")
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
        
        self._log("MCP wrapper shutdown complete")


def main():
    """Entry point"""
    try:
        wrapper = MCPStdioWrapper()
        wrapper.run()
    except Exception as e:
        print(f"[MCP-Wrapper] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
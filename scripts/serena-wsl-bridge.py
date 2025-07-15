#!/usr/bin/env python3
"""
Serena Workspace Isolation Bridge - MCP Stdio Wrapper

Provides isolated Serena server instances for multiple workspaces/clients.
Each workspace gets its own dedicated Serena server instance to prevent conflicts.

Usage:
    python serena_wsl_bridge.py [--debug] [--config path/to/config.json]

Configuration:
    Create server_config.json in the same directory or specify with --config:
    {
        "mcpServers": {
            "serena": {
                "command": "C:\\Python312\\python.exe",
                "args": ["-m", "serena.mcp_server"],
                "env": {"SERENA_LOG_LEVEL": "INFO"}
            }
        }
    }
"""

import sys
import os
import json
import threading
import subprocess
import time
import signal
import argparse
import select
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import tempfile


import tempfile

class SerenaWorkspaceIsolationBridge:
    """Workspace isolation bridge for Serena MCP server - provides dedicated server instances per workspace"""
    
    def __init__(self, config_path: Optional[Path] = None, debug: bool = False):
        self.workspace_id = self._generate_workspace_id()
        self.server_process = None
        self.shutdown_event = threading.Event()
        
        # Configuration
        self.config_path = config_path or Path(__file__).parent / "server_config.json"
        self.debug_mode = debug or os.environ.get('SERENA_BRIDGE_DEBUG', '0') == '1'

        # Debug logging
        self.debug_log_file = None
        if self.debug_mode:
            log_dir = tempfile.gettempdir()
            log_path = Path(log_dir) / f'serena_bridge_{self.workspace_id}.log'
            self.debug_log_file = open(log_path, 'w')
            self._log(f"Debug logging enabled: {log_path}")

        self.config = self._load_config()
        
        # Health monitoring
        self.restart_count = 0
        self.max_restarts = int(os.environ.get('SERENA_BRIDGE_MAX_RESTARTS', '3'))
        self.restart_cooldown = int(os.environ.get('SERENA_BRIDGE_RESTART_COOLDOWN', '10'))
        self.last_restart_time = 0
        
        # Path translation
        self.translate_paths = os.environ.get('SERENA_BRIDGE_TRANSLATE_PATHS', '1') == '1'
        
        # Performance tracking
        self.message_count_in = 0
        self.message_count_out = 0
        self.start_time = time.time()
        
        # Signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _generate_workspace_id(self) -> str:
        """Generate unique ID for this workspace instance"""
        return f"serena_wsl_{os.getpid()}_{int(time.time())}"
    
    def _log(self, message: str, level: str = "INFO"):
        """Log to stderr with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_msg = f"[{timestamp}] [{level}] [Bridge-{self.workspace_id}] {message}"
        print(log_msg, file=sys.stderr, flush=True)
        
        if self.debug_log_file:
            self.debug_log_file.write(log_msg + '\n')
            self.debug_log_file.flush()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load MCP server configuration"""
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                self._log(f"Loaded config from {self.config_path}")
                return config
        except FileNotFoundError:
            self._log(f"Config file not found at {self.config_path}, using defaults", "WARN")
            return self._get_default_config()
        except Exception as e:
            self._log(f"Failed to load config: {e}", "ERROR")
            sys.exit(1)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        # Try to find Python on Windows
        python_paths = [
            "E:\_ProjectBroadside\serena\.venv\Scripts\python.exe",
            "C:\Python312\python.exe",
            "C:\Python311\python.exe",
            "C:\Python310\python.exe",
            "C:\Python39\python.exe",
            "/mnt/e/_ProjectBroadside/serena/.venv/Scripts/python.exe",
            "/mnt/c/Python312/python.exe",
            "/mnt/c/Python311/python.exe",
            "/mnt/c/Python310/python.exe",
            "/mnt/c/Python39/python.exe",
        ]
        
        python_exe = "python"  # fallback
        for path in python_paths:
            if os.path.exists(path):
                python_exe = path
                self._log(f"Found Python at: {python_exe}")
                break
        
        return {
            "mcpServers": {
                "serena": {
                    "command": python_exe,
                    "args": ["-m", "serena.mcp_server"],
                    "env": {}
                }
            }
        }
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self._log(f"Received signal {signum}, initiating shutdown...")
        self.shutdown()
    
    def _translate_wsl_to_windows_command(self, command: str, args: List[str]) -> List[str]:
        """Convert WSL paths to Windows commands"""
        # If command is already using cmd.exe, return as-is
        if command == "cmd.exe" or command.endswith("\\cmd.exe"):
            return [command] + args
        
        # Check if command is a WSL path
        if command.startswith('/mnt/'):
            # Convert /mnt/c/... to C:\...
            parts = command.split('/')
            if len(parts) > 2 and len(parts[2]) == 1:
                drive = parts[2].upper()
                win_path = f"{drive}:\\" + "\\".join(parts[3:])
                self._log(f"Translated command path: {command} -> {win_path}")
                
                # For Python files, use Python interpreter
                if win_path.endswith('.py'):
                    return ['cmd.exe', '/c', 'python', win_path] + args
                else:
                    return ['cmd.exe', '/c', win_path] + args
        
        # For Python commands, try to use Windows Python
        if command in ['python', 'python3']:
            # Find Windows Python
            for path in ['C:\\Python312\\python.exe', 'C:\\Python311\\python.exe', 
                        'C:\\Python310\\python.exe', 'C:\\Python39\\python.exe']:
                if os.path.exists(path.replace('\\', '/')):
                    return ['cmd.exe', '/c', path] + args
        
        # Return command as-is if no translation needed
        return [command] + args
    
    def _start_serena_server(self) -> bool:
        """Start Serena server on Windows"""
        try:
            # Get server configuration
            server_name = next(iter(self.config['mcpServers'].keys()))
            server_config = self.config['mcpServers'][server_name]
            
            self._log(f"Starting {server_name} server for workspace {self.workspace_id}")
            
            # Translate command for Windows execution
            full_command = self._translate_wsl_to_windows_command(
                server_config['command'],
                server_config.get('args', [])
            )
            
            # Prepare environment
            env = os.environ.copy()
            if 'env' in server_config:
                env.update(server_config['env'])
            
            self._log(f"Executing: {' '.join(full_command)}")
            time.sleep(0.1)
            
            # Start the server process
            self.server_process = subprocess.Popen(
                full_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                cwd=server_config.get('cwd', '.'),
                env=env
            )
            
            # Wait briefly for server to start
            time.sleep(1.0)
            
            # Check if it started successfully
            if self.server_process.poll() is not None:
                stderr_output = self.server_process.stderr.read() if self.server_process.stderr else "No error output"
                self._log(f"Server failed to start. Exit code: {self.server_process.returncode}", "ERROR")
                self._log(f"Server stderr: {stderr_output}", "ERROR")
                return False
            
            self._log(f"Successfully started {server_name} server (PID: {self.server_process.pid})")
            return True
            
        except Exception as e:
            self._log(f"Error starting server: {e}", "ERROR")
            return False
    
    def _translate_path_in_string(self, text: str, to_windows: bool) -> str:
        """Translate paths in a string"""
        if not self.translate_paths:
            return text
        
        if to_windows:
            # WSL to Windows: /mnt/c/Users/... -> C:\Users\...
            if '/mnt/c/' in text:
                text = text.replace('/mnt/c/', 'C:\\').replace('/', '\\')
            if '/mnt/d/' in text:
                text = text.replace('/mnt/d/', 'D:\\').replace('/', '\\')
        else:
            # Windows to WSL: C:\Users\... -> /mnt/c/Users/...
            if 'C:\\' in text:
                text = text.replace('C:\\', '/mnt/c/').replace('\\', '/')
            if 'D:\\' in text:
                text = text.replace('D:\\', '/mnt/d/').replace('\\', '/')
        
        return text
    
    def _translate_paths_in_json(self, json_line: str, to_windows: bool) -> str:
        """Translate file paths within JSON-RPC messages"""
        if not self.translate_paths:
            return json_line
        
        try:
            # Parse JSON
            data = json.loads(json_line.strip())
            
            # Convert to string for simple path replacement
            json_str = json.dumps(data)
            translated_str = self._translate_path_in_string(json_str, to_windows)
            
            # Parse back and return as JSON line
            if json_str != translated_str:
                self._log(f"Translated paths in message", "DEBUG")
            
            return translated_str + '\n'
            
        except json.JSONDecodeError:
            # Not valid JSON, return as-is
            return json_line
        except Exception as e:
            self._log(f"Error translating paths: {e}", "ERROR")
            return json_line
    
    def _forward_stdin_to_server(self):
        """Forward stdin from Claude Code to Serena"""
        self._log("Starting stdin forwarding thread")
        
        try:
            while not self.shutdown_event.is_set():
                # Use select for non-blocking read with timeout
                if sys.platform != 'win32':
                    readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                    if not readable:
                        continue
                
                line = sys.stdin.readline()
                if not line:  # EOF
                    self._log("Stdin EOF received")
                    break
                
                self.message_count_in += 1
                
                if self.debug_mode:
                    self._log(f">>> FROM CLAUDE: {line.strip()}", "DEBUG")
                
                # Translate paths if needed
                translated_line = self._translate_paths_in_json(line, to_windows=True)
                
                # Forward to server
                if self.server_process and self.server_process.poll() is None:
                    self.server_process.stdin.write(translated_line)
                    self.server_process.stdin.flush()
                else:
                    self._log("Server not available for stdin forwarding", "WARN")
                    break
                    
        except Exception as e:
            self._log(f"Error in stdin forwarding: {e}", "ERROR")
        finally:
            self._log("Stdin forwarding stopped")
    
    def _forward_server_to_stdout(self):
        """Forward output from Serena to Claude Code"""
        self._log("Starting stdout forwarding thread")
        
        try:
            while not self.shutdown_event.is_set():
                if self.server_process and self.server_process.poll() is None:
                    line = self.server_process.stdout.readline()
                    if not line:  # EOF
                        self._log("Server stdout EOF")
                        break
                    
                    self.message_count_out += 1
                    
                    if self.debug_mode:
                        self._log(f"<<< FROM SERENA: {line.strip()}", "DEBUG")
                    
                    # Translate paths if needed
                    translated_line = self._translate_paths_in_json(line, to_windows=False)
                    
                    # Forward to Claude Code
                    sys.stdout.write(translated_line)
                    sys.stdout.flush()
                else:
                    # Server died, wait for health check
                    time.sleep(0.1)
                    
        except Exception as e:
            self._log(f"Error in stdout forwarding: {e}", "ERROR")
        finally:
            self._log("Stdout forwarding stopped")
    
    def _monitor_server_stderr(self):
        """Monitor Serena's stderr for debugging"""
        self._log("Starting stderr monitoring thread")
        
        try:
            while not self.shutdown_event.is_set():
                if self.server_process and self.server_process.poll() is None:
                    line = self.server_process.stderr.readline()
                    if not line:
                        break
                    
                    # Log server errors
                    self._log(f"SERENA STDERR: {line.strip()}", "WARN")
                else:
                    time.sleep(0.1)
                    
        except Exception as e:
            self._log(f"Error in stderr monitoring: {e}", "ERROR")
    
    def _health_check_loop(self):
        """Monitor server health and restart if necessary"""
        self._log("Starting health check thread")
        
        while not self.shutdown_event.is_set():
            try:
                # Check every 5 seconds
                for _ in range(50):
                    if self.shutdown_event.is_set():
                        return
                    time.sleep(0.1)
                
                # Log statistics periodically
                if self.debug_mode:
                    uptime = int(time.time() - self.start_time)
                    self._log(
                        f"Stats: uptime={uptime}s, messages_in={self.message_count_in}, "
                        f"messages_out={self.message_count_out}, restarts={self.restart_count}"
                    )
                
                # Check server health
                if self.server_process and self.server_process.poll() is not None:
                    exit_code = self.server_process.returncode
                    self._log(f"Server died with exit code: {exit_code}", "ERROR")
                    
                    # Check restart conditions
                    current_time = time.time()
                    if (current_time - self.last_restart_time) < self.restart_cooldown:
                        self._log(f"Restart cooldown active ({self.restart_cooldown}s)", "WARN")
                        continue
                    
                    if self.restart_count >= self.max_restarts:
                        self._log(f"Max restarts ({self.max_restarts}) exceeded", "ERROR")
                        self.shutdown_event.set()
                        break
                    
                    # Attempt restart
                    self.restart_count += 1
                    self.last_restart_time = current_time
                    self._log(f"Attempting restart {self.restart_count}/{self.max_restarts}")
                    
                    if self._start_serena_server():
                        self._log("Server restarted successfully")
                        # Notify Claude Code about restart
                        notification = {
                            "jsonrpc": "2.0",
                            "method": "$/serena/restarted",
                            "params": {
                                "reason": f"Exit code {exit_code}",
                                "restartCount": self.restart_count
                            }
                        }
                        sys.stdout.write(json.dumps(notification) + '\n')
                        sys.stdout.flush()
                    else:
                        self._log("Failed to restart server", "ERROR")
                        self.shutdown_event.set()
                        break
                        
            except Exception as e:
                self._log(f"Error in health check: {e}", "ERROR")
    
    def run(self):
        """Main execution loop"""
        self._log("Serena Workspace Isolation Bridge starting...")
        self._log(f"Configuration: {self.config_path}")
        self._log(f"Settings: debug={self.debug_mode}, max_restarts={self.max_restarts}, translate_paths={self.translate_paths}")
        
        # Start Serena server on Windows
        if not self._start_serena_server():
            self._log("Failed to start Serena server, exiting", "ERROR")
            sys.exit(1)
        
        # Create threads
        threads = [
            threading.Thread(target=self._forward_stdin_to_server, daemon=True, name="stdin-forward"),
            threading.Thread(target=self._forward_server_to_stdout, daemon=True, name="stdout-forward"),
            threading.Thread(target=self._monitor_server_stderr, daemon=True, name="stderr-monitor"),
            threading.Thread(target=self._health_check_loop, daemon=True, name="health-check")
        ]
        
        # Start all threads
        for thread in threads:
            thread.start()
            self._log(f"Started thread: {thread.name}")
        
        self._log("Bridge active - forwarding MCP communication between Claude Code and Serena")
        
        try:
            # Wait for shutdown signal
            while not self.shutdown_event.is_set():
                time.sleep(0.1)
                
        except KeyboardInterrupt:
            self._log("Keyboard interrupt received")
        finally:
            self.shutdown()
    
    def shutdown(self):
        """Clean shutdown of bridge and server"""
        if self.shutdown_event.is_set():
            return
        
        self._log("Shutting down Serena Workspace Isolation Bridge...")
        self.shutdown_event.set()
        
        # Log final statistics
        uptime = int(time.time() - self.start_time)
        self._log(
            f"Final stats: uptime={uptime}s, messages_in={self.message_count_in}, "
            f"messages_out={self.message_count_out}, restarts={self.restart_count}"
        )
        
        # Terminate server
        if self.server_process and self.server_process.poll() is None:
            try:
                self._log("Terminating Serena server...")
                self.server_process.terminate()
                
                try:
                    self.server_process.wait(timeout=5)
                    self._log("Server terminated gracefully")
                except subprocess.TimeoutExpired:
                    self._log("Server didn't terminate, killing...", "WARN")
                    self.server_process.kill()
                    self.server_process.wait()
                    
            except Exception as e:
                self._log(f"Error terminating server: {e}", "ERROR")
        
        # Close debug log
        if self.debug_log_file:
            self.debug_log_file.close()
        
        self._log("Bridge shutdown complete")


def main():
    """Entry point"""
    parser = argparse.ArgumentParser(
        description="Serena Workspace Isolation Bridge - Dedicated server instances per workspace"
    )
    parser.add_argument(
        '-c', '--config',
        type=Path,
        help='Path to configuration file (default: ./server_config.json)'
    )
    parser.add_argument(
        '-d', '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    try:
        bridge = SerenaWorkspaceIsolationBridge(config_path=args.config, debug=args.debug)
        bridge.run()
    except Exception as e:
        print(f"[SerenaWorkspaceIsolationBridge] Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
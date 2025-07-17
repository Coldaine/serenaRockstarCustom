#!/usr/bin/env python3
"""
Real-time Monitor for Workspace Isolation Bridge Activity

This script monitors the activity log and displays bridge activity in real-time.
Useful for debugging and understanding bridge behavior.
"""

import os
import sys
import json
import time
import tempfile
from typing import Dict, Any, Set
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[BridgeMonitor] %(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WorkspaceIsolationBridgeMonitor:
    """Real-time monitor for bridge activity"""
    
    def __init__(self):
        self.activity_log_file = os.path.join(tempfile.gettempdir(), 'workspace_isolation_bridge_activity.log')
        self.seen_entries = set()
        self.active_workspaces: Dict[str, Dict[str, Any]] = {}
        
    def format_timestamp(self, timestamp: float) -> str:
        """Format timestamp for display"""
        return time.strftime("%H:%M:%S", time.localtime(timestamp))
    
    def process_activity(self, activity: Dict[str, Any]):
        """Process and display activity entry"""
        event_type = activity.get("event_type", "UNKNOWN")
        workspace_id = activity.get("workspace_id", "unknown")
        timestamp = activity.get("timestamp", time.time())
        data = activity.get("data", {})
        
        time_str = self.format_timestamp(timestamp)
        
        if event_type == "BRIDGE_START":
            self.active_workspaces[workspace_id] = {
                "start_time": timestamp,
                "pid": data.get("pid"),
                "debug_mode": data.get("debug_mode", False),
                "log_file": data.get("log_file"),
                "server_pid": None
            }
            
            logger.info(f"🚀 [{time_str}] NEW BRIDGE: {workspace_id}")
            logger.info(f"   └─ PID: {data.get('pid')}, Debug: {data.get('debug_mode')}")
            
        elif event_type == "SERVER_START":
            if workspace_id in self.active_workspaces:
                self.active_workspaces[workspace_id]["server_pid"] = data.get("server_pid")
            
            logger.info(f"⚡ [{time_str}] SERVER START: {workspace_id}")
            logger.info(f"   └─ Server PID: {data.get('server_pid')}, Command: {data.get('command')}")
            
        elif event_type == "BRIDGE_SHUTDOWN":
            uptime = data.get("uptime_seconds", 0)
            uptime_str = f"{uptime:.1f}s" if uptime < 60 else f"{uptime/60:.1f}m"
            
            logger.info(f"🛑 [{time_str}] BRIDGE SHUTDOWN: {workspace_id}")
            logger.info(f"   └─ Uptime: {uptime_str}, Server PID: {data.get('server_pid')}")
            
            if workspace_id in self.active_workspaces:
                del self.active_workspaces[workspace_id]
        
        else:
            logger.info(f"📝 [{time_str}] {event_type}: {workspace_id}")
            if data:
                logger.info(f"   └─ Data: {json.dumps(data, indent=6)}")
    
    def display_status(self):
        """Display current status of active workspaces"""
        if not self.active_workspaces:
            logger.info("📊 STATUS: No active workspaces")
            return
        
        logger.info(f"📊 STATUS: {len(self.active_workspaces)} active workspace(s)")
        
        for workspace_id, info in self.active_workspaces.items():
            uptime = time.time() - info["start_time"]
            uptime_str = f"{uptime:.0f}s" if uptime < 60 else f"{uptime/60:.1f}m"
            
            short_id = workspace_id.split("_")[-2:]  # Show last 2 parts (pid_timestamp)
            short_id_str = "_".join(short_id)
            
            server_info = f"Server PID: {info['server_pid']}" if info['server_pid'] else "No server"
            debug_info = " (DEBUG)" if info.get('debug_mode') else ""
            
            logger.info(f"   └─ {short_id_str}: {uptime_str} uptime, {server_info}{debug_info}")
    
    def monitor_activity(self, show_status_interval: int = 30):
        """Monitor activity log in real-time"""
        logger.info("🔍 Starting Workspace Isolation Bridge Monitor")
        logger.info(f"📁 Monitoring: {self.activity_log_file}")
        logger.info("=" * 60)
        
        last_status_time = 0
        file_position = 0
        
        # If file exists, start from the end to only show new entries
        if os.path.exists(self.activity_log_file):
            with open(self.activity_log_file, 'r', encoding='utf-8') as f:
                f.seek(0, 2)  # Seek to end
                file_position = f.tell()
        
        try:
            while True:
                current_time = time.time()
                
                # Show status periodically
                if current_time - last_status_time >= show_status_interval:
                    self.display_status()
                    last_status_time = current_time
                
                # Check for new activity
                if os.path.exists(self.activity_log_file):
                    try:
                        with open(self.activity_log_file, 'r', encoding='utf-8') as f:
                            f.seek(file_position)
                            new_lines = f.readlines()
                            file_position = f.tell()
                            
                            for line in new_lines:
                                line = line.strip()
                                if line:
                                    try:
                                        activity = json.loads(line)
                                        activity_id = f"{activity.get('timestamp')}_{activity.get('workspace_id')}"
                                        
                                        if activity_id not in self.seen_entries:
                                            self.seen_entries.add(activity_id)
                                            self.process_activity(activity)
                                            
                                    except json.JSONDecodeError as e:
                                        logger.warning(f"Could not parse activity: {line} - {e}")
                                        
                    except Exception as e:
                        logger.error(f"Error reading activity log: {e}")
                
                time.sleep(1)  # Check every second
                
        except KeyboardInterrupt:
            logger.info("\n🛑 Monitor stopped by user")
            self.display_status()

def main():
    """Main entry point"""
    monitor = WorkspaceIsolationBridgeMonitor()
    
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        # Just show current status and exit
        monitor.display_status()
    else:
        # Run continuous monitoring
        monitor.monitor_activity()

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Comprehensive Test Suite for Workspace Isolation Bridge

This script tests whether the Workspace Isolation Bridge is working correctly
by simulating multiple workspace connections and validating isolation.
"""

import os
import sys
import json
import time
import subprocess
import threading
import tempfile
from pathlib import Path
from typing import List, Dict, Any
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[BridgeTest] %(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class WorkspaceIsolationBridgeTest:
    """Test suite for validating Workspace Isolation Bridge functionality"""
    
    def __init__(self):
        self.test_results = []
        self.bridge_processes = []
        self.activity_log_file = os.path.join(tempfile.gettempdir(), 'workspace_isolation_bridge_activity.log')
        
    def log_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        result = {
            "test_name": test_name,
            "passed": passed,
            "details": details,
            "timestamp": time.time()
        }
        self.test_results.append(result)
        status = "PASS" if passed else "FAIL"
        logger.info(f"[{status}] {test_name}: {details}")
    
    def clear_activity_log(self):
        """Clear the activity log before testing"""
        try:
            if os.path.exists(self.activity_log_file):
                os.remove(self.activity_log_file)
            logger.info("Cleared activity log")
        except Exception as e:
            logger.warning(f"Could not clear activity log: {e}")
    
    def read_activity_log(self) -> List[Dict[str, Any]]:
        """Read and parse activity log entries"""
        activities = []
        try:
            if os.path.exists(self.activity_log_file):
                with open(self.activity_log_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                activities.append(json.loads(line))
                            except json.JSONDecodeError as e:
                                logger.warning(f"Could not parse activity log line: {line} - {e}")
        except Exception as e:
            logger.error(f"Error reading activity log: {e}")
        return activities
    
    def test_single_bridge_startup(self) -> bool:
        """Test 1: Single bridge starts up correctly"""
        logger.info("=== Test 1: Single Bridge Startup ===")
        
        try:
            # Start a single bridge instance
            cmd = [
                "uv", "run", "--directory", "E:\\_ProjectBroadside\\serena",
                "serena-workspace-isolation-bridge", "--debug"
            ]
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Give it time to start
            time.sleep(3)
            
            # Check if process is running
            if process.poll() is None:
                self.log_test_result("single_bridge_startup", True, "Bridge process started successfully")
                
                # Terminate the process
                process.terminate()
                process.wait(timeout=5)
                return True
            else:
                stderr_output = process.stderr.read() if process.stderr else "No error output"
                self.log_test_result("single_bridge_startup", False, f"Bridge failed to start: {stderr_output}")
                return False
                
        except Exception as e:
            self.log_test_result("single_bridge_startup", False, f"Exception during startup: {e}")
            return False
    
    def test_activity_logging(self) -> bool:
        """Test 2: Activity logging works correctly"""
        logger.info("=== Test 2: Activity Logging ===")
        
        self.clear_activity_log()
        
        try:
            # Start bridge and let it run briefly
            cmd = [
                "uv", "run", "--directory", "E:\\_ProjectBroadside\\serena",
                "serena-workspace-isolation-bridge", "--debug"
            ]
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Give it time to start and log
            time.sleep(2)
            
            # Terminate
            process.terminate()
            process.wait(timeout=5)
            
            # Check activity log
            activities = self.read_activity_log()
            
            if len(activities) >= 1:
                # Look for BRIDGE_START event
                bridge_start_found = any(
                    activity.get("event_type") == "BRIDGE_START" 
                    for activity in activities
                )
                
                if bridge_start_found:
                    self.log_test_result("activity_logging", True, f"Found {len(activities)} activity entries including BRIDGE_START")
                    return True
                else:
                    self.log_test_result("activity_logging", False, f"BRIDGE_START event not found in {len(activities)} activities")
                    return False
            else:
                self.log_test_result("activity_logging", False, "No activity log entries found")
                return False
                
        except Exception as e:
            self.log_test_result("activity_logging", False, f"Exception during activity logging test: {e}")
            return False
    
    def test_multiple_bridge_isolation(self) -> bool:
        """Test 3: Multiple bridges create separate workspace IDs"""
        logger.info("=== Test 3: Multiple Bridge Isolation ===")
        
        self.clear_activity_log()
        
        try:
            processes = []
            
            # Start 3 bridge instances simultaneously
            for i in range(3):
                cmd = [
                    "uv", "run", "--directory", "E:\\_ProjectBroadside\\serena",
                    "serena-workspace-isolation-bridge", "--debug"
                ]
                
                process = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                processes.append(process)
                
                # Small delay between starts
                time.sleep(0.5)
            
            # Let them all run for a bit
            time.sleep(3)
            
            # Terminate all
            for process in processes:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except:
                    pass
            
            # Analyze activity log
            activities = self.read_activity_log()
            
            # Extract unique workspace IDs
            workspace_ids = set()
            bridge_starts = 0
            
            for activity in activities:
                if activity.get("event_type") == "BRIDGE_START":
                    bridge_starts += 1
                    workspace_id = activity.get("workspace_id")
                    if workspace_id:
                        workspace_ids.add(workspace_id)
            
            if len(workspace_ids) >= 3 and bridge_starts >= 3:
                self.log_test_result("multiple_bridge_isolation", True, 
                                   f"Found {len(workspace_ids)} unique workspace IDs from {bridge_starts} bridge starts")
                return True
            else:
                self.log_test_result("multiple_bridge_isolation", False, 
                                   f"Expected 3+ unique workspace IDs, found {len(workspace_ids)} from {bridge_starts} starts")
                return False
                
        except Exception as e:
            self.log_test_result("multiple_bridge_isolation", False, f"Exception during isolation test: {e}")
            return False
    
    def test_workspace_id_format(self) -> bool:
        """Test 4: Workspace ID format is correct"""
        logger.info("=== Test 4: Workspace ID Format ===")
        
        self.clear_activity_log()
        
        try:
            # Start a bridge
            cmd = [
                "uv", "run", "--directory", "E:\\_ProjectBroadside\\serena",
                "serena-workspace-isolation-bridge", "--debug"
            ]
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            time.sleep(2)
            process.terminate()
            process.wait(timeout=5)
            
            # Check workspace ID format
            activities = self.read_activity_log()
            
            for activity in activities:
                if activity.get("event_type") == "BRIDGE_START":
                    workspace_id = activity.get("workspace_id")
                    if workspace_id and workspace_id.startswith("workspace_isolation_bridge_"):
                        parts = workspace_id.split("_")
                        if len(parts) >= 4:  # workspace_isolation_bridge_{pid}_{timestamp}
                            self.log_test_result("workspace_id_format", True, 
                                               f"Workspace ID format correct: {workspace_id}")
                            return True
            
            self.log_test_result("workspace_id_format", False, "Workspace ID format incorrect or not found")
            return False
            
        except Exception as e:
            self.log_test_result("workspace_id_format", False, f"Exception during ID format test: {e}")
            return False
    
    def test_log_file_creation(self) -> bool:
        """Test 5: Individual log files are created per workspace"""
        logger.info("=== Test 5: Log File Creation ===")
        
        try:
            # Start a bridge
            cmd = [
                "uv", "run", "--directory", "E:\\_ProjectBroadside\\serena",
                "serena-workspace-isolation-bridge", "--debug"
            ]
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            time.sleep(2)
            process.terminate()
            process.wait(timeout=5)
            
            # Check for log files in temp directory
            temp_dir = tempfile.gettempdir()
            log_files = [f for f in os.listdir(temp_dir) if f.startswith("serena_bridge_workspace_isolation_bridge_")]
            
            if len(log_files) >= 1:
                self.log_test_result("log_file_creation", True, 
                                   f"Found {len(log_files)} bridge log files")
                return True
            else:
                self.log_test_result("log_file_creation", False, "No bridge log files found")
                return False
                
        except Exception as e:
            self.log_test_result("log_file_creation", False, f"Exception during log file test: {e}")
            return False
    
    def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests and return summary"""
        logger.info("🚀 Starting Workspace Isolation Bridge Test Suite")
        logger.info("=" * 60)
        
        start_time = time.time()
        
        # Run all tests
        tests = [
            self.test_single_bridge_startup,
            self.test_activity_logging,
            self.test_multiple_bridge_isolation,
            self.test_workspace_id_format,
            self.test_log_file_creation
        ]
        
        passed_tests = 0
        total_tests = len(tests)
        
        for test_func in tests:
            try:
                if test_func():
                    passed_tests += 1
            except Exception as e:
                logger.error(f"Test {test_func.__name__} failed with exception: {e}")
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Generate summary
        summary = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "success_rate": (passed_tests / total_tests) * 100,
            "duration_seconds": duration,
            "test_results": self.test_results
        }
        
        logger.info("=" * 60)
        logger.info("🎯 TEST SUMMARY")
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests}")
        logger.info(f"Failed: {total_tests - passed_tests}")
        logger.info(f"Success Rate: {summary['success_rate']:.1f}%")
        logger.info(f"Duration: {duration:.2f} seconds")
        
        if passed_tests == total_tests:
            logger.info("✅ ALL TESTS PASSED - Workspace Isolation Bridge is working correctly!")
        else:
            logger.warning("❌ SOME TESTS FAILED - Check the details above")
        
        return summary

def main():
    """Main entry point"""
    test_suite = WorkspaceIsolationBridgeTest()
    summary = test_suite.run_all_tests()
    
    # Exit with appropriate code
    if summary["failed_tests"] == 0:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()
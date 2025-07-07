#!/usr/bin/env python3
"""
WSL Bridge Performance Metrics

Tracks performance metrics for the WSL Bridge to help optimize and debug
file access performance improvements.
"""

import time
import threading
from collections import defaultdict, deque
from typing import Dict, Any, Optional
import logging
import json


class BridgeMetrics:
    """Performance metrics tracker for WSL Bridge"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.lock = threading.Lock()
        
        # Request metrics
        self.request_counts = defaultdict(int)
        self.request_durations = defaultdict(list)
        self.request_history = deque(maxlen=max_history)
        
        # Error metrics
        self.error_counts = defaultdict(int)
        self.error_history = deque(maxlen=max_history)
        
        # System metrics
        self.start_time = time.time()
        self.total_requests = 0
        self.total_errors = 0
        
        # Path translation metrics
        self.path_translations = 0
        self.translation_patterns = defaultdict(int)
        
        self.logger = logging.getLogger(__name__)
    
    def record_request(self, method: str, duration: float, success: bool = True) -> None:
        """Record a request with its duration"""
        with self.lock:
            self.total_requests += 1
            self.request_counts[method] += 1
            
            # Keep only recent durations to prevent memory growth
            if len(self.request_durations[method]) >= 100:
                self.request_durations[method].pop(0)
            self.request_durations[method].append(duration)
            
            # Record in history
            self.request_history.append({
                'timestamp': time.time(),
                'method': method,
                'duration': duration,
                'success': success
            })
            
            if duration > 1.0:  # Log slow requests
                self.logger.warning(f"Slow request: {method} took {duration:.2f}s")
    
    def record_error(self, error_type: str, context: Optional[str] = None) -> None:
        """Record an error occurrence"""
        with self.lock:
            self.total_errors += 1
            self.error_counts[error_type] += 1
            
            self.error_history.append({
                'timestamp': time.time(),
                'error_type': error_type,
                'context': context
            })
            
            self.logger.info(f"Recorded error: {error_type}")
    
    def record_path_translation(self, from_path: str, to_path: str) -> None:
        """Record a path translation"""
        with self.lock:
            self.path_translations += 1
            
            # Extract pattern (e.g., /mnt/c/ -> C:\)
            if from_path.startswith("/mnt/"):
                pattern = f"{from_path.split('/')[1]}/{from_path.split('/')[2]}/ -> {to_path.split(':')[0]}:\\"
                self.translation_patterns[pattern] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        with self.lock:
            uptime = time.time() - self.start_time
            
            # Calculate request statistics
            request_stats = {}
            for method, durations in self.request_durations.items():
                if durations:
                    request_stats[method] = {
                        'count': self.request_counts[method],
                        'avg_duration': sum(durations) / len(durations),
                        'min_duration': min(durations),
                        'max_duration': max(durations),
                        'recent_durations': list(durations)[-10:]  # Last 10 requests
                    }
            
            # Calculate error rates
            error_rate = (self.total_errors / max(self.total_requests, 1)) * 100
            
            # Calculate requests per second
            rps = self.total_requests / max(uptime, 1)
            
            return {
                'uptime_seconds': uptime,
                'total_requests': self.total_requests,
                'total_errors': self.total_errors,
                'error_rate_percent': error_rate,
                'requests_per_second': rps,
                'request_stats': request_stats,
                'error_counts': dict(self.error_counts),
                'path_translations': {
                    'total': self.path_translations,
                    'patterns': dict(self.translation_patterns)
                },
                'recent_requests': list(self.request_history)[-10:],
                'recent_errors': list(self.error_history)[-10:]
            }
    
    def get_performance_summary(self) -> str:
        """Get a human-readable performance summary"""
        stats = self.get_stats()
        
        summary = []
        summary.append(f"WSL Bridge Performance Summary")
        summary.append(f"==============================")
        summary.append(f"Uptime: {stats['uptime_seconds']:.1f}s")
        summary.append(f"Total Requests: {stats['total_requests']}")
        summary.append(f"Total Errors: {stats['total_errors']}")
        summary.append(f"Error Rate: {stats['error_rate_percent']:.1f}%")
        summary.append(f"Requests/sec: {stats['requests_per_second']:.2f}")
        summary.append(f"Path Translations: {stats['path_translations']['total']}")
        
        if stats['request_stats']:
            summary.append(f"\nRequest Performance:")
            for method, stats_data in stats['request_stats'].items():
                avg_ms = stats_data['avg_duration'] * 1000
                summary.append(f"  {method}: {stats_data['count']} requests, avg {avg_ms:.1f}ms")
        
        if stats['error_counts']:
            summary.append(f"\nError Breakdown:")
            for error_type, count in stats['error_counts'].items():
                summary.append(f"  {error_type}: {count}")
        
        return "\n".join(summary)
    
    def reset(self) -> None:
        """Reset all metrics"""
        with self.lock:
            self.request_counts.clear()
            self.request_durations.clear()
            self.request_history.clear()
            self.error_counts.clear()
            self.error_history.clear()
            self.translation_patterns.clear()
            
            self.start_time = time.time()
            self.total_requests = 0
            self.total_errors = 0
            self.path_translations = 0
            
            self.logger.info("Metrics reset")
    
    def export_to_file(self, filepath: str) -> None:
        """Export metrics to a JSON file"""
        try:
            stats = self.get_stats()
            with open(filepath, 'w') as f:
                json.dump(stats, f, indent=2, default=str)
            
            self.logger.info(f"Metrics exported to {filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to export metrics to {filepath}: {e}")
            raise
    
    def get_recent_performance(self, seconds: int = 60) -> Dict[str, Any]:
        """Get performance stats for the recent time period"""
        cutoff_time = time.time() - seconds
        
        with self.lock:
            recent_requests = [r for r in self.request_history if r['timestamp'] > cutoff_time]
            recent_errors = [e for e in self.error_history if e['timestamp'] > cutoff_time]
            
            if not recent_requests:
                return {
                    'period_seconds': seconds,
                    'request_count': 0,
                    'error_count': 0,
                    'avg_duration': 0,
                    'requests_per_second': 0
                }
            
            total_duration = sum(r['duration'] for r in recent_requests)
            avg_duration = total_duration / len(recent_requests)
            rps = len(recent_requests) / seconds
            
            return {
                'period_seconds': seconds,
                'request_count': len(recent_requests),
                'error_count': len(recent_errors),
                'avg_duration': avg_duration,
                'requests_per_second': rps,
                'success_rate': (len([r for r in recent_requests if r.get('success', True)]) / len(recent_requests)) * 100
            }


class MetricsContextManager:
    """Context manager for timing operations"""
    
    def __init__(self, metrics: BridgeMetrics, operation_name: str):
        self.metrics = metrics
        self.operation_name = operation_name
        self.start_time = None
        self.success = True
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time:
            duration = time.time() - self.start_time
            self.success = exc_type is None
            self.metrics.record_request(self.operation_name, duration, self.success)
        
        return False  # Don't suppress exceptions

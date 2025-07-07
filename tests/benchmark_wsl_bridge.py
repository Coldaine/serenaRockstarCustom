"""Benchmark file access performance with and without the bridge"""

import time
import subprocess
import statistics

def benchmark_direct_wsl_access():
    """Benchmark direct file access from WSL"""
    times = []
    test_file = "/mnt/c/Windows/System32/drivers/etc/hosts"
    
    for _ in range(100):
        start = time.time()
        with open(test_file, 'r') as f:
            content = f.read()
        times.append((time.time() - start) * 1000)  # ms
    
    return {
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'stdev': statistics.stdev(times),
        'min': min(times),
        'max': max(times)
    }

def benchmark_windows_native():
    """Benchmark native Windows file access"""
    times = []
    
    for _ in range(100):
        start = time.time()
        result = subprocess.run(
            ['powershell.exe', '-Command', 
             '[IO.File]::ReadAllText("C:\\Windows\\System32\\drivers\\etc\\hosts")'],
            capture_output=True,
            text=True
        )
        times.append((time.time() - start) * 1000)  # ms
    
    return {
        'mean': statistics.mean(times),
        'median': statistics.median(times),
        'stdev': statistics.stdev(times),
        'min': min(times),
        'max': max(times)
    }

if __name__ == "__main__":
    print("Benchmarking file access performance...\n")
    
    print("Direct WSL access (/mnt/c/):")
    wsl_stats = benchmark_direct_wsl_access()
    for key, value in wsl_stats.items():
        print(f"  {key}: {value:.2f}ms")
    
    print("\nWindows native access (PowerShell):")
    win_stats = benchmark_windows_native()
    for key, value in win_stats.items():
        print(f"  {key}: {value:.2f}ms")
    
    speedup = wsl_stats['mean'] / win_stats['mean']
    print(f"\nSpeedup: {speedup:.1f}x")

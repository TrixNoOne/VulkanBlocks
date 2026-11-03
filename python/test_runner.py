#!/usr/bin/env python3
import subprocess, time, urllib.request, sys, os

# Start the server
print("Starting Vulkan Node server...")
proc = subprocess.Popen(
    [sys.executable, '-m', 'vulkan.start_node'],
    cwd=r'C:\Users\Trix\Desktop\VulkanBlocks\python',
    stdout=subprocess.PIPE, 
    stderr=subprocess.PIPE
)

# Wait for startup
time.sleep(3)

# Test endpoints
try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/chain/info', timeout=5)
    data = r.read().decode()
    print("chain/info:", data)
except Exception as e:
    print("chain/info error:", e)

try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/mempool/status', timeout=5)
    data = r.read().decode()
    print("mempool/status:", data)
except Exception as e:
    print("mempool/status error:", e)

# Kill the server
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

print("Done testing. Server stopped.")
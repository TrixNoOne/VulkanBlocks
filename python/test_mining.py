#!/usr/bin/env python3
import subprocess, time, urllib.request, urllib.error, json, sys

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

# Test mining
print("\nMining a new block...")
try:
    req = urllib.request.Request(
        'http://127.0.0.1:8000/miner/mine',
        data=json.dumps({"transactions": [], "minerAddress": "VUL1address"}).encode(),
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    r = urllib.request.urlopen(req, timeout=30)
    data = r.read().decode()
    print("mine response:", data)
    
    # Check chain info after mining
    time.sleep(1)
    r = urllib.request.urlopen('http://127.0.0.1:8000/chain/info', timeout=5)
    data = r.read().decode()
    print("chain/info after mine:", data)
except urllib.error.HTTPError as e:
    print("mine HTTP error:", e.code, e.read().decode())
except Exception as e:
    print("mine error:", e)

# Kill the server
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

print("Done. Server stopped.")
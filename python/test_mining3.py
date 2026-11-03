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

# Test chain info first
print("\n1. Checking chain info...")
try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/chain/info', timeout=5)
    data = r.read().decode()
    print("   chain/info:", data)
except Exception as e:
    print("   chain/info error:", e)

# Test mempool
print("\n2. Checking mempool status...")
try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/mempool/status', timeout=5)
    data = r.read().decode()
    print("   mempool/status:", data)
except Exception as e:
    print("   mempool/status error:", e)

# Test mining with shorter PoW (lower difficulty)
print("\n3. Attempting to mine a block (this may take a moment)...")
try:
    req = urllib.request.Request(
        'http://127.0.0.1:8000/miner/mine',
        data=json.dumps({"transactions": [], "minerAddress": "VUL1address"}).encode(),
        method='POST',
        headers={'Content-Type': 'application/json'}
    )
    import threading
    import concurrent.futures
    
    # Run with timeout
    result = [None]
    error = [None]
    
    def mine():
        try:
            r = urllib.request.urlopen(req, timeout=15)
            result[0] = r.read().decode()
        except Exception as e:
            error[0] = str(e)
    
    t = threading.Thread(target=mine)
    t.start()
    t.join(timeout=15)
    
    if t.is_alive():
        print("   mine timed out - PoW taking too long")
    elif error[0]:
        print("   mine error:", error[0])
    else:
        data = result[0]
        print("   mine response:", data)
        # Check chain info after
        time.sleep(1)
        try:
            r = urllib.request.urlopen('http://127.0.0.1:8000/chain/info', timeout=5)
            data = r.read().decode()
            print("   chain/info after mine:", data)
        except Exception as e:
            print("   chain/info after mine error:", e)
except Exception as e:
    print("   mine exception:", e)

# Kill the server
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

print("Done. Server stopped.")
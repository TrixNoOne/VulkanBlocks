import urllib.request, json, time

# Wait a moment for server to be ready
time.sleep(2)

try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/chain/info', timeout=5)
    print("chain/info:", r.read().decode())
except Exception as e:
    print("chain/info error:", e)

try:
    r = urllib.request.urlopen('http://127.0.0.1:8000/mempool/status', timeout=5)
    print("mempool/status:", r.read().decode())
except Exception as e:
    print("mempool/status error:", e)
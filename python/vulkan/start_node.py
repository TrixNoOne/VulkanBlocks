"""
Vulkan Node Startup Script

Initializes the in-memory chainstate, loads the genesis block,
and starts the FastAPI RPC server.
"""

import sys
import os

# Add the venv site-packages path so vulkan_core can be found
# __file__ is at python/vulkan/start_node.py, so going up twice gives project root
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
venv_sp = os.path.join(project_root, ".venv", "Lib", "site-packages")
if os.path.isdir(venv_sp):
    sys.path.insert(0, venv_sp)

# Add the python directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vulkan.node.main import start_server

if __name__ == "__main__":
    print("=" * 60)
    print("VULKAN BLOCKCHAIN NODE")
    print("=" * 60)
    print()
    print("Initializing chainstate and genesis block...")
    print()
    
    # The startup is handled within the main module
    # Just start the server
    print("Starting RPC server on 127.0.0.1:8000")
    print()
    print("=" * 60)
    print("Available RPC Endpoints:")
    print("=" * 60)
    print("  GET  /chain/info    - Chain information (height, tip, difficulty)")
    print("  GET  /mempool/status - Mempool status (pending TX count)")
    print("  POST /miner/mine    - Mine a new block")
    print()
    print("=" * 60)
    print("Dashboard:")
    print("=" * 60)
    print("  Open test_dashboard.html in your browser")
    print("  to interact with the node via file:// protocol")
    print()
    print("-" * 60)
    
    start_server()
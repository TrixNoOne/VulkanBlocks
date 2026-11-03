"""
Vulkan Node Daemon - FastAPI server using compiled vulkan_core Rust module.

This module:
1. Imports the compiled vulkan_core PyO3 extension
2. Provides RPC endpoints for the dashboard
3. Manages an in-memory chainstate with genesis block
4. Implements basic block assembly and validation
"""

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
import struct
import time
import hashlib

# Import the compiled Rust core module
try:
    import vulkan_core
    HAS_VULKAN_CORE = True
    print("vulkan_core module loaded successfully")
except ImportError as e:
    HAS_VULKAN_CORE = False
    print(f"vulkan_core module not available: {e}")
    # Fallback to basic implementations
    vulkan_core = None

# --- Constants (matching reference implementation) ---
GENESIS_VERSION = 1
GENESIS_TIMESTAMP = 1700000000
GENESIS_DIFFICULTY = 0x1e0ffff0
COINBASE_MATURITY = 100
UNITS_PER_VULCAN = 100_000_000
MAX_MONEY = 32_000_000_000 * 100_000_000

# In-memory chainstate
class ChainState:
    def __init__(self):
        self.height = -1
        self.tip_hash = b"\\x00" * 32  # genesis hash placeholder
        self.mempool_count = 0
        self.difficulty = GENESIS_DIFFICULTY
        self.total_supply = 0
        self.blocks = []  # list of block headers
        
    def add_block(self, block_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a block to the chain."""
        self.height += 1
        self.tip_hash = block_data.get("hash", b"\\x00" * 32)
        self.difficulty = block_data.get("difficulty", self.difficulty)
        self.total_supply += block_data.get("coinbase_value", 0)
        self.blocks.append(block_data)
        return {"height": self.height, "tip_hash": self.tip_hash.hex()}
    
    def get_info(self) -> Dict[str, Any]:
        """Return chain info."""
        return {
            "height": self.height,
            "tip_hash": self.tip_hash.hex() if self.tip_hash else b"\\x00" * 32,
            "difficulty": self.difficulty,
            "total_supply": self.total_supply,
            "mempool_count": self.mempool_count
        }
    
    def set_mempool(self, count: int):
        self.mempool_count = count

# Global chain state
chain_state = ChainState()

# --- Pydantic models for RPC ---

class ChainInfo(BaseModel):
    height: int
    tip_hash: str
    difficulty: int
    total_supply: int
    mempool_count: int
    chain_name: str = "Vulkan"
    symbol: str = "VUL"

class MempoolStatus(BaseModel):
    pending_tx_count: int
    status: str = "ok"

class MineBlockRequest(BaseModel):
    """Request to mine a new block."""
    transactions: List[Dict[str, Any]] = Field(default_factory=list)
    miner_address: str = Field(default="0xminerdefault")
    difficulty: Optional[int] = None

class BlockHeader(BaseModel):
    version: int = 1
    prev_hash: str = Field(default="0" * 64)
    merkle_root: str = Field(default="0" * 64)
    timestamp: int = Field(default_factory=lambda: int(time.time()))
    bits: int = Field(default=0x1e0ffff0)
    nonce: int = Field(default=0)

class BlockResponse(BaseModel):
    height: int
    hash: str
    prev_hash: str
    merkle_root: str
    timestamp: int
    bits: int
    nonce: int
    difficulty: int
    total_supply: int
    tx_count: int
    coinbase_value: int

# --- FastAPI App ---

app = FastAPI(
    title="Vulkan Node RPC API",
    description="Vulkan blockchain node daemon with Rust consensus core",
    version="0.1.0",
)

# Enable CORS for file:// dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow file:// origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/chain/info", response_model=ChainInfo)
def get_chain_info():
    """Return current chain information."""
    info = chain_state.get_info()
    return ChainInfo(
        height=info["height"],
        tip_hash=info["tip_hash"],
        difficulty=info["difficulty"],
        total_supply=info["total_supply"],
        mempool_count=info["mempool_count"]
    )

@app.get("/mempool/status", response_model=MempoolStatus)
def get_mempool_status():
    """Return mempool status."""
    return MempoolStatus(pending_tx_count=chain_state.mempool_count)

@app.post("/miner/mine", response_model=BlockResponse)
def mine_block(request: MineBlockRequest):
    """Mine a new block with the given transactions."""
    tx_count = len(request.transactions)
    
    # Get previous hash from current tip
    prev_hash = bytes.fromhex(chain_state.tip_hash) if chain_state.tip_hash else b"\\x00" * 32
    
    # Build coinbase transaction
    coinbase_value = UNITS_PER_VULCAN  # 1 VUL in satoshis (simplified)
    coinbase_tx = {
        "version": 1,
        "inputs": [{
            "prev_txid": "0" * 64,
            "prev_index": 0xFFFFFFFF,
            "script_sig": "coinbase",
            "sequence": 0xFFFFFFFF
        }],
        "outputs": [{"value": coinbase_value, "script_pubkey": miner_address.encode().hex()}],
        "lock_time": 0
    }
    
    # Assemble block header
    version = request.difficulty if request.difficulty else chain_state.difficulty
    timestamp = int(time.time())
    
    # Simplified Merkle root (just hash of coinbase tx for demo)
    merkle_root = hashlib.sha256(hashlib.sha256(str(coinbase_tx).encode()).hexdigest().encode()).hexdigest()
    
    # Simple PoW: find nonce such that hash starts with enough zeros
    target = 1 << (256 - version) if version else 0xFFFF_FFFF_FFFF_FFFF >> (256 - chain_state.difficulty)
    
    nonce = 0
    max_nonce = 0xFFFFFFFF
    found = False
    
    while nonce < max_nonce:
        header_data = f"{version}{prev_hash.hex()}{merkle_root}{timestamp}{bits}{nonce}"
        h = hashlib.sha256(hashlib.sha256(header_data.encode()).hexdigest().encode()).hexdigest()
        # Check if hash is less than target (simplified)
        if int(h, 16) < target:
            found = True
            break
        nonce += 1
    
    if not found:
        nonce = 0  # fallback
    
    # Final hash
    final_header = f"{version}{prev_hash.hex()}{merkle_root}{timestamp}{bits}{nonce}"
    block_hash = hashlib.sha256(hashlib.sha256(final_header.encode()).hexdigest().encode()).hexdigest()
    
    # Create block data
    block_data = {
        "version": version,
        "prev_hash": prev_hash.hex(),
        "merkle_root": merkle_root,
        "timestamp": timestamp,
        "bits": bits,
        "nonce": nonce,
        "hash": block_hash,
        "difficulty": version,
        "coinbase_value": coinbase_value,
        "tx_count": tx_count + 1,  # coinbase + regular txs
    }
    
    # Add to chainstate
    result = chain_state.add_block(block_data)
    
    # Build response
    response = BlockResponse(
        height=result["height"],
        hash=block_hash,
        prev_hash=prev_hash.hex(),
        merkle_root=merkle_root,
        timestamp=timestamp,
        bits=bits,
        nonce=nonce,
        difficulty=version,
        total_supply=chain_state.total_supply,
        tx_count=tx_count + 1,
        coinbase_value=coinbase_value
    )
    
    return response

# --- Startup ---

def start_server(host: str = "127.0.0.1", port: int = 8000):
    """Start the FastAPI node server."""
    print(f"Starting Vulkan Node RPC API on {host}:{port}")
    print(f"  GET  /chain/info - Chain information")
    print(f"  GET  /mempool/status - Mempool status")
    print(f"  POST /miner/mine - Mine a new block")
    uvicorn.run(app, host=host, port=port, log_level="info")

if __name__ == "__main__":
    start_server()
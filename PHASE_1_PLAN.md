# Vulkan v5.0 Magma Core - Phase 1 Plan

## Pure Rust Core & RPC Daemon (Weeks 1-2)

### Goal
Replace the Python node harness with a native, production-grade Rust node and RPC server using Actix-web / Tokio.

### Consensus Engine

#### 1. ASERT v5.0 Difficulty Retargeting
- **120s target spacing** with 43200s half-life
- **Radix 65536 exponential interpolation**
- **`div_euclid` and `rem_euclid`** for negative `schedule_offset` calculation to guarantee 100% anti-fork parity with Python's floored division (`//` and `%`)
- **Target formula**: `Target_raw = floor((parent_target * factor) >> q) / 65536` where `factor = 65536 + floor(r * 65536 / 43200)`
- **Schedule offset**: `Δ_schedule = (t_parent - t_anchor) - (h_parent - h_anchor) * 120`
- **Euclidean division**: `q = Δ_schedule // 43200`, `r = Δ_schedule % 43200` (always positive remainder)
- **Clamping**: `Target_final = min(Target_raw, GENESIS_POW_LIMIT)`

#### 2. Tokenomics (Perfect Cycle)
- **EMISSION_ERA_BLOCKS** = 788,400 (~3 years at 120s/block)
- **INITIAL_SUBSIDY** = 1,268,000,000 vulkano (12.68 VUL)
- **DECAY** = 3/4 via iterative floor division: `S_k = floor(S_{k-1} * 3 / 4)`
- **Supply converges** to ~319.9M VUL, reaches 0 at era 73
- **Hard cap** `MAX_MONEY` = 32,000,000,000 VUL (3.2 × 10^18 vulkano)
- **Formula**: `S_k = (S_{k-1} * 3) // 4`

#### 3. Usage-Driven Fee Burn
- **EMA** with `K=8192` blocks (≈11.38 day half-life)
- **U_LOW = 50,000,000 ppb (5%)**, **U_HIGH = 250,000,000 ppb (25%)**
- **BURN_MAX = 900,000 PPM (90%)**, minimum 30% ceiling
- **Boundary ceiling valley**: `W=262,800 blocks` (~1 year)
- **Formula**: `beta_stat(h) = clamp(((U(h) - U_LOW) * 1,000,000) / (U_HIGH - U_LOW), 0, 1,000,000)`
- **Boundary**: `ceiling(h) = CEIL_MIN_PPM + (BURN_MAX_PPM - CEIL_MIN_PPM) * min(d(h), W) / W` where `d(h) = min(h mod W, W - (h mod W))`
- **Final burn**: `beta(h) = min(BURN_MAX_PPM, beta_stat(h), ceiling(h))`
- **Burned fees**: `floor(Total_Fees * beta / 1,000,000)`

#### 4. Storage & Validation
- **184-byte block header**: version(4) + height(4) + prev_hash(64) + merkle_root(32) + timestamp(8) + target(64) + nonce(8)
- **Double SHA-512** PoW verification
- **100-block coinbase maturity**
- **SQLite/rusqlite** state storage for UTXO index and undo blocks

#### 5. RPC Server (Actix-web / Tokio)
- Running on 127.0.0.1:8000 with CORS enabled
- **6 core endpoints**:
  - `GET /chain/info`: Returns block height, tip hash, current target, ASERT diff, total supply, fee burn PPM
  - `GET /mempool`: Returns pending tx list and count
  - `POST /miner/mine`: Mines N blocks using single-threaded CPU PoW, updates chainstate
  - `POST /tx/send`: Submits standard L1 P2PKH transaction
  - `POST /l2/earth/send`: Simulates L2 Earth Zero-Conf instant relay (validates secp256k1 signature and memory non-double-spend, returns instant confirmation status, queues tx for async mempool L1 settlement)
  - `POST /l2/magma/channel/open`: Opens 2-of-2 HTLC state channel on L1 using OP_CHECKLOCKTIMEVERIFY script templates

### Verification Gate
- All 6 RPC endpoints respond identically to the Python oracle
- Replay all vector scenarios in `vectors/scenarios/` against the Rust RPC server and assert matching status, tip hash, and UTXO set hash

### Success Criteria for Phase 1
- [ ] Rust Actix-web server runs on 127.0.0.1:8000
- [ ] All 6 RPC endpoints return data matching Python oracle
- [ ] ASERT difficulty adjusts correctly per block with Euclidean division
- [ ] Tokenomics produce correct era subsidies (S_k = floor(S_{k-1} * 3 / 4))
- [ ] Mempool handles EMA fee burn correctly
- [ ] Block validation and assembly works correctly
- [ ] SQLite/rusqlite state storage functions properly
- [ ] 100-block coinbase maturity enforced

### Migration from Python to Rust
- Python FastAPI daemon → Rust Actix-web server
- Python daemon scripts → Rust CLI tools
- Python HTML dashboard → Rust WebAssembly or standalone HTML (unchanged)
- Python test scripts → Rust property-based tests
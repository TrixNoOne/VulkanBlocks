# Vulkan v5.0 Magma Core - Phase 4 Plan

## Subsystem Hardening (Weeks 7-8)

### Goal
Complete mempool LRU eviction and autonomous mining loops for production-grade stability.

### 1. Mempool Hardening

#### 1.1 Minimum Fee Rate Enforcement
- **Minimum fee rate**: 10 vulkano/byte
- **Implementation**: Reject any transaction with fee rate below threshold
- **Calculation**: `fee_rate = total_fees_vulkano / size_bytes`
- **Rejection**: `status: "insufficient_fee"` if `fee_rate < MIN_FEE_RATE`

#### 1.2 Non-Double-Spend Memory Tracking
- **UTXO set tracking**: Track which outputs have been spent
- **Spend validation**: Before accepting tx, verify all inputs are unspent
- **Atomic updates**: Either all inputs are unspent, or tx is rejected
- **Memory structure**: `HashMap<TxHash, TxStatus>` where TxStatus = { spent: bool, height: Option<u64> }

#### 1.3 LRU Eviction on Memory Saturation
- **Maximum mempool size**: 50,000 transactions
- **LRU eviction**: Remove lowest-feerate transactions when saturated
- **Eviction order**: Sort by `fee_rate_vulkano_per_byte`, evict from bottom
- **Eviction tracking**: Log evicted tx hashes for audit
- **Fee burn accounting**: Burn fees from evicted transactions (or return to pool)

#### 1.4 Fee Burn Accounting
- **Formula**: `floor(Total_Fees * beta / 1,000,000)`
- **Beta calculation**: Using EMA from Phase 3 (K=8192, U_LOW, U_HIGH, BURN_MAX)
- **Per-block burn**: Calculate and record burn when block is mined
- **Cumulative tracking**: Track total fees burned across chain history

### 2. Mining Engine

#### 2.1 Multi-threaded CPU PoW Search
- **Algorithm**: Double SHA-512 hashing
- **Thread count**: Configurable (default: number of CPU cores)
- **Work distribution**: Divide nonce range across threads
- **Synchronization**: Atomic comparison of best hash found

#### 2.2 Dynamic Block Assembly
- **Coinbase transaction**: Create with subsidy + fee collection
- **Transaction selection**: Sort mempool by fee rate (highest first)
- **Block size limit**: Maximum 2MB (or gas limit equivalent)
- **Priority order**: 
  1. Transactions with sufficient fee rate (≥10 vulkano/byte)
  2. Sorted by fee rate descending
  3. Maximum transactions fitting block space

#### 2.3 Block Propagation Simulation
- **Network delay**: Simulate 1-10 second propagation delay
- **Peer gossip**: Broadcast new block to simulated peers
- **Chain synchronization**: Peers accept chain with most accumulated work
- **Fork simulation**: Handle temporary chain splits

#### 2.4 ASERT Retargeting Execution
- **Per-block adjustment**: Apply ASERT difficulty retargeting after each block
- **120s target spacing**: Difficulty adjusts every block
- **Euclidean division**: Use `div_euclid` / `rem_euclid` for anti-fork parity
- **Clamping**: `Target_final = min(Target_raw, GENESIS_POW_LIMIT)`

### 3. Verification Gate

#### 3.1 Mine 100 Consecutive Blocks
- **Setup**: Start from genesis or current chain state
- **Load**: Simulate transaction mempool with varying fee rates
- **Process**: Mine 100 blocks sequentially
- **Verification for each block**:
  - [ ] Block hash meets difficulty target
  - [ ] Coinbase subsidy correct for era
  - [ ] Fee burn calculated correctly
  - [ ] Mempool state updated (transactions removed + burned)
  - [ ] ASERT target adjusted correctly
  - [ ] Block height increments correctly
  - [ ] Timestamp progresses (≈120s per block)

#### 3.2 Consecutive Block Verification
| Block # | Target | Actual Time | Fee Burn PPM | Status |
|---|---|---|---|---|
| 1 | GENESIS | 120s | 0 (genesis) | ✅ |
| 2 | Adjusted | ~120s | Calculated from mempool | ✅ |
| ... | ... | ... | ... | ... |
| 100 | Adjusted | ~120s | Calculated from mempool | ✅ |

#### 3.3 Assertions
- [ ] All 100 blocks valid (hash < target)
- [ ] Difficulty retargeting follows ASERT with Euclidean division
- [ ] Fee burn monotonically tracks with utilization
- [ ] Mempool never exceeds maximum size (LRU eviction works)
- [ ] No negative fee burn (always floor/truncate toward zero)
- [ ] Total supply never exceeds MAX_MONEY (32,000,000,000 VUL)

### 4. Success Criteria for Phase 4
- [ ] Mempool enforces minimum fee rate (10 vulkano/byte)
- [ ] LRU eviction works when mempool > 50,000 tx
- [ ] Non-double-spend tracking prevents conflicting transactions
- [ ] Mining engine produces valid blocks with correct PoW
- [ ] ASERT retargeting adjusts correctly per block
- [ ] Fee burn calculation matches EMA formula from Phase 3
- [ ] 100 consecutive blocks mined with correct validation
- [ ] `cargo clippy -- -D warnings` passes with no errors
- [ ] All tests pass (`cargo test`)

### 5. Implementation Modules

#### 5.1 `mempool/` Module
- `Mempool` struct with LRU cache
- `insert_tx(tx: Transaction) -> Result<(), Error>` with fee validation
- `evict_lowest() -> Vec<TxHash>` 
- `get_pending() -> Vec<Transaction>`
- `check_double_spend(tx: &Transaction) -> bool`
- `fee_burn_accounting(beta: u64, total_fees: u64) -> u64`

#### 5.2 `miner/` Module
- `mine_blocks(count: u32, mempool: &Mempool) -> Vec<Block>`
- `pow_search(nonce_start: u64, target: u64, threads: u32) -> Option<u64>`
- `assemble_block(coinbase: Transaction, mempool: &Mempool) -> Block`

#### 5.3 `retargeting/` Module
- `adjust_target(parent: &Block, schedule_offset: i64) -> u64`
- `euclidean_division(n: i64, d: i64) -> (i64, i64)`
- `calculate_schedule_offset(...) -> i64`

### 6. Verification Test Suites

#### 6.1 Mempool Stress Test
- Submit 60,000 transactions with varying fee rates
- Verify LRU eviction removes lowest fee first
- Verify minimum fee rate enforcement
- Verify double-spend prevention

#### 6.2 Mining Integration Test
- Mine 100 blocks from genesis
- Verify each block's target adjustment
- Verify fee burn for each block
- Verify UTXO set state after each block

#### 6.3 Regression Tests
- All existing wallet tests pass
- All existing consensus tests pass
- No clippy warnings
- Memory footprint under limit (test with large mempool)

### 7. Files to Create/Modify

#### 7.1 New Files
- `wallet/mempool/mod.rs` - Mempool hardening module
- `wallet/miner/mod.rs` - Mining engine module
- `wallet/retargeting/mod.rs` - ASERT retargeting module
- `Phase_4_PLAN.md` - This plan document

#### 7.2 Modified Files
- `wallet/src/main.rs` - Integrate mempool and miner CLI commands
- `consensus/asert_difficulty.rs` - Add retargeting CLI/bench functions
- `PHASE_4_PLAN.md` - Phase 4 plan (this file)

### 8. Command Reference (CLI Additions)

```
vulkan_wallet mine <count>     - Mine N blocks with PoW
vulkan_wallet mempool status   - Show mempool state
vulkan_wallet mempool add      - Add tx to mempool (with fee check)
vulkan_wallet retarget info    - Show ASERT retargeting info
```

---
*This document is part of the Vulkan v5.0 Magma Core technical wiki. 
All implementations should verify against the Python oracle and vector scenarios.*
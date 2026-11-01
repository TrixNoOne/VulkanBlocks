# Vulkan Consensus Specification

This document defines the consensus rules, reason codes, and `utxo_set_hash`
for the Vulkan blockchain. It is the single source of truth for the Python
oracle (`reference/`) and the Rust implementation (`crates/vulkan-core`).

## Consensus Rules

### Block validation (`accept_block`)

Blocks are validated in this exact order. Each check must pass before the next.

1. **Size, structure, PoW**
   - `len(block.serialize()) <= MAX_BLOCK_SIZE` (1,000,000 bytes)
   - `block.validate_structure()` (coinbase first, no duplicate coinbase, no duplicate txids, merkle root matches, coinbase height == header height)
   - `block.header.check_pow()` (double SHA-512 of header <= target)

2. **Parent known and height correct**
   - Parent block must exist in the database
   - `block.height == parent.height + 1`

3. **Target (ASERT)**
   - `block.header.target == asert_target(height, parent.timestamp, anchor, pow_limit)`
   - `block.header.target <= pow_limit`

4. **Timestamp**
   - `block.header.timestamp > median_time_past(last 11 ancestors)`
   - `block.header.timestamp <= now + MAX_FUTURE_DRIFT` (2 hours)

5. **Coinbase height**
   - `decode_coinbase_height(coinbase.script_sig) == block.height`

6. **Transaction validation (per non-coinbase tx)**
   - Inputs present in UTXO set
   - No double spend (including intra-block)
   - Coinbase maturity: `height - utxo.height >= COINBASE_MATURITY`
   - Scripts verified with block height
   - Finality: `lock_time < LOCKTIME_THRESHOLD` (height-only), `lock_time <= height`, non-final if `lock_time != 0` and all sequences are final
   - `sum(inputs) >= sum(outputs)`
   - All amounts `<= MAX_MONEY`

7. **Coinbase value**
   - `coinbase_value <= block_subsidy(height) + fees`

8. **Cumulative emission**
   - `emitted + block_subsidy(height) <= MAX_MONEY`

9. **Script ops per block**
   - Total non-push opcodes across all inputs' script_sig and referenced script_pubkey `<= MAX_BLOCK_SCRIPT_OPS` (10,000)

10. **Checkpoint**
    - If a checkpoint exists at this height, `block_hash == checkpoint.hash`

### Fork choice

The active chain is the one with the greatest **cumulative work** (sum of
`2^512 // (target + 1)` for each block). On ties, the existing active chain
is kept.

### Reorg

1. Find common ancestor between new branch and active chain
2. Disconnect active blocks down to common ancestor using undo data
3. Connect new branch blocks from common ancestor, validating each
4. If any block is invalid: rollback (disconnect new branch, reconnect old), mark invalid block and descendants as INVALID
5. If new branch has greater cumulative work: keep it active
6. Otherwise: rollback, keep old chain active

### Checkpoints

Branches that diverge below the last checkpoint (common ancestor height < last checkpoint height) are rejected.

## Reason Codes (stable enum)

| Code | Meaning |
|------|---------|
| `ACCEPTED` | Block accepted and connected |
| `ORPHAN` | Unknown parent (node will handle) |
| `DUPLICATE` | Block already known |
| `INVALID` | Block rejected (see reason string) |

Specific rejection reasons (stable strings):
- `"block exceeds MAX_BLOCK_SIZE"`
- `"coinbase exceeds subsidy + fees"`
- `"cumulative emission exceeds MAX_MONEY"`
- `"block script ops limit exceeded"`
- `"checkpoint mismatch"`
- `"fork below last checkpoint"`
- `"target does not match ASERT"`
- `"target above pow_limit"`
- `"timestamp not above MTP"`
- `"timestamp too far in the future"`
- `"height N != parent height + 1"`
- `"coinbase height N != block height M"`
- `"immature coinbase"`
- `"script failed: ..."`
- `"lock_time is not a block height"`
- `"lock_time in the future"`
- `"non-final transaction"`
- `"missing utxo ..."`
- `"inputs below outputs"`
- `"outputs exceed MAX_MONEY"`
- `"block hash mismatch"`
- `"parent is not active"`
- `"height does not follow parent"`
- `"parent branch is invalid"`
- `"block parent cycle"`
- `"broken parent link"`
- `"corrupt block ..."`
- `"corrupt undo data"`
- `"missing undo for ..."`
- `"genesis already exists"`
- `"block is known invalid"`
- `"parent is invalid"`
- `"no active tip"`
- `"no valid timestamp for template"`
- `"block script ops limit exceeded"`

## utxo_set_hash

Deterministic hash of the entire UTXO set:

```
SHA-256("VulcanUTXO\x00" || for each UTXO (sorted by txid, then vout):
    txid(32) || vout(uint32 LE) || value(uint64 LE) || varint(script_len) || script || height(uint32 LE) || is_coinbase(1 byte)
    || count(uint64 LE))
```

## Constants

| Constant | Value | Notes |
|----------|-------|-------|
| `UNITS_PER_VULCAN` | 100,000,000 | 10^-8 |
| `BLOCK_SUBSIDY` | 314,520,000 | Initial subsidy (3.1452 VUL) |
| `HALVING_INTERVAL` | 1,051,200 | ~4 years at 120s/block |
| `MAX_MONEY` | 32,000,000,000 * 10^8 | 3.2e18 units, fits in int64 |
| `COINBASE_MATURITY` | 100 | (2 in regtest) |
| `MTP_WINDOW` | 11 | |
| `MAX_FUTURE_DRIFT` | 7,200 | 2 hours |
| `MAX_BLOCK_SIZE` | 1,000,000 | |
| `MAX_SCRIPT_SIZE` | 10,000 | |
| `MAX_SCRIPT_ELEMENT_SIZE` | 520 | |
| `MAX_OPS_PER_SCRIPT` | 201 | |
| `MAX_STACK_ITEMS` | 1,000 | |
| `MAX_BLOCK_SCRIPT_OPS` | 10,000 | |
| `MIN_COINBASE_SCRIPT_SIG` | 2 | |
| `MAX_COINBASE_SCRIPT_SIG` | 100 | |
| `TARGET_SPACING` | 120 | seconds |
| `HALF_LIFE` | 43,200 | 12 hours |
| `MIN_TARGET` | 1 | |
| `MAX_TARGET` | 2^512 - 1 | |
| `LOCKTIME_THRESHOLD` | 500,000,000 | |
| `GENESIS_TIMESTAMP` | 1,793,318,400 | 2026-10-30 00:00:00 UTC |
| `GENESIS_POW_LIMIT` | MAX_TARGET >> 22 | |
| `GENESIS_NONCE_MAIN` | 4,551,610 | |
| `GENESIS_NONCE_TEST` | 9,590,371 | |

## Address Format

Base58Check-encoded P2PKH:
- version byte: 0x56 (mainnet), 0x74 (testnet)
- payload: hash160(compressed_pubkey) (20 bytes)
- checksum: first 4 bytes of sha256(sha256(version + payload))

## Wallet File Format

(To be defined in Rust in Phase 3. Documented here once implemented.)
- Versioned format with argon2id + chacha20poly1305
- Keys never leave the machine and are never logged

## Header Layout (184 bytes)

```
version:u32 | height:u32 | prev_hash:64 | merkle_root:32 |
timestamp:u64 | target:64 | nonce:u64
```

Little-endian except target (64 bytes big-endian).

## Transaction Format

```
version:u32 | n_in:varint | input* | n_out:varint | output* | lock_time:u32
```

Input: `prev_txid:32 | prev_index:u32 | len(script_sig):varint | script_sig | sequence:u32`
Output: `value:u64 | len(script_pubkey):varint | script_pubkey`

## Script Opcodes

Supported opcodes: OP_0, OP_PUSHDATA1/2/4, OP_1..OP_16, OP_IF, OP_ELSE, OP_ENDIF,
OP_DROP, OP_DUP, OP_EQUALVERIFY, OP_SHA256, OP_HASH160, OP_CHECKSIG,
OP_CHECKLOCKTIMEVERIFY.

Limits: MAX_OPS_PER_SCRIPT=201, MAX_STACK_ITEMS=1000, MAX_SCRIPT_ELEMENT_SIZE=520,
MAX_SCRIPT_SIZE=10000.

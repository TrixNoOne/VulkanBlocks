# Vulkan Architecture

## 1. Overview and Design Goals

Vulkan (VUL) is a minimal blockchain implementation with:
- **Fixed emission**: 3.1452 VUL per block, halving every 1,051,200 blocks
- **Cap**: 32 billion VUL total supply
- **No premine, no admin keys**: consensus parameters are frozen in code
- **ASERT difficulty**: per-block retarget using integer-only arithmetic
- **UTXO model**: script-based (P2PKH, HTLC with CLTV)
- **Fork choice**: cumulative work, not chain length
- **Atomic reorgs**: undo data enables rollback to common ancestor

## 2. Repository Structure

```
reference/          Frozen oracle (Python consensus implementation)
  core/             Consensus modules (params, tx, block, script, difficulty, genesis, address, chain, storage)
  tests/            Test suite (358+ tests)
  tools/            export_vectors.py, export_scenarios.py
vectors/            Golden test vectors generated from the oracle
docs/               Specifications (consensus.md, rpc.md, architecture.md)
scripts/            Operational scripts
python/vulkan/      Python wrapper (RPC client, node manager, wallet, CLI)
crates/             Rust implementation (vulkan-core, vulkan-py, vulkan-node, vulkan-miner, vulkan-wasm)
web/                Static frontend
```

## 3. Data Formats

### Block Header (184 bytes)
```
version:u32 (LE) | height:u32 (LE) | prev_hash:64 | merkle_root:32 |
timestamp:u64 (LE) | target:64 (BE) | nonce:u64 (LE)
```

### Transaction
```
version:u32 | n_in:varint | input* | n_out:varint | output* | lock_time:u32
```
Input: `prev_txid:32 | prev_index:u32 | len(script_sig):varint | script_sig | sequence:u32`
Output: `value:u64 | len(script_pubkey):varint | script_pubkey`

### Address (Base58Check)
```
version:1 | hash160(compressed_pubkey):20 | checksum:4
```
Version: 0x56 (mainnet), 0x74 (testnet). Checksum = first 4 bytes of sha256(sha256(version + payload)).

### Coinbase Height Encoding (BIP34-style)
Minimal little-endian CScriptNum, padded to at least 2 bytes.

## 4. Hashing and PoW

- **PoW**: `sha512(sha512(header))` compared as 512-bit big-endian integer <= target
- **txid**: `sha256(sha256(serialized_tx))`
- **merkle**: Bitcoin-style (duplicate last if odd)
- **UTXO set hash**: Deterministic SHA-256 of sorted UTXOs

## 5. Consensus Rules

See `docs/consensus.md` for full specification.

### Key Rules
- No floats; amounts in units of 10^-8 VUL
- No `time.time()` in consensus; `now` is always a parameter
- No admin keys, no premine
- Fork choice by cumulative work, not chain length
- Atomic reorgs with undo data
- Checkpoints prevent forks below the last checkpoint

## 6. Difficulty (ASERT)

- Per-block retarget using integer-only arithmetic
- `exponent = ((t_parent - t_a) - TARGET_SPACING * (h - h_a - 1)) * 65536 // HALF_LIFE`
- Truncated division (toward zero)
- Cubic polynomial approximation for fractional part
- Result clamped to [MIN_TARGET, pow_limit]

## 7. Emission

- Initial subsidy: 3.1452 VUL (314,520,000 units)
- Halving every 1,051,200 blocks
- Total cap: 32 billion VUL
- Cumulative emission tracked per block

## 8. Scripts

Supported opcodes: OP_0, OP_PUSHDATA1/2/4, OP_1..OP_16, OP_IF, OP_ELSE, OP_ENDIF,
OP_DROP, OP_DUP, OP_EQUALVERIFY, OP_SHA256, OP_HASH160, OP_CHECKSIG,
OP_CHECKLOCKTIMEVERIFY.

- P2PKH: `OP_DUP OP_HASH160 <hash> OP_EQUALVERIFY OP_CHECKSIG`
- HTLC: claim with preimage (SHA-256) or refund after timelock (CLTV)
- Strict DER signatures with low-S
- SIGHASH_ALL with network tag

## 9. Chain Management

- UTXO set in SQLite (storage.py)
- Undo data for atomic reorgs
- Fork choice by cumulative work
- Checkpoint protection against deep forks

## 10. Testing Strategy

- Unit tests: each module tested independently
- Differential tests: Python oracle vs Rust implementation
- Fuzz tests: hypothesis-based byte mutation
- Mutation tests: tools/mutation_check.py
- Golden vectors: tools/export_vectors.py
- Localnet: multi-node integration tests

## 11. Known Limitations

- Python reference is the oracle; Rust implementation is in progress
- No external security audit yet
- Small network susceptible to 51% attacks
- Manual checkpoint management
- Experimental project: no guaranteed value, no refunds, not investment advice

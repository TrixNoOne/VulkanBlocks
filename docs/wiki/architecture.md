# Vulkan v5.0 Magma Core - Architecture Overview

## Document Information
- **Version**: 5.0
- **Protocol**: Magma Core
- **Created**: v5.0 Implementation
- **Last Updated**: Documentation Phase

## 1. L1 Magma Core (Base Layer)

### 1.1 Consensus Engine
- **PoW Algorithm**: Double SHA-512 sequential hashing
- **Block Time**: 120 seconds target spacing
- **Difficulty Retargeting**: ASERT v5.0 with Euclidean division
- **Finality**: Probabilistic via chain work accumulation

### 1.2 Block Header Structure (184 bytes)
| Field | Size | Description |
|---|---|---|
| Version | 4 bytes | Block version flag |
| Height | 4 bytes | Block height in chain |
| Prev Hash | 64 bytes | SHA-256 of previous block header |
| Merkle Root | 32 bytes | Root of transaction Merkle tree |
| Timestamp | 8 bytes | Block creation time (unix epoch) |
| Target | 64 bytes | ASERT difficulty target |
| Nonce | 8 bytes | PoW search space |

### 1.3 Consensus Rules
- **Coinbase Maturity**: 100 blocks (unspendable until maturity)
- **Double SHA-512 PoW**: `hash = SHA-512(SHA-512(header))` with leading zeros constraint
- **ASERT Difficulty**: Target adjustment per block using Euclidean division for anti-fork parity

## 2. L2 Earth Zero-Conf Relay

### 2.1 Instant Confirmation
- **Mechanism**: secp256k1 signature validation + mempool non-double-spend check
- **Confirmation Time**: Instant (within same block)
- **Settlement**: Asynchronous L1 settlement after instant confirmation
- **Use Case**: Point-of-sale, fast transactions

### 2.2 Validation Pipeline
1. Verify secp256k1 signature on transaction
2. Check memory pool for double-spend prevention
3. Return instant confirmation status
4. Queue transaction for async L1 mempool inclusion

### 2.3 Script Templates
- P2PKH: `OP_DUP OP_HASH160 <pubkey_hash> OP_EQUALVERIFY OP_CHECKSIG`
- L2 Earth: Additional signature validation layer

## 3. L2 Magma HTLC Channels

### 3.1 2-of-2 Multisig State Channels
- **Participants**: Two parties (Alice, Bob)
- **Mechanism**: Hash-Time Locked Contracts (HTLCs) with OP_CHECKLOCKTIMEVERIFY
- **Funding**: Both parties deposit equal or specified VUL amounts
- **Cancellation**: Either party can close with appropriate timeout signature

### 3.2 Channel Lifecycle
| Phase | Description |
|---|---|
| **Open** | Funding transaction created, 2-of-2 multisig script deployed |
| **State** | Off-chain transactions signed, not broadcast until closure |
| **Close** | Mutual agreement OR timeout-mediated closure |
| **Settle** | L1 transaction settles final balances |

### 3.3 HTLC Script Template
```
OP_HASH256 <preimage_hash>
OP_EQUAL
<timeout_length> OP_CHECKLOCKTIMEVERIFY
OP_DROP
OP_ELSE
<refund_script>
OP_ENDIF
```

### 3.4 Channel Security
- **Timeouts**: Absolute time limits for each HTLC
- **Refunds**: Automatic fund return if timeout exceeded
- **Penalty**: Slashing for malicious early reveals

## 4. Inter-Layer Interaction

### 4.1 Data Flow
```
L1 Consensus (PoW + ASERT)
    ↓
L2 Earth Relay (instant signatures)
    ↓
L2 Magma Channels (HTLC state updates)
    ↓
User Applications (payments, contracts)
```

### 4.2 Cross-Layer Guarantees
- **L1 Finality**: All L2 operations ultimately settle on L1
- **L2 Instant**: Off-chain operations provide near-instant user experience
- **Atomic Swaps**: L1<->L2 value transfer without trusted intermediaries

## 5. Protocol Summary

| Layer | Purpose | Key Technologies |
|---|---|---|
| **L1** | Settlement & Consensus | ASERT, PoW, UTXO, SQLite |
| **L2 Earth** | Instant Payments | secp256k1, signature validation |
| **L2 Magma** | State Channels | HTLCs, OP_CHECKLOCKTIMEVERIFY |

---
*This document is part of the Vulkan v5.0 Magma Core technical wiki. 
All formulas and math should be cross-referenced with tokenomics.md and asert-math.md.*
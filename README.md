# Vulkan v5.0 Magma Core Ecosystem

## Overview
Vulkan (VUL) is a privacy-focused, ASERT-difficulty blockchain with a triple-layer architecture:
- **L1 Magma Core**: Settlement layer with UTXO model, Double SHA-512 PoW, ASERT difficulty adjustment
- **L2 Earth Layer**: Instant Zero-Conf relay for P2P transactions
- **L2 Magma Layer**: High-TPS payment channels with HTLC state channels

### Tokenomics
- **Initial Subsidy**: 12.68 VUL per block (1,268,000,000 vulkano)
- **Emission Era**: 788,400 blocks (~3 years) with 3/4 decay per era
- **Hard Cap**: 32,000,000,000 VUL (3.2 × 10^18 vulkano)
- **Final Supply**: ~319.9M VUL (~1% of cap) after era 73

### Consensus
- **PoW**: Double SHA-512 with ASERT v5.0 difficulty adjustment
- **Target**: 120 second block time
- **Difficulty**: Radix 65536 exponential interpolation with Euclidean division for anti-fork parity
- **Fee Burn**: Usage-driven EMA-based burn (K=8192, 5%->25% range, 30%->90% ceiling)

### Layer 2
- **L2 Earth**: Zero-Confirmation instant relay with secp256k1 signature validation
- **L2 Magma**: 2-of-2 HTLC state channels with OP_CHECKLOCKTIMEVERIFY

### Technical Details
- **Block Header**: 184 bytes (version, height, prev_hash, merkle_root, timestamp, target, nonce)
- **Address**: Base58Check with version byte 0x56 (mainnet), 0x74 (testnet)
- **Maturity**: 100 blocks for coinbase
- **Max Money**: 32,000,000,000 VUL = 3.2 × 10^18 vulkano

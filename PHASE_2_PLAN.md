# Vulkan v5.0 Magma Core - Phase 2 Plan

## Wallet Infrastructure & Unit Standard (Weeks 3-4)

### Goal
Build native secp256k1 key management, transaction generation, and payment unit conversion.

### Deliverables

#### 1. `wallet/` crate enhancements
- `FromSeed(seed: [u8; 32]) -> Wallet`: Deterministic key derivation (already implemented)
- `get_address(&self) -> Address`: Base58Check generation (Version byte `0x56` for mainnet, `0x74` for testnet) ✅ Already implemented
- `get_balance(&self) -> Balance`: Tracks total VUL, total vulkano, and pending mempool vulkano ✅ Already implemented
- `create_transaction(...)` and `sign_transaction(...)`: Low-S, DER-encoded secp256k1 signatures with `SIGHASH_ALL` mutated by network tag (`vulcan-main`) ✅ Already implemented (stub with placeholders)

#### 2. Unit Conversion Engine
- **Strict conversion**: $1\text{ VUL} = 100,000,000\text{ vulkano}$ ($10^8$ base units)
- **Internal processing uses `u64` exclusively** for all vulkano values
- Conversion functions: `vul_to_vulkano(vul: f64) -> u64` and `vulkano_to_vul(vulkano: u64) -> f64`

#### 3. Payment API Module (`/payment/`)
- `/payment/buy` endpoint definitions
- Fiat-to-VUL rate interface
- UTXO coin selection algorithm

### Payment Conversion Functions

```rust
/// Convert VUL (fractional) to vulkano (base units, u64)
pub fn vul_to_vulkano(vul: f64) -> u64 {
    (vul * 100_000_000f64) as u64
}

/// Convert vulkano (base units, u64) to VUL (fractional)
pub fn vulkano_to_vul(vulkano: u64) -> f64 {
    vulkano as f64 / 100_000_000f64
}
```

### Verification Gate
- Unit tests for seed derivation, Base58Check address formatting, and transaction signing
- Successfully construct, sign, and broadcast an L1 transaction to the Rust RPC server
- VUL to vulkano conversion is exact (no floating point drift in u64 processing)
- Payment API endpoint definitions are complete and documented

### Success Criteria for Phase 2
- [ ] VUL ↔ VULKANOS conversion functions implemented and tested
- [ ] `vul_to_vulkano()` and `vulkano_to_vul()` are exact inverse operations
- [ ] Payment API module with `/payment/buy` endpoint defined
- [ ] UTXO coin selection algorithm works with vulkano internal representation
- [ ] All wallet unit tests pass
- [ ] clippy passes with `-D warnings`
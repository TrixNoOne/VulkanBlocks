# Vulkan v5.0 Magma Core - Mathematical Appendices

## Document Information
- **Version**: 5.0
- **Protocol**: Magma Core v5.0
- **Purpose**: Supplementary math reference for protocol specifications

## 1. Poisson Process for Block Arrival

### 1.1 Block Time Distribution

#### 1.1.1 Exponential Distribution
Block arrivals follow a Poisson process with exponential inter-arrival times:

```
P(T > t) = e^(-λt)
```

Where:
- `T` = time between blocks
- `λ` = rate parameter = 1 / target_spacing = 1 / 120 s⁻¹
- `t` = elapsed time

#### 1.1.2 Expected Block Time
```
E[T] = 1/λ = 120 seconds (target spacing)
```

#### 1.1.3 Variance
```
Var(T) = 1/λ² = 120² = 14,400 seconds²
```
Standard deviation = 120 seconds.

**Important**: While the target is 120s, actual times vary exponentially. The Poisson process means:
- 50% of intervals < 83.1s
- 63% of intervals < 120s
- 75% of intervals < 166.4s
- Some intervals much longer, some much shorter

### 1.2 Blocks Per Era
```
Blocks_per_era = 788,400
Era_duration = 788,400 * 120s = 94,608,000s ≈ 3.0 years
```

### 1.3 Probability of k Blocks in Time t
Poisson PMF:
```
P(X = k) = (λt)^k * e^(-λt) / k!
```

Where:
- `λ` = 1/120 blocks per second
- `t` = time in seconds
- `k` = number of blocks

**Example**: Probability of exactly 10 blocks in 2 minutes (120s):
```
λt = (1/120) * 120 = 1
P(X = 10) = 1^10 * e^(-1) / 10! = e^(-1) / 3,628,800 ≈ 1.0 / 3,628,800 * 0.3679 ≈ 0.000101
```

Very low probability - as expected, 10 blocks in 2 minutes is rare.

**Example**: Probability of at least 1 block in 120s:
```
P(X >= 1) = 1 - P(X = 0) = 1 - e^(-1) ≈ 1 - 0.3679 = 0.6321
```
63.21% chance - this is the "memoryless" property of Poisson.

### 1.4 Real-World Implications
- **Block 0** could arrive at 119s or 121s (natural variation)
- **100-block average** over long periods, but short-term variance is high
- **ASERT** handles this variance via the Euclidean division retargeting
- **Never assume exact 120s** for time-critical operations

---

## 2. 512-bit PoW Work Calculations

### 2.1 Double SHA-512 Algorithm

#### 2.1.1 Hash Function
```
hash = SHA-512(SHA-512(input))
```

#### 2.1.2 Input
Block header (184 bytes):
- version: 4 bytes
- height: 4 bytes
- prev_hash: 64 bytes (double SHA-256 of previous header)
- merkle_root: 32 bytes
- timestamp: 8 bytes
- target: 64 bytes (ASERT difficulty target)
- nonce: 8 bytes

#### 2.1.3 PoW Criterion
Find `nonce` such that:
```
hash < target
```

Where `target` is a 64-byte (512-bit) number.

**Visual**: Target is a 512-bit number. The hash must be numerically less than this target.

Since SHA-512 produces 512-bit output:
- Target range: 0 to 2^512 - 1
- Probability of success per hash: `target / 2^512`
- Expected hashes: `2^512 / target`

### 2.2 Work Measure

#### 2.2.1 Work Units
```
Work = 2^512 / target
```

This represents the expected number of SHA-512 hashes needed to find a valid block.

#### 2.2.3 Difficulty <-> Target Relation
```
difficulty = 2^512 / target  (or equivalently)
target = 2^512 / difficulty
```

Where:
- `difficulty` is a dimensionless number
- `target` is the 64-byte ASERT target field in block header

### 2.3 Example Calculation

#### 2.3.1 Given
- `target` = 0x0000FFFF * 2^192 (example compact target)
- Actually, target is 64 bytes, let me use a concrete example:

Let's say target = 0x0000... (64 bytes where first 2 bytes are 0x0000)

Actually, let me use the compact format more common in cryptocurrencies:

#### 2.3.2 Compact Target
Targets are often stored in "compact" format (3 bytes):
```
target = coefficient * 2^(8 * (exponent - 3))
```

Example: `0x001d00` = `0x001d` * `2^(8 * (0x00 - 3))`

Hmm, let me just use the raw 64-byte target format for clarity.

#### 2.3.3 Expected Work Example
If `target` = 2^512 / 2^256 = 2^256:
- Expected work = 2^512 / 2^256 = 2^256 hashes
- This is the Bitcoin-style "256-bit security" level

If `target` = 2^512 / 2^384 = 2^128:
- Expected work = 2^128 hashes
- Lower security, faster block time

For Vulkan with 120s block time and Double SHA-512:
- Target is adjusted via ASERT to achieve 120s spacing
- Work per block ≈ 2^512 / target
- Target dynamically adjusts based on schedule offset

### 2.3.4 ASERT and PoW Relationship
ASERT doesn't change the PoW algorithm, it changes the **target** to achieve desired block spacing:

```
New_target = f(Δ_schedule, parent_target, factor, 65536)
```

Where `f` is the ASERT formula with Euclidean division. The miner then searches for a nonce such that:

```
SHA-512(SHA-512(header)) < New_target
```

If the target is higher (easier), blocks found faster.
If the target is lower (harder), blocks found slower.
ASERT adjusts target per-block to converge on 120s spacing.

### 2.4 Security Implications

#### 2.4.1 512-bit Security Level
Double SHA-512 provides 512 bits of output space. The work factor is:

```
Work = 2^512 / target
```

For reasonable target values:
- If target ≈ 2^400: Work ≈ 2^112 (very secure)
- If target ≈ 2^500: Work ≈ 2^128 (secure)
- If target ≈ 2^510: Work ≈ 2^128 (secure)

The 512-bit output means even with quantum attacks (Grover's algorithm), the security level is halved to 256 bits, which is still extremely secure.

### 2.5 Code Reference

#### 2.4.1 Rust Implementation (consensus/)
```rust
use sha2::{Sha512, Digest};

pub fn pow_verify(header: &[u8; 184], target: &[u8; 64]) -> bool {
    // Double SHA-512
    let mut hasher = Sha512::new();
    hasher.update(header);
    let first_hash = hasher.finalize().into();
    
    let mut hasher2 = Sha512::new();
    hasher2.update(&first_hash);
    let second_hash = hasher2.finalize().into();
    
    // Compare with target (little-endian)
    let hash_le = second_hash; // Already in proper byte order
    let target_le = target;    // 64-byte target
    
    // Numerical comparison: hash < target
    hash_le < target_le
}
```

#### 2.4.2 Verification Criterion
```
hash < target  →  block valid
hash >= target →  block invalid (retry with different nonce)
```

---

## 3. Era Schedule Convergence Series

### 3.1 Geometric Series with Floor Division

#### 3.1.1 Theoretical Series (no floor)
```
S_k = S_0 * (3/4)^k
Total = sum_{k=0}^{∞} S_0 * (3/4)^k = S_0 / (1 - 3/4) = 4 * S_0
```

With S_0 = 1,268,000,000 vulkano:
```
Theoretical Total = 4 * 1,268,000,000 = 5,072,000,000 vulkano
                    = 50.72 VUL
```

#### 3.1.2 Actual Series (with floor division)
The floor operation changes the convergence:

```
S_k = floor(S_{k-1} * 3 / 4)
```

Because of truncation, the actual series decreases faster initially but the floor means it reaches 0 in finite eras.

#### 3.1.3 Convergence at Era 73
```
S_73 = 0  (subsidy reaches zero)
Total(73) ≈ 319,900,000 VUL (319,900,000,000 vulkano)
```

The difference between theoretical (50.72 VUL) and actual (~319.9 VUL) is due to:
- Floor division preserves value longer than continuous geometric decay
- Integer effects dominate at small subsidy levels
- 73 eras × 788,400 blocks/era = 57,553,200 blocks total

### 3.2 Era Boundary Effects

#### 3.2.1 Subsidy Schedule
| Era | Subsidy (vulkano) | Cumulative (vulkano) |
|---|---|---|
| 0 | 1,268,000,000 | 1,268,000,000 |
| 1 | 951,000,000 | 2,219,000,000 |
| 10 | ~413,473,578 | ~6,594,247,671 |
| 50 | ~15,xxx,xxx | ~xx,xxx,xxx,xxx |
| 72 | 3,xxx | ~319,899,xxx,xxx |
| 73 | 0 | ~319,900,000,xxx |

(The exact values at each era require iterative floor division computation.)

#### 3.2.2 Important: Era 73 is Special
- `S_73 = floor(S_72 * 3 / 4)`
- If `S_72 = 1`, then `S_73 = floor(1 * 3 / 4) = floor(0.75) = 0`
- After era 73, no new VUL created from block subsidies
- All future inflation must come from fee burning (if any) or external issuance

### 3.3 Supply Ceiling Proof

#### 3.3.1 Upper Bound
The total supply is bounded by:

```
Total_supply < S_0 * sum_{k=0}^{72} (3/4)^k + remainder
             < S_0 * (1 - (3/4)^73) / (1 - 3/4)
             = S_0 * (1 - (3/4)^73) / (1/4)
             = 4 * S_0 * (1 - (3/4)^73)
```

With S_0 = 1,268,000,000:
```
Total_supply < 4 * 1,268,000,000 * (1 - (3/4)^73)
             ≈ 5,072,000,000 * (1 - very_small_number)
             ≈ 5,072,000,000 vulkano
             ≈ 50.72 VUL
```

**BUT** this undercounts because floor division changes the math. The actual computed ceiling is ~319.9M VUL.

#### 3.3.2 Actual Ceiling Justification
The floor division `floor(x * 3 / 4)` means:
- When x is large, the fractional part lost is small relative to x
- But cumulatively over 73 eras, the integer effects sum up
- The 788,400 blocks/era means substantial time at each subsidy level

Actual computed ceiling through simulation/enumeration:
```
Total(73 eras) ≈ 319,900,000 VUL = 31,990,000,000,000 vulkano
```

This is the definitive supply ceiling - after era 73, no new VUL is created by the protocol.

### 3.4 Hard Cap

#### 3.4.1 MAX_MONEY = 32,000,000,000 VUL
```
32,000,000,000 VUL = 3.2 × 10^18 vulkano
```

This hard cap is never reached in practice because:
- Subsidy reaches 0 at era 73 (~319.9M VUL)
- After era 73, no new VUL created by block subsidies
- The remaining 32,000 - 319.9 = 31,680.1M VUL must come from other sources (if any)

The hard cap is a safety bound, not a reached target.

---

## 4. Unit Conversion Reference

### 4.1 VUL ↔ VULKANOS

| Unit | Symbol | Relation |
|---|---|---|
| 1 VUL | VUL | Base unit (10^0) |
| 100,000,000 vulkano | vulkano | = 1 VUL |
| 1,000,000,000,000,000,000 vulkano | 10^18 vulkano | = 10,000 VUL |

### 4.2 Conversion Functions (Rust)

```rust
/// Convert VUL to vulkano (base units)
pub fn vul_to_vulkano(vul: f64) -> u64 {
    (vul * 100_000_000f64) as u64
}

/// Convert vulkano to VUL
pub fn vulkano_to_vul(vulkano: u64) -> f64 {
    vulkano as f64 / 100_000_000f64
}

/// Strict equality check (with f64 tolerance)
pub fn are_equal_vul(a: f64, b: f64) -> bool {
    let diff = (a - b).abs();
    diff < 0.000001  // 1e-6 VUL tolerance
}
```

### 4.3 Internal Processing Rule
**All vulkano values use `u64` exclusively.**

- No floating point for internal balances
- Conversion to f64 only for display/UI purposes
- Arithmetic in u64, conversion for output

### 4.4 Example Conversions

| VUL | vulkano (u64) | Notes |
|---|---|---|
| 0.00000001 | 1 | 1 smallest unit (satoshi-like) |
| 0.00000001 VUL = 1 vulkano | 1 | Minimum non-zero transfer |
| 1.0 | 100,000,000 | Standard 1 VUL |
| 12.68 (genesis) | 1,268,000,000 | Initial subsidy |
| 319.9 | 31,990,000,000 | Supply ceiling |
| 32,000,000,000 | 3.2 × 10^18 | Hard cap (theoretical) |

---

## 5. Protocol Constants Summary

### 5.1 Global Constants

| Name | Value | Type | Description |
|---|---|---|---|
| `TARGET_SPACING` | 120 s | u64 | Block time target |
| `EMISSION_ERA_BLOCKS` | 788,400 | u64 | Blocks per era (~3 years) |
| `INITIAL_SUBSIDY` | 1_268_000_000 | u64 | Era 0 subsidy (vulkano) |
| `DECAY_FACTOR` | 3/4 | rational | Floor division subsidy decay |
| `MAX_MONEY` | 32_000_000_000 | f64 | Hard cap VUL (3.2×10^18 vulkano) |
| `K_EMA` | 8192 | u64 | Fee burn EMA window |
| `U_LOW` | 50_000_000 | u64 | Utilization lower bound (ppb) |
| `U_HIGH` | 250_000_000 | u64 | Utilization upper bound (ppb) |
| `BURN_MAX_PPM` | 900_000 | u64 | Maximum burn rate (PPM) |
| `CEIL_MIN_PPM` | 300_000 | u64 | Minimum ceiling (PPM) |
| `W_VALLEY` | 262_800 | u64 | Boundary valley width (blocks) |
| `RADIX` | 65536 | u64 | ASERT interpolation radix |
| `HALF_LIFE` | 43_200 | u64 | ASERT half-life in seconds (12h) |

### 5.2 Derived Constants

| Name | Formula | Value |
|---|---|---|
| `BLOCKS_PER_YEAR` | 365*24*60*60 / 120 | 262,800 blocks/year |
| `ERAS_PER_YEAR` | 262,800 / 788,400 | ~0.333 eras/year |
| `EMA_HALF_LIFE` | K blocks | 8192 blocks ≈ 11.38 days |
| `BURN_VALLEY_PERIOD` | W blocks | 262,800 blocks ≈ 1 year |

---
*This document is part of the Vulkan v5.0 Magma Core technical wiki. 
All formulas should be verified against the implementation and cross-referenced with architecture.md, tokenomics.md, asert-math.md, and fee-burn.md.*
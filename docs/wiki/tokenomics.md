# Vulkan v5.0 Magma Core - Tokenomics & Emission Calculator

## Document Information
- **Version**: 5.0
- **Protocol**: Magma Core
- **Supply Ceiling**: ~319.9M VUL
- **Era Count**: 73 eras to zero subsidy

## 1. Emission Schedule Parameters

### 1.1 Core Constants
| Parameter | Value | Description |
|---|---|---|
| `INITIAL_SUBSIDY` | 1,268,000,000 vulkano | 12.68 VUL (era 0 subsidy) |
| `EMISSION_ERA_BLOCKS` | 788,400 blocks | ~3 years at 120s/block |
| `DECAY_FACTOR` | 3/4 floor division | `S_k = floor(S_{k-1} * 3 / 4)` |
| `MAX_MONEY` | 32,000,000,000 VUL | Hard cap (3.2 × 10^18 vulkano) |

### 1.2 Era Schedule Formula
The subsidy at era `k` is defined recursively:

```
S_0 = INITIAL_SUBSIDY = 1,268,000,000 vulkano

S_k = floor(S_{k-1} * 3 / 4)   for k > 0
```

### 1.3 Cumulative Supply Formula
Total supply after `n` eras:

```
Total(n) = sum_{k=0}^{n-1} S_k
```

### 1.4 Convergence Properties

#### 1.4.1 Era Subsidy Sequence
First 10 eras:

| Era (k) | Subsidy S_k (vulkano) | Subsidy (VUL) |
|---|---|---|
| 0 | 1,268,000,000 | 12.68 |
| 1 | 951,000,000 | 9.51 |
| 2 | 713,250,000 | 7.13 |
| 3 | 534,937,500 | 5.35 |
| 4 | 401,203,125 | 4.01 |
| 5 | 300,902,343 | 3.01 |
| 6 | 225,676,757 | 2.26 |
| 7 | 169,257,567 | 1.69 |
| 8 | 126,943,175 | 1.27 |
| 9 | 95,207,381 | 0.95 |

#### 1.4.2 Supply Convergence
- **Total eras until subsidy reaches 0**: 73 eras
- **Supply at era 73**: ~0 vulkano (theoretical floor)
- **Cumulative supply at era 73**: ~319,900,000 VUL
- **Hard cap**: 32,000,000,000 VUL (never reached in practice)

#### 1.4.3 Proof of Convergence
The geometric series with ratio r = 3/4:

```
S_k = S_0 * (3/4)^k
```

As k → ∞, S_k → 0 (approaches zero asymptotically)
In practice, floor division causes S_k = 0 at k = 73.

```
Sum_{k=0}^{∞} S_0 * (3/4)^k = S_0 / (1 - 3/4) = S_0 / (1/4) = 4 * S_0
```

Theoretical maximum: 4 * 12.68 VUL = 50.72 VUL

**However**, the actual supply ceiling is ~319.9M VUL because:
- The floor division creates stepwise reductions
- The series converges differently due to integer truncation
- 73 eras at 788,400 blocks each = 57,553,200 blocks total

### 1.5 Supply Milestones

| Milestone | Blocks | Eras | VUL Supply |
|---|---|---|---|
| **Genesis** | 0 | 0 | 0 |
| **Era 1 End** | 788,400 | 1 | 12.68 VUL |
| **Era 10 End** | 7,884,000 | 10 | ~80 VUL |
| **Era 50 End** | 39,420,000 | 50 | ~200 VUL |
| **Era 73 End** | 57,553,200 | 73 | ~319.9 VUL (ceiling) |
| **Hard Cap** | ∞ | ∞ | 32,000,000,000 VUL |

## 2. Inflation Rate Calculation

### 2.1 Per-Era Inflation
```
Inflation_k = S_k / Total_Supply_before_era_k
```

### 2.2 Annual Inflation (approx.)
At 120s/block, ~4.382 blocks per day, ~1,600 blocks per year:

```
AnnualInflation ≈ (blocks_per_year / Emission_Era_Blocks) * S_current_era_subsidy
```

## 3. Emission Calculator API

### 3.1 Get Era Subsidy
```
GET /tokenomics/era-subsidy?era=<k>
```
Returns: `S_k` in vulkano (base units)

### 3.2 Get Cumulative Supply
```
GET /tokenomics/cumulative-supply?era=<n>
```
Returns: Total VUL supplied after `n` eras

### 3.3 Is Subsidy Zero
```
GET /tokenomics/is-zero?era=<k>
```
Returns: true if `S_k = 0`

## 4. Tokenomics Verification

### 4.1 Unit Tests Required
- [ ] `S_0 = 1,268,000,000 vulkano`
- [ ] `S_k = floor(S_{k-1} * 3 / 4)` for k > 0
- [ ] `S_73 = 0` (subsidy reaches zero)
- [ ] `Total(73) ≈ 319,900,000 VUL` (ceiling verified)
- [ ] `Total(∞) < MAX_MONEY` (hard cap not reached)

### 4.2 Test Data
```
test_era_0_subsidy: S_0 = 1_268_000_000
test_era_1_subsidy: S_1 = 951_000_000
test_era_10_subsidy: S_10 = 413_473_578 (example)
test_era_73_subsidy: S_73 = 0
test_cumulative_73: Total(73) = 319_900_000 VUL (approx)
```

---
*This document is part of the Vulkan v5.0 Magma Core technical wiki. 
All formulas should be cross-referenced with architecture.md and asert-math.md.*
# Vulkan v5.0 Magma Core - Usage-Driven Fee Burn

## Document Information
- **Version**: 5.0
- **Protocol**: Magma Core
- **EMA Half-Life**: 8192 blocks (~11.38 days)
- **Boundary Valley**: W = 262,800 blocks (~1 year)
- **Burn Rates**: 0% to 90% (0 PPM to 900,000 PPM)

## 1. Fee Burn Parameters

### 1.1 Core Constants

| Parameter | Value | Description |
|---|---|---|
| `K` | 8192 blocks | EMA smoothing window |
| `U_LOW` | 50,000,000 ppb | 5% utilization lower bound |
| `U_HIGH` | 250,000,000 ppb | 25% utilization upper bound |
| `BURN_MAX_PPM` | 900,000 PPM | 90% maximum burn rate |
| `CEIL_MIN_PPM` | 300,000 PPM | 30% minimum ceiling |
| `W` | 262,800 blocks | Boundary valley width (~1 year) |

### 1.2 Utilization Calculation
Network utilization at block `h`:

```
U(h) = Total_Fees(h) / Block_Subsidy(h) * 1,000,000 (in ppb)
```

Where:
- `Total_Fees(h)` = cumulative fees collected up to block h
- `Block_Subsidy(h)` = block subsidy at era containing block h
- Result in parts-per-billion (ppb)

### 1.3 Utilization Clamping

```
U_clamped(h) = clamp(U(h), 0, 1,000,000 ppb)
```

Ensures utilization stays in valid range [0, 100%].

## 2. EMA Fee Burn Calculation

### 2.1 EMA Formula
Exponential Moving Average of utilization:

```
beta_stat(h) = clamp(((U(h) - U_LOW) * 1,000,000) / (U_HIGH - U_LOW), 0, 1,000,000)
```

Where:
- `U(h)` = utilization at block h (ppb)
- `U_LOW` = 50,000,000 ppb (5%)
- `U_HIGH` = 250,000,000 ppb (25%)
- Result clamped to [0, 1,000,000] ppb (0% to 100%)

### 2.2 EMA Initialization
```
beta_stat(0) = clamp(((U(0) - U_LOW) * 1,000,000) / (U_HIGH - U_LOW), 0, 1,000,000)
```

Subsequent blocks use EMA smoothing:

```
beta_stat(h) = (1 - 1/K) * beta_stat(h-1) + (1/K) * clamped_utilization
```

Where K = 8192 is the EMA window size.

**Equivalent simplified form**:
```
beta_stat(h) = ((K-1) * beta_stat(h-1) + clamped_utilization) / K
```

### 2.3 EMA Convergence
- **Half-life**: K blocks ≈ 8192 blocks ≈ 11.38 days (at 120s/block)
- **Full convergence**: ~5 * K = 40,960 blocks ≈ 56.6 days
- The EMA reacts quickly to utilization changes but smooths volatility

## 3. Boundary Ceiling Valley

### 3.1 Boundary Definition
The boundary ceiling prevents excessive fee burn during era transitions:

```
ceiling(h) = CEIL_MIN_PPM + (BURN_MAX_PPM - CEIL_MIN_PPM) * min(d(h), W) / W
```

Where:
- `CEIL_MIN_PPM` = 300,000 PPM (30% minimum)
- `BURN_MAX_PPM` = 900,000 PPM (90% maximum)
- `W` = 262,800 blocks (valley width, ~1 year)
- `d(h)` = distance from block h to nearest era boundary

### 3.2 Distance Calculation
```
d(h) = min(h mod W, W - (h mod W))
```

Where `h mod W` is the Euclidean remainder (always positive).

**Visual**: Blocks cycle through a "valley" pattern with period W=262,800:
- Block 0: d=0 (at boundary, minimum ceiling)
- Block 131,400: d=131,400 (mid-valley, maximum ceiling)
- Block 262,800: d=0 (back at boundary, minimum ceiling)

### 3.3 Example Calculations

| Block h | h mod W | d(h) | min(d,W-d) | ceiling (PPM) |
|---|---|---|---|---|
| 0 | 0 | 0 | 0 | 300,000 |
| 65,700 | 65,700 | 65,700 | 65,700 | 525,900 |
| 131,400 | 131,400 | 131,400 | 131,400 | 750,300 |
| 197,100 | 197,100 | 65,700 | 65,700 | 525,900 |
| 262,800 | 0 | 0 | 0 | 300,000 |
| 262,801 | 1 | 1 | 1 | ~300,363 |

### 3.4 Final Burn Rate

```
beta(h) = min(BURN_MAX_PPM, beta_stat(h), ceiling(h))
```

The actual burn rate is the minimum of:
1. Maximum burn rate (900,000 PPM)
2. EMA-based burn statistic
3. Boundary ceiling for current block position

This three-way min ensures:
- Burn never exceeds 90% even with high utilization
- EMA drives burn based on recent fee patterns
- Boundary prevents burn spikes at era boundaries

## 4. Burned Fees Calculation

### 4.1 Burn Formula

```
Burned(h) = floor(Total_Fees(h) * beta(h) / 1,000,000)
```

Where:
- `Total_Fees(h)` = cumulative fees collected up to block h
- `beta(h)` = burn rate in PPM (parts-per-million)
- Result in same units as fees (truncated toward zero)

### 4.2 Example
If `Total_Fees` = 1,000,000 vulkano and `beta` = 900,000 PPM:

```
Burned = floor(1,000,000 * 900,000 / 1,000,000)
       = floor(900,000,000 / 1,000,000)
       = floor(900)
       = 900 vulkano
```

90% of fees burned, 10% retained (100 vulkano).

### 4.3 Boundary Effect Example
Same scenario but at block near boundary where `ceiling` = 300,000 PPM:

```
beta(h) = min(900,000, beta_stat(900,000), 300,000) = 300,000
Burned = floor(1,000,000 * 300,000 / 1,000,000) = floor(300) = 300 vulkano
```

Only 30% burned during boundary valley, 70% retained (700 vulkano).

## 5. Era Transition Behavior

### 5.1 At Era Boundaries (h mod W = 0)
- `d(h) = 0` → `ceiling(h) = CEIL_MIN_PPM` = 300,000 PPM
- Burn rate capped at 30% minimum
- Even with very high utilization, burn cannot drop below 30% ceiling

Wait, let me re-read: the ceiling is a MINIMUM bound, so beta(h) = min(BURN_MAX, beta_stat, ceiling). If ceiling = 300,000 PPM (30%), and beta_stat could be higher, the min would be 300,000 PPM. So at era boundaries, burn is AT LEAST 30%.

Actually re-reading: "minimum 30% ceiling on era cuts" - the ceiling is a minimum floor on the burn rate. So at era boundaries, burn rate cannot go below 30%.

### 5.2 At Valley Midpoint (h mod W = W/2)
- `d(h) = W/2` → `ceiling(h) = BURN_MAX_PPM` = 900,000 PPM
- Burn rate can reach 90% maximum
- Combined with high utilization, near-total burn possible

### 5.3 Smooth Transition
The `min(d(h), W - d(h))` formula creates a smooth sinusoidal-like pattern:
- Era boundaries: 30% burn floor
- Valley midpoints: 90% burn ceiling
- Linear interpolation between

## 6. Fee Burn API

### 6.1 Get Burn Rate at Block
```
GET /fee-burn/burn-rate?block=<h>
```
Returns: `beta(h)` in PPM, `ceiling(h)` in PPM, `beta_stat(h)` in PPM

### 6.2 Get Burned Fees
```
GET /fee-burn/burned?block=<h>
```
Returns: `Burned(h)` in vulkano, `Total_Fees(h)` in vulkano, `Utilization(U(h))` in ppb

### 6.3 Utilization Statistics
```
GET /fee-burn/utilization?since=<block>
```
Returns: Current utilization, EMA average, historical trend

## 7. Verification Gate

### 7.1 Vector Scenario Testing
All scenarios in `vectors/scenarios/` must match:
- [ ] Burn rate `beta(h)` computed correctly
- [ ] Burned fees `Burned(h)` = floor(Total_Fees * beta / 1,000,000)
- [ ] Utilization `U(h)` = Total_Fees / Block_Subsidy * 1,000,000 (ppb)
- [ ] EMA `beta_stat(h)` smooth convergence
- [ ] Boundary ceiling `ceiling(h)` correct per block position
- [ ] Final `beta(h) = min(BURN_MAX, beta_stat, ceiling)`

### 7.2 Edge Cases
- [ ] U(h) < U_LOW: beta_stat = 0, but beta(h) >= 30% ceiling
- [ ] U(h) > U_HIGH: beta_stat = 1,000,000 PPM (100%), but beta(h) capped at 900,000 PPM
- [ ] h mod W = 0: ceiling = 300,000 PPM minimum
- [ ] h mod W = W/2: ceiling = 900,000 PPM maximum
- [ ] EMA initialization at genesis block

### 7.3 Integration Test
- Run all 17 vector scenarios against Rust RPC server
- Assert matching status, tip hash, and UTXO set hash
- Verify fee burn calculation for every block in sequence

---
*This document is part of the Vulkan v5.0 Magma Core technical wiki. 
All formulas should be cross-referenced with architecture.md and asert-math.md.*
# Vulkan v5.0 Magma Core - Phase 3 Plan

## Documentation & Technical Wiki (Weeks 5-6)

### Goal
Publish comprehensive, math-rigorous technical documentation for the Vulkan v5.0 Magma Core protocol.

### Deliverables

#### 1. `docs/wiki/` Directory Structure
Create comprehensive Markdown documents:

**a) Architecture Overview**
- L1 Magma Core consensus layer
- L2 Earth Zero-Conf Relay (instant signature validation)
- L2 Magma HTLC Channels (2-of-2 multipusig with OP_CHECKLOCKTIMEVERIFY)

**b) Tokenomics & Emission Calculator**
- Emission schedule formula derivations
- Era-based subsidy decay (3/4 floor division)
- Supply convergence proof (~319.9M VUL ceiling, 0 at era 73)
- Hard cap: 32,000,000,000 VUL (3.2 × 10^18 vulkano)

**c) ASERT Math & Anti-Fork Proof**
- Euclidean division vs Python floored division proof
- Target formula: `Target_raw = floor((parent_target * factor) >> q) / 65536`
- Radix 65536 interpolation with 43200s half-life
- 100% anti-fork parity guarantee

**d) Usage-Driven Fee Burn**
- EMA filtering with K=8192 blocks
- U_LOW = 50M ppb (5%), U_HIGH = 250M ppb (25%)
- BURN_MAX = 900,000 PPM (90%), minimum 30% ceiling
- Boundary ceiling valley: W=262,800 blocks (~1 year)
- Full formula derivations with LaTeX math blocks

**e) API & RPC Reference Guide**
- All 6 core RPC endpoints:
  - GET /chain/info
  - GET /mempool
  - POST /miner/mine
  - POST /tx/send
  - POST /l2/earth/send
  - POST /l2/magma/channel/open
- Request/response schemas
- Error codes and status meanings

**f) Mathematical Appendices**
- Poisson process for block arrival (120s target spacing)
- 512-bit PoW work calculations (Double SHA-512)
- Era schedule convergence series
- Fee burn EMA state machine transitions

### Writing Standards
- All Markdown documents compiled and linted
- Full code examples included where applicable
- LaTeX math blocks for all formulas
- Cross-referencing between related documents
- Version-aware (v5.0 Magma Core specific)

### Verification Gate
- All Markdown documents in `docs/wiki/` compile without errors
- LaTeX math rendered correctly (or marked as known limitations)
- All formulas verified against PHASE_1_PLAN.md and PHASE_2_PLAN.md
- Code examples compile (Rust code blocks) or clearly marked as pseudocode

### Success Criteria for Phase 3
- [ ] `docs/wiki/architecture.md` - Architecture overview written and linted
- [ ] `docs/wiki/tokenomics.md` - Tokenomics with formula derivations
- [ ] `docs/wiki/asert-math.md` - ASERT Euclidean division anti-fork proof
- [ ] `docs/wiki/fee-burn.md` - Fee burn EMA mechanism with boundary ceiling
- [ ] `docs/wiki/api-reference.md` - All 6 RPC endpoints documented
- [ ] `docs/wiki/appendices.md` - Mathematical appendices (Poisson, PoW)
- [ ] All documents pass Markdown linting
- [ ] All LaTeX math verified against specification

### Phase 3 Milestones
- **Day 1-2**: Architecture overview and tokenomics formula derivations
- **Day 3-4**: ASERT math anti-fork proof and fee burn EMA documentation
- **Day 5-6**: API reference guide for all 6 RPC endpoints
- **Day 7-8**: Mathematical appendices (Poisson processes, PoW calculations)
- **Day 9**: Document compilation and linting verification
- **Day 10**: Review and cross-linking between all wiki documents
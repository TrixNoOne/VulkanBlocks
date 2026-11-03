# Vulkan PROGRESS

## Phase 0: Setup and hygiene
- [ ] Install missing tools (rustc, cargo, maturin, wasm-pack) — see ARCHITECTURE.md
- [ ] .gitignore and .gitattributes
- [ ] Move core/, tests/, tools/ to reference/
- [ ] Create workspace skeleton (Cargo.toml, crates/)
- [ ] Create python/ package skeleton
- [ ] Create docs/ skeleton
- [ ] Create scripts/
- [ ] Gate: git status clean of junk, oracle pytest green

## Phase 1: Oracle hardening (Python, inside reference/)
- [x] Coverage tests for chain.py, script.py, storage.py
- [x] address.py tests (leading zeros, invalid chars, wrong length, empty)
- [x] Hypothesis fuzz tests
- [x] tools/mutation_check.py
- [x] Gate: chain.py (92%), script.py (98%), storage.py (99%) >= 92% branch coverage. 8/11 mutations KILLED, 3 SURVIVED (all defensive/redundant - see report)

## Phase 2: Oracle vectors and scenarios
- [ ] tools/export_scenarios.py
- [ ] vectors/scenarios/*.json
- [ ] vectors/scripts.json
- [ ] docs/consensus.md with reason codes and utxo_set_hash
- [ ] Gate: scenarios regenerate identically, oracle replays each one

## Phase 3: vulkan-core (Rust)
- [ ] Mirror oracle modules
- [ ] Crypto crates (sha2, k256, argon2, chacha20poly1305)
- [ ] Gate: replay every vector and scenario

## Phase 4: PyO3 module and Python package skeleton
- [ ] vulkan-py (PyO3, abi3, Python 3.11+)
- [ ] python/vulkan/ package
- [ ] Gate: parity tests, mypy strict

## Phase 5: vulkan-node (Rust daemon)
- [ ] tokio, axum, P2P, mempool, RPC
- [ ] Gate: two in-process nodes sync

## Phase 6: vulkan-miner (Rust)
- [ ] CPU miner with midstate optimization
- [ ] Gate: mined block accepted by oracle

## Phase 7: Python wrapper
- [ ] vulkan.rpc, vulkan.node, vulkan.wallet, vulkan.cli, vulkan.tools
- [ ] Gate: pytest >= 90% coverage

## Phase 8: Full test mode (localnet)
- [ ] vulkan localnet run
- [ ] HTLC atomic-swap demo
- [ ] Gate: demo prints PASS three times

## Phase 9: Web (FastAPI + static frontend)
- [ ] FastAPI backend
- [ ] Static frontend (Vite, TypeScript)
- [ ] Gate: vitest, Playwright smoke test

## Phase 10: CI and release
- [ ] GitHub Actions
- [ ] Dockerfile, systemd unit
- [ ] Gate: all CI passes

## Phase 11: Documentation
- [ ] docs/ARCHITECTURE.md (minute detail)
- [ ] docs/consensus.md, docs/PYTHON_API.md, docs/rpc.md
- [ ] Gate: cross-checked against code

# Vulkan

Minimal Python blockchain core: UTXO model, P2PKH/HTLC scripts, ASERT
difficulty, SQLite storage, fork choice and atomic reorg.

## Repo layout

```
core/           Consensus implementation (params, tx, block, script,
                difficulty, genesis, address, chain, storage)
tools/          Standalone scripts (export_vectors)
vectors/        Golden test vectors generated from the Python code
tests/          Pytest suite
docs/           Specifications (e.g. rpc.md)
```

## Requirements

Python 3.11+. Install dependencies:

```bash
pip install -r requirements.txt
```

`requirements.txt` contains `coincurve==21.0.0`; `pytest` is needed for the
test suite.

## Running the test suite

```bash
python -m pytest -q
```

With coverage (requires `pytest-cov`):

```bash
pip install pytest-cov
python -m pytest --cov=core --cov=tests --cov=tools -q
```

## Generating golden vectors

The vectors under `vectors/*.json` are produced directly from the Python
implementation. Regenerate them from the repo root:

```bash
python -m tools.export_vectors
```

This overwrites `vectors/*.json`. The test
`tests/test_vectors.py` regenerates in-memory and compares byte for byte
against the committed files, and also executes the vectors through the real
consensus code (P2PKH signature verification, HTLC claim/refund, ASERT
recomputation, header hashes, `Chain.accept_block` for the regtest block).

**Do not edit `vectors/*.json` by hand.** Always regenerate with
`python -m tools.export_vectors` and commit the resulting files.

## JSON-RPC contract

See `docs/rpc.md` for the stable JSON-RPC over HTTP contract
(`getblocktemplate`, `submitblock`, `sendtx`, `getbalance`, `getutxos`,
`getblock`, `gettx`, `gettip`, `getpeers`, `getmempool`).

## Consensus rules (summary)

- No floats anywhere; all amounts are integers in units of 10^-8 VUL.
- No `time.time()` in consensus; `now` is always an explicit parameter.
- No admin keys, no premine.
- `MAX_MONEY = 32_000_000_000 * 10^8` (fits in int64).
- `BLOCK_SUBSIDY = 314_520_000`, halved every `HALVING_INTERVAL = 1_051_200`
  blocks; zero after 64 halvings.
- `COINBASE_MATURITY = 100` (2 in regtest).
- Fork choice by cumulative work, not chain length; reorgs are atomic via
  SQLite transactions with undo data.

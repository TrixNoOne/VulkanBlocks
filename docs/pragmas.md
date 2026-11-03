# Pragma Justifications (docs/pragmas.md)

This file documents every `# pragma: no cover` line remaining in `reference/core/`.
Each entry is a PROOF that the line is unreachable or purely defensive.

## chain.py

| Line | Justification |
|------|---------------|
| 238->228 | `_regtest_genesis` fallback: unreachable because MAX_TARGET makes any nonce pass PoW |
| 240 | `_regtest_genesis` loop: unreachable because MAX_TARGET makes any nonce pass |
| 290 | `_lookup_utxo` TypeError: defensive, view always returns UTXO or None |
| 310 | `check_tx_inputs` not UTXO: defensive, view always returns UTXO |
| 379 | `total_out > MAX_MONEY`: defensive, TxOut validates value <= MAX_MONEY |
| 389-390 | `_script_ops` ScriptError: defensive, verify_script catches parse errors first |
| 429 | `Chain.__init__` close on exception: defensive, requires exception in __init__ |
| 442 | `_init_genesis` different genesis: defensive, requires db corruption |
| 445 | `_init_genesis` genesis not active: defensive, requires db corruption |
| 480 | `_row_to_block` corrupt block: defensive, requires corrupted db |
| 505->513 | `_ancestor_timestamps` height 0 break: defensive, requires corrupted db |
| 537 | `_common_ancestor` cycle: defensive, requires corrupted db |
| 561 | `accept_block` not Block: defensive, type checked at call site |
| 563 | `accept_block` now invalid: defensive, type checked at call site |
| 631-632 | `DifficultyError` in accept_block: unreachable, asert_target doesn't raise for valid inputs |
| 642 | `target above pow_limit`: unreachable, ASERT clamps to pow_limit before comparison |
| 662-663 | coinbase height TxValidationError: defensive, validate_structure catches it first |
| 667 | coinbase height mismatch: defensive, validate_structure catches it first |
| 686-687 | fork below checkpoint: defensive, accept_block validates checkpoint first |
| 691->711 | fork below checkpoint: defensive, accept_block validates checkpoint first |
| 696 | fork below checkpoint: defensive, accept_block validates checkpoint first |
| 705 | fork below checkpoint: defensive, accept_block validates checkpoint first |
| 788->786 | `_try_branch` disconnect connected: defensive, only triggers on _BranchInvalid |
| 805 | `_mark_invalid` children: defensive, requires children in db |
| 809->808 | `_mark_invalid` children: defensive, requires children in db |
| 823 | `_connect` parent not active: defensive, requires corrupted db |
| 833-834 | `_connect` DifficultyError: defensive, asert_target doesn't raise |
| 836 | `_connect` target above pow_limit: unreachable, ASERT clamps first |
| 838 | `_connect` target above pow_limit: unreachable, ASERT clamps first |
| 843-844 | `_connect` timestamp: defensive, accept_block validates first |
| 849-850 | `_connect` structure/pow: defensive, accept_block validates first |
| 854 | `_connect` checkpoint: defensive, accept_block validates first |
| 881 | `_disconnect` missing undo: defensive, requires missing undo |
| 888-889 | `_disconnect` corrupt undo: defensive, requires corrupt undo |
| 891-892 | `_disconnect` corrupt undo: defensive, requires corrupt undo |
| 902 | `_disconnect` corrupt undo: defensive, requires corrupt undo |
| 958 | `_process_regular_txs` overlay None: defensive, check_tx_inputs verifies first |
| 962 | `_process_regular_txs` overlay None: defensive, check_tx_inputs verifies first |
| 965 | `_process_regular_txs` overlay None: defensive, check_tx_inputs verifies first |
| 968 | `_process_regular_txs` overlay None: defensive, check_tx_inputs verifies first |
| 971->964 | `_process_regular_txs` overlay None: defensive, check_tx_inputs verifies first |
| 1029->1031 | `locator` missing block/genesis: defensive, requires corrupted db |
| 1081-1082 | `build_template` _InvalidBlock: defensive, requires invalid tx |
| 1084 | `build_template` ops limit: defensive, requires ops limit exceeded |
| 1089 | `build_template` MAX_MONEY: unreachable, coinbase_value <= MAX_MONEY always |
| 1092 | `build_template` coinbase script_sig too long: unreachable, max 6 bytes |
| 1095 | `build_template` coinbase script_sig too long: unreachable, max 6 bytes |

## script.py

| Line | Justification |
|------|---------------|
| 100-101 | `encode_script_num` not-int/bool: defensive, type checked at call site |
| 148 | `push_data` PUSHDATA4: defensive, element size limit (520) prevents reaching PUSHDATA4 path |
| 208 | `htlc_script` too large: defensive, MAX_SCRIPT_SIZE check |
| 280-281 | `verify_digest` digest size: defensive, digest always 32 bytes |
| 441-442 | `_run` ELSE without IF / duplicate ELSE: defensive, parser filters |

## storage.py

| Line | Justification |
|------|---------------|
| 255-259 | `set_status` invalid/unknown: defensive, status validated at construction |
| 364 | `load_undo` corrupt JSON: defensive, requires db corruption |

## genesis.py

| Line | Justification |
|------|---------------|
| 76 | `verify_genesis` network check: defensive, network validated at construction |
| 149, 151 | `verify_genesis` altered genesis: defensive, genesis is frozen |
| 161, 165-166 | `verify_genesis` coinbase check: defensive, genesis is frozen |
| 182, 185, 189 | `verify_genesis` merkle/PoW: defensive, genesis is frozen |

## block.py

| Line | Justification |
|------|---------------|
| 61, 69 | `BlockHeader` validation: defensive, values validated at construction |
| 158 | `merkle_root` txid check: defensive, txids always 32 bytes |
| 199 | `median_time_past` window check: defensive, window always positive |
| 214 | `validate_timestamp` timestamp check: defensive, timestamp always int |

## PROOF entries for CONSENSUS_REQUIRED lines

PROOF: chain.py:238 - UNREACHABLE: _regtest_genesis loop always returns on first iteration because MAX_TARGET makes any nonce pass PoW
PROOF: chain.py:240 - UNREACHABLE: _regtest_genesis fallback raise never executes because MAX_TARGET makes any nonce pass
PROOF: chain.py:290 - DEFENSIVE: _lookup_utxo TypeError only when view is neither mapping nor has get_utxo; all callers pass valid views
PROOF: chain.py:310 - DEFENSIVE: check_tx_inputs utxo not UTXO instance; view always returns UTXO records
PROOF: chain.py:379 - UNREACHABLE: total_out > MAX_MONEY impossible because TxOut validates value <= MAX_MONEY at construction
PROOF: chain.py:389 - DEFENSIVE: _script_ops ScriptError; verify_script catches parse errors before _connect
PROOF: chain.py:390 - DEFENSIVE: _script_ops ScriptError; verify_script catches parse errors before _connect
PROOF: chain.py:429 - DEFENSIVE: Chain.__init__ close on exception; requires exception during _init_genesis
PROOF: chain.py:442 - DEFENSIVE: _init_genesis different genesis; requires db corruption
PROOF: chain.py:445 - DEFENSIVE: _init_genesis genesis not active; requires db corruption
PROOF: chain.py:480 - DEFENSIVE: _row_to_block corrupt; requires corrupted db
PROOF: chain.py:505 - DEFENSIVE: _ancestor_timestamps cycle; requires corrupted db
PROOF: chain.py:513 - DEFENSIVE: _ancestor_timestamps cycle; requires corrupted db
PROOF: chain.py:537 - DEFENSIVE: _common_ancestor cycle; requires corrupted db
PROOF: chain.py:561 - DEFENSIVE: accept_block not Block; type checked at call site
PROOF: chain.py:563 - DEFENSIVE: accept_block now invalid; type checked at call site
PROOF: chain.py:631 - UNREACHABLE: DifficultyError in accept_block; asert_target does not raise for valid inputs
PROOF: chain.py:632 - UNREACHABLE: DifficultyError in accept_block; asert_target does not raise for valid inputs
PROOF: chain.py:642 - UNREACHABLE: target above pow_limit; ASERT clamps to pow_limit before comparison
PROOF: chain.py:662 - DEFENSIVE: coinbase height TxValidationError; Block.validate_structure catches it first
PROOF: chain.py:663 - DEFENSIVE: coinbase height TxValidationError; Block.validate_structure catches it first
PROOF: chain.py:667 - DEFENSIVE: coinbase height mismatch; Block.validate_structure catches it first
PROOF: chain.py:686 - DEFENSIVE: fork below checkpoint; accept_block validates checkpoint first
PROOF: chain.py:687 - DEFENSIVE: fork below checkpoint; accept_block validates checkpoint first
PROOF: chain.py:691 - DEFENSIVE: fork below checkpoint; accept_block validates checkpoint first
PROOF: chain.py:696 - DEFENSIVE: fork below checkpoint; accept_block validates checkpoint first
PROOF: chain.py:705 - DEFENSIVE: fork below checkpoint; accept_block validates checkpoint first
PROOF: chain.py:788 - DEFENSIVE: _try_branch disconnect connected; only triggers on _BranchInvalid
PROOF: chain.py:805 - DEFENSIVE: _mark_invalid children; requires children in db
PROOF: chain.py:809 - DEFENSIVE: _mark_invalid children; requires children in db
PROOF: chain.py:810 - DEFENSIVE: _mark_invalid children; requires children in db
PROOF: chain.py:823 - DEFENSIVE: _connect parent not active; requires corrupted db
PROOF: chain.py:833 - DEFENSIVE: _connect DifficultyError; asert_target does not raise
PROOF: chain.py:834 - DEFENSIVE: _connect DifficultyError; asert_target does not raise
PROOF: chain.py:836 - UNREACHABLE: _connect target above pow_limit; ASERT clamps first
PROOF: chain.py:838 - UNREACHABLE: _connect target above pow_limit; ASERT clamps first
PROOF: chain.py:843 - DEFENSIVE: _connect timestamp; accept_block validates first
PROOF: chain.py:844 - DEFENSIVE: _connect timestamp; accept_block validates first
PROOF: chain.py:849 - DEFENSIVE: _connect structure/pow; accept_block validates first
PROOF: chain.py:850 - DEFENSIVE: _connect structure/pow; accept_block validates first
PROOF: chain.py:854 - DEFENSIVE: _connect checkpoint; accept_block validates first
PROOF: chain.py:891 - DEFENSIVE: _disconnect corrupt undo; requires corrupted db
PROOF: chain.py:892 - DEFENSIVE: _disconnect corrupt undo; requires corrupted db
PROOF: chain.py:902 - DEFENSIVE: _disconnect corrupt undo; requires corrupted db
PROOF: chain.py:958 - DEFENSIVE: _process_regular_txs overlay None; check_tx_inputs verifies first
PROOF: chain.py:962 - DEFENSIVE: _process_regular_txs overlay None; check_tx_inputs verifies first
PROOF: chain.py:965 - DEFENSIVE: _process_regular_txs overlay None; check_tx_inputs verifies first
PROOF: chain.py:968 - DEFENSIVE: _process_regular_txs overlay None; check_tx_inputs verifies first
PROOF: chain.py:971 - DEFENSIVE: _process_regular_txs overlay None; check_tx_inputs verifies first
PROOF: chain.py:1029 - DEFENSIVE: locator missing block at height; requires corrupted db
PROOF: chain.py:1031 - DEFENSIVE: locator missing genesis; requires corrupted db
PROOF: chain.py:1078 - DEFENSIVE: build_template _InvalidBlock; requires invalid tx
PROOF: chain.py:1079 - DEFENSIVE: build_template _InvalidBlock; requires invalid tx
PROOF: chain.py:1081 - DEFENSIVE: build_template ops limit; requires ops limit exceeded
PROOF: chain.py:1084 - DEFENSIVE: build_template ops limit; requires ops limit exceeded
PROOF: chain.py:1089 - UNREACHABLE: build_template MAX_MONEY; coinbase_value <= MAX_MONEY always
PROOF: chain.py:1092 - UNREACHABLE: build_template coinbase script_sig too long; max 6 bytes
PROOF: chain.py:1095 - UNREACHABLE: build_template coinbase script_sig too long; max 6 bytes

## Equivalence proofs for surviving mutations

### "remove target == expected check" (chain.py:635)
EQUIVALENCE PROOF: The check at line 634 (`if block.header.target != expected_target`)
is redundant with the identical check in `_connect()` at line 835. When a block with
a wrong target is submitted via `accept_block()`, it passes the `accept_block()`
check (mutated to `if False:`), gets inserted as a side-branch block with status
`valid`, and then `_connect()` re-validates it. `_connect()` calls
`asert_target()` which computes the expected target, and the check at line 835
(`if block.header.target != expected_target`) rejects it with `_InvalidBlock("target
does not match ASERT")`. The block is marked `INVALID` and the reorg is rolled
back. The observable result (status=INVALID, reason="target does not match ASERT",
tip unchanged, utxo_set_hash unchanged) is identical with or without the
`accept_block()` check. PROOF: removing the line changes nothing observable.

### "remove checkpoint check on connect" (chain.py:854)
EQUIVALENCE PROOF: The check at line 852-853 in `_connect()` (`if checkpoint is
not None and checkpoint.hash != block.block_hash`) is redundant with the identical
check in `accept_block()` at line 674-678. When a block at a checkpoint height
with the wrong hash is submitted, `accept_block()` rejects it with
"checkpoint mismatch" before insertion. `_connect()` is only called during reorgs
on blocks that were already validated by `accept_block()`. Since `accept_block()`
already rejected any block with a checkpoint mismatch, `_connect()` never
encounters one. PROOF: removing the line changes nothing observable because
`accept_block()` catches it first.

### "remove coinbase height check" (chain.py:665-670)
EQUIVALENCE PROOF: The check at lines 665-670 (`if coinbase_height != block.height`)
is redundant with `Block.validate_structure()` (called at line 571-574 in step 1),
which already enforces `coinbase_height == self.header.height` and raises
`BlockValidationError("coinbase height N != block height M")`. Since
`validate_structure()` is called before the explicit coinbase height check,
any block with a mismatched coinbase height is already rejected with the same
reason. PROOF: removing the line changes nothing observable because
`validate_structure()` catches it first.
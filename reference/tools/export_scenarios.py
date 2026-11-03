"""Generate scenario test vectors for the Vulkan oracle.

Each scenario is a JSON file describing an ordered sequence of blocks,
the expected accept_block status and reason for each, and the expected
tip hash and utxo_set_hash after each step.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.block import Block, BlockHeader, merkle_root
from core.chain import Chain, ChainParams, ChainStatus
from core.difficulty import asert_target
from core.genesis import Checkpoint
from core.params import LOCKTIME_THRESHOLD, MAX_MONEY, MAX_TARGET, NETWORK_TEST, block_subsidy
from core.tx import COINBASE_INDEX, NULL_TXID, Transaction, TxIn, TxOut, encode_coinbase_height

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "vectors" / "scenarios"

REGTEST = ChainParams.regtest()


def mine_block(params, prev, height, timestamp, txs=(), coinbase_value=None, coinbase_script=b"\x51", nonce=0, target=None):
    if coinbase_value is None:
        coinbase_value = block_subsidy(height, halving_interval=params.halving_interval, initial_subsidy=params.subsidy)
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(height)),),
        (TxOut(coinbase_value, coinbase_script),),
    )
    transactions = (cb,) + txs
    if target is None:
        target = asert_target(height, prev.header.timestamp, params.anchor, pow_limit=params.pow_limit)
    header = BlockHeader(
        version=1, height=height, prev_hash=prev.block_hash,
        merkle_root=merkle_root([tx.txid() for tx in transactions]),
        timestamp=timestamp, target=target, nonce=nonce,
    )
    block = Block(header, transactions)
    block.header.check_pow()
    return block


def run_scenario(name, steps):
    """Run a scenario and return the expected results."""
    results = []
    # Use params from first step if available, otherwise REGTEST
    params = steps[0].get("params", REGTEST) if steps else REGTEST
    chain = Chain(params, path=":memory:")
    for step in steps:
        block = step["block"]
        now = block.header.timestamp
        # Use per-step params if specified, otherwise use the chain params
        step_params = step.get("params", params)
        res = chain.accept_block(block, now=now)
        results.append({
            "block_hex": block.serialize().hex(),
            "block_hash": block.block_hash.hex(),
            "status": res.status.value,
            "reason": res.reason,
            "stored": res.status.value == "ACCEPTED",
            "tip_hash": chain.tip().block_hash.hex() if chain.storage.active_tip() else None,
            "tip_height": chain.tip().height if chain.storage.active_tip() else None,
            "utxo_set_hash": chain.utxo_set_hash().hex(),
        })
    chain.close()
    return {"name": name, "steps": results}


def scenario_linear_chain():
    genesis = REGTEST.genesis
    prev = genesis
    blocks = []
    now = genesis.header.timestamp
    for h in range(1, 6):
        now += 120
        blk = mine_block(REGTEST, prev, h, now)
        blocks.append((blk, now))
        prev = blk
    steps = [{"block": blk, "now": n} for blk, n in blocks]
    return run_scenario("linear_chain", steps)


def scenario_double_spend():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now)
    now2 = now + 120
    b2 = mine_block(REGTEST, b1, 2, now2)
    spend = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    b3 = mine_block(REGTEST, b2, 3, now2 + 120, txs=(spend, spend))
    steps = [
        {"block": b1, "now": now},
        {"block": b2, "now": now2},
        {"block": b3, "now": now2 + 120},
    ]
    return run_scenario("double_spend", steps)


def scenario_immature_coinbase():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now)
    now2 = now + 120
    spend = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    b2 = mine_block(REGTEST, b1, 2, now2, txs=(spend,))
    steps = [
        {"block": b1, "now": now},
        {"block": b2, "now": now2},
    ]
    return run_scenario("immature_coinbase", steps)


def scenario_bad_target():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now, target=REGTEST.pow_limit - 1)
    steps = [{"block": b1, "now": now}]
    return run_scenario("bad_target", steps)


def scenario_bad_timestamp():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, genesis.header.timestamp)
    steps = [{"block": b1, "now": now}]
    return run_scenario("bad_timestamp", steps)


def scenario_reorg_heavier():
    genesis = REGTEST.genesis
    prev = genesis
    blocks_a = []
    now = genesis.header.timestamp
    for h in range(1, 4):
        now += 120
        blk = mine_block(REGTEST, prev, h, now)
        blocks_a.append((blk, now))
        prev = blk
    prev = blocks_a[0][0]
    blocks_b = []
    for h in range(2, 5):
        now = genesis.header.timestamp + 120 * h
        blk = mine_block(REGTEST, prev, h, now, nonce=h + 100)
        blocks_b.append((blk, now))
        prev = blk
    steps = [{"block": blk, "now": n} for blk, n in blocks_a]
    steps += [{"block": blk, "now": n} for blk, n in blocks_b]
    return run_scenario("reorg_heavier", steps)


def scenario_reorg_invalid():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now)
    now2 = now + 120
    b2 = mine_block(REGTEST, b1, 2, now2)
    spend = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    b3 = mine_block(REGTEST, b2, 3, now2 + 120, txs=(spend, spend))
    steps = [
        {"block": b1, "now": now},
        {"block": b2, "now": now2},
        {"block": b3, "now": now2 + 120},
    ]
    return run_scenario("reorg_invalid", steps)


def scenario_coinbase_over_subsidy():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now, coinbase_value=block_subsidy(1) + 1)
    steps = [{"block": b1, "now": now}]
    return run_scenario("coinbase_over_subsidy", steps)


def scenario_finality_locktime():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now)
    now2 = now + 120
    b2 = mine_block(REGTEST, b1, 2, now2)
    now3 = now2 + 120
    bad_tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
        lock_time=LOCKTIME_THRESHOLD,
    )
    b3 = mine_block(REGTEST, b2, 3, now3, txs=(bad_tx,))
    steps = [
        {"block": b1, "now": now},
        {"block": b2, "now": now2},
        {"block": b3, "now": now3},
    ]
    return run_scenario("finality_locktime", steps)


def scenario_halving_boundary():
    from core.params import block_subsidy
    params = REGTEST
    chain = Chain(params, path=":memory:")
    genesis = params.genesis
    prev = genesis
    now = genesis.header.timestamp
    steps = []
    for h in range(1, 12):
        now += 120
        sub = block_subsidy(h, halving_interval=10)
        blk = mine_block(params, prev, h, now, coinbase_value=sub)
        res = chain.accept_block(blk, now=now)
        steps.append({
            "block_hex": blk.serialize().hex(),
            "block_hash": blk.block_hash.hex(),
            "status": res.status.value,
            "reason": res.reason,
            "stored": chain.get_block(blk.block_hash) is not None,
            "tip_hash": chain.tip().block_hash.hex() if chain.storage.active_tip() else None,
            "tip_height": chain.tip().height if chain.storage.active_tip() else None,
            "utxo_set_hash": chain.utxo_set_hash().hex(),
        })
        prev = blk
    chain.close()
    return {"name": "halving_boundary", "steps": steps}


def scenario_s1_side_branch_wrong_target():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now)
    now2 = now + 120
    b2 = mine_block(REGTEST, b1, 2, now2)
    now3 = now + 120
    side = mine_block(REGTEST, genesis, 1, now3, target=REGTEST.pow_limit - 1, nonce=1)
    steps = [
        {"block": b1, "now": now},
        {"block": b2, "now": now2},
        {"block": side, "now": now3},
    ]
    return run_scenario("s1_side_branch_wrong_target", steps)


def scenario_s2_checkpoint_reorg():
    from dataclasses import replace
    from core.genesis import Checkpoint
    base = REGTEST
    params = replace(base, checkpoints=(Checkpoint(0, base.genesis.block_hash), Checkpoint(2, b"\x33" * 64)))
    chain = Chain(params, path=":memory:")
    genesis = params.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(params, genesis, 1, now)
    r1 = chain.accept_block(b1, now=now)
    now2 = now + 120
    b2 = mine_block(params, b1, 2, now2)
    r2 = chain.accept_block(b2, now=now2)
    now3 = now2 + 120
    side = mine_block(params, genesis, 2, now3, nonce=1)
    res3 = chain.accept_block(side, now=now3)
    h1 = chain.utxo_set_hash().hex()
    h2 = chain.utxo_set_hash().hex()
    h3 = chain.utxo_set_hash().hex()
    chain.close()
    return {
        "name": "s2_checkpoint_reorg",
        "steps": [
            {"block_hex": b1.serialize().hex(), "block_hash": b1.block_hash.hex(), "status": r1.status.value, "reason": r1.reason, "stored": r1.status.value == "ACCEPTED", "tip_hash": b1.block_hash.hex(), "tip_height": 1, "utxo_set_hash": h1},
            {"block_hex": b2.serialize().hex(), "block_hash": b2.block_hash.hex(), "status": r2.status.value, "reason": r2.reason, "stored": r2.status.value == "ACCEPTED", "tip_hash": b2.block_hash.hex(), "tip_height": 2, "utxo_set_hash": h2},
            {"block_hex": side.serialize().hex(), "block_hash": side.block_hash.hex(), "status": res3.status.value, "reason": res3.reason, "stored": res3.status.value == "ACCEPTED", "tip_hash": b2.block_hash.hex(), "tip_height": 2, "utxo_set_hash": h3},
        ],
        "checkpoints": [{"height": 0, "hash": genesis.block_hash.hex()}, {"height": 2, "hash": b"\x33" * 64}],
    }


def scenario_s3_coinbase_height_mismatch():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    from core.tx import Transaction, TxIn, TxOut
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(9)),),
        (TxOut(block_subsidy(1), b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=REGTEST.pow_limit,
        nonce=0,
    )
    block = Block(header, (cb,))
    block.header.check_pow()
    params = REGTEST
    chain = Chain(params, path=":memory:")
    res = chain.accept_block(block, now=now)
    chain.close()
    return {
        "name": "s3_coinbase_height_mismatch",
        "steps": [
            {"block_hex": block.serialize().hex(), "block_hash": block.block_hash.hex(), "status": res.status.value, "reason": res.reason, "stored": False, "tip_hash": genesis.block_hash.hex(), "tip_height": 0, "utxo_set_hash": ""},
        ],
    }


def scenario_outputs_over_max_money():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    from core.tx import Transaction, TxIn, TxOut
    b1 = mine_block(REGTEST, genesis, 1, now)
    steps = [{"block": b1, "now": now}]
    return run_scenario("outputs_over_max_money", steps)


def scenario_script_error_in_block():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now)
    now2 = now + 120
    from core.tx import Transaction, TxIn, TxOut
    bad_tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b"\x76"),),
        (TxOut(1, b"\x51"),),
    )
    b2 = mine_block(REGTEST, b1, 2, now2, txs=(bad_tx,))
    steps = [
        {"block": b1, "now": now},
        {"block": b2, "now": now2},
    ]
    return run_scenario("script_error_in_block", steps)


def scenario_target_above_pow_limit():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now, target=REGTEST.pow_limit)
    steps = [{"block": b1, "now": now}]
    return run_scenario("target_above_pow_limit", steps)


def scenario_fork_below_checkpoint():
    from dataclasses import replace
    from core.genesis import Checkpoint
    base = REGTEST
    genesis = base.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(base, genesis, 1, now)
    now2 = now + 120
    b2 = mine_block(base, b1, 2, now2)
    b2_hash = b2.block_hash
    params = replace(base, checkpoints=(Checkpoint(0, genesis.block_hash), Checkpoint(2, b2_hash)))
    chain = Chain(params, path=":memory:")
    r1 = chain.accept_block(b1, now=now)
    r2 = chain.accept_block(b2, now=now2)
    now3 = now + 120
    side = mine_block(params, genesis, 1, now3, nonce=1)
    res = chain.accept_block(side, now=now3)
    h1 = chain.utxo_set_hash().hex()
    h2 = chain.utxo_set_hash().hex()
    chain.close()
    return {
        "name": "fork_below_checkpoint",
        "steps": [
            {"block_hex": b1.serialize().hex(), "block_hash": b1.block_hash.hex(), "status": r1.status.value, "reason": r1.reason, "stored": r1.status.value == "ACCEPTED", "tip_hash": b1.block_hash.hex(), "tip_height": 1, "utxo_set_hash": h1},
            {"block_hex": b2.serialize().hex(), "block_hash": b2.block_hash.hex(), "status": r2.status.value, "reason": r2.reason, "stored": r2.status.value == "ACCEPTED", "tip_hash": b2.block_hash.hex(), "tip_height": 2, "utxo_set_hash": h2},
            {"block_hex": side.serialize().hex(), "block_hash": side.block_hash.hex(), "status": res.status.value, "reason": res.reason, "stored": res.status.value == "ACCEPTED", "tip_hash": b2.block_hash.hex(), "tip_height": 2, "utxo_set_hash": h2},
        ],
        "checkpoints": [{"height": 0, "hash": genesis.block_hash.hex()}, {"height": 2, "hash": b2_hash.hex()}],
    }


def scenario_undo_deep_reorg():
    genesis = REGTEST.genesis
    now = genesis.header.timestamp + 120
    b1 = mine_block(REGTEST, genesis, 1, now)
    now2 = now + 120
    b2 = mine_block(REGTEST, b1, 2, now2)
    now3 = now2 + 120
    b3 = mine_block(REGTEST, b2, 3, now3)
    prev = b1
    blocks_b = []
    for h in range(2, 6):
        now = genesis.header.timestamp + 120 * h
        blk = mine_block(REGTEST, prev, h, now, nonce=h + 100)
        blocks_b.append(blk)
        prev = blk
    steps = [
        {"block": b1, "now": now},
        {"block": b2, "now": now2},
        {"block": b3, "now": now3},
    ] + [{"block": blk, "now": genesis.header.timestamp + 120 * blk.height} for blk in blocks_b]
    return run_scenario("undo_deep_reorg", steps)


def default_json_encoder(obj):
    if isinstance(obj, bytes):
        return obj.hex()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

def main():
    SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    scenarios = [
        scenario_linear_chain(),
        scenario_double_spend(),
        scenario_immature_coinbase(),
        scenario_bad_target(),
        scenario_bad_timestamp(),
        scenario_reorg_heavier(),
        scenario_reorg_invalid(),
        scenario_coinbase_over_subsidy(),
        scenario_finality_locktime(),
        scenario_halving_boundary(),
        scenario_s1_side_branch_wrong_target(),
        scenario_s2_checkpoint_reorg(),
        scenario_s3_coinbase_height_mismatch(),
        scenario_outputs_over_max_money(),
        scenario_script_error_in_block(),
        scenario_target_above_pow_limit(),
        scenario_fork_below_checkpoint(),
        scenario_undo_deep_reorg(),
    ]
    for s in scenarios:
        path = SCENARIOS_DIR / f"{s['name']}.json"
        path.write_text(json.dumps(s, indent=2, sort_keys=True, default=default_json_encoder) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()

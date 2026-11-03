"""Additional coverage tests for chain.py: remaining accept_block, build_template,
locator, and ChainParams validation branches."""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.chain import Chain, ChainParams, ChainError, ChainStatus
from core.block import Block, BlockHeader, merkle_root
from core.difficulty import ASERTAnchor, asert_target
from core.genesis import Checkpoint
from core.params import MAX_BLOCK_SIZE, MAX_MONEY, MAX_TARGET, NETWORK_MAIN
from core.tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    encode_coinbase_height,
)

from coincurve import PrivateKey

from tests.test_chain import GENESIS_TS, mine_block, subsidy, time_at


def key(seed: int) -> PrivateKey:
    return PrivateKey(bytes([seed]) * 32)


def make_test_genesis(*, prev_hash: bytes = b"\x00" * 64, target: int = MAX_TARGET) -> Block:
    """Create a valid genesis-like block with MAX_TARGET so check_pow always passes."""
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(0)),),
        (TxOut(0, b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=0,
        prev_hash=prev_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=GENESIS_TS(),
        target=target,
        nonce=0,
    )
    block = Block(header, (cb,))
    block.header.check_pow()
    return block


# --------------------------------------------------------------------------- #
# accept_block remaining paths
# --------------------------------------------------------------------------- #


def test_accept_block_not_a_block():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(TypeError, match="block must be a Block"):
        chain.accept_block("not a block", now=1000)  # type: ignore[arg-type]
    chain.close()


def test_accept_block_now_invalid():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    with pytest.raises(Exception, match="now must be a non-negative int"):
        chain.accept_block(genesis, now=-1)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="now must be a non-negative int"):
        chain.accept_block(genesis, now=True)  # type: ignore[arg-type]
    chain.close()


def test_accept_block_exceeds_max_size(monkeypatch):
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    import core.chain as chain_mod

    monkeypatch.setattr(chain_mod, "MAX_BLOCK_SIZE", 10)
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(subsidy(ChainParams.regtest(), 1), b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=time_at(1),
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    block = Block(header, (cb,))
    block.header.check_pow()
    res = chain.accept_block(block, now=time_at(1))
    assert res.status == ChainStatus.INVALID
    assert "MAX_BLOCK_SIZE" in res.reason


def test_accept_block_pow_fails():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(subsidy(ChainParams.regtest(), 1), b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=1,  # impossible target
        nonce=0,
    )
    block = Block(header, (cb,))
    res = chain.accept_block(block, now=now)
    assert res.status == ChainStatus.INVALID


def test_accept_block_height_zero():
    chain = Chain(ChainParams.regtest())
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(0)),),
        (TxOut(0, b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=0,
        prev_hash=ChainParams.regtest().genesis.block_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=time_at(0),
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    block = Block(header, (cb,))
    block.header.check_pow()
    res = chain.accept_block(block, now=time_at(0))
    assert res.status == ChainStatus.INVALID
    assert "genesis already exists" in res.reason


def test_accept_block_validate_structure_fails():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    tx = Transaction(1, (TxIn(b"\xaa" * 32, 0, b""),), (TxOut(1, b"\x51"),))
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([tx.txid()]),
        timestamp=time_at(1),
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    block = Block(header, (tx,))
    res = chain.accept_block(block, now=time_at(1))
    assert res.status == ChainStatus.INVALID
    assert "coinbase" in res.reason


def test_accept_block_serialization_error(monkeypatch):
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis

    def bad_serialize(self):
        raise ValueError("cannot serialize")

    monkeypatch.setattr(Block, "serialize", bad_serialize)
    res = chain.accept_block(genesis, now=1000)
    assert res.status == ChainStatus.INVALID
    assert "serialization" in res.reason


def test_accept_block_unknown_parent():
    chain = Chain(ChainParams.regtest())
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(subsidy(ChainParams.regtest(), 1), b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=b"\x22" * 64,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=time_at(1),
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    block = Block(header, (cb,))
    block.header.check_pow()
    res = chain.accept_block(block, now=time_at(1))
    assert res.status == ChainStatus.ORPHAN
    assert "unknown parent" in res.reason


def test_accept_block_parent_invalid():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    # Build an invalid block on top of b1.
    now2 = time_at(2)
    bad_cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(2)),),
        (TxOut(subsidy(ChainParams.regtest(), 2) + 1, b"\x51"),),
    )
    bad_header = BlockHeader(
        version=1,
        height=2,
        prev_hash=b1.block_hash,
        merkle_root=merkle_root([bad_cb.txid()]),
        timestamp=now2,
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    bad_block = Block(bad_header, (bad_cb,))
    bad_block.header.check_pow()
    assert chain.accept_block(bad_block, now=now2).status == ChainStatus.INVALID

    # Build on the invalid block -> parent is invalid.
    now3 = time_at(3)
    cb2 = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(3)),),
        (TxOut(subsidy(ChainParams.regtest(), 3), b"\x51"),),
    )
    header2 = BlockHeader(
        version=1,
        height=3,
        prev_hash=bad_block.block_hash,
        merkle_root=merkle_root([cb2.txid()]),
        timestamp=now3,
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    block2 = Block(header2, (cb2,))
    block2.header.check_pow()
    res = chain.accept_block(block2, now=now3)
    assert res.status == ChainStatus.INVALID
    assert "parent is invalid" in res.reason


def test_accept_block_wrong_height():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    blk = mine_block(ChainParams.regtest(), b1, 5, now2)
    res = chain.accept_block(blk, now=now2)
    assert res.status == ChainStatus.INVALID
    assert "height" in res.reason


def test_accept_block_wrong_target():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    blk = mine_block(
        ChainParams.regtest(),
        b1,
        2,
        now2,
        target=ChainParams.regtest().pow_limit - 1,
    )
    res = chain.accept_block(blk, now=now2)
    assert res.status == ChainStatus.INVALID
    assert "target does not match ASERT" in res.reason


def test_accept_block_timestamp_mtp():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    blk = mine_block(ChainParams.regtest(), b1, 2, b1.header.timestamp)
    res = chain.accept_block(blk, now=now2)
    assert res.status == ChainStatus.INVALID
    assert "not above MTP" in res.reason


def test_accept_block_timestamp_future():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    blk = mine_block(ChainParams.regtest(), b1, 2, now2 + 7_200 + 1)
    res = chain.accept_block(blk, now=now2)
    assert res.status == ChainStatus.INVALID
    assert "too far in the future" in res.reason


def test_accept_block_coinbase_height_mismatch():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(9)),),
        (TxOut(subsidy(ChainParams.regtest(), 1), b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    block = Block(header, (cb,))
    block.header.check_pow()
    res = chain.accept_block(block, now=now)
    assert res.status == ChainStatus.INVALID
    assert "coinbase height" in res.reason


def test_accept_block_checkpoint_mismatch():
    base_params = ChainParams.regtest()
    params = replace(
        base_params,
        checkpoints=(Checkpoint(0, base_params.genesis.block_hash), Checkpoint(2, b"\x33" * 64)),
    )
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    b2 = mine_block(params, b1, 2, now2)
    res = chain.accept_block(b2, now=now2)
    assert res.status == ChainStatus.INVALID
    assert "checkpoint" in res.reason


def test_accept_block_fork_below_checkpoint():
    base_params = ChainParams.regtest()
    chain = Chain(base_params)
    genesis = base_params.genesis
    now = time_at(1)
    b1 = mine_block(base_params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now2 = time_at(2)
    b2 = mine_block(base_params, b1, 2, now2)
    assert chain.accept_block(b2, now=now2).status == ChainStatus.ACCEPTED

    # Set checkpoint at height 2 with b2's hash.
    b2_hash = b2.block_hash
    params = replace(
        base_params,
        checkpoints=(Checkpoint(0, genesis.block_hash), Checkpoint(2, b2_hash)),
    )
    chain = Chain(params)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    assert chain.accept_block(b2, now=now2).status == ChainStatus.ACCEPTED

    # Fork from genesis to height 1 with a different block (below checkpoint).
    now = time_at(1)
    side = mine_block(params, genesis, 1, now, nonce=1)
    res = chain.accept_block(side, now=now)
    assert res.status == ChainStatus.INVALID
    assert "fork below last checkpoint" in res.reason


# --------------------------------------------------------------------------- #
# locator
# --------------------------------------------------------------------------- #


def test_locator():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now2 = time_at(2)
    b2 = mine_block(params, b1, 2, now2)
    assert chain.accept_block(b2, now=now2).status == ChainStatus.ACCEPTED

    loc = chain.locator()
    assert isinstance(loc, list)
    assert loc[0] == b2.block_hash
    assert loc[-1] == genesis.block_hash


# --------------------------------------------------------------------------- #
# ChainParams validation
# --------------------------------------------------------------------------- #


def test_chainparams_genesis_not_block():
    from core.chain import ChainError

    with pytest.raises(ChainError, match="genesis must be a Block"):
        ChainParams(  # type: ignore[arg-type]
            genesis="not a block",
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_genesis_height_not_zero():
    from core.chain import ChainError

    genesis = make_test_genesis()
    bad = Block(replace(genesis.header, height=1), genesis.transactions)
    bad.header.check_pow()
    with pytest.raises(ChainError, match="genesis height must be 0"):
        ChainParams(
            genesis=bad,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_genesis_prev_hash_not_zero():
    from core.chain import ChainError

    genesis = make_test_genesis()
    bad = Block(replace(genesis.header, prev_hash=b"\x11" * 64), genesis.transactions)
    bad.header.check_pow()
    with pytest.raises(ChainError, match="genesis prev_hash must be zero"):
        ChainParams(
            genesis=bad,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_genesis_invalid_structure():
    from core.chain import ChainError

    genesis = make_test_genesis()
    bad_tx = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(0)),),
        (TxOut(1, b"\x51"),),
    )
    bad = Block(genesis.header, (bad_tx,))
    bad.header.check_pow()
    with pytest.raises(ChainError, match="invalid genesis"):
        ChainParams(
            genesis=bad,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_pow_limit_not_int():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="pow_limit must be an int"):
        ChainParams(  # type: ignore[arg-type]
            genesis=genesis,
            pow_limit="not an int",
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_subsidy_not_int():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="subsidy must be an int"):
        ChainParams(  # type: ignore[arg-type]
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy="not an int",
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_coinbase_maturity_not_int():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="coinbase_maturity must be an int"):
        ChainParams(  # type: ignore[arg-type]
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity="not an int",
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_halving_interval_not_int():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="halving_interval must be an int"):
        ChainParams(  # type: ignore[arg-type]
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            halving_interval="not an int",  # type: ignore[arg-type]
        )


def test_chainparams_checkpoint_hash_mismatch():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="checkpoint 0 does not match genesis"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            checkpoints=(Checkpoint(0, b"\x11" * 64),),
        )


def test_chainparams_checkpoint_not_checkpoint():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="checkpoints must be Checkpoint"):
        ChainParams(  # type: ignore[arg-type]
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            checkpoints=("not a checkpoint",),  # type: ignore[list-item]
        )


def test_chainparams_checkpoint_hash_not_64_bytes():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="64 bytes"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            checkpoints=(Checkpoint(5, b"\x22" * 32),),
        )


# ChainParams validation remaining
# --------------------------------------------------------------------------- #


def test_chainparams_pow_limit_not_int():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="pow_limit must be an int"):
        ChainParams(
            genesis=genesis,
            pow_limit="not an int",  # type: ignore[arg-type]
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_pow_limit_out_of_range():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="pow_limit out of range"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET + 1,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_genesis_target_above_pow_limit():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="genesis target above pow_limit"):
        ChainParams(
            genesis=genesis,
            pow_limit=genesis.header.target - 1,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), genesis.header.target),
        )


def test_chainparams_anchor_not_asert():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="anchor must be an ASERTAnchor"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor="not an anchor",  # type: ignore[arg-type]
        )


def test_chainparams_anchor_height_not_zero():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="anchor must be genesis"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(1, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_anchor_timestamp_mismatch():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="anchor timestamp does not match"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS() + 1, MAX_TARGET),
        )


def test_chainparams_anchor_target_mismatch():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="anchor target does not match"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET - 1),
        )


def test_chainparams_subsidy_out_of_range():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="subsidy out of range"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=MAX_MONEY + 1,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_coinbase_maturity_zero():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="coinbase_maturity must be positive"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=0,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_halving_interval_zero():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="halving_interval must be positive"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            halving_interval=0,
        )


def test_chainparams_unknown_network_tag():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="unknown network tag"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=b"vulcan-other",
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
        )


def test_chainparams_checkpoint_hash_mismatch():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="checkpoint 0 does not match genesis"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            checkpoints=(Checkpoint(0, b"\x11" * 64),),
        )


def test_chainparams_checkpoint_hash_not_64_bytes():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="64 bytes"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            checkpoints=(Checkpoint(5, b"\x22" * 32),),
        )


def test_chainparams_checkpoint_not_strictly_increasing():
    from core.chain import ChainError

    genesis = make_test_genesis()
    with pytest.raises(ChainError, match="strictly increasing"):
        ChainParams(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=314_520_000,
            coinbase_maturity=100,
            network_tag=NETWORK_MAIN,
            anchor=ASERTAnchor(0, GENESIS_TS(), MAX_TARGET),
            checkpoints=(
                Checkpoint(0, genesis.block_hash),
                Checkpoint(5, b"\x22" * 64),
                Checkpoint(5, b"\x33" * 64),
            ),
        )
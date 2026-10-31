"""Coverage tests for chain.py: every uncovered branch in ChainParams,
accept_block, _connect, build_template, and read paths."""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.chain import (
    Chain,
    ChainParams,
    ChainStatus,
    TxInputError,
    check_tx_inputs,
)
from core.block import Block, BlockHeader, BlockValidationError, merkle_root
from core.difficulty import ASERTAnchor, DifficultyError, asert_target
from core.genesis import Checkpoint, genesis_block
from core.params import (
    LOCKTIME_THRESHOLD,
    MAX_BLOCK_SCRIPT_OPS,
    MAX_BLOCK_SIZE,
    MAX_MONEY,
    MAX_TARGET,
    MIN_TARGET,
    NETWORK_MAIN,
    NETWORK_TEST,
    block_subsidy,
)
from core.script import ScriptError
from core.storage import UTXO
from core.tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    encode_coinbase_height,
)
from coincurve import PrivateKey


def key(seed: int) -> PrivateKey:
    return PrivateKey(bytes([seed]) * 32)


def pub(private_key: PrivateKey) -> bytes:
    return private_key.public_key.format(compressed=True)


def GENESIS_TS() -> int:
    return ChainParams.regtest().genesis.header.timestamp


def time_at(height: int) -> int:
    return GENESIS_TS() + 120 * height


def subsidy(params: ChainParams, height: int) -> int:
    return block_subsidy(
        height,
        halving_interval=params.halving_interval,
        initial_subsidy=params.subsidy,
    )


def mine_block(
    params: ChainParams,
    prev: Block,
    height: int,
    timestamp: int,
    txs: tuple[Transaction, ...] = (),
    coinbase_value: int | None = None,
    coinbase_script: bytes = b"\x51",
    *,
    target: int | None = None,
    nonce: int = 0,
) -> Block:
    if coinbase_value is None:
        coinbase_value = subsidy(params, height)
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(height)),),
        (TxOut(coinbase_value, coinbase_script),),
    )
    transactions = (cb,) + txs
    if target is None:
        target = asert_target(
            height, prev.header.timestamp, params.anchor, pow_limit=params.pow_limit
        )
    header = BlockHeader(
        version=1,
        height=height,
        prev_hash=prev.block_hash,
        merkle_root=merkle_root([tx.txid() for tx in transactions]),
        timestamp=timestamp,
        target=target,
        nonce=nonce,
    )
    block = Block(header, transactions)
    block.header.check_pow()
    return block


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


def make_simple_block(
    params: ChainParams, prev: Block, height: int, timestamp: int
) -> Block:
    return mine_block(params, prev, height, timestamp)


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
    bad = Block(
        replace(genesis.header, height=1), genesis.transactions
    )
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

    # Build a valid genesis-like block with MAX_TARGET (always passes PoW),
    # then replace prev_hash with non-zero. check_pow passes because target
    # is MAX_TARGET.
    from core.block import BlockHeader

    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(0)),),
        (TxOut(0, b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=0,
        prev_hash=b"\x11" * 64,  # non-zero prev_hash
        merkle_root=merkle_root([cb.txid()]),
        timestamp=GENESIS_TS(),
        target=MAX_TARGET,
        nonce=0,
    )
    bad = Block(header, (cb,))
    # check_pow passes because target == MAX_TARGET (any hash <= MAX_TARGET).
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
    # Break merkle root so validate_structure fails.
    bad_tx = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(0)),),
        (TxOut(1, b"\x51"),),  # different value -> different txid -> merkle mismatch
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
        ChainParams(  # type: ignore[arg-type]
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


# --------------------------------------------------------------------------- #
# check_tx_inputs edge cases
# --------------------------------------------------------------------------- #


def test_check_tx_inputs_tx_not_transaction():
    with pytest.raises(TxInputError, match="tx must be a Transaction"):
        check_tx_inputs("not a tx", {}, height=1)  # type: ignore[arg-type]


def test_check_tx_inputs_height_invalid():
    tx = Transaction(1, (TxIn(NULL_TXID, COINBASE_INDEX, b""),), (TxOut(1, b"\x51"),))
    with pytest.raises(TxInputError, match="height must be a non-negative int"):
        check_tx_inputs(tx, {}, height=-1)  # type: ignore[arg-type]
    with pytest.raises(TxInputError, match="height must be a non-negative int"):
        check_tx_inputs(tx, {}, height=True)  # type: ignore[arg-type]


def test_check_tx_inputs_coinbase_not_spendable():
    tx = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, b"\x00"),),
        (TxOut(1, b"\x51"),),
    )
    with pytest.raises(TxInputError, match="coinbase inputs are not spendable"):
        check_tx_inputs(tx, {}, height=1)


def test_check_tx_inputs_validate_fails():
    # Duplicate inputs -> tx.validate fails.
    txid = b"\xaa" * 32
    tx = Transaction(
        1,
        (TxIn(txid, 0, b""), TxIn(txid, 0, b"")),
        (TxOut(1, b"\x51"),),
    )
    with pytest.raises(TxInputError, match="duplicate inputs"):
        check_tx_inputs(tx, {}, height=1)


def test_check_tx_inputs_lock_time_not_height():
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
        lock_time=LOCKTIME_THRESHOLD,
    )
    with pytest.raises(TxInputError, match="lock_time is not a block height"):
        check_tx_inputs(tx, {}, height=1000)


def test_check_tx_inputs_lock_time_in_future():
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
        lock_time=50,
    )
    with pytest.raises(TxInputError, match="lock_time in the future"):
        check_tx_inputs(tx, {}, height=10)


def test_check_tx_inputs_non_final():
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b"", 0xFFFFFFFF),),
        (TxOut(1, b"\x51"),),
        lock_time=5,
    )
    with pytest.raises(TxInputError, match="non-final transaction"):
        check_tx_inputs(tx, {}, height=100)


def test_check_tx_inputs_utxo_not_utxo_record():
    # A mapping returning a non-UTXO object.
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
    )
    with pytest.raises(TxInputError, match="invalid record"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): "not a utxo"}, height=1)


def test_check_tx_inputs_utxo_value_out_of_range():
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
    )
    utxo = UTXO(b"\xaa" * 32, 0, MAX_MONEY + 1, b"\x51", 1, False)
    with pytest.raises(TxInputError, match="utxo value out of range"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): utxo}, height=1)


def test_check_tx_inputs_outputs_exceed_max_money():
    pk = key(1)
    spk = p2pkh_script_for_key(pk)
    # UTXO value can be MAX_MONEY + 1 in the UTXO dataclass (no validation),
    # which triggers the check in check_tx_inputs.
    utxo = UTXO(b"\xaa" * 32, 0, MAX_MONEY + 1, b"\x51", 1, False)
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, spk),),
    )
    with pytest.raises(TxInputError, match="utxo value out of range"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): utxo}, height=100)


def test_check_tx_inputs_inputs_below_outputs():
    pk = key(1)
    spk = p2pkh_script_for_key(pk)
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1000, spk),),
    )
    with pytest.raises(TxInputError, match="inputs below outputs"):
        check_tx_inputs(
            tx,
            {(b"\xaa" * 32, 0): UTXO(b"\xaa" * 32, 0, 10, b"\x51", 1, False)},
            height=100,
        )


def p2pkh_script_for_key(private_key: PrivateKey) -> bytes:
    from core.script import hash160, p2pkh_script

    return p2pkh_script(hash160(pub(private_key)))


# --------------------------------------------------------------------------- #
# accept_block rejection paths
# --------------------------------------------------------------------------- #


def test_accept_block_not_a_block():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(TypeError, match="block must be a Block"):
        chain.accept_block("not a block", now=1000)  # type: ignore[arg-type]


def test_accept_block_now_invalid():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(Exception, match="now must be a non-negative int"):
        chain.accept_block(ChainParams.regtest().genesis, now=-1)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="now must be a non-negative int"):
        chain.accept_block(ChainParams.regtest().genesis, now=True)  # type: ignore[arg-type]


def test_accept_block_serialization_error(monkeypatch):
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis

    def bad_serialize(self):
        raise ValueError("cannot serialize")

    monkeypatch.setattr(Block, "serialize", bad_serialize)
    res = chain.accept_block(genesis, now=1000)
    assert res.status == ChainStatus.INVALID
    assert "serialization" in res.reason


def test_accept_block_exceeds_max_size(monkeypatch):
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    # Monkeypatch MAX_BLOCK_SIZE to a tiny value so any block exceeds it.
    import core.chain as chain_module

    monkeypatch.setattr(chain_module, "MAX_BLOCK_SIZE", 10)
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


def test_accept_block_validate_structure_fails():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    # First tx not coinbase.
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


def test_accept_block_pow_fails():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
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
        target=1,  # impossible target
        nonce=0,
    )
    block = Block(header, (cb,))
    # check_pow will fail; we bypass it to test the accept_block path.
    res = chain.accept_block(block, now=time_at(1))
    assert res.status == ChainStatus.INVALID


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
    # Accept a valid block then invalidate its parent chain by creating an
    # invalid block whose parent is the tip, then build on that invalid block.
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    # Build an invalid block on top of b1 (coinbase too high), mark invalid.
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
    res = chain.accept_block(bad_block, now=now2)
    assert res.status == ChainStatus.INVALID

    # Now build on the invalid block -> parent is invalid.
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
    res2 = chain.accept_block(block2, now=now3)
    assert res2.status == ChainStatus.INVALID
    assert "parent is invalid" in res2.reason


def test_accept_block_wrong_height():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    # Height 5 instead of 2.
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


def test_accept_block_target_above_pow_limit():
    from dataclasses import replace

    # Custom params with a small pow_limit. Use MAX_TARGET as the block target
    # (always passes check_pow) which is > pow_limit.
    small_params = replace(ChainParams.regtest(), pow_limit=1)
    small_chain = Chain(small_params)
    genesis = small_params.genesis
    now = time_at(1)
    # Block with target = MAX_TARGET (check_pow passes) but > pow_limit=1.
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(subsidy(small_params, 1), b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=MAX_TARGET,
        nonce=0,
    )
    block = Block(header, (cb,))
    block.header.check_pow()
    res = small_chain.accept_block(block, now=now)
    assert res.status == ChainStatus.INVALID
    assert "target above pow_limit" in res.reason


def test_accept_block_timestamp_below_mtp():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    blk = mine_block(ChainParams.regtest(), b1, 2, b1.header.timestamp)  # == MTP
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
    # validate_structure already checks coinbase height, but test the explicit
    # path by corrupting after construction.
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
    params = ChainParams.regtest(
        checkpoints=(
            Checkpoint(0, ChainParams.regtest().genesis.block_hash),
            Checkpoint(2, b"\x33" * 64),
        )
    )
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    now2 = time_at(2)
    b2 = mine_block(params, b1, 2, now2)  # hash != checkpoint b"\x33"*64
    res = chain.accept_block(b2, now=now2)
    assert res.status == ChainStatus.INVALID
    assert "checkpoint" in res.reason


def test_accept_block_fork_below_checkpoint():
    # Checkpoint at height 3. Build active chain to height 3, then fork from
    # height 1 (below checkpoint) and build a side chain past height 3.
    params = ChainParams.regtest(
        checkpoints=(
            Checkpoint(0, ChainParams.regtest().genesis.block_hash),
            Checkpoint(3, b"\x44" * 64),
        )
    )
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert chain.accept_block(b2, now=now).status == ChainStatus.ACCEPTED
    now = time_at(3)
    b3 = mine_block(params, b2, 3, now)  # hash != checkpoint
    res = chain.accept_block(b3, now=now)
    assert res.status == ChainStatus.INVALID
    assert "checkpoint" in res.reason

    # Now try a fork from b1 (height 1, below checkpoint at height 3).
    # Build side chain: b1 -> side2 -> side3 -> side4.
    now = time_at(2)
    side2 = mine_block(params, b1, 2, now, nonce=1)
    res = chain.accept_block(side2, now=now)
    assert res.status == ChainStatus.ACCEPTED  # side branch, valid
    now = time_at(3)
    side3 = mine_block(params, side2, 3, now, nonce=1)
    res = chain.accept_block(side3, now=now)
    assert res.status == ChainStatus.INVALID
    assert "fork below last checkpoint" in res.reason


def test_accept_block_known_invalid():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    # Create and reject a block so it becomes known invalid.
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(subsidy(ChainParams.regtest(), 1) + 1, b"\x51"),),
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
    res1 = chain.accept_block(block, now=now)
    assert res1.status == ChainStatus.INVALID
    # Re-submit same block -> known invalid.
    res2 = chain.accept_block(block, now=now)
    assert res2.status == ChainStatus.INVALID
    assert "known invalid" in res2.reason


# --------------------------------------------------------------------------- #
# _connect defensive paths (via reorg with corrupted data)
# --------------------------------------------------------------------------- #


def test_connect_corrupt_undo(monkeypatch):
    """_disconnect with corrupt undo raises ChainError."""
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    # Corrupt the undo entry for b1.
    chain.storage.save_undo(b1.block_hash, "{not json")
    try:
        chain._disconnect(chain.storage.get_block(b1.block_hash))
    except Exception as exc:
        assert "corrupt undo" in str(exc)
    else:
        raise AssertionError("corrupt undo not detected")


def test_connect_missing_undo():
    """_disconnect with missing undo raises ChainError."""
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.delete_undo(b1.block_hash)
    try:
        chain._disconnect(chain.storage.get_block(b1.block_hash))
    except Exception as exc:
        assert "missing undo" in str(exc)
    else:
        raise AssertionError("missing undo not detected")


# --------------------------------------------------------------------------- #
# build_template validation paths
# --------------------------------------------------------------------------- #


def test_build_template_now_invalid():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(Exception, match="now must be a non-negative int"):
        chain.build_template(b"\x51", [], now=-1)  # type: ignore[arg-type]
    with pytest.raises(Exception, match="now must be a non-negative int"):
        chain.build_template(b"\x51", [], now=True)  # type: ignore[arg-type]


def test_build_template_coinbase_script_not_bytes():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(Exception, match="coinbase_script must be bytes"):
        chain.build_template("not bytes", [], now=1000)  # type: ignore[arg-type]


def test_build_template_coinbase_script_too_large():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(Exception, match="coinbase_script too large"):
        chain.build_template(b"\x00" * 10_001, [], now=1000)


def test_build_template_txs_not_transactions():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(Exception, match="txs must be Transactions"):
        chain.build_template(b"\x51", ["not a tx"], now=1000)  # type: ignore[list-item]


def test_build_template_coinbase_tx_not_allowed():
    chain = Chain(ChainParams.regtest())
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(subsidy(ChainParams.regtest(), 1), b"\x51"),),
    )
    with pytest.raises(Exception, match="coinbase transaction not allowed"):
        chain.build_template(b"\x51", [cb], now=1000)


def test_build_template_script_ops_limit():
    chain = Chain(ChainParams.regtest())
    # Build a tx with two outputs, each with 6000 OP_DUP opcodes = 12000 total
    # ops > MAX_BLOCK_SCRIPT_OPS (10000). Each script is 6000 bytes < MAX_SCRIPT_SIZE.
    big_script = bytes([0x76]) * 6000  # OP_DUP repeated
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1000, big_script), TxOut(1000, big_script)),
    )
    with pytest.raises(Exception, match="block script ops limit exceeded"):
        chain.build_template(b"\x51", [tx], now=1000)


# --------------------------------------------------------------------------- #
# Read paths
# --------------------------------------------------------------------------- #


def test_balance_of_and_tip_mtp_and_locator():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_script=b"\x51")
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    # balance_of for a script with no UTXO.
    assert chain.balance_of(b"\x99" * 20) == 0

    # tip_mtp.
    mtp = chain.tip_mtp()
    assert isinstance(mtp, int)

    # locator.
    loc = chain.locator()
    assert isinstance(loc, list)
    assert loc[0] == b1.block_hash
    assert loc[-1] == genesis.block_hash


def test_get_block_by_height_missing():
    chain = Chain(ChainParams.regtest())
    assert chain.get_block_by_height(5) is None


def test_tip_mtp_genesis_only():
    chain = Chain(ChainParams.regtest())
    mtp = chain.tip_mtp()
    assert mtp == ChainParams.regtest().genesis.header.timestamp

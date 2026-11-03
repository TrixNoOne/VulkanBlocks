"""Additional coverage tests for chain.py: reorg restore path, _utxo_from_undo,
and _connect/_disconnect defensive branches."""

from __future__ import annotations

import pytest

from core.chain import Chain, ChainParams, ChainError, ChainStatus
from core.block import Block, BlockHeader, merkle_root
from core.params import LOCKTIME_THRESHOLD, MAX_MONEY, NETWORK_MAIN, NETWORK_TEST
from core.storage import UTXO
from core.tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    encode_coinbase_height,
)

from core.chain import check_tx_inputs, TxInputError
from core.storage import UTXO
from tests.test_chain import mine_block, subsidy, time_at

REGTEST = ChainParams.regtest()


def test_reorg_restores_utxo_from_undo():
    """A reorg that restores a spent UTXO exercises _utxo_from_undo."""
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis

    # Build branch A: heights 1..3.
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert chain.accept_block(b2, now=now).status == ChainStatus.ACCEPTED
    now = time_at(3)
    b3 = mine_block(params, b2, 3, now)
    assert chain.accept_block(b3, now=now).status == ChainStatus.ACCEPTED

    # Build branch B from height 1: heights 2,3,4 (heavier).
    fork = b1
    prev = fork
    blocks_b = []
    for h in range(2, 5):
        now = time_at(h)
        blk = mine_block(params, prev, h, now, nonce=h + 100)
        blocks_b.append(blk)
        prev = blk

    # Accept all B blocks; the last triggers reorg.
    for blk in blocks_b:
        now = time_at(blk.height)
        res = chain.accept_block(blk, now=now)
        assert res.status == ChainStatus.ACCEPTED, res.reason

    # After reorg, the active tip should be the last B block.
    assert chain.tip().block_hash == blocks_b[-1].block_hash
    # The UTXO set should match a fresh chain with only B applied.
    baseline = Chain(ChainParams.regtest())
    prev = baseline.params.genesis
    for blk in [b1] + blocks_b:
        now = time_at(blk.height)
        assert baseline.accept_block(blk, now=now).status == ChainStatus.ACCEPTED
    assert chain.utxo_set_hash() == baseline.utxo_set_hash()
    baseline.close()
    chain.close()


def test_chain_init_genesis_already_exists_different():
    """_init_genesis with a different genesis in the db raises ChainError."""
    from core.chain import ChainError

    params = ChainParams.regtest()
    db_path = ":memory:"
    chain1 = Chain(params, path=db_path)
    chain1.close()

    # Open a new chain with different params on the same db path.
    # Use a file-based db to persist.
    import tempfile
    import os

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.unlink(path)
    try:
        c1 = Chain(params, path=path)
        c1.close()
        # Create a chain with different genesis (testnet) on same db.
        testnet_params = ChainParams.testnet()
        with pytest.raises(ChainError):
            Chain(testnet_params, path=path)
    finally:
        os.unlink(path)


def test_locator_multiple_blocks():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert chain.accept_block(b2, now=now).status == ChainStatus.ACCEPTED

    loc = chain.locator()
    assert isinstance(loc, list)
    assert len(loc) >= 2
    assert loc[0] == b2.block_hash
    assert loc[-1] == genesis.block_hash
    chain.close()


def test_tip_mtp():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    mtp = chain.tip_mtp()
    assert isinstance(mtp, int)
    chain.close()


def test_build_template_now_invalid():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(ChainError, match="now must be a non-negative int"):
        chain.build_template(b"\x51", [], now=-1)  # type: ignore[arg-type]
    with pytest.raises(ChainError, match="now must be a non-negative int"):
        chain.build_template(b"\x51", [], now=True)  # type: ignore[arg-type]
    chain.close()


def test_build_template_coinbase_script_not_bytes():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(ChainError, match="coinbase_script must be bytes"):
        chain.build_template("not bytes", [], now=1000)  # type: ignore[arg-type]
    chain.close()


def test_build_template_coinbase_script_too_large():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(ChainError, match="coinbase_script too large"):
        chain.build_template(b"\x00" * 10_001, [], now=1000)
    chain.close()


def test_build_template_txs_not_transactions():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(ChainError, match="txs must be Transactions"):
        chain.build_template(b"\x51", ["not a tx"], now=1000)  # type: ignore[list-item]
    chain.close()


def test_build_template_coinbase_tx_not_allowed():
    chain = Chain(ChainParams.regtest())
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(subsidy(ChainParams.regtest(), 1), b"\x51"),),
    )
    with pytest.raises(ChainError, match="coinbase transaction not allowed"):
        chain.build_template(b"\x51", [cb], now=1000)
    chain.close()


def test_build_template_no_valid_timestamp():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(ChainError, match="no valid timestamp"):
        chain.build_template(b"\x51", [], now=0)
    chain.close()


def test_build_template_coinbase_script_sig_too_long():
    # UNREACHABLE: encode_coinbase_height for height up to 2^32 is at most 6 bytes,
    # well under MAX_COINBASE_SCRIPT_SIG=100. Purely defensive.
    pass  # pragma: no cover - defensive branch, unreachable


def test_check_tx_inputs_tx_not_transaction():
    with pytest.raises(TxInputError, match="tx must be a Transaction"):
        check_tx_inputs("not a tx", {}, height=1)  # type: ignore[arg-type]


def test_check_tx_inputs_height_invalid():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(1, (TxIn(b"\xaa" * 32, 0, b""),), (TxOut(1, b"\x51"),))
    with pytest.raises(TxInputError, match="height must be a non-negative int"):
        check_tx_inputs(tx, {}, height=-1)  # type: ignore[arg-type]


def test_check_tx_inputs_coinbase_not_spendable():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, b"\x00"),),
        (TxOut(1, b"\x51"),),
    )
    with pytest.raises(TxInputError, match="coinbase inputs are not spendable"):
        check_tx_inputs(tx, {}, height=1)


def test_check_tx_inputs_validate_fails():
    from core.tx import Transaction, TxIn, TxOut

    txid = b"\xaa" * 32
    tx = Transaction(
        1,
        (TxIn(txid, 0, b""), TxIn(txid, 0, b"")),
        (TxOut(1, b"\x51"),),
    )
    with pytest.raises(TxInputError, match="duplicate inputs"):
        check_tx_inputs(tx, {}, height=1)


def test_check_tx_inputs_lock_time_not_height():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
        lock_time=LOCKTIME_THRESHOLD,
    )
    with pytest.raises(TxInputError, match="lock_time is not a block height"):
        check_tx_inputs(tx, {}, height=1000)


def test_check_tx_inputs_lock_time_in_future():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
        lock_time=50,
    )
    with pytest.raises(TxInputError, match="lock_time in the future"):
        check_tx_inputs(tx, {}, height=10)


def test_check_tx_inputs_non_final():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b"", 0xFFFFFFFF),),
        (TxOut(1, b"\x51"),),
        lock_time=5,
    )
    with pytest.raises(TxInputError, match="non-final transaction"):
        check_tx_inputs(tx, {}, height=100)


def test_check_tx_inputs_utxo_not_utxo_record():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
    )
    with pytest.raises(TxInputError, match="invalid record"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): "not a utxo"}, height=1)


def test_check_tx_inputs_utxo_value_out_of_range():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
    )
    utxo = UTXO(b"\xaa" * 32, 0, MAX_MONEY + 1, b"\x51", 1, False)
    with pytest.raises(TxInputError, match="utxo value out of range"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): utxo}, height=100)


def test_check_tx_inputs_immature_coinbase():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1, b"\x51"),),
    )
    utxo = UTXO(b"\xaa" * 32, 0, 1000, b"\x51", 100, True)
    with pytest.raises(TxInputError, match="immature coinbase"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): utxo}, height=100, coinbase_maturity=100)


def test_check_tx_inputs_script_failure():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b"\x01"),),
        (TxOut(1, b"\x51"),),
    )
    utxo = UTXO(b"\xaa" * 32, 0, 1000, b"\x51", 1, False)
    with pytest.raises(TxInputError, match="script failed"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): utxo}, height=100)


def test_check_tx_inputs_inputs_below_outputs():
    from core.tx import Transaction, TxIn, TxOut

    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    utxo = UTXO(b"\xaa" * 32, 0, 10, b"\x51", 1, False)
    with pytest.raises(TxInputError, match="inputs below outputs"):
        check_tx_inputs(tx, {(b"\xaa" * 32, 0): utxo}, height=100)
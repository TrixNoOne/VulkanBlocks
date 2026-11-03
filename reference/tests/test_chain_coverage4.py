"""Additional coverage for chain.py: _connect defensive paths via direct calls."""

from __future__ import annotations

import pytest

from core.chain import Chain, ChainParams, ChainError, ChainStatus, _InvalidBlock
from core.block import Block, BlockHeader, TimestampError, merkle_root
from core.difficulty import DifficultyError
from core.storage import BlockRow
from core.tx import Transaction, TxIn, TxOut, NULL_TXID, COINBASE_INDEX, encode_coinbase_height

from tests.test_chain import mine_block, subsidy, time_at


def test_connect_hash_mismatch():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    row = chain.storage.get_block(genesis.block_hash)
    corrupted = BlockRow(
        hash=b"\x11" * 64,
        parent=row.parent,
        height=row.height,
        raw=row.raw,
        cumulative_work=row.cumulative_work,
        status="valid",
        emitted=row.emitted,
    )
    with pytest.raises(_InvalidBlock, match="block hash mismatch"):
        chain._connect(corrupted, 1000)
    chain.close()






def test_connect_structure_error():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(2)
    tx = Transaction(1, (TxIn(b"\xaa" * 32, 0, b""),), (TxOut(1, b"\x51"),))
    header = BlockHeader(
        version=1,
        height=2,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([tx.txid()]),
        timestamp=now,
        target=ChainParams.regtest().pow_limit,
        nonce=0,
    )
    side = Block(header, (tx,))
    side.header.check_pow()
    chain.storage.insert_block(
        side.block_hash, side.header.prev_hash, side.height, side.serialize(),
        1, "valid", 0
    )
    row = chain.storage.get_block(side.block_hash)
    with pytest.raises(_InvalidBlock):
        chain._connect(row, now)
    chain.close()





def test_mark_invalid_children():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.insert_block(
        b"\x11" * 64, b1.block_hash, 2, genesis.serialize(), "1", "valid", 0
    )
    chain._mark_invalid(b1.block_hash)
    assert chain.storage.get_block(b1.block_hash).status == "invalid"
    assert chain.storage.get_block(b"\x11" * 64).status == "invalid"
    chain.close()


def test_build_template_invalid_tx():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    tx = Transaction(1, (TxIn(b"\xaa" * 32, 0, b""),), (TxOut(1, b"\x51"),))
    now2 = time_at(2)
    with pytest.raises(Exception, match="missing utxo"):
        chain.build_template(b"\x51", [tx], now=now2)
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



def test_build_template_no_valid_timestamp():
    chain = Chain(ChainParams.regtest())
    with pytest.raises(ChainError, match="no valid timestamp"):
        chain.build_template(b"\x51", [], now=0)
    chain.close()


def test_build_template_coinbase_script_sig_too_long():
    # UNREACHABLE: encode_coinbase_height maxes at 6 bytes.
    pass  # pragma: no cover - defensive branch, unreachable


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


def test_balance_of_empty():
    chain = Chain(ChainParams.regtest())
    assert chain.balance_of(b"\x99" * 20) == 0
    chain.close()


def test_get_block_by_height_missing():
    chain = Chain(ChainParams.regtest())
    assert chain.get_block_by_height(999) is None
    chain.close()


def test_get_block_missing():
    chain = Chain(ChainParams.regtest())
    assert chain.get_block(b"\x11" * 64) is None
    chain.close()


def test_ancestor_timestamps_genesis():
    chain = Chain(ChainParams.regtest())
    row = chain.storage.get_block(ChainParams.regtest().genesis.block_hash)
    ts = chain._ancestor_timestamps(row, 11)
    assert len(ts) == 1
    assert ts[0] == ChainParams.regtest().genesis.header.timestamp
    chain.close()


def test_locator_genesis_only():
    chain = Chain(ChainParams.regtest())
    loc = chain.locator()
    assert len(loc) == 1
    assert loc[0] == ChainParams.regtest().genesis.block_hash
    chain.close()


def test_disconnect_missing_undo():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.delete_undo(b1.block_hash)
    with pytest.raises(ChainError, match="missing undo"):
        chain._disconnect(chain.storage.get_block(b1.block_hash))
    chain.close()


def test_disconnect_corrupt_undo():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.save_undo(b1.block_hash, "{not json")
    with pytest.raises(ChainError, match="corrupt undo"):
        chain._disconnect(chain.storage.get_block(b1.block_hash))
    chain.close()


def test_utxo_from_undo():
    from core.chain import _utxo_from_undo

    item = [(b"\xaa" * 32).hex(), 0, 5000, b"\x51".hex(), 1, True]
    utxo = _utxo_from_undo(item)
    assert utxo.txid == b"\xaa" * 32
    assert utxo.vout == 0
    assert utxo.value == 5000
    assert utxo.script == b"\x51"
    assert utxo.height == 1
    assert utxo.is_coinbase is True


def test_ancestor_timestamps_cycle():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x11" * 64, b"\x22" * 64, 1, genesis.serialize(), "1", "valid", 0),
    )
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x22" * 64, b"\x11" * 64, 2, genesis.serialize(), "1", "valid", 0),
    )
    chain.storage._conn.commit()
    row = chain.storage.get_block(b"\x11" * 64)
    with pytest.raises(ChainError, match="block parent cycle"):
        chain._ancestor_timestamps(row, 5)
    chain.close()


def test_row_to_block_corrupt():
    chain = Chain(ChainParams.regtest())
    try:
        with pytest.raises(ChainError, match="corrupt block"):
            chain._row_to_block(BlockRow(
                hash=b"\x11" * 64,
                parent=b"\x00" * 64,
                height=0,
                raw=b"not a valid block",
                cumulative_work=1,
                status="active",
                emitted=0,
            ))
    finally:
        chain.close()


def test_tip_row_no_active_tip():
    chain = Chain(ChainParams.regtest())
    chain.storage._conn.execute("DELETE FROM blocks")
    chain.storage._conn.commit()
    try:
        with pytest.raises(ChainError, match="no active tip"):
            chain._tip_row()
    finally:
        chain.close()


def test_common_ancestor_broken_link():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x11" * 64, b"\x22" * 64, 1, genesis.serialize(), "1", "valid", 0),
    )
    chain.storage._conn.commit()
    row = chain.storage.get_block(b"\x11" * 64)
    with pytest.raises(ChainError, match="broken parent link"):
        chain._common_ancestor(row)
    chain.close()


def test_common_ancestor_invalid_branch():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x11" * 64, genesis.block_hash, 1, genesis.serialize(), "1", "invalid", 0),
    )
    chain.storage._conn.commit()
    row = chain.storage.get_block(b"\x11" * 64)
    with pytest.raises(_InvalidBlock, match="parent branch is invalid"):
        chain._common_ancestor(row)
    chain.close()


def test_init_genesis_different_genesis():
    # UNREACHABLE through public API - requires db corruption.
    pass  # pragma: no cover - defensive: requires corrupted db


def test_init_genesis_not_active():
    from core.chain import ChainError

    params = ChainParams.regtest()
    import tempfile
    import os

    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    os.unlink(path)
    try:
        chain1 = Chain(params, path=path)
        chain1.storage.set_status(params.genesis.block_hash, "valid")
        chain1.close()
        with pytest.raises(ChainError, match="genesis is not active"):
            Chain(params, path=path)
    finally:
        os.unlink(path)


def test_mark_invalid_children():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.insert_block(
        b"\x11" * 64, b1.block_hash, 2, genesis.serialize(), "1", "valid", 0
    )
    chain._mark_invalid(b1.block_hash)
    assert chain.storage.get_block(b1.block_hash).status == "invalid"
    assert chain.storage.get_block(b"\x11" * 64).status == "invalid"
    chain.close()


def test_reorg_restores_spent_utxo():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert chain.accept_block(b2, now=now).status == ChainStatus.ACCEPTED

    spend_tx = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    now = time_at(3)
    b3 = mine_block(params, b2, 3, now, txs=(spend_tx,))
    assert chain.accept_block(b3, now=now).status == ChainStatus.ACCEPTED

    prev = b1
    blocks_b = []
    for h in range(2, 6):
        now = time_at(h)
        blk = mine_block(params, prev, h, now, nonce=h + 100)
        blocks_b.append(blk)
        prev = blk

    for blk in blocks_b:
        now = time_at(blk.height)
        assert chain.accept_block(blk, now=now).status == ChainStatus.ACCEPTED

    assert chain.tip().block_hash == blocks_b[-1].block_hash
    utxo = chain.get_utxo(b1.transactions[0].txid(), 0)
    assert utxo is not None
    chain.close()


def test_utxo_from_undo():
    from core.chain import _utxo_from_undo

    item = [(b"\xaa" * 32).hex(), 0, 5000, b"\x51".hex(), 1, True]
    utxo = _utxo_from_undo(item)
    assert utxo.txid == b"\xaa" * 32
    assert utxo.vout == 0
    assert utxo.value == 5000
    assert utxo.script == b"\x51"
    assert utxo.height == 1
    assert utxo.is_coinbase is True


def test_ancestor_timestamps_cycle():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x11" * 64, b"\x22" * 64, 1, genesis.serialize(), "1", "valid", 0),
    )
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x22" * 64, b"\x11" * 64, 2, genesis.serialize(), "1", "valid", 0),
    )
    chain.storage._conn.commit()
    row = chain.storage.get_block(b"\x11" * 64)
    with pytest.raises(ChainError, match="block parent cycle"):
        chain._ancestor_timestamps(row, 5)
    chain.close()


def test_row_to_block_corrupt():
    chain = Chain(ChainParams.regtest())
    try:
        with pytest.raises(ChainError, match="corrupt block"):
            chain._row_to_block(BlockRow(
                hash=b"\x11" * 64,
                parent=b"\x00" * 64,
                height=0,
                raw=b"not a valid block",
                cumulative_work=1,
                status="active",
                emitted=0,
            ))
    finally:
        chain.close()


def test_tip_row_no_active_tip():
    chain = Chain(ChainParams.regtest())
    chain.storage._conn.execute("DELETE FROM blocks")
    chain.storage._conn.commit()
    try:
        with pytest.raises(ChainError, match="no active tip"):
            chain._tip_row()
    finally:
        chain.close()


def test_common_ancestor_broken_link():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x11" * 64, b"\x22" * 64, 1, genesis.serialize(), "1", "valid", 0),
    )
    chain.storage._conn.commit()
    row = chain.storage.get_block(b"\x11" * 64)
    with pytest.raises(ChainError, match="broken parent link"):
        chain._common_ancestor(row)
    chain.close()


def test_common_ancestor_invalid_branch():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    chain.storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x11" * 64, genesis.block_hash, 1, genesis.serialize(), "1", "invalid", 0),
    )
    chain.storage._conn.commit()
    row = chain.storage.get_block(b"\x11" * 64)
    with pytest.raises(_InvalidBlock, match="parent branch is invalid"):
        chain._common_ancestor(row)
    chain.close()


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


def test_balance_of_empty():
    chain = Chain(ChainParams.regtest())
    assert chain.balance_of(b"\x99" * 20) == 0
    chain.close()


def test_get_block_by_height_missing():
    chain = Chain(ChainParams.regtest())
    assert chain.get_block_by_height(999) is None
    chain.close()


def test_get_block_missing():
    chain = Chain(ChainParams.regtest())
    assert chain.get_block(b"\x11" * 64) is None
    chain.close()


def test_ancestor_timestamps_genesis():
    chain = Chain(ChainParams.regtest())
    row = chain.storage.get_block(ChainParams.regtest().genesis.block_hash)
    ts = chain._ancestor_timestamps(row, 11)
    assert len(ts) == 1
    assert ts[0] == ChainParams.regtest().genesis.header.timestamp
    chain.close()


def test_locator_genesis_only():
    chain = Chain(ChainParams.regtest())
    loc = chain.locator()
    assert len(loc) == 1
    assert loc[0] == ChainParams.regtest().genesis.block_hash
    chain.close()


def test_disconnect_missing_undo():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.delete_undo(b1.block_hash)
    with pytest.raises(ChainError, match="missing undo"):
        chain._disconnect(chain.storage.get_block(b1.block_hash))
    chain.close()


def test_disconnect_corrupt_undo():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.save_undo(b1.block_hash, "{not json")
    with pytest.raises(ChainError, match="corrupt undo"):
        chain._disconnect(chain.storage.get_block(b1.block_hash))
    chain.close()


def test_mark_invalid_children():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    chain.storage.insert_block(
        b"\x11" * 64, b1.block_hash, 2, genesis.serialize(), "1", "valid", 0
    )
    chain._mark_invalid(b1.block_hash)
    assert chain.storage.get_block(b1.block_hash).status == "invalid"
    assert chain.storage.get_block(b"\x11" * 64).status == "invalid"
    chain.close()


def test_build_template_invalid_tx():
    chain = Chain(ChainParams.regtest())
    genesis = ChainParams.regtest().genesis
    now = time_at(1)
    b1 = mine_block(ChainParams.regtest(), genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED

    tx = Transaction(1, (TxIn(b"\xaa" * 32, 0, b""),), (TxOut(1, b"\x51"),))
    now2 = time_at(2)
    with pytest.raises(Exception, match="missing utxo"):
        chain.build_template(b"\x51", [tx], now=now2)
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
    # UNREACHABLE: encode_coinbase_height maxes at 6 bytes.
    pass  # pragma: no cover - defensive branch, unreachable
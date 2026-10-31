"""Coverage tests for storage.py: validation errors, transaction rollback,
corrupt/missing undo, empty UTXO balance, and edge cases."""

from __future__ import annotations

import json
import sqlite3

import pytest

from core.chain import Chain, ChainParams
from core.storage import (
    ACTIVE,
    INVALID,
    VALID,
    BlockRow,
    Storage,
    StorageError,
    UTXO,
)
from core.tx import NULL_TXID, Transaction, TxIn, TxOut, encode_coinbase_height


def _store_block(storage: Storage, block_hash: bytes, parent: bytes, height: int) -> BlockRow:
    raw = b"\x00" * 10  # dummy raw; not validated by storage layer
    storage.insert_block(
        block_hash, parent, height, raw, 1, ACTIVE, 0
    )
    return storage.get_block(block_hash)


# --------------------------------------------------------------------------- #
# _as_hash / _as_txid validation
# --------------------------------------------------------------------------- #


def test_as_hash_wrong_type():
    from core.storage import _as_hash

    with pytest.raises(StorageError, match="must be bytes"):
        _as_hash("not bytes", "block_hash")  # type: ignore[arg-type]


def test_as_hash_wrong_length():
    from core.storage import _as_hash

    with pytest.raises(StorageError, match="must be 64 bytes"):
        _as_hash(b"\x11" * 63, "block_hash")


def test_as_txid_wrong_type():
    from core.storage import _as_txid

    with pytest.raises(StorageError, match="must be bytes"):
        _as_txid("not bytes", "txid")  # type: ignore[arg-type]


def test_as_txid_wrong_length():
    from core.storage import _as_txid

    with pytest.raises(StorageError, match="must be 32 bytes"):
        _as_txid(b"\x11" * 31, "txid")


# --------------------------------------------------------------------------- #
# _row_to_block unknown status
# --------------------------------------------------------------------------- #


def test_row_to_block_unknown_status(tmp_path):
    storage = Storage(str(tmp_path / "test.sqlite"))
    # Manually insert a block with a bad status.
    storage._conn.execute(
        "INSERT INTO blocks (hash, parent, height, raw, cumulative_work, status, emitted) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (b"\x11" * 64, b"\x22" * 64, 0, b"raw", "1", "bogus", 0),
    )
    storage._conn.commit()
    try:
        with pytest.raises(StorageError, match="unknown block status"):
            storage.get_block(b"\x11" * 64)
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# transaction rollback on exception
# --------------------------------------------------------------------------- #


def test_transaction_rollback_on_exception(tmp_path):
    storage = Storage(str(tmp_path / "rollback.sqlite"))
    try:
        # Insert a block successfully.
        storage.insert_block(
            b"\x11" * 64, b"\x00" * 64, 0, b"raw", "1", ACTIVE, 0
        )
        # Now force an exception inside a transaction; changes must roll back.
        try:
            with storage.transaction():
                storage.insert_block(
                    b"\x22" * 64, b"\x11" * 64, 1, b"raw2", "2", ACTIVE, 0
                )
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        # The second block must not be present.
        assert storage.get_block(b"\x22" * 64) is None
        # The first block must still be present.
        assert storage.get_block(b"\x11" * 64) is not None
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# close / context manager
# --------------------------------------------------------------------------- #


def test_storage_close():
    storage = Storage(":memory:")
    storage.close()
    # Closing twice should not raise.
    storage.close()


def test_storage_context_manager():
    with Storage(":memory:") as storage:
        storage.insert_block(
            b"\x11" * 64, b"\x00" * 64, 0, b"raw", "1", ACTIVE, 0
        )
    # After exit, connection is closed.


# --------------------------------------------------------------------------- #
# insert_block invalid status
# --------------------------------------------------------------------------- #


def test_insert_block_invalid_status(tmp_path):
    storage = Storage(str(tmp_path / "status.sqlite"))
    try:
        with pytest.raises(StorageError, match="invalid block status"):
            storage.insert_block(  # type: ignore[arg-type]
                b"\x11" * 64, b"\x00" * 64, 0, b"raw", "1", "bogus", 0
            )
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# set_status invalid status / unknown block
# --------------------------------------------------------------------------- #


def test_set_status_invalid_status(tmp_path):
    storage = Storage(str(tmp_path / "setstat.sqlite"))
    try:
        storage.insert_block(
            b"\x11" * 64, b"\x00" * 64, 0, b"raw", "1", ACTIVE, 0
        )
        with pytest.raises(StorageError, match="invalid block status"):
            storage.set_status(b"\x11" * 64, "bogus")  # type: ignore[arg-type]
    finally:
        storage.close()


def test_set_status_unknown_block(tmp_path):
    storage = Storage(str(tmp_path / "unknown.sqlite"))
    try:
        with pytest.raises(StorageError, match="unknown block"):
            storage.set_status(b"\x11" * 64, INVALID)
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# update_emitted unknown block
# --------------------------------------------------------------------------- #


def test_update_emitted_unknown_block(tmp_path):
    storage = Storage(str(tmp_path / "emitted.sqlite"))
    try:
        with pytest.raises(StorageError, match="unknown block"):
            storage.update_emitted(b"\x11" * 64, 100)
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# balance_of with no rows (empty)
# --------------------------------------------------------------------------- #


def test_balance_of_empty(tmp_path):
    storage = Storage(str(tmp_path / "balance.sqlite"))
    try:
        assert storage.balance_of(b"\x99" * 20) == 0
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# load_undo corrupt JSON / not dict
# --------------------------------------------------------------------------- #


def test_load_undo_corrupt_json(tmp_path):
    storage = Storage(str(tmp_path / "undo.sqlite"))
    try:
        storage.insert_block(
            b"\x11" * 64, b"\x00" * 64, 0, b"raw", "1", ACTIVE, 0
        )
        # Corrupt the undo data.
        storage._conn.execute(
            "INSERT INTO undo (block_hash, data) VALUES (?, ?)",
            (b"\x11" * 64, "{not valid json"),
        )
        storage._conn.commit()
        try:
            with pytest.raises(StorageError, match="corrupt undo data"):
                storage.load_undo(b"\x11" * 64)
        finally:
            storage.close()
    finally:
        storage.close()


def test_load_undo_not_dict(tmp_path):
    storage = Storage(str(tmp_path / "undonotdict.sqlite"))
    try:
        storage.insert_block(
            b"\x11" * 64, b"\x00" * 64, 0, b"raw", "1", ACTIVE, 0
        )
        storage._conn.execute(
            "INSERT INTO undo (block_hash, data) VALUES (?, ?)",
            (b"\x11" * 64, json.dumps([1, 2, 3])),
        )
        storage._conn.commit()
        try:
            with pytest.raises(StorageError, match="corrupt undo data"):
                storage.load_undo(b"\x11" * 64)
        finally:
            storage.close()
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# UTXO roundtrip and utxo_set_hash empty
# --------------------------------------------------------------------------- #


def test_utxo_put_get_delete_and_hash():
    storage = Storage(":memory:")
    try:
        utxo = UTXO(
            txid=b"\xaa" * 32,
            vout=0,
            value=5000,
            script=b"\x51",
            height=1,
            is_coinbase=False,
        )
        storage.put_utxo(utxo)
        fetched = storage.get_utxo(b"\xaa" * 32, 0)
        assert fetched == utxo
        assert storage.balance_of(b"\x51") == 5000

        h = storage.utxo_set_hash()
        assert isinstance(h, bytes) and len(h) == 32

        storage.delete_utxo(b"\xaa" * 32, 0)
        assert storage.get_utxo(b"\xaa" * 32, 0) is None
        assert storage.balance_of(b"\x51") == 0
    finally:
        storage.close()


# --------------------------------------------------------------------------- #
# insert via chain then check storage statuses
# --------------------------------------------------------------------------- #


def test_storage_statuses_via_chain():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis
    row = chain.storage.get_block(genesis.block_hash)
    assert row.status == ACTIVE
    chain.close()

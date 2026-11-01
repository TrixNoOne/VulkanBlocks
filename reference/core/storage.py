"""Persistenza SQLite della catena Vulcan.

Il database contiene solo blocchi, UTXO e dati di undo. Ogni modifica alla
catena attiva viene eseguita dal chiamante dentro ``Storage.transaction()``:
un connect o un disconnect e' quindi una singola transazione SQL atomica.

Gli hash sono BLOB da 64 byte (SHA-512 doppio dell'header). Il lavoro cumulato
e' un intero a 512 bit e viene conservato come testo decimale, per non perdere
precisione con il limite a 64 bit di SQLite.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .tx import encode_varint

# Stati possibili di un blocco.
ACTIVE = "active"
VALID = "valid"
INVALID = "invalid"

STATUSES = frozenset((ACTIVE, VALID, INVALID))


@dataclass(frozen=True, slots=True)
class UTXO:
    """Output non speso, con il contesto necessario alle regole di spesa."""

    txid: bytes
    vout: int
    value: int
    script: bytes
    height: int
    is_coinbase: bool

    @property
    def outpoint(self) -> tuple[bytes, int]:
        return self.txid, self.vout


@dataclass(frozen=True, slots=True)
class BlockRow:
    """Riga della tabella ``blocks`` con lavoro e emissione cumulati."""

    hash: bytes
    parent: bytes
    height: int
    raw: bytes
    cumulative_work: int
    status: str
    emitted: int


class StorageError(ValueError):
    """Database incoerente o operazione di storage non valida."""


_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS blocks (
        hash BLOB PRIMARY KEY,
        parent BLOB NOT NULL,
        height INTEGER NOT NULL,
        raw BLOB NOT NULL,
        cumulative_work TEXT NOT NULL,
        status TEXT NOT NULL,
        emitted INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(height)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_blocks_active_height
        ON blocks(height) WHERE status = 'active'
    """,
    """
    CREATE TABLE IF NOT EXISTS utxo (
        txid BLOB NOT NULL,
        vout INTEGER NOT NULL,
        value INTEGER NOT NULL,
        script BLOB NOT NULL,
        height INTEGER NOT NULL,
        is_coinbase INTEGER NOT NULL,
        PRIMARY KEY (txid, vout)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS undo (
        block_hash BLOB PRIMARY KEY,
        data TEXT NOT NULL
    )
    """,
)


def _as_hash(value: bytes, name: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise StorageError(f"{name} must be bytes")
    raw = bytes(value)
    if len(raw) != 64:
        raise StorageError(f"{name} must be 64 bytes")
    return raw


def _as_txid(value: bytes, name: str) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise StorageError(f"{name} must be bytes")
    raw = bytes(value)
    if len(raw) != 32:
        raise StorageError(f"{name} must be 32 bytes")
    return raw


def _row_to_block(row: sqlite3.Row) -> BlockRow:
    status = row["status"]
    if status not in STATUSES:
        raise StorageError(f"unknown block status {status!r}")
    return BlockRow(
        hash=bytes(row["hash"]),
        parent=bytes(row["parent"]),
        height=int(row["height"]),
        raw=bytes(row["raw"]),
        cumulative_work=int(row["cumulative_work"]),
        status=status,
        emitted=int(row["emitted"]),
    )


def _row_to_utxo(row: sqlite3.Row) -> UTXO:
    return UTXO(
        txid=bytes(row["txid"]),
        vout=int(row["vout"]),
        value=int(row["value"]),
        script=bytes(row["script"]),
        height=int(row["height"]),
        is_coinbase=bool(row["is_coinbase"]),
    )


class Storage:
    """Accesso sincrono al database; nessun thread o lock interno."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        # Autocommit: le transazioni sono gestite esplicitamente, cosi' un
        # reorg completo puo' essere una sola transazione.
        self._conn = sqlite3.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
        self._create_schema()

    # -- transazioni --------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Transazione atomica; nessuna chiamata annidata."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            yield self._conn
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def _create_schema(self) -> None:
        with self.transaction() as conn:
            for statement in _SCHEMA:
                conn.execute(statement)

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- blocchi ------------------------------------------------------------

    def has_blocks(self) -> bool:
        row = self._conn.execute("SELECT 1 FROM blocks LIMIT 1").fetchone()
        return row is not None

    def insert_block(
        self,
        block_hash: bytes,
        parent: bytes,
        height: int,
        raw: bytes,
        cumulative_work: int,
        status: str,
        emitted: int,
    ) -> None:
        if status not in STATUSES:
            raise StorageError("invalid block status")
        self._conn.execute(
            """
            INSERT INTO blocks
                (hash, parent, height, raw, cumulative_work, status, emitted)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_hash(block_hash, "block_hash"),
                _as_hash(parent, "parent"),
                int(height),
                bytes(raw),
                str(int(cumulative_work)),
                status,
                int(emitted),
            ),
        )

    def get_block(self, block_hash: bytes) -> BlockRow | None:
        row = self._conn.execute(
            "SELECT * FROM blocks WHERE hash = ?", (bytes(block_hash),)
        ).fetchone()
        return None if row is None else _row_to_block(row)

    def get_active_block_by_height(self, height: int) -> BlockRow | None:
        row = self._conn.execute(
            "SELECT * FROM blocks WHERE height = ? AND status = ?",
            (int(height), ACTIVE),
        ).fetchone()
        return None if row is None else _row_to_block(row)

    def active_tip(self) -> BlockRow | None:
        row = self._conn.execute(
            "SELECT * FROM blocks WHERE status = ? ORDER BY height DESC LIMIT 1",
            (ACTIVE,),
        ).fetchone()
        return None if row is None else _row_to_block(row)

    def active_rows_desc(self) -> list[BlockRow]:
        rows = self._conn.execute(
            "SELECT * FROM blocks WHERE status = ? ORDER BY height DESC",
            (ACTIVE,),
        ).fetchall()
        return [_row_to_block(row) for row in rows]

    def active_rows_asc(self) -> list[BlockRow]:
        rows = self._conn.execute(
            "SELECT * FROM blocks WHERE status = ? ORDER BY height ASC",
            (ACTIVE,),
        ).fetchall()
        return [_row_to_block(row) for row in rows]

    def set_status(self, block_hash: bytes, status: str) -> None:
        if status not in STATUSES:
            raise StorageError("invalid block status")
        cursor = self._conn.execute(
            "UPDATE blocks SET status = ? WHERE hash = ?",
            (status, bytes(block_hash)),
        )
        if cursor.rowcount != 1:
            raise StorageError("unknown block")

    def update_emitted(self, block_hash: bytes, emitted: int) -> None:
        cursor = self._conn.execute(
            "UPDATE blocks SET emitted = ? WHERE hash = ?",
            (int(emitted), bytes(block_hash)),
        )
        if cursor.rowcount != 1:
            raise StorageError("unknown block")

    def children(self, block_hash: bytes) -> list[BlockRow]:
        rows = self._conn.execute(
            "SELECT * FROM blocks WHERE parent = ? ORDER BY height",
            (bytes(block_hash),),
        ).fetchall()
        return [_row_to_block(row) for row in rows]

    # -- UTXO ---------------------------------------------------------------

    def put_utxo(self, utxo: UTXO) -> None:
        txid = _as_txid(utxo.txid, "txid")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO utxo
                (txid, vout, value, script, height, is_coinbase)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                txid,
                int(utxo.vout),
                int(utxo.value),
                bytes(utxo.script),
                int(utxo.height),
                1 if utxo.is_coinbase else 0,
            ),
        )

    def delete_utxo(self, txid: bytes, vout: int) -> None:
        self._conn.execute(
            "DELETE FROM utxo WHERE txid = ? AND vout = ?",
            (_as_txid(txid, "txid"), int(vout)),
        )

    def get_utxo(self, txid: bytes, vout: int) -> UTXO | None:
        row = self._conn.execute(
            "SELECT * FROM utxo WHERE txid = ? AND vout = ?",
            (_as_txid(txid, "txid"), int(vout)),
        ).fetchone()
        return None if row is None else _row_to_utxo(row)

    def iter_utxos(self) -> Iterator[UTXO]:
        cursor = self._conn.execute(
            "SELECT * FROM utxo ORDER BY txid ASC, vout ASC"
        )
        for row in cursor:
            yield _row_to_utxo(row)

    def balance_of(self, script: bytes) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(SUM(value), 0) AS total FROM utxo WHERE script = ?",
            (bytes(script),),
        ).fetchone()
        return int(row["total"])

    def utxo_set_hash(self) -> bytes:
        """Hash deterministico dell'intero UTXO set, ordinato per outpoint."""
        digest = hashlib.sha256()
        digest.update(b"VulcanUTXO\x00")
        count = 0
        for utxo in self.iter_utxos():
            digest.update(utxo.txid)
            digest.update(struct.pack("<I", utxo.vout))
            digest.update(struct.pack("<Q", utxo.value))
            digest.update(encode_varint(len(utxo.script)))
            digest.update(utxo.script)
            digest.update(struct.pack("<I", utxo.height))
            digest.update(b"\x01" if utxo.is_coinbase else b"\x00")
            count += 1
        digest.update(struct.pack("<Q", count))
        return digest.digest()

    # -- undo ---------------------------------------------------------------

    def save_undo(self, block_hash: bytes, data: dict) -> None:
        payload = json.dumps(data, separators=(",", ":"), sort_keys=True)
        self._conn.execute(
            "INSERT OR REPLACE INTO undo (block_hash, data) VALUES (?, ?)",
            (_as_hash(block_hash, "block_hash"), payload),
        )

    def load_undo(self, block_hash: bytes) -> dict | None:
        row = self._conn.execute(
            "SELECT data FROM undo WHERE block_hash = ?", (bytes(block_hash),)
        ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["data"])
        except json.JSONDecodeError as exc:  # pragma: no cover - corruzione
            raise StorageError("corrupt undo data") from exc
        if not isinstance(data, dict):
            raise StorageError("corrupt undo data")
        return data

    def delete_undo(self, block_hash: bytes) -> None:
        self._conn.execute(
            "DELETE FROM undo WHERE block_hash = ?", (bytes(block_hash),)
        )

"""Blocchi Vulcan: header, proof of work double SHA-512, merkle root, tempo.

Layout header (184 byte, numeri little-endian tranne il target big-endian):
    version:u32 | height:u32 | prev_hash:64 | merkle_root:32 |
    timestamp:u64 | target:64 | nonce:u64

Il target e' un intero a 512 bit: il blocco e' valido se
    int(sha512(sha512(header)), "big") <= target
Il lavoro del blocco e' 2^512 // (target + 1), come in Bitcoin, cosi' la
fork choice puo' sommare lavoro invece di contare blocchi.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Sequence

from .params import (
    BLOCK_SUBSIDY,
    MAX_BLOCK_SIZE,
    MAX_FUTURE_DRIFT,
    MAX_TARGET,
    MIN_TARGET,
    MTP_WINDOW,
)
from .tx import (
    ByteReader,
    SerializationError,
    Transaction,
    decode_coinbase_height,
    encode_varint,
    double_sha256,
)

HEADER_SIZE = 4 + 4 + 64 + 32 + 8 + 64 + 8  # 184

UINT32_MAX = 0xFFFFFFFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF


class BlockValidationError(ValueError):
    """Blocco o header non valido."""


class ProofOfWorkError(BlockValidationError):
    """Hash sopra il target."""


class TimestampError(BlockValidationError):
    """Timestamp fuori dalle regole di consenso."""


def double_sha512(data: bytes) -> bytes:
    return hashlib.sha512(hashlib.sha512(data).digest()).digest()


def _check_uint(value: int, field_name: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise BlockValidationError(f"{field_name} must be an int")
    if value < 0 or value > maximum:
        raise BlockValidationError(f"{field_name} out of range")
    return value


def _check_bytes(value: bytes, field_name: str, size: int) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise BlockValidationError(f"{field_name} must be bytes")
    raw = bytes(value)
    if len(raw) != size:
        raise BlockValidationError(f"{field_name} must be {size} bytes")
    return raw


@dataclass(frozen=True, slots=True)
class BlockHeader:
    version: int
    height: int
    prev_hash: bytes
    merkle_root: bytes
    timestamp: int
    target: int
    nonce: int
    _hash: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _check_uint(self.version, "version", UINT32_MAX))
        object.__setattr__(self, "height", _check_uint(self.height, "height", UINT32_MAX))
        object.__setattr__(self, "prev_hash", _check_bytes(self.prev_hash, "prev_hash", 64))
        object.__setattr__(
            self, "merkle_root", _check_bytes(self.merkle_root, "merkle_root", 32)
        )
        object.__setattr__(
            self, "timestamp", _check_uint(self.timestamp, "timestamp", UINT64_MAX)
        )
        object.__setattr__(self, "target", _check_uint(self.target, "target", MAX_TARGET))
        if self.target < MIN_TARGET:
            raise BlockValidationError("target below MIN_TARGET")
        object.__setattr__(self, "nonce", _check_uint(self.nonce, "nonce", UINT64_MAX))
        object.__setattr__(self, "_hash", double_sha512(self.serialize()))

    def serialize(self) -> bytes:
        return b"".join(
            (
                struct.pack("<II", self.version, self.height),
                self.prev_hash,
                self.merkle_root,
                struct.pack("<Q", self.timestamp),
                self.target.to_bytes(64, "big"),
                struct.pack("<Q", self.nonce),
            )
        )

    @property
    def block_hash(self) -> bytes:
        """Digest double SHA-512 dell'header (64 byte)."""
        return self._hash

    @property
    def pow_value(self) -> int:
        """Hash interpretato come intero big-endian da confrontare col target."""
        return int.from_bytes(self._hash, "big")

    @property
    def meets_target(self) -> bool:
        return self.pow_value <= self.target

    def check_pow(self) -> None:
        if self.meets_target:
            return
        raise ProofOfWorkError(
            f"hash {self.pow_value:0128x} above target {self.target:0128x}"
        )

    @property
    def work(self) -> int:
        """Lavoro cumulabile: 2^512 // (target + 1)."""
        return (1 << 512) // (self.target + 1)

    @classmethod
    def from_reader(cls, reader: ByteReader) -> "BlockHeader":
        raw = reader.read(HEADER_SIZE)
        version, height = struct.unpack_from("<II", raw, 0)
        return cls(
            version=version,
            height=height,
            prev_hash=raw[8:72],
            merkle_root=raw[72:104],
            timestamp=struct.unpack_from("<Q", raw, 104)[0],
            target=int.from_bytes(raw[112:176], "big"),
            nonce=struct.unpack_from("<Q", raw, 176)[0],
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "BlockHeader":
        if len(data) != HEADER_SIZE:
            raise SerializationError(f"header must be {HEADER_SIZE} bytes")
        reader = ByteReader(data)
        header = cls.from_reader(reader)
        reader.expect_end()
        return header


def merkle_root(txids: Sequence[bytes]) -> bytes:
    """Merkle root stile Bitcoin: duplica l'ultimo nodo se il livello e' dispari."""
    if not txids:
        return b"\x00" * 32
    layer = [bytes(txid) for txid in txids]
    for txid in layer:
        if len(txid) != 32:
            raise BlockValidationError("txid must be 32 bytes")
    while len(layer) > 1:
        if len(layer) % 2:
            layer.append(layer[-1])
        layer = [
            double_sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)
        ]
    return layer[0]


def median_time_past(
    timestamps: Sequence[int], window: int = MTP_WINDOW
) -> int:
    """Mediana dei timestamp degli ultimi `window` blocchi disponibili."""
    if window < 1:
        raise ValueError("window must be positive")
    if not timestamps:
        raise ValueError("needs at least one timestamp")
    recent = sorted(timestamps[-window:])
    return recent[len(recent) // 2]


def validate_timestamp(
    timestamp: int, past_timestamps: Sequence[int], now: int
) -> None:
    """Regola: timestamp > MTP(ultimi 11) e non oltre 2 ore nel futuro."""
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        raise TimestampError("timestamp must be an int")
    mtp = median_time_past(past_timestamps)
    if timestamp <= mtp:
        raise TimestampError(f"timestamp {timestamp} not above MTP {mtp}")
    if timestamp > now + MAX_FUTURE_DRIFT:
        raise TimestampError("timestamp too far in the future")


@dataclass(frozen=True, slots=True)
class Block:
    header: BlockHeader
    transactions: tuple[Transaction, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.header, BlockHeader):
            raise BlockValidationError("header must be a BlockHeader")
        object.__setattr__(self, "transactions", tuple(self.transactions))
        for tx in self.transactions:
            if not isinstance(tx, Transaction):
                raise BlockValidationError("transactions must be Transaction")

    @property
    def height(self) -> int:
        return self.header.height

    @property
    def block_hash(self) -> bytes:
        return self.header.block_hash

    def txids(self) -> list[bytes]:
        return [tx.txid() for tx in self.transactions]

    def compute_merkle_root(self) -> bytes:
        return merkle_root(self.txids())

    def validate_structure(self) -> None:
        """Regole locali del blocco; UTXO, firme e difficolta' vivono in chain."""
        if not self.transactions:
            raise BlockValidationError("block has no transactions")
        if not self.transactions[0].is_coinbase:
            raise BlockValidationError("first transaction must be coinbase")
        if any(tx.is_coinbase for tx in self.transactions[1:]):
            raise BlockValidationError("block has more than one coinbase")

        for tx in self.transactions:
            tx.validate()

        # L'altezza dichiarata nella coinbase deve coincidere con l'header.
        coinbase_height = decode_coinbase_height(
            self.transactions[0].inputs[0].script_sig
        )
        if coinbase_height != self.header.height:
            raise BlockValidationError(
                f"coinbase height {coinbase_height} != block height {self.header.height}"
            )

        txids = self.txids()
        if len(set(txids)) != len(txids):
            raise BlockValidationError("duplicate transaction id")

        if self.compute_merkle_root() != self.header.merkle_root:
            raise BlockValidationError("merkle root mismatch")

    def serialize(self) -> bytes:
        parts = [self.header.serialize(), encode_varint(len(self.transactions))]
        parts.extend(tx.serialize() for tx in self.transactions)
        return b"".join(parts)

    @classmethod
    def from_reader(cls, reader: ByteReader) -> "Block":
        header = BlockHeader.from_reader(reader)
        txs = tuple(
            Transaction.from_reader(reader) for _ in range(reader.read_varint())
        )
        return cls(header=header, transactions=txs)

    @classmethod
    def from_bytes(cls, data: bytes) -> "Block":
        # Controllo di dimensione prima di qualsiasi parsing.
        if len(data) > MAX_BLOCK_SIZE:
            raise SerializationError(
                f"block exceeds MAX_BLOCK_SIZE ({len(data)} > {MAX_BLOCK_SIZE})"
            )
        reader = ByteReader(data)
        block = cls.from_reader(reader)
        reader.expect_end()
        return block

"""Transazioni Vulcan: modello UTXO, importi interi, serializzazione canonica.

Formato wire (numeri little-endian):
    version:u32 | n_in:varint | input* | n_out:varint | output* | lock_time:u32

    input  = prev_txid:32 | prev_index:u32 | len(script_sig):varint | script_sig | sequence:u32
    output = value:u64    | len(script_pubkey):varint | script_pubkey

Gli importi sono sempre interi in unita' da 10^-8 Vulcan: nessun float.
I limiti di emissione (sussidio, maturita' coinbase) sono regole di catena.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Sequence

from .params import (
    COINBASE_MATURITY,
    MAX_COINBASE_SCRIPT_SIG,
    MAX_MONEY,
    MAX_SCRIPT_SIZE,
    MIN_COINBASE_SCRIPT_SIG,
    UNITS_PER_VULCAN,
)

# Outpoint nullo: marca l'input coinbase.
NULL_TXID = b"\x00" * 32
COINBASE_INDEX = 0xFFFFFFFF

UINT32_MAX = 0xFFFFFFFF
UINT64_MAX = 0xFFFFFFFFFFFFFFFF


class SerializationError(ValueError):
    """Byte non decodificabili o non canonici."""


class TxValidationError(ValueError):
    """Transazione non valida a livello strutturale."""


def double_sha256(data: bytes) -> bytes:
    """SHA-256 applicato due volte (txid e merkle)."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def encode_varint(value: int) -> bytes:
    """CompactSize canonico: rifiuta valori negativi o fuori da uint64."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise SerializationError("varint must be an int")
    if value < 0 or value > UINT64_MAX:
        raise SerializationError("varint out of range")
    if value < 0xFD:
        return bytes((value,))
    if value <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", value)
    if value <= UINT32_MAX:
        return b"\xfe" + struct.pack("<I", value)
    return b"\xff" + struct.pack("<Q", value)


class ByteReader:
    """Lettore sequenziale con controllo di troncamento e varint canonici."""

    __slots__ = ("_data", "_offset")

    def __init__(self, data: bytes, offset: int = 0) -> None:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data must be bytes-like")
        if offset < 0 or offset > len(data):
            raise SerializationError("invalid offset")
        self._data = bytes(data)
        self._offset = offset

    @property
    def offset(self) -> int:
        return self._offset

    @property
    def remaining(self) -> int:
        return len(self._data) - self._offset

    def read(self, size: int) -> bytes:
        if size < 0:
            raise SerializationError("negative read size")
        end = self._offset + size
        if end > len(self._data):
            raise SerializationError("unexpected end of data")
        chunk = self._data[self._offset:end]
        self._offset = end
        return chunk

    def read_uint32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def read_uint64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def read_varint(self) -> int:
        first = self.read(1)[0]
        if first < 0xFD:
            return first
        if first == 0xFD:
            value = struct.unpack("<H", self.read(2))[0]
            if value < 0xFD:
                raise SerializationError("non-canonical varint")
            return value
        if first == 0xFE:
            value = struct.unpack("<I", self.read(4))[0]
            if value <= 0xFFFF:
                raise SerializationError("non-canonical varint")
            return value
        value = struct.unpack("<Q", self.read(8))[0]
        if value <= UINT32_MAX:
            raise SerializationError("non-canonical varint")
        return value

    def read_bytes(self) -> bytes:
        return self.read(self.read_varint())

    def expect_end(self) -> None:
        if self.remaining:
            raise SerializationError("trailing data")


def _as_bytes(value: bytes, field: str, max_size: int | None = None) -> bytes:
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise TxValidationError(f"{field} must be bytes")
    raw = bytes(value)
    if max_size is not None and len(raw) > max_size:
        raise TxValidationError(f"{field} too large")
    return raw


def _as_uint(value: int, field: str, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TxValidationError(f"{field} must be an int")
    if value < 0 or value > maximum:
        raise TxValidationError(f"{field} out of range")
    return value


def encode_coinbase_height(height: int) -> bytes:
    """Prefisso della coinbase (stile BIP34): push dell'altezza minimale.

    L'altezza e' un CScriptNum little-endian; 0 e' OP_0. Il risultato e'
    portato ad almeno MIN_COINBASE_SCRIPT_SIG byte con padding.
    """
    if not isinstance(height, int) or isinstance(height, bool):
        raise TxValidationError("height must be an int")
    if height < 0 or height > UINT32_MAX:
        raise TxValidationError("height out of range")

    if height == 0:
        encoded = b"\x00"
    else:
        size = (height.bit_length() + 7) // 8
        raw = height.to_bytes(size, "little")
        if raw[-1] & 0x80:  # bit di segno: aggiungi 0x00
            raw += b"\x00"
        encoded = bytes((len(raw),)) + raw

    if len(encoded) < MIN_COINBASE_SCRIPT_SIG:
        encoded += b"\x00" * (MIN_COINBASE_SCRIPT_SIG - len(encoded))
    return encoded


def decode_coinbase_height(script_sig: bytes) -> int:
    """Estrae l'altezza dal primo push della coinbase; non guarda il resto."""
    raw = _as_bytes(script_sig, "coinbase script_sig")
    if len(raw) < MIN_COINBASE_SCRIPT_SIG:
        raise TxValidationError("coinbase script_sig too short")
    if len(raw) > MAX_COINBASE_SCRIPT_SIG:
        raise TxValidationError("coinbase script_sig too long")

    first = raw[0]
    if first == 0:  # OP_0 => altezza 0
        return 0
    if not 1 <= first <= 5:
        raise TxValidationError("coinbase height missing")

    encoded = raw[1 : 1 + first]
    if len(encoded) != first:
        raise TxValidationError("truncated coinbase height")
    if encoded[-1] & 0x80:
        raise TxValidationError("negative coinbase height")
    if encoded == b"\x00":
        raise TxValidationError("non-minimal coinbase height")
    if len(encoded) > 1 and encoded[-1] == 0 and not (encoded[-2] & 0x80):
        raise TxValidationError("non-minimal coinbase height")

    height = int.from_bytes(encoded, "little")
    if height > UINT32_MAX:
        raise TxValidationError("coinbase height out of range")
    return height


@dataclass(frozen=True, slots=True)
class TxIn:
    """Riferimento a un output non speso piu' lo script di sblocco."""

    prev_txid: bytes
    prev_index: int
    script_sig: bytes = b""
    sequence: int = UINT32_MAX

    def __post_init__(self) -> None:
        txid = _as_bytes(self.prev_txid, "prev_txid")
        if len(txid) != 32:
            raise TxValidationError("prev_txid must be 32 bytes")
        object.__setattr__(self, "prev_txid", txid)
        object.__setattr__(
            self, "prev_index", _as_uint(self.prev_index, "prev_index", UINT32_MAX)
        )
        object.__setattr__(
            self,
            "script_sig",
            _as_bytes(self.script_sig, "script_sig", MAX_SCRIPT_SIZE),
        )
        object.__setattr__(
            self, "sequence", _as_uint(self.sequence, "sequence", UINT32_MAX)
        )

    @property
    def is_null(self) -> bool:
        """True se l'input punta all'outpoint nullo (solo coinbase)."""
        return self.prev_txid == NULL_TXID and self.prev_index == COINBASE_INDEX

    def serialize(self) -> bytes:
        return b"".join(
            (
                self.prev_txid,
                struct.pack("<I", self.prev_index),
                encode_varint(len(self.script_sig)),
                self.script_sig,
                struct.pack("<I", self.sequence),
            )
        )

    @classmethod
    def from_reader(cls, reader: ByteReader) -> "TxIn":
        return cls(
            prev_txid=reader.read(32),
            prev_index=reader.read_uint32(),
            script_sig=reader.read_bytes(),
            sequence=reader.read_uint32(),
        )


@dataclass(frozen=True, slots=True)
class TxOut:
    """Output: importo intero e script che definisce la condizione di spesa."""

    value: int
    script_pubkey: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _as_uint(self.value, "value", MAX_MONEY))
        object.__setattr__(
            self,
            "script_pubkey",
            _as_bytes(self.script_pubkey, "script_pubkey", MAX_SCRIPT_SIZE),
        )

    def serialize(self) -> bytes:
        return (
            struct.pack("<Q", self.value)
            + encode_varint(len(self.script_pubkey))
            + self.script_pubkey
        )

    @classmethod
    def from_reader(cls, reader: ByteReader) -> "TxOut":
        return cls(value=reader.read_uint64(), script_pubkey=reader.read_bytes())


@dataclass(frozen=True, slots=True)
class Transaction:
    """Transazione immutabile; l'ordine degli input/output e' consensus-relevant."""

    version: int
    inputs: tuple[TxIn, ...]
    outputs: tuple[TxOut, ...]
    lock_time: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _as_uint(self.version, "version", UINT32_MAX))
        object.__setattr__(self, "lock_time", _as_uint(self.lock_time, "lock_time", UINT32_MAX))
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "outputs", tuple(self.outputs))
        for txin in self.inputs:
            if not isinstance(txin, TxIn):
                raise TxValidationError("inputs must be TxIn")
        for txout in self.outputs:
            if not isinstance(txout, TxOut):
                raise TxValidationError("outputs must be TxOut")

    @property
    def is_coinbase(self) -> bool:
        return len(self.inputs) == 1 and self.inputs[0].is_null

    def txid(self) -> bytes:
        """Identificatore: double SHA-256 della forma serializzata."""
        return double_sha256(self.serialize())

    def serialize(self) -> bytes:
        parts = [struct.pack("<I", self.version), encode_varint(len(self.inputs))]
        parts.extend(txin.serialize() for txin in self.inputs)
        parts.append(encode_varint(len(self.outputs)))
        parts.extend(txout.serialize() for txout in self.outputs)
        parts.append(struct.pack("<I", self.lock_time))
        return b"".join(parts)

    @classmethod
    def from_reader(cls, reader: ByteReader) -> "Transaction":
        version = reader.read_uint32()
        inputs = tuple(TxIn.from_reader(reader) for _ in range(reader.read_varint()))
        outputs = tuple(TxOut.from_reader(reader) for _ in range(reader.read_varint()))
        lock_time = reader.read_uint32()
        return cls(version=version, inputs=inputs, outputs=outputs, lock_time=lock_time)

    @classmethod
    def from_bytes(cls, data: bytes) -> "Transaction":
        reader = ByteReader(data)
        tx = cls.from_reader(reader)
        reader.expect_end()
        return tx

    def validate(self) -> None:
        """Controlli strutturali; i controlli UTXO/firma vivono in chain/script."""
        if not self.inputs:
            raise TxValidationError("transaction has no inputs")
        if not self.outputs:
            raise TxValidationError("transaction has no outputs")

        if self.is_coinbase:
            if len(self.inputs) != 1:  # difensivo: is_coinbase lo implica gia'
                raise TxValidationError("coinbase must have exactly one input")
            # Formato dell'altezza; l'uguaglianza con l'altezza del blocco
            # e' un controllo contestuale (Block.validate_structure/chain).
            decode_coinbase_height(self.inputs[0].script_sig)
        else:
            for txin in self.inputs:
                if txin.prev_txid == NULL_TXID:
                    raise TxValidationError("null prevout only allowed in coinbase")

        outpoints = [(txin.prev_txid, txin.prev_index) for txin in self.inputs]
        if not self.is_coinbase and len(set(outpoints)) != len(outpoints):
            raise TxValidationError("duplicate inputs")

        total = 0
        for txout in self.outputs:
            total += txout.value
            if total > MAX_MONEY:
                raise TxValidationError("outputs exceed MAX_MONEY")

    def fee(self, input_values: Sequence[int]) -> int:
        """Fee = somma input - somma output; richiede i valori UTXO risolti."""
        if len(input_values) != len(self.inputs):
            raise TxValidationError("input_values length mismatch")
        total_in = 0
        for value in input_values:
            total_in += _as_uint(value, "input value", MAX_MONEY)
        total_out = sum(txout.value for txout in self.outputs)
        if total_in < total_out:
            raise TxValidationError("inputs below outputs")
        return total_in - total_out

import hashlib

import pytest

from core.block import (
    BLOCK_SUBSIDY,
    HEADER_SIZE,
    MAX_FUTURE_DRIFT,
    MAX_TARGET,
    MTP_WINDOW,
    Block,
    BlockHeader,
    BlockValidationError,
    ProofOfWorkError,
    TimestampError,
    double_sha512,
    median_time_past,
    merkle_root,
    validate_timestamp,
)
from core.params import MAX_BLOCK_SIZE
from core.tx import COINBASE_INDEX, NULL_TXID, Transaction, TxIn, TxOut, encode_coinbase_height


def coinbase(value: int = BLOCK_SUBSIDY, height: int = 1) -> Transaction:
    return Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(height)),),
        (TxOut(value, b"\x51"),),
    )


def regular(value_in: int = 50_000, value_out: int = 49_000) -> Transaction:
    return Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0, b"\x00"),),
        (TxOut(value_out, b"\x51"),),
    )


def make_header(
    *,
    height: int = 1,
    prev_hash: bytes = b"\x11" * 64,
    merkle: bytes = b"\x22" * 32,
    timestamp: int = 1_000,
    target: int = MAX_TARGET,
    nonce: int = 0,
    version: int = 1,
) -> BlockHeader:
    return BlockHeader(
        version=version,
        height=height,
        prev_hash=prev_hash,
        merkle_root=merkle,
        timestamp=timestamp,
        target=target,
        nonce=nonce,
    )


def make_block(
    txs: tuple[Transaction, ...] | None = None,
    *,
    height: int = 1,
    timestamp: int = 1_000,
    target: int = MAX_TARGET,
    nonce: int = 0,
    merkle: bytes | None = None,
) -> Block:
    transactions = txs if txs is not None else (coinbase(height=height),)
    if merkle is None:
        merkle = merkle_root([tx.txid() for tx in transactions])
    header = make_header(
        height=height,
        merkle=merkle,
        timestamp=timestamp,
        target=target,
        nonce=nonce,
    )
    return Block(header, transactions)


def test_header_layout_and_roundtrip():
    header = make_header()
    raw = header.serialize()
    assert HEADER_SIZE == 184
    assert len(raw) == HEADER_SIZE
    assert BlockHeader.from_bytes(raw) == header
    assert header.block_hash == double_sha512(raw)


def test_header_endianness():
    header = make_header(height=0x01020304, nonce=0x0A0B0C0D, target=0x0102)
    raw = header.serialize()
    assert raw[:4] == b"\x01\x00\x00\x00"
    assert raw[4:8] == b"\x04\x03\x02\x01"
    assert raw[176:184] == b"\x0d\x0c\x0b\x0a\x00\x00\x00\x00"
    # target: 64 byte big-endian, quindi in coda alla sua finestra
    assert raw[112:176] == (0x0102).to_bytes(64, "big")
    assert raw[174:176] == b"\x01\x02"


def test_header_hash_is_double_sha512():
    header = make_header()
    expected = hashlib.sha512(hashlib.sha512(header.serialize()).digest()).digest()
    assert header.block_hash == expected
    assert header.pow_value == int.from_bytes(expected, "big")


def test_header_pow_bounds():
    with pytest.raises(BlockValidationError):
        make_header(target=0)
    with pytest.raises(BlockValidationError):
        make_header(target=MAX_TARGET + 1)
    with pytest.raises(BlockValidationError):
        make_header(prev_hash=b"\x00" * 63)
    with pytest.raises(BlockValidationError):
        make_header(merkle=b"\x00" * 31)


def test_pow_trivial_target_passes():
    header = make_header(target=MAX_TARGET)
    header.check_pow()
    assert header.meets_target


def test_pow_rejects_bad_nonce():
    header = make_header(target=1, nonce=0)
    assert header.pow_value > 1
    with pytest.raises(ProofOfWorkError):
        header.check_pow()


def test_pow_nonce_search():
    target = 1 << 500  # circa 1 hash su 4096
    header = None
    for nonce in range(1_000_000):
        candidate = make_header(target=target, nonce=nonce)
        if candidate.meets_target:
            header = candidate
            break
    assert header is not None
    header.check_pow()
    assert header.work == (1 << 512) // (target + 1)


def test_work_formula():
    assert make_header(target=MAX_TARGET).work == 1
    assert make_header(target=(1 << 510)).work == 3
    for target in (1, 12345, 1 << 500, 1 << 511):
        assert make_header(target=target).work == (1 << 512) // (target + 1)


def test_merkle_root_single_and_empty():
    txid = b"\x33" * 32
    assert merkle_root([txid]) == txid
    assert merkle_root([]) == b"\x00" * 32


def test_merkle_root_odd_duplicates_last():
    a, b, c = b"\x01" * 32, b"\x02" * 32, b"\x03" * 32
    left = double_sha256_pairs(a, b)
    right = double_sha256_pairs(c, c)
    assert merkle_root([a, b, c]) == double_sha256_pairs(left, right)


def double_sha256_pairs(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(left + right).digest()).digest()


def test_merkle_root_rejects_bad_txid():
    with pytest.raises(BlockValidationError):
        merkle_root([b"\x00" * 31])


def test_median_time_past():
    timestamps = list(range(100, 113))  # 13 elementi
    assert median_time_past(timestamps) == median_time_past(timestamps[-MTP_WINDOW:])
    eleven = sorted(timestamps[-MTP_WINDOW:])
    assert median_time_past(timestamps) == eleven[len(eleven) // 2]
    assert median_time_past([5, 1, 9, 3]) == 5  # con numero pari vince il centrale alto
    assert median_time_past([7]) == 7
    with pytest.raises(ValueError):
        median_time_past([])
    with pytest.raises(ValueError):
        median_time_past([1], window=0)


def test_timestamp_rules():
    past = list(range(1_000, 1_011))  # mediana 1005
    now = 10_000
    assert median_time_past(past) == 1_005

    validate_timestamp(1_006, past, now)
    validate_timestamp(now + MAX_FUTURE_DRIFT, past, now)

    with pytest.raises(TimestampError):
        validate_timestamp(1_005, past, now)
    with pytest.raises(TimestampError):
        validate_timestamp(now + MAX_FUTURE_DRIFT + 1, past, now)


def test_valid_block_structure():
    block = make_block()
    block.validate_structure()
    assert block.height == 1
    assert block.block_hash == block.header.block_hash
    assert block.compute_merkle_root() == block.header.merkle_root


def test_block_requires_known_transactions():
    with pytest.raises(BlockValidationError):
        Block(make_header(), (object(),))  # type: ignore[arg-type]


def test_block_first_tx_must_be_coinbase():
    block = make_block((regular(),))
    with pytest.raises(BlockValidationError, match="coinbase"):
        block.validate_structure()


def test_block_rejects_second_coinbase():
    block = make_block((coinbase(), coinbase()))
    with pytest.raises(BlockValidationError, match="more than one coinbase"):
        block.validate_structure()


def test_block_rejects_duplicate_txids():
    block = make_block((coinbase(), regular(), regular()))
    with pytest.raises(BlockValidationError, match="duplicate"):
        block.validate_structure()


def test_block_rejects_merkle_mismatch():
    block = make_block(merkle=b"\x00" * 32)
    with pytest.raises(BlockValidationError, match="merkle"):
        block.validate_structure()


def test_block_empty_tx_list_rejected():
    block = Block(make_header(merkle=b"\x00" * 32), ())
    with pytest.raises(BlockValidationError, match="no transactions"):
        block.validate_structure()


def test_block_serialization_roundtrip():
    block = make_block((coinbase(), regular()))
    raw = block.serialize()
    decoded = Block.from_bytes(raw)
    assert decoded == block
    assert decoded.block_hash == block.block_hash
    from core.tx import SerializationError

    with pytest.raises(SerializationError):
        Block.from_bytes(raw + b"\x00")


def test_block_rejects_coinbase_height_mismatch():
    block = make_block((coinbase(height=1),), height=2)
    with pytest.raises(BlockValidationError, match="coinbase height"):
        block.validate_structure()


def test_block_rejects_coinbase_without_height():
    from core.tx import TxValidationError

    bad_coinbase = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, b"\x05\x01"),),
        (TxOut(1, b"\x51"),),
    )
    block = make_block((bad_coinbase,))
    with pytest.raises(TxValidationError):
        block.validate_structure()


def test_block_from_bytes_rejects_oversized_data_before_parsing():
    from core.tx import SerializationError

    with pytest.raises(SerializationError, match="MAX_BLOCK_SIZE"):
        Block.from_bytes(b"\x00" * (MAX_BLOCK_SIZE + 1))

import pytest

from core.tx import (
    COINBASE_INDEX,
    MAX_COINBASE_SCRIPT_SIG,
    MAX_MONEY,
    MAX_SCRIPT_SIZE,
    MIN_COINBASE_SCRIPT_SIG,
    NULL_TXID,
    ByteReader,
    SerializationError,
    Transaction,
    TxIn,
    TxOut,
    TxValidationError,
    decode_coinbase_height,
    double_sha256,
    encode_coinbase_height,
    encode_varint,
)


def coinbase(script_sig: bytes = b"\x01\x01", value: int = 314_520_000) -> Transaction:
    return Transaction(
        version=1,
        inputs=(TxIn(NULL_TXID, COINBASE_INDEX, script_sig),),
        outputs=(TxOut(value, b"\x51"),),
    )


def spend(value_in: int = 1000, value_out: int = 900) -> Transaction:
    return Transaction(
        version=1,
        inputs=(TxIn(b"\xaa" * 32, 0, b"\x00"),),
        outputs=(TxOut(value_out, b"\x51"),),
    )


@pytest.mark.parametrize(
    "value",
    [0, 1, 0xFC, 0xFD, 0xFF, 0xFFFF, 0x10000, 0xFFFFFFFF, 0x100000000, (1 << 64) - 1],
)
def test_varint_roundtrip(value):
    encoded = encode_varint(value)
    reader = ByteReader(encoded)
    assert reader.read_varint() == value
    reader.expect_end()


@pytest.mark.parametrize(
    "raw",
    [
        b"\xfd\xfc\x00",  # 0xFC encoded in 2 byte
        b"\xfe\xff\xff\x00\x00",  # 0xFFFF encoded in 4 byte
        b"\xff\xff\xff\xff\xff\x00\x00\x00\x00",  # 0xFFFFFFFF encoded in 8 byte
    ],
)
def test_varint_non_canonical_rejected(raw):
    with pytest.raises(SerializationError):
        ByteReader(raw).read_varint()


@pytest.mark.parametrize("value", [-1, 1 << 64, True, 1.5])
def test_encode_varint_invalid(value):
    with pytest.raises(SerializationError):
        encode_varint(value)


def test_truncated_bytes_rejected():
    with pytest.raises(SerializationError):
        ByteReader(b"\x01").read(2)


def test_transaction_roundtrip():
    tx = Transaction(
        version=2,
        inputs=(
            TxIn(b"\x01" * 32, 0, b"\xab\xcd", sequence=7),
            TxIn(b"\x02" * 32, 3, b"", sequence=0xFFFFFFFF),
        ),
        outputs=(TxOut(1234, b"\x51\x21"), TxOut(0, b"")),
        lock_time=42,
    )
    raw = tx.serialize()
    assert Transaction.from_bytes(raw) == tx
    assert tx.txid() == double_sha256(raw)
    assert len(tx.txid()) == 32


def test_txid_depends_on_every_relevant_field():
    base = spend()
    variants = [
        Transaction(2, base.inputs, base.outputs),
        Transaction(1, (TxIn(b"\xaa" * 32, 1, b"\x00"),), base.outputs),
        Transaction(1, base.inputs, (TxOut(901, b"\x51"),)),
        Transaction(1, base.inputs, (TxOut(900, b"\x52"),)),
        Transaction(1, base.inputs, base.outputs, 1),
    ]
    assert len({base.txid(), *(tx.txid() for tx in variants)}) == 6


def test_transaction_rejects_trailing_data():
    raw = spend().serialize()
    with pytest.raises(SerializationError):
        Transaction.from_bytes(raw + b"\x00")


def test_coinbase_detection():
    assert coinbase().is_coinbase
    assert not spend().is_coinbase
    # due input non rendono una coinbase
    two = Transaction(1, (TxIn(NULL_TXID, COINBASE_INDEX), TxIn(b"\xaa" * 32, 0)), (TxOut(1, b""),))
    assert not two.is_coinbase


def test_coinbase_requires_single_null_input():
    tx = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX), TxIn(b"\xaa" * 32, 0)),
        (TxOut(1, b""),),
    )
    with pytest.raises(TxValidationError, match="no inputs|coinbase|null"):
        tx.validate()


def test_null_prevout_only_in_coinbase():
    tx = Transaction(1, (TxIn(NULL_TXID, 0),), (TxOut(1, b""),))
    with pytest.raises(TxValidationError, match="null prevout"):
        tx.validate()


def test_duplicate_inputs_rejected():
    tx = Transaction(
        1,
        (TxIn(b"\xaa" * 32, 0), TxIn(b"\xaa" * 32, 0)),
        (TxOut(1, b""),),
    )
    with pytest.raises(TxValidationError, match="duplicate inputs"):
        tx.validate()


def test_empty_inputs_or_outputs_rejected():
    with pytest.raises(TxValidationError, match="no inputs"):
        Transaction(1, (), (TxOut(1, b""),)).validate()
    with pytest.raises(TxValidationError, match="no outputs"):
        Transaction(1, (TxIn(b"\xaa" * 32, 0),), ()).validate()


def test_negative_and_oversized_amounts_rejected():
    with pytest.raises(TxValidationError):
        TxOut(-1, b"")
    with pytest.raises(TxValidationError):
        TxOut(MAX_MONEY + 1, b"")
    with pytest.raises(TxValidationError):
        TxOut(True, b"")
    with pytest.raises(TxValidationError):
        TxOut(1.5, b"")


def test_output_sum_overflow_rejected():
    half = MAX_MONEY // 2 + 1
    tx = Transaction(1, (TxIn(b"\xaa" * 32, 0),), (TxOut(half, b""), TxOut(half, b"")))
    with pytest.raises(TxValidationError, match="MAX_MONEY"):
        tx.validate()


def test_script_size_limit():
    with pytest.raises(TxValidationError):
        TxOut(1, b"\x00" * (MAX_SCRIPT_SIZE + 1))
    with pytest.raises(TxValidationError):
        TxIn(b"\xaa" * 32, 0, b"\x00" * (MAX_SCRIPT_SIZE + 1))


def test_bad_outpoint_length():
    with pytest.raises(TxValidationError):
        TxIn(b"\xaa" * 31, 0)
    with pytest.raises(TxValidationError):
        TxIn(b"\xaa" * 32, -1)


def test_fee():
    tx = spend(value_in=1000, value_out=900)
    assert tx.fee([1000]) == 100
    with pytest.raises(TxValidationError, match="below"):
        tx.fee([899])
    with pytest.raises(TxValidationError, match="length"):
        tx.fee([1000, 1])


def test_zero_value_output_allowed():
    tx = Transaction(1, (TxIn(b"\xaa" * 32, 0),), (TxOut(0, b"\x51"),))
    tx.validate()


@pytest.mark.parametrize(
    "height",
    [0, 1, 2, 127, 128, 255, 256, 0xFFFF, 0x10000, 2**31 - 1, 2**31, 2**32 - 1],
)
def test_coinbase_height_roundtrip(height):
    encoded = encode_coinbase_height(height)
    assert MIN_COINBASE_SCRIPT_SIG <= len(encoded) <= MAX_COINBASE_SCRIPT_SIG
    assert decode_coinbase_height(encoded) == height


def test_coinbase_height_rejects_malformed_prefixes():
    too_long = b"\x01\x01" + b"\x00" * (MAX_COINBASE_SCRIPT_SIG - 1)
    assert len(too_long) == MAX_COINBASE_SCRIPT_SIG + 1
    cases = [
        b"",  # vuoto
        b"\x01",  # sotto il minimo
        b"\x05\x01",  # push troncato
        b"\x01\x00",  # zero non canonico (deve essere OP_0)
        b"\x02\x01\x00",  # intero non minimale
        b"\x01\x80",  # negativo
        b"\x4c\x01\x01",  # primo opcode non e' un push di altezza
        too_long,
    ]
    for raw in cases:
        with pytest.raises(TxValidationError):
            decode_coinbase_height(raw)


def test_coinbase_requires_valid_height_in_tx():
    Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(42)),),
        (TxOut(1, b"\x51"),),
    ).validate()

    with pytest.raises(TxValidationError):
        Transaction(
            1, (TxIn(NULL_TXID, COINBASE_INDEX, b"\x05\x01"),), (TxOut(1, b"\x51"),)
        ).validate()

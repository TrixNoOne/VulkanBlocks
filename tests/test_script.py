import hashlib
import struct

import pytest
from coincurve import PrivateKey

from core.params import (
    LOCKTIME_THRESHOLD,
    MAX_OPS_PER_SCRIPT,
    MAX_STACK_ITEMS,
    NETWORK_MAIN,
    NETWORK_TEST,
)
from core.script import (
    HALF_ORDER,
    OP_1,
    OP_DUP,
    OP_PUSHDATA2,
    ScriptError,
    SignatureError,
    decode_script_num,
    encode_script_num,
    hash160,
    htlc_claim_script_sig,
    htlc_refund_script_sig,
    htlc_script,
    p2pkh_script,
    p2pkh_script_sig,
    parse_der_signature,
    push_data,
    sign_digest,
    sighash,
    verify_digest,
    verify_script,
)
from core.tx import Transaction, TxIn, TxOut

PREV_TXID = b"\xaa" * 32
OTHER_TXID = b"\xbb" * 32


def key(seed: int) -> PrivateKey:
    return PrivateKey(bytes([seed]) * 32)


def pubkey(private_key: PrivateKey) -> bytes:
    return private_key.public_key.format(compressed=True)


def spend_tx(
    *,
    prev_txid: bytes = PREV_TXID,
    value: int = 900,
    sequence: int = 0xFFFFFFFF,
    lock_time: int = 0,
    txid_byte: bytes = b"\x01",
) -> Transaction:
    return Transaction(
        1,
        (TxIn(prev_txid, 0, b"", sequence),),
        (TxOut(value, txid_byte),),
        lock_time,
    )


def p2pkh_case(seed: int = 1):
    private_key = key(seed)
    pub = pubkey(private_key)
    script_pubkey = p2pkh_script(hash160(pub))
    tx = spend_tx()
    digest = sighash(tx, 0, script_pubkey)
    signature = sign_digest(private_key, digest)
    return private_key, pub, script_pubkey, tx, signature


def verify_p2pkh(tx, script_pubkey, signature, pub, **kwargs):
    return verify_script(
        tx,
        0,
        script_sig=p2pkh_script_sig(signature, pub),
        script_pubkey=script_pubkey,
        **kwargs,
    )


def htlc_case(locktime: int = 200):
    sender = key(2)
    receiver = key(3)
    preimage = bytes(range(32))
    payment_hash = hashlib.sha256(preimage).digest()
    script_pubkey = htlc_script(
        payment_hash, pubkey(receiver), pubkey(sender), locktime
    )
    return sender, receiver, preimage, script_pubkey


def refund_tx(lock_time: int, sequence: int, value: int = 900) -> Transaction:
    return spend_tx(
        prev_txid=OTHER_TXID,
        value=value,
        sequence=sequence,
        lock_time=lock_time,
    )


def sign_refund(htlc, sender, tx):
    digest = sighash(tx, 0, htlc)
    return htlc_refund_script_sig(sign_digest(sender, digest))


def der_int(value: int) -> bytes:
    raw = value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return b"\x02" + bytes((len(raw),)) + raw


def der_signature(r: int, s: int) -> bytes:
    body = der_int(r) + der_int(s)
    return b"\x30" + bytes((len(body),)) + body


# --- P2PKH -----------------------------------------------------------------


def test_p2pkh_valid():
    _, pub, script_pubkey, tx, signature = p2pkh_case()
    verify_p2pkh(tx, script_pubkey, signature, pub)


def test_p2pkh_wrong_pubkey_fails_hash_check():
    _, _, script_pubkey, tx, signature = p2pkh_case(1)
    _, other_pub = key(2), pubkey(key(2))
    with pytest.raises(ScriptError, match="EQUALVERIFY"):
        verify_p2pkh(tx, script_pubkey, signature, other_pub)


def test_p2pkh_wrong_signature_fails():
    private_key, pub, script_pubkey, tx, signature = p2pkh_case(1)
    wrong_digest = sighash(spend_tx(value=899), 0, script_pubkey)
    wrong_signature = sign_digest(private_key, wrong_digest)
    with pytest.raises(ScriptError, match="false"):
        verify_p2pkh(tx, script_pubkey, wrong_signature, pub)


def test_p2pkh_tampered_transaction_fails():
    _, pub, script_pubkey, _, signature = p2pkh_case()
    tampered = spend_tx(value=899)
    with pytest.raises(ScriptError, match="false"):
        verify_p2pkh(tampered, script_pubkey, signature, pub)


def test_signature_is_low_s():
    _, _, _, _, signature = p2pkh_case()
    _, s = parse_der_signature(signature)
    assert s <= HALF_ORDER


# --- HTLC ------------------------------------------------------------------


def test_htlc_claim_with_correct_preimage():
    _, receiver, preimage, htlc = htlc_case()
    tx = spend_tx(prev_txid=OTHER_TXID)
    digest = sighash(tx, 0, htlc)
    signature = sign_digest(receiver, digest)
    verify_script(
        tx,
        0,
        script_sig=htlc_claim_script_sig(signature, preimage),
        script_pubkey=htlc,
        block_height=100,
    )


def test_htlc_claim_with_wrong_preimage_fails():
    _, receiver, _, htlc = htlc_case()
    tx = spend_tx(prev_txid=OTHER_TXID)
    digest = sighash(tx, 0, htlc)
    signature = sign_digest(receiver, digest)
    with pytest.raises(ScriptError, match="EQUALVERIFY"):
        verify_script(
            tx,
            0,
            script_sig=htlc_claim_script_sig(signature, b"\x00" * 32),
            script_pubkey=htlc,
            block_height=100,
        )


def test_htlc_claim_by_sender_fails():
    sender, _, preimage, htlc = htlc_case()
    tx = spend_tx(prev_txid=OTHER_TXID)
    signature = sign_digest(sender, sighash(tx, 0, htlc))
    with pytest.raises(ScriptError, match="false"):
        verify_script(
            tx,
            0,
            script_sig=htlc_claim_script_sig(signature, preimage),
            script_pubkey=htlc,
            block_height=100,
        )


def test_htlc_refund_after_expiry():
    sender, _, _, htlc = htlc_case(locktime=200)
    tx = refund_tx(lock_time=200, sequence=199)
    signature = sign_refund(htlc, sender, tx)
    verify_script(
        tx,
        0,
        script_sig=signature,
        script_pubkey=htlc,
        block_height=200,
    )
    # anche molto dopo la scadenza
    verify_script(
        tx,
        0,
        script_sig=signature,
        script_pubkey=htlc,
        block_height=10_000,
    )


def test_htlc_refund_before_expiry_fails():
    sender, _, _, htlc = htlc_case(locktime=200)
    tx = refund_tx(lock_time=199, sequence=198)
    signature = sign_refund(htlc, sender, tx)
    with pytest.raises(ScriptError, match="below CLTV"):
        verify_script(
            tx,
            0,
            script_sig=signature,
            script_pubkey=htlc,
            block_height=199,
        )


def test_htlc_refund_fails_if_block_height_before_lock_time():
    sender, _, _, htlc = htlc_case(locktime=200)
    tx = refund_tx(lock_time=200, sequence=199)
    signature = sign_refund(htlc, sender, tx)
    with pytest.raises(ScriptError, match="block height below"):
        verify_script(
            tx,
            0,
            script_sig=signature,
            script_pubkey=htlc,
            block_height=199,
        )


def test_htlc_refund_with_final_sequence_fails():
    sender, _, _, htlc = htlc_case(locktime=200)
    tx = refund_tx(lock_time=200, sequence=0xFFFFFFFF)
    signature = sign_refund(htlc, sender, tx)
    with pytest.raises(ScriptError, match="final sequence"):
        verify_script(
            tx,
            0,
            script_sig=signature,
            script_pubkey=htlc,
            block_height=200,
        )


def test_htlc_refund_without_block_height_fails():
    sender, _, _, htlc = htlc_case(locktime=200)
    tx = refund_tx(lock_time=200, sequence=199)
    signature = sign_refund(htlc, sender, tx)
    with pytest.raises(ScriptError, match="block height required"):
        verify_script(tx, 0, script_sig=signature, script_pubkey=htlc)


def test_htlc_refund_with_timestamp_locktime_fails():
    sender, _, _, htlc = htlc_case(locktime=200)
    tx = refund_tx(lock_time=LOCKTIME_THRESHOLD, sequence=199)
    signature = sign_refund(htlc, sender, tx)
    with pytest.raises(ScriptError, match="not a block height"):
        verify_script(
            tx,
            0,
            script_sig=signature,
            script_pubkey=htlc,
            block_height=LOCKTIME_THRESHOLD,
        )


def test_htlc_builder_rejects_bad_parameters():
    receiver = pubkey(key(3))
    sender = pubkey(key(2))
    with pytest.raises(ScriptError):
        htlc_script(b"\x00" * 31, receiver, sender, 10)
    with pytest.raises(ScriptError):
        htlc_script(b"\x00" * 32, b"\x01" * 32, sender, 10)
    with pytest.raises(ScriptError):
        htlc_script(b"\x00" * 32, receiver, sender, 0)
    with pytest.raises(ScriptError):
        htlc_script(b"\x00" * 32, receiver, sender, LOCKTIME_THRESHOLD)


# --- rete, DER, limiti -----------------------------------------------------


def test_testnet_signature_rejected_on_mainnet():
    private_key = key(1)
    pub = pubkey(private_key)
    script_pubkey = p2pkh_script(hash160(pub))
    tx = spend_tx()
    test_digest = sighash(tx, 0, script_pubkey, network=NETWORK_TEST)
    signature = sign_digest(private_key, test_digest)

    verify_p2pkh(tx, script_pubkey, signature, pub, network=NETWORK_TEST)
    with pytest.raises(ScriptError, match="false"):
        verify_p2pkh(tx, script_pubkey, signature, pub, network=NETWORK_MAIN)


def test_unknown_network_rejected():
    _, _, script_pubkey, tx, _ = p2pkh_case()
    with pytest.raises(ScriptError, match="network"):
        sighash(tx, 0, script_pubkey, network=b"vulcan-other")


def test_high_s_signature_rejected():
    _, pub, script_pubkey, tx, signature = p2pkh_case()
    r, s = parse_der_signature(signature)
    high_s = der_signature(r, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141 - s)
    with pytest.raises(SignatureError, match="high-S"):
        verify_p2pkh(tx, script_pubkey, high_s, pub)
    # la firma originale resta valida
    assert verify_digest(pub, signature, sighash(tx, 0, script_pubkey))


def test_strict_der_rejects_trailing_and_non_minimal():
    _, pub, script_pubkey, tx, signature = p2pkh_case(1)
    with pytest.raises(SignatureError):
        verify_p2pkh(tx, script_pubkey, signature + b"\x00", pub)

    _, s = parse_der_signature(signature)
    # r = 1 con un byte 0x00 non necessario: DER non minimale
    body = b"\x02\x02\x00\x01" + der_int(s)
    bad = b"\x30" + bytes((len(body),)) + body
    with pytest.raises(SignatureError, match="non-minimal"):
        verify_p2pkh(tx, script_pubkey, bad, pub)


def test_strict_der_rejects_negative_integer():
    private_key = key(1)
    pub = pubkey(private_key)
    script_pubkey = p2pkh_script(hash160(pub))
    tx = spend_tx()
    bad = b"\x30\x06\x02\x01\x80\x02\x01\x01"
    with pytest.raises(SignatureError, match="negative"):
        verify_p2pkh(tx, script_pubkey, bad, pub)


def test_undefined_opcode_rejected():
    tx = spend_tx()
    with pytest.raises(ScriptError, match="undefined opcode"):
        verify_script(tx, 0, script_sig=b"", script_pubkey=b"\xff")


def test_script_sig_must_only_push():
    tx = spend_tx()
    with pytest.raises(ScriptError, match="only push"):
        verify_script(tx, 0, script_sig=bytes((OP_DUP,)), script_pubkey=b"\x51")


def test_op_limit_enforced():
    tx = spend_tx()
    script_pubkey = bytes((OP_1,)) + bytes((OP_DUP,)) * (MAX_OPS_PER_SCRIPT + 1)
    with pytest.raises(ScriptError, match="too many operations"):
        verify_script(tx, 0, script_sig=b"", script_pubkey=script_pubkey)


def test_stack_limit_enforced():
    tx = spend_tx()
    script_sig = bytes((OP_1,)) * (MAX_STACK_ITEMS + 1)
    with pytest.raises(ScriptError, match="stack too large"):
        verify_script(tx, 0, script_sig=script_sig, script_pubkey=b"\x51")


def test_stack_element_limit_enforced():
    tx = spend_tx()
    script_sig = bytes((OP_PUSHDATA2,)) + struct.pack("<H", 521) + b"\x00" * 521
    with pytest.raises(ScriptError, match="element too large"):
        verify_script(tx, 0, script_sig=script_sig, script_pubkey=b"\x51")


def test_unbalanced_if_rejected():
    tx = spend_tx()
    with pytest.raises(ScriptError, match="unbalanced"):
        verify_script(tx, 0, script_sig=bytes((OP_1,)), script_pubkey=b"\x63")


def test_cleanstack_enforced():
    tx = spend_tx()
    with pytest.raises(ScriptError, match="cleanstack"):
        verify_script(tx, 0, script_sig=bytes((OP_1,)), script_pubkey=b"\x51")


def test_script_num_roundtrip_and_validation():
    for value in (0, 1, 127, 128, 255, 256, 2**31, 2**32 - 1):
        assert decode_script_num(encode_script_num(value)) == value
    with pytest.raises(ScriptError):
        encode_script_num(-1)
    with pytest.raises(ScriptError):
        decode_script_num(b"\x02\x01\x00")
    with pytest.raises(ScriptError):
        decode_script_num(b"\x01\x80")
    with pytest.raises(ScriptError):
        decode_script_num(b"\x06" + b"\x01" * 6)


def test_push_data_rejects_oversized_element():
    with pytest.raises(ScriptError):
        push_data(b"\x00" * 521)


def test_sign_digest_requires_32_byte_digest():
    with pytest.raises(SignatureError):
        sign_digest(key(1), b"\x00" * 31)

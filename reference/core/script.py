"""Script minimale Vulcan: P2PKH e HTLC su secp256k1.

Il modello e' a stack, senza loop e senza opcode non definiti. Le firme sono
ECDSA DER strette e low-S; il sighash e' SIGHASH_ALL e include il tag di rete.
Il timelock dell'HTLC e' sempre un'altezza di blocco (mai time.time()).
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Sequence

from coincurve import PrivateKey, PublicKey

from .params import (
    LOCKTIME_THRESHOLD,
    MAX_OPS_PER_SCRIPT,
    MAX_SCRIPT_ELEMENT_SIZE,
    MAX_SCRIPT_SIZE,
    MAX_STACK_ITEMS,
    NETWORK_MAIN,
    NETWORK_TAGS,
    SIGHASH_ALL,
)
from .tx import Transaction, TxIn, double_sha256, encode_varint

# Opcode supportati.
OP_0 = 0x00
OP_PUSHDATA1 = 0x4C
OP_PUSHDATA2 = 0x4D
OP_PUSHDATA4 = 0x4E
OP_1 = 0x51
OP_16 = 0x60
OP_IF = 0x63
OP_ELSE = 0x67
OP_ENDIF = 0x68
OP_DROP = 0x75
OP_DUP = 0x76
OP_EQUALVERIFY = 0x88
OP_SHA256 = 0xA8
OP_HASH160 = 0xA9
OP_CHECKSIG = 0xAC
OP_CHECKLOCKTIMEVERIFY = 0xB1

SIGHASH_DOMAIN = b"VulcanSighash\x00"
MAX_DER_SIGNATURE_SIZE = 72

# Ordine della curva secp256k1 (per il controllo low-S).
SECP256K1_ORDER = (
    0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
)
HALF_ORDER = SECP256K1_ORDER // 2

_SUPPORTED_OPCODES = frozenset(
    {
        OP_IF,
        OP_ELSE,
        OP_ENDIF,
        OP_DROP,
        OP_DUP,
        OP_EQUALVERIFY,
        OP_SHA256,
        OP_HASH160,
        OP_CHECKSIG,
        OP_CHECKLOCKTIMEVERIFY,
    }
)


class ScriptError(ValueError):
    """Script non valido o valutato falso."""


class SignatureError(ScriptError):
    """Firma non DER-stretta, high-S o fuori dominio."""


def hash160(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data)), usato per gli hash delle chiavi pubbliche."""
    return hashlib.new("ripemd160", hashlib.sha256(data).digest()).digest()


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _check_network(network: bytes) -> None:
    if network not in NETWORK_TAGS:
        raise ScriptError("unknown network tag")


def _check_pubkey(pubkey: bytes) -> bytes:
    raw = bytes(pubkey)
    if len(raw) not in (33, 65):
        raise ScriptError("invalid public key length")
    try:
        PublicKey(raw)
    except ValueError as exc:
        raise ScriptError("invalid public key") from exc
    return raw


def encode_script_num(value: int) -> bytes:
    """CScriptNum minimale little-endian per numeri non negativi."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise ScriptError("script number must be an int")
    if value < 0:
        raise ScriptError("negative script number")
    if value == 0:
        return b""
    raw = value.to_bytes((value.bit_length() + 7) // 8, "little")
    if raw[-1] & 0x80:
        raw += b"\x00"
    if len(raw) > 5:
        raise ScriptError("script number too large")
    return raw


def decode_script_num(data: bytes, *, max_size: int = 5) -> int:
    """Decodifica CScriptNum; richiede la forma minimale e non negativa."""
    if len(data) > max_size:
        raise ScriptError("script number too large")
    if not data:
        return 0
    if data[-1] & 0x80:
        raise ScriptError("negative script number")
    if data == b"\x00":
        raise ScriptError("non-minimal script number")
    if len(data) > 1 and data[-1] == 0 and not (data[-2] & 0x80):
        raise ScriptError("non-minimal script number")
    return int.from_bytes(data, "little")


def push_data(data: bytes) -> bytes:
    """Push minimale (diretto o PUSHDATA) di un elemento."""
    raw = bytes(data)
    size = len(raw)
    if size > MAX_SCRIPT_ELEMENT_SIZE:
        raise ScriptError("script element too large")
    if size <= 75:
        return bytes((size,)) + raw
    if size <= 0xFF:
        return bytes((OP_PUSHDATA1, size)) + raw
    if size <= 0xFFFF:
        return bytes((OP_PUSHDATA2,)) + struct.pack("<H", size) + raw
    return bytes((OP_PUSHDATA4,)) + struct.pack("<I", size) + raw


def p2pkh_script(pubkey_hash: bytes) -> bytes:
    """OP_DUP OP_HASH160 <hash> OP_EQUALVERIFY OP_CHECKSIG."""
    digest = bytes(pubkey_hash)
    if len(digest) != 20:
        raise ScriptError("pubkey hash must be 20 bytes")
    script = b"".join(
        (
            bytes((OP_DUP, OP_HASH160)),
            push_data(digest),
            bytes((OP_EQUALVERIFY, OP_CHECKSIG)),
        )
    )
    return script


def p2pkh_script_sig(signature: bytes, pubkey: bytes) -> bytes:
    return push_data(signature) + push_data(_check_pubkey(pubkey))


def htlc_script(
    payment_hash: bytes,
    receiver_pubkey: bytes,
    sender_pubkey: bytes,
    locktime_height: int,
) -> bytes:
    """HTLC: claim con segreto o refund del mittente dopo il timelock.

    OP_IF
        OP_SHA256 <H> OP_EQUALVERIFY <receiver> OP_CHECKSIG
    OP_ELSE
        <locktime_height> OP_CHECKLOCKTIMEVERIFY OP_DROP <sender> OP_CHECKSIG
    OP_ENDIF
    """
    digest = bytes(payment_hash)
    if len(digest) != 32:
        raise ScriptError("payment hash must be 32 bytes (SHA-256)")
    receiver = _check_pubkey(receiver_pubkey)
    sender = _check_pubkey(sender_pubkey)
    if not isinstance(locktime_height, int) or isinstance(locktime_height, bool):
        raise ScriptError("locktime must be an int")
    if not 1 <= locktime_height < LOCKTIME_THRESHOLD:
        raise ScriptError("locktime must be a block height")

    script = b"".join(
        (
            bytes((OP_IF, OP_SHA256)),
            push_data(digest),
            bytes((OP_EQUALVERIFY,)),
            push_data(receiver),
            bytes((OP_CHECKSIG, OP_ELSE)),
            push_data(encode_script_num(locktime_height)),
            bytes((OP_CHECKLOCKTIMEVERIFY, OP_DROP)),
            push_data(sender),
            bytes((OP_CHECKSIG, OP_ENDIF)),
        )
    )
    if len(script) > MAX_SCRIPT_SIZE:
        raise ScriptError("script too large")
    return script


def htlc_claim_script_sig(signature: bytes, preimage: bytes) -> bytes:
    """<sig> <preimage> OP_1: ramo IF."""
    return push_data(signature) + push_data(preimage) + bytes((OP_1,))


def htlc_refund_script_sig(signature: bytes) -> bytes:
    """<sig> OP_0: ramo ELSE (refund)."""
    return push_data(signature) + bytes((OP_0,))


def _der_uint(raw: bytes) -> int:
    if not raw:
        raise SignatureError("empty DER integer")
    if raw[0] & 0x80:
        raise SignatureError("negative DER integer")
    if len(raw) > 1 and raw[0] == 0 and raw[1] < 0x80:
        raise SignatureError("non-minimal DER integer")
    if len(raw) > 33:
        raise SignatureError("DER integer too large")
    return int.from_bytes(raw, "big")


def parse_der_signature(signature: bytes) -> tuple[int, int]:
    """DER stretto + low-S. Restituisce (r, s) gia' validati."""
    der = bytes(signature)
    if not 8 <= len(der) <= MAX_DER_SIGNATURE_SIZE:
        raise SignatureError("bad DER signature length")
    if der[0] != 0x30:
        raise SignatureError("bad DER sequence")
    if der[1] & 0x80:
        raise SignatureError("DER long form not allowed")
    if der[1] != len(der) - 2:
        raise SignatureError("bad DER sequence length")

    pos = 2
    if der[pos] != 0x02:
        raise SignatureError("missing DER r")
    rlen = der[pos + 1]
    pos += 2
    if rlen == 0 or pos + rlen + 2 > len(der):
        raise SignatureError("bad DER r length")
    r = _der_uint(der[pos : pos + rlen])
    pos += rlen

    if der[pos] != 0x02:
        raise SignatureError("missing DER s")
    slen = der[pos + 1]
    pos += 2
    if slen == 0 or pos + slen != len(der):
        raise SignatureError("bad DER s length")
    s = _der_uint(der[pos : pos + slen])

    if not 1 <= r < SECP256K1_ORDER or not 1 <= s < SECP256K1_ORDER:
        raise SignatureError("signature scalar out of range")
    if s > HALF_ORDER:
        raise SignatureError("high-S signature")
    return r, s


def verify_digest(pubkey: bytes, signature: bytes, digest: bytes) -> bool:
    """Verifica una firma DER low-S contro un digest gia' calcolato."""
    if len(digest) != 32:
        raise SignatureError("digest must be 32 bytes")
    parse_der_signature(signature)  # consenso: DER stretto e low-S
    raw = _check_pubkey(pubkey)
    key = PublicKey(raw)
    try:
        return key.verify(bytes(signature), digest, hasher=None)
    except ValueError:
        return False


def sighash(
    tx: Transaction,
    input_index: int,
    script_pubkey: bytes,
    *,
    network: bytes = NETWORK_MAIN,
) -> bytes:
    """SIGHASH_ALL: tag di rete + indice + tx con lo script dell'input corrente."""
    _check_network(network)
    if not isinstance(input_index, int) or isinstance(input_index, bool):
        raise ScriptError("input_index must be an int")
    if not 0 <= input_index < len(tx.inputs):
        raise ScriptError("input_index out of range")
    spk = bytes(script_pubkey)
    if len(spk) > MAX_SCRIPT_SIZE:
        raise ScriptError("script_pubkey too large")

    inputs = tuple(
        TxIn(
            txin.prev_txid,
            txin.prev_index,
            spk if index == input_index else b"",
            txin.sequence,
        )
        for index, txin in enumerate(tx.inputs)
    )
    unsigned = Transaction(tx.version, inputs, tx.outputs, tx.lock_time)

    preimage = b"".join(
        (
            SIGHASH_DOMAIN,
            encode_varint(len(network)),
            network,
            struct.pack("<II", input_index, SIGHASH_ALL),
            unsigned.serialize(),
        )
    )
    return double_sha256(preimage)


def sign_digest(private_key: PrivateKey, digest: bytes) -> bytes:
    """Firma deterministica (RFC6979) di un digest; produce DER low-S."""
    if len(digest) != 32:
        raise SignatureError("digest must be 32 bytes")
    return private_key.sign(digest, hasher=None)


def _is_push_opcode(opcode: int) -> bool:
    return opcode == OP_0 or 1 <= opcode <= OP_PUSHDATA4 or OP_1 <= opcode <= OP_16


def _parse_script(script: bytes) -> list[tuple[int, bytes | None]]:
    ops: list[tuple[int, bytes | None]] = []
    pos = 0
    size = len(script)
    while pos < size:
        opcode = script[pos]
        pos += 1
        if opcode == OP_0:
            ops.append((opcode, b""))
        elif 1 <= opcode <= 75:
            end = pos + opcode
            if end > size:
                raise ScriptError("truncated push")
            ops.append((opcode, script[pos:end]))
            pos = end
        elif opcode in (OP_PUSHDATA1, OP_PUSHDATA2, OP_PUSHDATA4):
            width = {OP_PUSHDATA1: 1, OP_PUSHDATA2: 2, OP_PUSHDATA4: 4}[opcode]
            if pos + width > size:
                raise ScriptError("truncated PUSHDATA length")
            length = int.from_bytes(script[pos : pos + width], "little")
            pos += width
            end = pos + length
            if end > size:
                raise ScriptError("truncated PUSHDATA payload")
            ops.append((opcode, script[pos:end]))
            pos = end
        elif OP_1 <= opcode <= OP_16:
            ops.append((opcode, bytes((opcode - OP_1 + 1,))))
        elif opcode in _SUPPORTED_OPCODES:
            ops.append((opcode, None))
        else:
            raise ScriptError(f"undefined opcode 0x{opcode:02x}")
    return ops


def _cast_bool(data: bytes) -> bool:
    if not data:
        return False
    if data[-1] == 0x80:
        return any(byte != 0 for byte in data[:-1])
    return any(byte != 0 for byte in data)


def _push(stack: list[bytes], data: bytes) -> None:
    if len(data) > MAX_SCRIPT_ELEMENT_SIZE:
        raise ScriptError("stack element too large")
    stack.append(data)
    if len(stack) > MAX_STACK_ITEMS:
        raise ScriptError("stack too large")


@dataclass(frozen=True, slots=True)
class _Context:
    tx: Transaction
    input_index: int
    digest: bytes
    block_height: int | None


def _check_locktime(stack: Sequence[bytes], ctx: _Context) -> None:
    if not stack:
        raise ScriptError("CHECKLOCKTIMEVERIFY on empty stack")
    locktime = decode_script_num(stack[-1])
    if locktime >= LOCKTIME_THRESHOLD:
        raise ScriptError("locktime is not a block height")
    txin = ctx.tx.inputs[ctx.input_index]
    if txin.sequence == 0xFFFFFFFF:
        raise ScriptError("CHECKLOCKTIMEVERIFY with final sequence")
    if ctx.tx.lock_time < locktime:
        raise ScriptError("transaction lock_time below CLTV")
    if ctx.tx.lock_time >= LOCKTIME_THRESHOLD:
        raise ScriptError("transaction lock_time is not a block height")
    if ctx.block_height is None:
        raise ScriptError("block height required for CHECKLOCKTIMEVERIFY")
    if ctx.block_height < ctx.tx.lock_time:
        raise ScriptError("block height below transaction lock_time")


def _run(
    ops: list[tuple[int, bytes | None]],
    stack: list[bytes],
    ctx: _Context,
    *,
    push_only: bool,
) -> None:
    executing = True
    # (parent_executing, branch_condition, else_seen)
    conditions: list[tuple[bool, bool, bool]] = []
    op_count = 0

    for opcode, data in ops:
        # Conta tutti gli opcode non-push, anche nei rami non eseguiti.
        if not _is_push_opcode(opcode):
            op_count += 1
            if op_count > MAX_OPS_PER_SCRIPT:
                raise ScriptError("too many operations")

        if opcode in (OP_IF, OP_ELSE, OP_ENDIF):
            if opcode == OP_IF:
                if executing:
                    if not stack:
                        raise ScriptError("IF on empty stack")
                    condition = _cast_bool(stack.pop())
                    conditions.append((True, condition, False))
                    executing = condition
                else:
                    conditions.append((False, False, False))
                    executing = False
            elif opcode == OP_ELSE:
                if not conditions:
                    raise ScriptError("ELSE without IF")
                parent, condition, else_seen = conditions[-1]
                if else_seen:
                    raise ScriptError("duplicate ELSE")
                conditions[-1] = (parent, condition, True)
                executing = parent and not condition
            else:
                if not conditions:
                    raise ScriptError("ENDIF without IF")
                parent, _, _ = conditions.pop()
                executing = parent
            continue

        if not executing:
            continue
        if push_only and not _is_push_opcode(opcode):
            raise ScriptError("scriptSig may only push data")

        if _is_push_opcode(opcode):
            _push(stack, data if data is not None else b"")
            continue

        if opcode == OP_DUP:
            if not stack:
                raise ScriptError("DUP on empty stack")
            _push(stack, stack[-1])
        elif opcode == OP_DROP:
            if not stack:
                raise ScriptError("DROP on empty stack")
            stack.pop()
        elif opcode == OP_SHA256:
            if not stack:
                raise ScriptError("SHA256 on empty stack")
            _push(stack, sha256(stack.pop()))
        elif opcode == OP_HASH160:
            if not stack:
                raise ScriptError("HASH160 on empty stack")
            _push(stack, hash160(stack.pop()))
        elif opcode == OP_EQUALVERIFY:
            if len(stack) < 2:
                raise ScriptError("EQUALVERIFY needs two elements")
            right = stack.pop()
            left = stack.pop()
            if left != right:
                raise ScriptError("EQUALVERIFY failed")
        elif opcode == OP_CHECKSIG:
            if len(stack) < 2:
                raise ScriptError("CHECKSIG needs two elements")
            pubkey = stack.pop()
            signature = stack.pop()
            _push(stack, b"\x01" if verify_digest(pubkey, signature, ctx.digest) else b"")
        elif opcode == OP_CHECKLOCKTIMEVERIFY:
            _check_locktime(stack, ctx)
        else:  # pragma: no cover - il parser filtra gli opcode
            raise ScriptError(f"unsupported opcode 0x{opcode:02x}")

    if conditions:
        raise ScriptError("unbalanced IF/ENDIF")


def verify_script(
    tx: Transaction,
    input_index: int,
    *,
    script_sig: bytes,
    script_pubkey: bytes,
    network: bytes = NETWORK_MAIN,
    block_height: int | None = None,
) -> None:
    """Valida script_sig + script_pubkey per l'input indicato.

    Solleva ScriptError se lo script fallisce; ritorna None se valido.
    """
    sig_script = bytes(script_sig)
    pub_script = bytes(script_pubkey)
    if len(sig_script) > MAX_SCRIPT_SIZE or len(pub_script) > MAX_SCRIPT_SIZE:
        raise ScriptError("script too large")
    digest = sighash(tx, input_index, pub_script, network=network)
    ctx = _Context(tx=tx, input_index=input_index, digest=digest, block_height=block_height)

    stack: list[bytes] = []
    _run(_parse_script(sig_script), stack, ctx, push_only=True)
    _run(_parse_script(pub_script), stack, ctx, push_only=False)

    if len(stack) != 1:
        raise ScriptError("cleanstack: exactly one element required")
    if not _cast_bool(stack[0]):
        raise ScriptError("script evaluated to false")

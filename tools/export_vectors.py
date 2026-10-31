"""Generate golden test vectors for the Vulkan core.

All vectors are produced directly from the Python implementation, so they are
guaranteed to agree with the code at generation time. Commit the resulting
JSON files under ``vectors/`` and let :mod:`tests.test_vectors` regenerate and
compare them byte for byte.

Run from the repo root::

    python -m tools.export_vectors
"""

from __future__ import annotations

import json
from pathlib import Path

from coincurve import PrivateKey

from core.address import pubkey_to_address
from core.block import Block, BlockHeader, merkle_root
from core.chain import Chain, ChainParams
from core.difficulty import asert_target
from core.genesis import genesis_block, genesis_anchor
from core.params import (
    HALVING_INTERVAL,
    MAX_TARGET,
    NETWORK_MAIN,
    NETWORK_TEST,
    block_subsidy,
)
from core.script import (
    hash160,
    htlc_claim_script_sig,
    htlc_refund_script_sig,
    htlc_script,
    p2pkh_script,
    p2pkh_script_sig,
    sha256,
    sighash,
    sign_digest,
)
from core.tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    encode_coinbase_height,
)

VECTORS_DIR = Path(__file__).resolve().parent.parent / "vectors"

# JSON / JavaScript can only safely represent integers up to 2**53 - 1.
# Anything wider must be emitted as a decimal string, with a *_hex companion.
SAFE_MAX = (1 << 53) - 1

PRIVATE_KEY = PrivateKey(bytes([0x03]) * 32)
PUBLIC_KEY = PRIVATE_KEY.public_key.format(compressed=True)
PUBKEY_HASH = hash160(PUBLIC_KEY)

SECOND_KEY = PrivateKey(bytes([0x07]) * 32)
SECOND_PUBLIC_KEY = SECOND_KEY.public_key.format(compressed=True)


def _big_int(n: int) -> int | str:
    """Return ``n`` as-is if JS-safe, otherwise as a decimal string."""
    if n > SAFE_MAX:
        return str(n)
    return n


def _big_int_hex(n: int, width: int) -> str:
    return n.to_bytes(width, "big").hex()


def header_vector(block: Block) -> dict:
    header = block.header
    header_bytes = header.serialize()
    full_bytes = block.serialize()
    digest = header.block_hash
    target = header.target
    pow_value = header.pow_value
    work = header.work
    return {
        "height": header.height,
        "version": header.version,
        "prev_hash": header.prev_hash.hex(),
        "merkle_root": header.merkle_root.hex(),
        "timestamp": header.timestamp,
        "target": _big_int(target),
        "target_hex": _big_int_hex(target, 64),
        "nonce": _big_int(header.nonce),
        "header_hex": header_bytes.hex(),
        "block_hex": full_bytes.hex(),
        "hash": digest.hex(),
        "pow_value": _big_int(pow_value),
        "pow_value_hex": _big_int_hex(pow_value, 64),
        "work": _big_int(work),
        "work_hex": _big_int_hex(work, 64),
    }


def tx_vector(tx: Transaction) -> dict:
    return {
        "txid": tx.txid().hex(),
        "version": tx.version,
        "lock_time": tx.lock_time,
        "serialized": tx.serialize().hex(),
        "inputs": [
            {
                "prev_txid": txin.prev_txid.hex(),
                "vout": txin.prev_index,
                "script_sig": txin.script_sig.hex(),
                "sequence": txin.sequence,
            }
            for txin in tx.inputs
        ],
        "outputs": [
            {"value": _big_int(txout.value), "script_pubkey": txout.script_pubkey.hex()}
            for txout in tx.outputs
        ],
    }


def build() -> dict:
    vectors: dict[str, object] = {}

    # --- Block headers -----------------------------------------------------
    genesis = genesis_block(NETWORK_MAIN)
    vectors["block_headers"] = [header_vector(genesis)]

    # A few regtest blocks (target == MAX_TARGET, so nonce 0 is valid).
    regtest = ChainParams.regtest()
    prev = regtest.genesis
    for height in range(1, 4):
        timestamp = genesis.header.timestamp + 120 * height
        cb = Transaction(
            1,
            (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(height)),),
            (TxOut(block_subsidy(height), b"\x51"),),
        )
        header = BlockHeader(
            version=1,
            height=height,
            prev_hash=prev.block_hash,
            merkle_root=merkle_root([cb.txid()]),
            timestamp=timestamp,
            target=MAX_TARGET,
            nonce=0,
        )
        block = Block(header, (cb,))
        block.header.check_pow()
        vectors["block_headers"].append(header_vector(block))  # type: ignore[attr-defined]
        prev = block

    # --- Regtest block accepted through Chain.accept_block -----------------
    regtest_chain = Chain(regtest, path=":memory:")
    accepted_ts = regtest.genesis.header.timestamp + 120
    accepted_cb = Transaction(
        1,
        (
            TxIn(
                NULL_TXID,
                COINBASE_INDEX,
                encode_coinbase_height(1),
            ),
        ),
        (TxOut(block_subsidy(1), PUBKEY_HASH),),
    )
    accepted_header = BlockHeader(
        version=1,
        height=1,
        prev_hash=regtest.genesis.block_hash,
        merkle_root=merkle_root([accepted_cb.txid()]),
        timestamp=accepted_ts,
        target=regtest.pow_limit,
        nonce=0,
    )
    accepted_block = Block(accepted_header, (accepted_cb,))
    accepted_block.header.check_pow()
    result = regtest_chain.accept_block(accepted_block, now=accepted_ts)
    vectors["regtest_block"] = {
        **header_vector(accepted_block),
        "accepted": result.accepted,
        "reason": result.reason,
        "tip": regtest_chain.tip().block_hash.hex(),
        "utxo_set_hash": regtest_chain.utxo_set_hash().hex(),
    }
    regtest_chain.close()

    # --- Transactions ------------------------------------------------------
    coinbase = Transaction(
        1,
        (
            TxIn(
                NULL_TXID,
                COINBASE_INDEX,
                encode_coinbase_height(1),
            ),
        ),
        (TxOut(block_subsidy(1), PUBKEY_HASH),),
    )
    vectors["transactions"] = [
        tx_vector(coinbase),
        tx_vector(
            Transaction(
                1,
                (
                    TxIn(b"\xaa" * 32, 0, b"", 0xFFFFFFFF),
                    TxIn(b"\xbb" * 32, 1, b"\x01", 42),
                ),
                (
                    TxOut(5000, b"\x51"),
                    TxOut(3000, hash160(SECOND_PUBLIC_KEY)),
                ),
                0,
            )
        ),
    ]

    # --- Signed P2PKH transaction -----------------------------------------
    spending = Transaction(
        1,
        (TxIn(b"\xcc" * 32, 0, b"", 0xFFFFFFFF),),
        (TxOut(9000, hash160(PUBLIC_KEY)),),
        0,
    )
    script_pubkey = p2pkh_script(PUBKEY_HASH)
    digest = sighash(spending, 0, script_pubkey, network=NETWORK_MAIN)
    signature = sign_digest(PRIVATE_KEY, digest)
    script_sig = p2pkh_script_sig(signature, PUBLIC_KEY)
    vectors["p2pkh"] = {
        "network": NETWORK_MAIN.decode(),
        "pubkey": PUBLIC_KEY.hex(),
        "address": pubkey_to_address(PUBLIC_KEY, NETWORK_MAIN),
        "address_testnet": pubkey_to_address(PUBLIC_KEY, NETWORK_TEST),
        "script_pubkey": script_pubkey.hex(),
        "tx_serialized": spending.serialize().hex(),
        "txid": spending.txid().hex(),
        "input_index": 0,
        "sighash": digest.hex(),
        "signature": signature.hex(),
        "script_sig": script_sig.hex(),
    }

    # --- HTLC --------------------------------------------------------------
    # The HTLC script checks ``SHA256(preimage) == payment_hash`` (single
    # SHA-256 via OP_SHA256, see core/script.py).
    sender = PrivateKey(bytes([0x09]) * 32)
    receiver = PrivateKey(bytes([0x0B]) * 32)
    preimage = bytes(range(32))
    payment_hash = sha256(preimage)
    locktime_height = 500
    htlc = htlc_script(
        payment_hash,
        receiver.public_key.format(compressed=True),
        sender.public_key.format(compressed=True),
        locktime_height,
    )
    refund_tx = Transaction(
        1,
        (TxIn(b"\xdd" * 32, 0, b"", 499),),
        (TxOut(9000, b"\x51"),),
        500,
    )
    refund_digest = sighash(refund_tx, 0, htlc, network=NETWORK_MAIN)
    refund_sig = sign_digest(sender, refund_digest)
    refund_script_sig = htlc_refund_script_sig(refund_sig)
    claim_tx = Transaction(
        1,
        (TxIn(b"\xdd" * 32, 0, b"", 498),),
        (TxOut(9000, b"\x51"),),
        500,
    )
    claim_digest = sighash(claim_tx, 0, htlc, network=NETWORK_MAIN)
    claim_sig = sign_digest(receiver, claim_digest)
    claim_script_sig = htlc_claim_script_sig(claim_sig, preimage)
    vectors["htlc"] = {
        "payment_hash": payment_hash.hex(),
        "preimage": preimage.hex(),
        "sender_pubkey": sender.public_key.format(compressed=True).hex(),
        "receiver_pubkey": receiver.public_key.format(compressed=True).hex(),
        "locktime_height": locktime_height,
        "script": htlc.hex(),
        "refund_tx_serialized": refund_tx.serialize().hex(),
        "refund_sighash": refund_digest.hex(),
        "refund_signature": refund_sig.hex(),
        "refund_script_sig": refund_script_sig.hex(),
        "claim_tx_serialized": claim_tx.serialize().hex(),
        "claim_sighash": claim_digest.hex(),
        "claim_signature": claim_sig.hex(),
        "claim_script_sig": claim_script_sig.hex(),
    }

    # --- ASERT -------------------------------------------------------------
    anchor = genesis_anchor(NETWORK_MAIN)
    asert_cases = []
    for height, parent_ts in (
        (0, genesis.header.timestamp),
        (1, genesis.header.timestamp),
        (2, genesis.header.timestamp + 120),
        (100, genesis.header.timestamp + 120 * 99),
        (1000, genesis.header.timestamp + 120 * 999),
    ):
        target = asert_target(
            height,
            parent_ts,
            anchor,
            pow_limit=genesis.header.target,
        )
        asert_cases.append(
            {
                "height": height,
                "parent_timestamp": parent_ts,
                "anchor_height": anchor.height,
                "anchor_timestamp": anchor.timestamp,
                "anchor_target": _big_int(anchor.target),
                "anchor_target_hex": _big_int_hex(anchor.target, 64),
                "target": _big_int(target),
                "target_hex": _big_int_hex(target, 64),
            }
        )
    vectors["asert"] = asert_cases

    # --- Addresses ---------------------------------------------------------
    vectors["addresses"] = {
        "mainnet": pubkey_to_address(PUBLIC_KEY, NETWORK_MAIN),
        "testnet": pubkey_to_address(PUBLIC_KEY, NETWORK_TEST),
        "pubkey": PUBLIC_KEY.hex(),
    }

    # --- Subsidy -----------------------------------------------------------
    subsidy_cases = []
    for height in (
        0,
        1,
        HALVING_INTERVAL - 1,
        HALVING_INTERVAL,
        HALVING_INTERVAL + 1,
        2 * HALVING_INTERVAL,
        63 * HALVING_INTERVAL,
        64 * HALVING_INTERVAL,
        100 * HALVING_INTERVAL,
    ):
        subsidy_cases.append(
            {"height": height, "subsidy": _big_int(block_subsidy(height))}
        )
    vectors["subsidy"] = subsidy_cases

    return vectors


def main() -> None:
    VECTORS_DIR.mkdir(parents=True, exist_ok=True)
    data = build()
    for name, payload in data.items():
        path = VECTORS_DIR / f"{name}.json"
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"wrote {path}")


if __name__ == "__main__":
    main()

"""Golden-vector tests: regeneration plus execution through real code."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.export_vectors import build, VECTORS_DIR  # noqa: E402

from core.block import Block, double_sha512  # noqa: E402
from core.chain import Chain, ChainParams  # noqa: E402
from core.address import pubkey_to_address  # noqa: E402
from core.difficulty import asert_target  # noqa: E402
from core.genesis import genesis_block, genesis_anchor  # noqa: E402
from core.params import NETWORK_MAIN, NETWORK_TEST, block_subsidy  # noqa: E402
from core.script import (  # noqa: E402
    ScriptError,
    hash160,
    htlc_claim_script_sig,
    htlc_script,
    p2pkh_script,
    sha256,
    sighash,
    verify_script,
)
from core.tx import Transaction  # noqa: E402


def _regenerated_text(name: str) -> str:
    payload = build()[name]
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def test_vectors_match_committed_files():
    names = [
        "block_headers",
        "regtest_block",
        "transactions",
        "p2pkh",
        "htlc",
        "asert",
        "addresses",
        "subsidy",
    ]
    assert VECTORS_DIR.is_dir(), f"vectors directory missing: {VECTORS_DIR}"
    for name in names:
        committed = VECTORS_DIR / f"{name}.json"
        assert committed.is_file(), f"committed vector missing: {committed}"
        expected = committed.read_text(encoding="utf-8")
        actual = _regenerated_text(name)
        assert actual == expected, (
            f"vector {name}.json is stale; re-run python -m tools.export_vectors"
        )


def test_block_headers_hash_and_header_hex():
    vectors = json.loads(
        (VECTORS_DIR / "block_headers.json").read_text(encoding="utf-8")
    )
    for entry in vectors:
        raw = bytes.fromhex(entry["header_hex"])
        assert len(raw) == 184, f"header_hex must be 184 bytes, got {len(raw)}"
        digest = double_sha512(raw)
        assert digest.hex() == entry["hash"], "header double SHA-512 mismatch"
        block = Block.from_bytes(bytes.fromhex(entry["block_hex"]))
        assert block.header.block_hash.hex() == entry["hash"]


def test_regtest_block_accepted_through_chain():
    vectors = json.loads(
        (VECTORS_DIR / "regtest_block.json").read_text(encoding="utf-8")
    )
    assert vectors["accepted"] is True
    assert vectors["reason"] == ""
    params = ChainParams.regtest()
    chain = Chain(params, path=":memory:")
    block = Block.from_bytes(bytes.fromhex(vectors["block_hex"]))
    res = chain.accept_block(block, now=vectors["timestamp"])
    assert res.accepted, res.reason
    assert chain.tip().block_hash.hex() == vectors["tip"]
    assert chain.utxo_set_hash().hex() == vectors["utxo_set_hash"]
    chain.close()


def test_p2pkh_signature_verification():
    vectors = json.loads((VECTORS_DIR / "p2pkh.json").read_text(encoding="utf-8"))
    pubkey = bytes.fromhex(vectors["pubkey"])
    script_pubkey = bytes.fromhex(vectors["script_pubkey"])
    tx = Transaction.from_bytes(bytes.fromhex(vectors["tx_serialized"]))
    digest = bytes.fromhex(vectors["sighash"])

    expected_spk = p2pkh_script(hash160(pubkey))
    assert expected_spk == script_pubkey
    expected_digest = sighash(tx, 0, script_pubkey, network=NETWORK_MAIN)
    assert expected_digest == digest

    verify_script(
        tx,
        0,
        script_sig=bytes.fromhex(vectors["script_sig"]),
        script_pubkey=script_pubkey,
        network=NETWORK_MAIN,
    )

    import pytest

    with pytest.raises(Exception):
        verify_script(
            tx,
            0,
            script_sig=bytes.fromhex(vectors["script_sig"]),
            script_pubkey=script_pubkey,
            network=NETWORK_TEST,
        )


def test_htlc_claim_valid_then_rejected_wrong_preimage():
    vectors = json.loads((VECTORS_DIR / "htlc.json").read_text(encoding="utf-8"))
    script = bytes.fromhex(vectors["script"])
    preimage = bytes.fromhex(vectors["preimage"])
    wrong_preimage = bytes(range(1, 33))
    receiver_pubkey = bytes.fromhex(vectors["receiver_pubkey"])
    sender_pubkey = bytes.fromhex(vectors["sender_pubkey"])
    locktime_height = vectors["locktime_height"]

    assert sha256(preimage).hex() == vectors["payment_hash"]

    rebuilt = htlc_script(
        sha256(preimage), receiver_pubkey, sender_pubkey, locktime_height
    )
    assert rebuilt == script

    claim_tx = Transaction.from_bytes(
        bytes.fromhex(vectors["claim_tx_serialized"])
    )
    claim_digest = bytes.fromhex(vectors["claim_sighash"])
    expected_claim_digest = sighash(claim_tx, 0, script, network=NETWORK_MAIN)
    assert claim_digest == expected_claim_digest

    verify_script(
        claim_tx,
        0,
        script_sig=bytes.fromhex(vectors["claim_script_sig"]),
        script_pubkey=script,
        network=NETWORK_MAIN,
        block_height=locktime_height,
    )

    bad_claim_sig = htlc_claim_script_sig(
        bytes.fromhex(vectors["claim_signature"]), wrong_preimage
    )
    try:
        verify_script(
            claim_tx,
            0,
            script_sig=bad_claim_sig,
            script_pubkey=script,
            network=NETWORK_MAIN,
            block_height=locktime_height,
        )
    except ScriptError:
        pass
    else:
        raise AssertionError("HTLC claim with wrong preimage was accepted")


def test_htlc_refund_rejected_before_locktime_valid_after():
    vectors = json.loads((VECTORS_DIR / "htlc.json").read_text(encoding="utf-8"))
    script = bytes.fromhex(vectors["script"])
    locktime_height = vectors["locktime_height"]

    refund_tx = Transaction.from_bytes(
        bytes.fromhex(vectors["refund_tx_serialized"])
    )
    refund_digest = bytes.fromhex(vectors["refund_sighash"])
    expected_refund_digest = sighash(refund_tx, 0, script, network=NETWORK_MAIN)
    assert refund_digest == expected_refund_digest

    try:
        verify_script(
            refund_tx,
            0,
            script_sig=bytes.fromhex(vectors["refund_script_sig"]),
            script_pubkey=script,
            network=NETWORK_MAIN,
            block_height=locktime_height - 1,
        )
    except ScriptError:
        pass
    else:
        raise AssertionError("HTLC refund before locktime was accepted")

    verify_script(
        refund_tx,
        0,
        script_sig=bytes.fromhex(vectors["refund_script_sig"]),
        script_pubkey=script,
        network=NETWORK_MAIN,
        block_height=locktime_height,
    )


def test_asert_vectors_recomputed_independently():
    vectors = json.loads((VECTORS_DIR / "asert.json").read_text(encoding="utf-8"))
    genesis = genesis_block(NETWORK_MAIN)
    anchor = genesis_anchor(NETWORK_MAIN)
    for entry in vectors:
        target = asert_target(
            entry["height"],
            entry["parent_timestamp"],
            anchor,
            pow_limit=genesis.header.target,
        )
        assert str(target) == entry["target"], (
            f"ASERT mismatch at height {entry['height']}"
        )
        assert target.to_bytes(64, "big").hex() == entry["target_hex"]
        assert str(anchor.target) == entry["anchor_target"]
        assert anchor.target.to_bytes(64, "big").hex() == entry["anchor_target_hex"]


def test_subsidy_values():
    vectors = json.loads((VECTORS_DIR / "subsidy.json").read_text(encoding="utf-8"))
    for entry in vectors:
        assert block_subsidy(entry["height"]) == int(entry["subsidy"])


def test_addresses_match_pubkey():
    vectors = json.loads((VECTORS_DIR / "addresses.json").read_text(encoding="utf-8"))
    pubkey = bytes.fromhex(vectors["pubkey"])
    assert pubkey_to_address(pubkey, NETWORK_MAIN) == vectors["mainnet"]
    assert pubkey_to_address(pubkey, NETWORK_TEST) == vectors["testnet"]

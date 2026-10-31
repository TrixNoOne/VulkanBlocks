"""Test del genesis riproducibile e dei checkpoint."""

import json
from dataclasses import replace

import pytest

from core.block import Block, merkle_root
from core.genesis import (
    CHECKPOINTS_PATH,
    GENESIS_HEIGHT,
    GENESIS_PREV_HASH,
    OP_RETURN,
    Checkpoint,
    CheckpointError,
    GenesisError,
    genesis_anchor,
    genesis_block,
    genesis_script_pubkey,
    genesis_script_sig,
    load_checkpoints,
    verify_genesis,
    verify_startup,
)
from core.params import (
    GENESIS_HASH_MAIN,
    GENESIS_HASH_TEST,
    GENESIS_MESSAGE_MAIN,
    GENESIS_MESSAGE_TEST,
    GENESIS_NONCE_MAIN,
    GENESIS_NONCE_TEST,
    GENESIS_OUTPUT_VALUE,
    GENESIS_POW_LIMIT,
    GENESIS_TIMESTAMP,
    NETWORK_MAIN,
    NETWORK_TEST,
)
from core.tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    decode_coinbase_height,
)

NETWORKS = (NETWORK_MAIN, NETWORK_TEST)


def write_checkpoints(tmp_path, data) -> object:
    path = tmp_path / "checkpoints.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("network", NETWORKS)
def test_genesis_is_valid(network):
    block = verify_genesis(network)
    assert block.height == GENESIS_HEIGHT
    assert block.header.version == 1
    assert block.header.prev_hash == GENESIS_PREV_HASH
    assert block.header.timestamp == GENESIS_TIMESTAMP
    assert block.header.target == GENESIS_POW_LIMIT
    assert block.header.meets_target
    assert block.header.check_pow() is None

    assert len(block.transactions) == 1
    coinbase = block.transactions[0]
    assert coinbase.is_coinbase
    assert coinbase.inputs[0].prev_txid == NULL_TXID
    assert coinbase.inputs[0].prev_index == COINBASE_INDEX
    assert decode_coinbase_height(coinbase.inputs[0].script_sig) == 0

    assert len(coinbase.outputs) == 1
    assert coinbase.outputs[0].value == GENESIS_OUTPUT_VALUE == 0
    assert coinbase.outputs[0].script_pubkey[0] == OP_RETURN
    assert coinbase.outputs[0].script_pubkey == genesis_script_pubkey(network)
    assert sum(txout.value for txout in coinbase.outputs) == 0

    # Nessuna allocazione: l'unico output vale zero ed e' OP_RETURN.
    assert coinbase.outputs[0].value == 0
    assert coinbase.outputs[0].script_pubkey.startswith(bytes((OP_RETURN,)))


@pytest.mark.parametrize("network", NETWORKS)
def test_genesis_is_reproducible(network):
    block = genesis_block(network)
    again = genesis_block(network)
    assert block == again
    assert block.block_hash == again.block_hash
    assert Block.from_bytes(block.serialize()) == block
    assert verify_genesis(network, block=block) == block


def test_genesis_messages_heights_and_hashes():
    main = genesis_block(NETWORK_MAIN)
    test = genesis_block(NETWORK_TEST)
    assert main.block_hash == GENESIS_HASH_MAIN
    assert test.block_hash == GENESIS_HASH_TEST
    assert main.block_hash != test.block_hash
    assert GENESIS_MESSAGE_MAIN in main.transactions[0].inputs[0].script_sig
    assert GENESIS_MESSAGE_TEST in test.transactions[0].inputs[0].script_sig
    assert GENESIS_MESSAGE_MAIN not in test.transactions[0].inputs[0].script_sig
    assert main.transactions[0].outputs[0].script_pubkey != (
        test.transactions[0].outputs[0].script_pubkey
    )
    assert genesis_script_sig(NETWORK_MAIN).startswith(b"\x00\x00")
    assert genesis_script_sig(NETWORK_TEST).startswith(b"\x00\x00")


def test_genesis_anchor_matches_the_block():
    for network in NETWORKS:
        block = genesis_block(network)
        anchor = genesis_anchor(network)
        assert anchor.height == block.height == 0
        assert anchor.timestamp == block.header.timestamp
        assert anchor.target == block.header.target


def test_unknown_network_rejected():
    with pytest.raises(GenesisError):
        genesis_block(b"vulcan-other")
    with pytest.raises(GenesisError):
        verify_genesis(b"vulcan-other")


@pytest.mark.parametrize("network", NETWORKS)
def test_altered_genesis_is_rejected(network):
    block = genesis_block(network)

    wrong_timestamp = Block(
        replace(block.header, timestamp=block.header.timestamp + 1),
        block.transactions,
    )
    with pytest.raises(GenesisError, match="timestamp"):
        verify_genesis(network, block=wrong_timestamp)

    wrong_version = Block(replace(block.header, version=2), block.transactions)
    with pytest.raises(GenesisError, match="version"):
        verify_genesis(network, block=wrong_version)

    wrong_target = Block(
        replace(block.header, target=block.header.target + 1),
        block.transactions,
    )
    with pytest.raises(GenesisError, match="target"):
        verify_genesis(network, block=wrong_target)

    wrong_prev = Block(replace(block.header, prev_hash=b"\x01" * 64), block.transactions)
    with pytest.raises(GenesisError, match="prev_hash"):
        verify_genesis(network, block=wrong_prev)


@pytest.mark.parametrize("network", NETWORKS)
def test_altered_genesis_coinbase_is_rejected(network):
    block = genesis_block(network)
    bad_coinbase = Transaction(
        block.transactions[0].version,
        (TxIn(NULL_TXID, COINBASE_INDEX, genesis_script_sig(network)),),
        (TxOut(1, genesis_script_pubkey(network)),),
    )
    header = replace(block.header, merkle_root=merkle_root([bad_coinbase.txid()]))
    bad = Block(header, (bad_coinbase,))
    with pytest.raises(GenesisError, match="coinbase"):
        verify_genesis(network, block=bad)


@pytest.mark.parametrize("network", NETWORKS)
def test_bad_pow_nonce_is_rejected(network):
    nonce = GENESIS_NONCE_MAIN if network == NETWORK_MAIN else GENESIS_NONCE_TEST
    block = genesis_block(network, nonce=nonce + 1)
    with pytest.raises(GenesisError):
        verify_genesis(network, block=block)


def test_wrong_hardcoded_genesis_hash_is_rejected(monkeypatch):
    import core.genesis as genesis

    monkeypatch.setattr(genesis, "GENESIS_HASH_MAIN", b"\x11" * 64)
    with pytest.raises(GenesisError, match="hash"):
        verify_genesis(NETWORK_MAIN)


def test_empty_checkpoints_include_genesis(tmp_path):
    path = write_checkpoints(tmp_path, [])
    checkpoints = load_checkpoints(path, network=NETWORK_MAIN)
    assert checkpoints == (Checkpoint(0, GENESIS_HASH_MAIN),)


def test_checkpoints_are_loaded_and_sorted(tmp_path):
    second = b"\x22" * 64
    path = write_checkpoints(
        tmp_path,
        [
            {"height": 0, "hash": GENESIS_HASH_MAIN.hex()},
            {"height": 10, "hash": second.hex()},
            {"height": 200, "hash": ("ab" * 64)},
        ],
    )
    checkpoints = load_checkpoints(path, network=NETWORK_MAIN)
    assert [checkpoint.height for checkpoint in checkpoints] == [0, 10, 200]
    assert checkpoints[0].hash == GENESIS_HASH_MAIN
    assert checkpoints[1].hash == second


def test_missing_genesis_checkpoint_is_prepended(tmp_path):
    path = write_checkpoints(tmp_path, [{"height": 5, "hash": "ab" * 64}])
    checkpoints = load_checkpoints(path, network=NETWORK_TEST)
    assert checkpoints[0] == Checkpoint(0, GENESIS_HASH_TEST)
    assert checkpoints[1].height == 5


def test_wrong_genesis_checkpoint_hash_is_rejected(tmp_path):
    path = write_checkpoints(tmp_path, [{"height": 0, "hash": "11" * 64}])
    with pytest.raises(CheckpointError, match="checkpoint 0"):
        load_checkpoints(path, network=NETWORK_MAIN)


@pytest.mark.parametrize(
    "data",
    [
        [{"height": 10, "hash": "ab" * 64}, {"height": 5, "hash": "cd" * 64}],
        [{"height": 5, "hash": "ab" * 64}, {"height": 5, "hash": "cd" * 64}],
        [{"height": -1, "hash": "ab" * 64}],
        [{"height": 2**32, "hash": "ab" * 64}],
        [{"height": True, "hash": "ab" * 64}],
        [{"height": "1", "hash": "ab" * 64}],
        [{"height": 1, "hash": "ab"}],
        [{"height": 1, "hash": "zz" * 64}],
        [{"height": 1, "hash": "ab" * 64, "extra": 1}],
        [{"height": 1}],
        [1],
        {"height": 1, "hash": "ab" * 64},
    ],
)
def test_malformed_checkpoints_are_rejected(tmp_path, data):
    path = write_checkpoints(tmp_path, data)
    with pytest.raises(CheckpointError):
        load_checkpoints(path)


def test_invalid_checkpoint_json_is_rejected(tmp_path):
    path = tmp_path / "checkpoints.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(CheckpointError):
        load_checkpoints(path)


def test_default_checkpoints_file_is_empty_and_loads_genesis():
    assert CHECKPOINTS_PATH.name == "checkpoints.json"
    assert json.loads(CHECKPOINTS_PATH.read_text(encoding="utf-8")) == []
    assert load_checkpoints() == (Checkpoint(0, GENESIS_HASH_MAIN),)


def test_verify_startup_checks_genesis_and_checkpoints():
    genesis, checkpoints = verify_startup(NETWORK_MAIN)
    assert genesis.block_hash == GENESIS_HASH_MAIN
    assert checkpoints[0] == Checkpoint(0, GENESIS_HASH_MAIN)

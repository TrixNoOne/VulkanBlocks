"""Genesis e checkpoint di Vulcan: blocchi fissi e riproducibili.

Il genesis non distribuisce nulla: la coinbase ha un solo output di valore 0
con script OP_RETURN, e il ``script_sig`` contiene l'altezza 0 e un messaggio
fisso. Non esistono chiavi amministrative ne' premine.

Mainnet e testnet hanno messaggi (e quindi hash) diversi; il tag di rete
distingue le due catene anche nel sighash.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .block import Block, BlockHeader, BlockValidationError, merkle_root
from .difficulty import ASERTAnchor
from .params import (
    GENESIS_HASH_MAIN,
    GENESIS_HASH_TEST,
    GENESIS_MESSAGE_MAIN,
    GENESIS_MESSAGE_TEST,
    GENESIS_NONCE_MAIN,
    GENESIS_NONCE_TEST,
    GENESIS_OUTPUT_VALUE,
    GENESIS_POW_LIMIT,
    GENESIS_TIMESTAMP,
    GENESIS_VERSION,
    NETWORK_MAIN,
    NETWORK_TEST,
    NETWORK_TAGS,
)
from .script import push_data
from .tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    TxValidationError,
    encode_coinbase_height,
)

OP_RETURN = 0x6A
GENESIS_HEIGHT = 0
GENESIS_PREV_HASH = b"\x00" * 64

CHECKPOINTS_PATH = Path(__file__).resolve().parent.parent.parent / "checkpoints.json"

_HEX_HASH = re.compile(r"^[0-9a-fA-F]{128}$")

UINT32_MAX = 0xFFFFFFFF


class GenesisError(ValueError):
    """Genesis non conforme alle costanti di consenso."""


class CheckpointError(ValueError):
    """File dei checkpoint malformato o incoerente."""


@dataclass(frozen=True, slots=True)
class Checkpoint:
    height: int
    hash: bytes


def _network_values(network: bytes) -> tuple[bytes, int, bytes]:
    if network == NETWORK_MAIN:
        return GENESIS_MESSAGE_MAIN, GENESIS_NONCE_MAIN, GENESIS_HASH_MAIN
    if network == NETWORK_TEST:
        return GENESIS_MESSAGE_TEST, GENESIS_NONCE_TEST, GENESIS_HASH_TEST
    raise GenesisError("unknown network tag")


def _check_network(network: bytes) -> bytes:
    raw = bytes(network)
    if raw not in NETWORK_TAGS:
        raise GenesisError("unknown network tag")
    return raw


def genesis_script_sig(network: bytes) -> bytes:
    """Altezza 0 (stile BIP34) seguita dal messaggio fisso della rete."""
    message, _, _ = _network_values(_check_network(network))
    return encode_coinbase_height(GENESIS_HEIGHT) + message


def genesis_script_pubkey(network: bytes) -> bytes:
    """Script non spendibile: OP_RETURN con il tag di rete."""
    tag = _check_network(network)
    return bytes((OP_RETURN,)) + push_data(tag)


def genesis_coinbase(network: bytes = NETWORK_MAIN) -> Transaction:
    return Transaction(
        GENESIS_VERSION,
        (TxIn(NULL_TXID, COINBASE_INDEX, genesis_script_sig(network)),),
        (TxOut(GENESIS_OUTPUT_VALUE, genesis_script_pubkey(network)),),
    )


def genesis_header(network: bytes = NETWORK_MAIN, *, nonce: int | None = None) -> BlockHeader:
    _check_network(network)
    if nonce is None:
        _, default_nonce, _ = _network_values(network)
        nonce = default_nonce
    coinbase = genesis_coinbase(network)
    return BlockHeader(
        version=GENESIS_VERSION,
        height=GENESIS_HEIGHT,
        prev_hash=GENESIS_PREV_HASH,
        merkle_root=merkle_root([coinbase.txid()]),
        timestamp=GENESIS_TIMESTAMP,
        target=GENESIS_POW_LIMIT,
        nonce=nonce,
    )


def genesis_block(network: bytes = NETWORK_MAIN, *, nonce: int | None = None) -> Block:
    """Ricostruisce il genesis dai parametri; il nonce puo' essere esplicito."""
    return Block(genesis_header(network, nonce=nonce), (genesis_coinbase(network),))


def genesis_anchor(network: bytes = NETWORK_MAIN) -> ASERTAnchor:
    _check_network(network)
    return ASERTAnchor(GENESIS_HEIGHT, GENESIS_TIMESTAMP, GENESIS_POW_LIMIT)


def verify_genesis(
    network: bytes = NETWORK_MAIN,
    *,
    block: Block | None = None,
) -> Block:
    """Verifica hash, merkle, PoW e contenuto del genesis; ritorna il blocco.

    Senza ``block`` ricostruisce il genesis dalle costanti. Con ``block``
    controlla anche che coincida esattamente con quello atteso.
    """
    network = _check_network(network)
    _, nonce, expected_hash = _network_values(network)
    expected = genesis_block(network, nonce=nonce)
    candidate = expected if block is None else block

    if not isinstance(candidate, Block):
        raise GenesisError("genesis must be a Block")
    if candidate.height != GENESIS_HEIGHT:
        raise GenesisError("genesis height must be 0")
    if candidate.header.version != GENESIS_VERSION:
        raise GenesisError("genesis version mismatch")
    if candidate.header.prev_hash != GENESIS_PREV_HASH:
        raise GenesisError("genesis prev_hash must be zero")
    if candidate.header.timestamp != GENESIS_TIMESTAMP:
        raise GenesisError("genesis timestamp mismatch")
    if candidate.header.target != GENESIS_POW_LIMIT:
        raise GenesisError("genesis target mismatch")
    if len(candidate.transactions) != 1:
        raise GenesisError("genesis must contain exactly one transaction")

    try:
        candidate.validate_structure()
    except (BlockValidationError, TxValidationError) as exc:
        raise GenesisError(str(exc)) from exc

    expected_coinbase = expected.transactions[0]
    coinbase = candidate.transactions[0]
    if coinbase != expected_coinbase:
        raise GenesisError("genesis coinbase mismatch")

    try:
        candidate.header.check_pow()
    except BlockValidationError as exc:
        raise GenesisError(str(exc)) from exc

    if (
        len(candidate.txids()) != 1
        or candidate.compute_merkle_root() != candidate.header.merkle_root
    ):
        raise GenesisError("genesis merkle root mismatch")

    if len(expected_hash) != 64:
        raise GenesisError("GENESIS_HASH must be 32 bytes")
    if candidate.block_hash != expected_hash:
        raise GenesisError("genesis hash mismatch")
    if candidate.block_hash != expected.block_hash:
        raise GenesisError("genesis is not reproducible")
    return candidate


def verify_startup(
    network: bytes = NETWORK_MAIN,
    *,
    checkpoints_path: str | Path = CHECKPOINTS_PATH,
) -> tuple[Block, tuple[Checkpoint, ...]]:
    """Controllo di avvio: genesis valido e checkpoint caricati."""
    genesis = verify_genesis(network)
    return genesis, load_checkpoints(checkpoints_path, network=network)


def load_checkpoints(
    path: str | Path = CHECKPOINTS_PATH,
    *,
    network: bytes = NETWORK_MAIN,
) -> tuple[Checkpoint, ...]:
    """Carica e valida ``checkpoints.json``.

    Formato: ``[{"height": <int>, "hash": "<128 hex>"}, ...]`` ordinato per
    altezza strettamente crescente. Il genesis (altezza 0) e' sempre il primo
    checkpoint: se manca nel file viene aggiunto, se c'e' deve corrispondere.
    """
    network = _check_network(network)
    _, _, genesis_hash = _network_values(network)
    raw = Path(path).read_text(encoding="utf-8")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CheckpointError(f"invalid checkpoint JSON: {exc}") from exc
    if not isinstance(data, list):
        raise CheckpointError("checkpoints must be a JSON list")

    checkpoints: list[Checkpoint] = []
    last_height = -1
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise CheckpointError(f"checkpoint {index} must be an object")
        if set(item) != {"height", "hash"}:
            raise CheckpointError(
                f"checkpoint {index} must have exactly 'height' and 'hash'"
            )
        height = item["height"]
        if not isinstance(height, int) or isinstance(height, bool):
            raise CheckpointError(f"checkpoint {index} height must be an int")
        if height < 0 or height > UINT32_MAX:
            raise CheckpointError(f"checkpoint {index} height out of range")
        if height <= last_height:
            raise CheckpointError("checkpoints must be strictly increasing")
        last_height = height

        encoded = item["hash"]
        if not isinstance(encoded, str) or not _HEX_HASH.match(encoded):
            raise CheckpointError(f"checkpoint {index} hash must be 128 hex chars")
        digest = bytes.fromhex(encoded)
        if height == GENESIS_HEIGHT and digest != genesis_hash:
            raise CheckpointError("checkpoint 0 hash does not match genesis")
        checkpoints.append(Checkpoint(height, digest))

    if not checkpoints or checkpoints[0].height != GENESIS_HEIGHT:
        checkpoints.insert(0, Checkpoint(GENESIS_HEIGHT, genesis_hash))
    return tuple(checkpoints)

"""Catena Vulcan: validazione, connessione, fork choice e reorg.

La catena attiva e' sempre l'unica con UTXO e undo nel database. I blocchi dei
rami laterali restano nella tabella ``blocks`` con stato ``valid``; quando un
ramo diventa piu' pesante, i blocchi attivi vengono disconnessi usando l'undo
fino all'antenato comune e il nuovo ramo viene riconnesso e rivalidato.

Nessuna funzione legge l'orologio: ``now`` e' sempre un parametro esplicito.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from functools import lru_cache
from typing import Any, Iterable, Mapping, Sequence

from .block import (
    Block,
    BlockHeader,
    BlockValidationError,
    TimestampError,
    median_time_past,
    merkle_root,
    validate_timestamp,
)
from .difficulty import ASERTAnchor, DifficultyError, asert_target
from .genesis import (
    Checkpoint,
    genesis_anchor,
    genesis_block,
    load_checkpoints,
    verify_genesis,
)
from .params import (
    BLOCK_SUBSIDY,
    COINBASE_MATURITY,
    GENESIS_TIMESTAMP,
    GENESIS_VERSION,
    HALVING_INTERVAL,
    LOCKTIME_THRESHOLD,
    MAX_BLOCK_SCRIPT_OPS,
    MAX_BLOCK_SIZE,
    MAX_COINBASE_SCRIPT_SIG,
    MAX_FUTURE_DRIFT,
    MAX_MONEY,
    MAX_TARGET,
    MIN_TARGET,
    MTP_WINDOW,
    NETWORK_MAIN,
    NETWORK_TAGS,
    NETWORK_TEST,
    block_subsidy,
)
from .script import ScriptError, _is_push_opcode, _parse_script, verify_script
from .storage import ACTIVE, INVALID, VALID, BlockRow, Storage, UTXO
from .tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    TxValidationError,
    decode_coinbase_height,
    encode_coinbase_height,
)

UINT32_MAX = 0xFFFFFFFF


class ChainError(ValueError):
    """Errore di configurazione o di stato interno della catena."""


class TxInputError(ValueError):
    """Transazione non spendibile contro la vista UTXO fornita."""


class ChainStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    ORPHAN = "ORPHAN"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"


@dataclass(frozen=True, slots=True)
class AcceptResult:
    status: ChainStatus
    reason: str = ""
    block_hash: bytes | None = None
    tip: bytes | None = None

    @property
    def accepted(self) -> bool:
        return self.status is ChainStatus.ACCEPTED


@dataclass(frozen=True, slots=True)
class ChainParams:
    """Parametri di consenso di una rete; immutabili a runtime."""

    genesis: Block
    pow_limit: int
    subsidy: int
    coinbase_maturity: int
    network_tag: bytes
    anchor: ASERTAnchor
    halving_interval: int = HALVING_INTERVAL
    checkpoints: tuple[Checkpoint, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.genesis, Block):
            raise ChainError("genesis must be a Block")
        if self.genesis.height != 0:
            raise ChainError("genesis height must be 0")
        if self.genesis.header.prev_hash != b"\x00" * 64:
            raise ChainError("genesis prev_hash must be zero")
        try:
            self.genesis.validate_structure()
            self.genesis.header.check_pow()
        except (BlockValidationError, TxValidationError) as exc:
            raise ChainError(f"invalid genesis: {exc}") from exc

        if not isinstance(self.pow_limit, int) or isinstance(self.pow_limit, bool):
            raise ChainError("pow_limit must be an int")
        if not MIN_TARGET <= self.pow_limit <= MAX_TARGET:
            raise ChainError("pow_limit out of range")
        if self.genesis.header.target > self.pow_limit:
            raise ChainError("genesis target above pow_limit")

        if not isinstance(self.anchor, ASERTAnchor):
            raise ChainError("anchor must be an ASERTAnchor")
        if self.anchor.height != 0:
            raise ChainError("anchor must be genesis")
        if self.anchor.timestamp != self.genesis.header.timestamp:
            raise ChainError("anchor timestamp does not match genesis")
        if self.anchor.target != self.genesis.header.target:
            raise ChainError("anchor target does not match genesis")

        if not isinstance(self.subsidy, int) or isinstance(self.subsidy, bool):
            raise ChainError("subsidy must be an int")
        if not 0 <= self.subsidy <= MAX_MONEY:
            raise ChainError("subsidy out of range")
        if not isinstance(self.coinbase_maturity, int) or isinstance(
            self.coinbase_maturity, bool
        ):
            raise ChainError("coinbase_maturity must be an int")
        if self.coinbase_maturity < 1:
            raise ChainError("coinbase_maturity must be positive")
        if (
            not isinstance(self.halving_interval, int)
            or isinstance(self.halving_interval, bool)
        ):
            raise ChainError("halving_interval must be an int")
        if self.halving_interval < 1:
            raise ChainError("halving_interval must be positive")
        if bytes(self.network_tag) not in NETWORK_TAGS:
            raise ChainError("unknown network tag")
        object.__setattr__(self, "network_tag", bytes(self.network_tag))

        checkpoints = tuple(self.checkpoints)
        if not checkpoints or checkpoints[0].height != 0:
            checkpoints = (Checkpoint(0, self.genesis.block_hash),) + checkpoints
        if checkpoints[0].hash != self.genesis.block_hash:
            raise ChainError("checkpoint 0 does not match genesis")
        last = -1
        for checkpoint in checkpoints:
            if not isinstance(checkpoint, Checkpoint):
                raise ChainError("checkpoints must be Checkpoint")
            if checkpoint.height <= last:
                raise ChainError("checkpoints must be strictly increasing")
            if len(checkpoint.hash) != 64:
                raise ChainError("checkpoint hash must be 64 bytes")
            last = checkpoint.height
        object.__setattr__(self, "checkpoints", checkpoints)

    @classmethod
    def mainnet(cls) -> "ChainParams":
        genesis = verify_genesis(NETWORK_MAIN)
        return cls(
            genesis=genesis,
            pow_limit=genesis.header.target,
            subsidy=BLOCK_SUBSIDY,
            coinbase_maturity=COINBASE_MATURITY,
            network_tag=NETWORK_MAIN,
            anchor=genesis_anchor(NETWORK_MAIN),
            halving_interval=HALVING_INTERVAL,
            checkpoints=load_checkpoints(network=NETWORK_MAIN),
        )

    @classmethod
    def testnet(cls) -> "ChainParams":
        genesis = verify_genesis(NETWORK_TEST)
        return cls(
            genesis=genesis,
            pow_limit=genesis.header.target,
            subsidy=BLOCK_SUBSIDY,
            coinbase_maturity=COINBASE_MATURITY,
            network_tag=NETWORK_TEST,
            anchor=genesis_anchor(NETWORK_TEST),
            halving_interval=HALVING_INTERVAL,
            checkpoints=load_checkpoints(network=NETWORK_TEST),
        )

    @classmethod
    def regtest(cls, *, halving_interval: int = 10) -> "ChainParams":
        """Rete di test: PoW gratuito, maturita' coinbase 2, halving ogni 10 blocchi."""
        genesis = _regtest_genesis()
        return cls(
            genesis=genesis,
            pow_limit=MAX_TARGET,
            subsidy=BLOCK_SUBSIDY,
            coinbase_maturity=2,
            network_tag=NETWORK_TEST,
            anchor=ASERTAnchor(
                0, genesis.header.timestamp, genesis.header.target
            ),
            halving_interval=halving_interval,
            checkpoints=(Checkpoint(0, genesis.block_hash),),
        )


@lru_cache(maxsize=1)
def _regtest_genesis() -> Block:
    """Genesis regtest deterministico: stesso contenuto del testnet, PoW libero."""
    base = genesis_block(NETWORK_TEST)
    for nonce in range(10_000):
        header = BlockHeader(
            version=GENESIS_VERSION,
            height=0,
            prev_hash=b"\x00" * 64,
            merkle_root=base.header.merkle_root,
            timestamp=GENESIS_TIMESTAMP,
            target=MAX_TARGET,
            nonce=nonce,
        )
        if header.meets_target:
            return Block(header, base.transactions)
    raise ChainError("cannot build regtest genesis")  # pragma: no cover


@dataclass(frozen=True, slots=True)
class _BlockChanges:
    created: tuple[UTXO, ...]
    spent_keys: tuple[tuple[bytes, int], ...]
    restore: tuple[UTXO, ...]
    fees: int
    coinbase_value: int


@dataclass(frozen=True, slots=True)
class _TxProcessing:
    created: tuple[UTXO, ...]
    spent_keys: tuple[tuple[bytes, int], ...]
    restore: tuple[UTXO, ...]
    fees: int
    ops: int


class _InvalidBlock(Exception):
    def __init__(self, reason: str, block_hash: bytes | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.block_hash = block_hash


class _BranchInvalid(Exception):
    def __init__(self, block_hash: bytes, reason: str) -> None:
        super().__init__(reason)
        self.block_hash = block_hash
        self.reason = reason


class _Overlay:
    """Vista UTXO con aggiunte/rimozioni in memoria, per un singolo blocco."""

    def __init__(self, base: Any) -> None:
        self._base = base
        self._added: dict[tuple[bytes, int], UTXO] = {}
        self._removed: set[tuple[bytes, int]] = set()
        self.created_keys: set[tuple[bytes, int]] = set()

    def get_utxo(self, txid: bytes, vout: int) -> UTXO | None:
        key = (bytes(txid), int(vout))
        if key in self._removed:
            return None
        found = self._added.get(key)
        if found is not None:
            return found
        return self._base.get_utxo(key[0], key[1])

    def add(self, utxo: UTXO) -> None:
        key = utxo.outpoint
        self._added[key] = utxo
        self.created_keys.add(key)
        self._removed.discard(key)

    def spend(self, key: tuple[bytes, int]) -> None:
        self._added.pop(key, None)
        self._removed.add(key)


def _lookup_utxo(view: Any, txid: bytes, vout: int) -> UTXO | None:
    getter = getattr(view, "get_utxo", None)
    if callable(getter):
        return getter(txid, vout)
    if isinstance(view, Mapping):
        return view.get((bytes(txid), int(vout)))
    raise TypeError("utxo_view must expose get_utxo() or be a mapping")


def check_tx_inputs(
    tx: Transaction,
    utxo_view: Any,
    height: int,
    *,
    network: bytes = NETWORK_MAIN,
    coinbase_maturity: int = COINBASE_MATURITY,
) -> int:
    """Controlla gli input di una transazione non coinbase.

    Restituisce la somma dei valori degli input. Solleva ``TxInputError`` per
    UTXO mancante, doppia spesa, coinbase immatura, script fallito, importi non
    validi o finalita' non rispettata. Riusabile da mempool e nodo.
    """
    if not isinstance(tx, Transaction):
        raise TxInputError("tx must be a Transaction")
    if not isinstance(height, int) or isinstance(height, bool) or height < 0:
        raise TxInputError("height must be a non-negative int")
    if tx.is_coinbase:
        raise TxInputError("coinbase inputs are not spendable")
    try:
        tx.validate()
    except TxValidationError as exc:
        raise TxInputError(str(exc)) from exc

    # Il locktime Vulcan e' sempre un'altezza: niente timestamp.
    if tx.lock_time >= LOCKTIME_THRESHOLD:
        raise TxInputError("lock_time is not a block height")
    if tx.lock_time > height:
        raise TxInputError("lock_time in the future")
    if tx.lock_time != 0 and all(
        txin.sequence == UINT32_MAX for txin in tx.inputs
    ):
        raise TxInputError("non-final transaction")

    total_in = 0
    for index, txin in enumerate(tx.inputs):
        utxo = _lookup_utxo(utxo_view, txin.prev_txid, txin.prev_index)
        if utxo is None:
            raise TxInputError(
                f"missing utxo {txin.prev_txid.hex()}:{txin.prev_index}"
            )
        if not isinstance(utxo, UTXO):
            raise TxInputError("utxo view returned an invalid record")
        if utxo.value < 0 or utxo.value > MAX_MONEY:
            raise TxInputError("utxo value out of range")
        if utxo.is_coinbase:
            if height - utxo.height < coinbase_maturity:
                raise TxInputError(
                    f"immature coinbase {utxo.txid.hex()}:{utxo.vout}"
                )
        try:
            verify_script(
                tx,
                index,
                script_sig=txin.script_sig,
                script_pubkey=utxo.script,
                network=network,
                block_height=height,
            )
        except ScriptError as exc:
            raise TxInputError(f"script failed: {exc}") from exc
        total_in += utxo.value

    total_out = sum(txout.value for txout in tx.outputs)
    if total_out > MAX_MONEY:
        raise TxInputError("outputs exceed MAX_MONEY")
    if total_in < total_out:
        raise TxInputError("inputs below outputs")
    return total_in


def _script_ops(script: bytes) -> int:
    """Opcode non-push di uno script, contati come nel parser di consenso."""
    try:
        ops = _parse_script(bytes(script))
    except ScriptError as exc:
        raise _InvalidBlock(f"invalid script: {exc}") from exc
    return sum(1 for opcode, _ in ops if not _is_push_opcode(opcode))


def _undo_payload(changes: _BlockChanges) -> dict:
    created = [[utxo.txid.hex(), utxo.vout] for utxo in changes.created]
    restore = [
        [
            utxo.txid.hex(),
            utxo.vout,
            utxo.value,
            utxo.script.hex(),
            utxo.height,
            1 if utxo.is_coinbase else 0,
        ]
        for utxo in changes.restore
    ]
    return {"created": created, "restore": restore}


def _utxo_from_undo(item: Sequence[Any]) -> UTXO:
    txid_hex, vout, value, script_hex, height, is_coinbase = item
    return UTXO(
        txid=bytes.fromhex(txid_hex),
        vout=int(vout),
        value=int(value),
        script=bytes.fromhex(script_hex),
        height=int(height),
        is_coinbase=bool(is_coinbase),
    )


class Chain:
    """Catena attiva con rami laterali persistenti e reorg atomico."""

    def __init__(
        self, params: ChainParams, path: str = ":memory:"
    ) -> None:
        if not isinstance(params, ChainParams):
            raise ChainError("params must be ChainParams")
        self.params = params
        self.storage = Storage(path)
        try:
            self._init_genesis()
        except BaseException:
            self.storage.close()
            raise

    def close(self) -> None:
        self.storage.close()

    def __enter__(self) -> "Chain":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- inizializzazione ---------------------------------------------------

    def _init_genesis(self) -> None:
        genesis = self.params.genesis
        raw = genesis.serialize()
        row = self.storage.get_block(genesis.block_hash)
        if row is None:
            if self.storage.has_blocks():
                raise ChainError("database contains a different genesis")
            with self.storage.transaction():
                self.storage.insert_block(
                    genesis.block_hash,
                    genesis.header.prev_hash,
                    genesis.height,
                    raw,
                    genesis.header.work,
                    ACTIVE,
                    0,
                )
                for vout, txout in enumerate(genesis.transactions[0].outputs):
                    self.storage.put_utxo(
                        UTXO(
                            genesis.transactions[0].txid(),
                            vout,
                            txout.value,
                            txout.script_pubkey,
                            genesis.height,
                            True,
                        )
                    )
            return

        if row.raw != raw or row.height != 0:
            raise ChainError("database contains a different genesis")
        if row.status != ACTIVE:
            raise ChainError("genesis is not active")

    # -- conversione righe --------------------------------------------------

    @staticmethod
    def _row_to_block(row: BlockRow) -> Block:
        try:
            return Block.from_bytes(row.raw)
        except (ValueError, TypeError) as exc:
            raise ChainError(f"corrupt block {row.hash.hex()}") from exc

    def _tip_row(self) -> BlockRow:
        row = self.storage.active_tip()
        if row is None:
            raise ChainError("no active tip")
        return row

    def _ancestor_timestamps(
        self, start: BlockRow, limit: int = MTP_WINDOW
    ) -> list[int]:
        timestamps: list[int] = []
        row: BlockRow | None = start
        seen: set[bytes] = set()
        while row is not None and len(timestamps) < limit:
            if row.hash in seen:
                raise ChainError("block parent cycle")
            seen.add(row.hash)
            timestamps.append(self._row_to_block(row).header.timestamp)
            if row.height == 0:
                break
            row = self.storage.get_block(row.parent)
        timestamps.reverse()
        return timestamps

    def _checkpoint_at(self, height: int) -> Checkpoint | None:
        for checkpoint in self.params.checkpoints:
            if checkpoint.height == height:
                return checkpoint
        return None

    def _last_checkpoint_at_or_below(self, height: int) -> Checkpoint | None:
        found: Checkpoint | None = None
        for checkpoint in self.params.checkpoints:
            if checkpoint.height <= height:
                found = checkpoint
        return found

    def _common_ancestor(self, parent: BlockRow) -> tuple[BlockRow, list[BlockRow]]:
        path: list[BlockRow] = []
        row = parent
        seen: set[bytes] = set()
        while row.status != ACTIVE:
            if row.status == INVALID:
                raise _InvalidBlock("parent branch is invalid", row.hash)
            if row.hash in seen:
                raise ChainError("block parent cycle")
            seen.add(row.hash)
            path.append(row)
            ancestor = self.storage.get_block(row.parent)
            if ancestor is None:
                raise ChainError("broken parent link")
            row = ancestor
        path.reverse()
        return row, path

    # -- accettazione -------------------------------------------------------

    def _result(self, status: ChainStatus, reason: str = "", **kwargs: Any) -> AcceptResult:
        tip = self.storage.active_tip()
        return AcceptResult(
            status=status,
            reason=reason,
            tip=None if tip is None else tip.hash,
            **kwargs,
        )

    def accept_block(self, block: Block, now: int) -> AcceptResult:
        """Valida e, se possibile, connette ``block`` alla catena attiva."""
        if not isinstance(block, Block):
            raise TypeError("block must be a Block")
        if not isinstance(now, int) or isinstance(now, bool) or now < 0:
            raise ChainError("now must be a non-negative int")

        # 1. dimensione, struttura, PoW.
        try:
            raw = block.serialize()
        except (ValueError, TypeError) as exc:
            return self._result(ChainStatus.INVALID, f"serialization: {exc}")
        if len(raw) > MAX_BLOCK_SIZE:
            return self._result(ChainStatus.INVALID, "block exceeds MAX_BLOCK_SIZE")
        try:
            block.validate_structure()
        except (BlockValidationError, TxValidationError) as exc:
            return self._result(ChainStatus.INVALID, str(exc))
        try:
            block.header.check_pow()
        except BlockValidationError as exc:
            return self._result(ChainStatus.INVALID, str(exc))

        existing = self.storage.get_block(block.block_hash)
        if existing is not None:
            if existing.status == INVALID:
                return self._result(
                    ChainStatus.INVALID,
                    "block is known invalid",
                    block_hash=block.block_hash,
                )
            return self._result(
                ChainStatus.DUPLICATE,
                "block already known",
                block_hash=block.block_hash,
            )
        if block.height == 0:
            return self._result(
                ChainStatus.INVALID,
                "genesis already exists",
                block_hash=block.block_hash,
            )

        # 2. parent noto e altezza coerente.
        parent_row = self.storage.get_block(block.header.prev_hash)
        if parent_row is None:
            return self._result(
                ChainStatus.ORPHAN,
                "unknown parent",
                block_hash=block.block_hash,
            )
        if parent_row.status == INVALID:
            return self._result(
                ChainStatus.INVALID,
                "parent is invalid",
                block_hash=block.block_hash,
            )
        if block.height != parent_row.height + 1:
            return self._result(
                ChainStatus.INVALID,
                f"height {block.height} != parent height + 1",
                block_hash=block.block_hash,
            )

        # 3. target ASERT atteso e limite.
        parent_block = self._row_to_block(parent_row)
        try:
            expected_target = asert_target(
                block.height,
                parent_block.header.timestamp,
                self.params.anchor,
                pow_limit=self.params.pow_limit,
            )
        except DifficultyError as exc:
            return self._result(
                ChainStatus.INVALID, str(exc), block_hash=block.block_hash
            )
        if block.header.target != expected_target:
            return self._result(
                ChainStatus.INVALID,
                "target does not match ASERT",
                block_hash=block.block_hash,
            )
        if block.header.target > self.params.pow_limit:
            return self._result(
                ChainStatus.INVALID,
                "target above pow_limit",
                block_hash=block.block_hash,
            )

        # 4. timestamp > MTP(11) e <= now + 2h.
        try:
            past = self._ancestor_timestamps(parent_row, MTP_WINDOW)
            validate_timestamp(block.header.timestamp, past, now)
        except (TimestampError, ValueError) as exc:
            return self._result(
                ChainStatus.INVALID, str(exc), block_hash=block.block_hash
            )

        # 5. altezza coinbase == altezza blocco.
        try:
            coinbase_height = decode_coinbase_height(
                block.transactions[0].inputs[0].script_sig
            )
        except TxValidationError as exc:
            return self._result(
                ChainStatus.INVALID, str(exc), block_hash=block.block_hash
            )
        if coinbase_height != block.height:
            return self._result(
                ChainStatus.INVALID,
                f"coinbase height {coinbase_height} != block height {block.height}",
                block_hash=block.block_hash,
            )

        # 10 (parte locale). Checkpoint esatto.
        checkpoint = self._checkpoint_at(block.height)
        if checkpoint is not None and checkpoint.hash != block.block_hash:
            return self._result(
                ChainStatus.INVALID,
                "checkpoint mismatch",
                block_hash=block.block_hash,
            )

        # Ramo che si stacca sotto l'ultimo checkpoint.
        tip_row = self._tip_row()
        try:
            common, side_path = self._common_ancestor(parent_row)
        except _InvalidBlock as exc:
            return self._result(
                ChainStatus.INVALID, exc.reason, block_hash=block.block_hash
            )
        last_checkpoint = self._last_checkpoint_at_or_below(tip_row.height)
        if last_checkpoint is not None:
            if (
                block.height <= last_checkpoint.height
                and block.block_hash != last_checkpoint.hash
            ):
                return self._result(
                    ChainStatus.INVALID,
                    "fork below last checkpoint",
                    block_hash=block.block_hash,
                )
            if (
                block.height > last_checkpoint.height
                and common.height < last_checkpoint.height
            ):
                return self._result(
                    ChainStatus.INVALID,
                    "fork below last checkpoint",
                    block_hash=block.block_hash,
                )

        coinbase_value = sum(
            txout.value for txout in block.transactions[0].outputs
        )
        cumulative_work = parent_row.cumulative_work + block.header.work
        emitted = parent_row.emitted + coinbase_value
        incoming = BlockRow(
            hash=block.block_hash,
            parent=block.header.prev_hash,
            height=block.height,
            raw=raw,
            cumulative_work=cumulative_work,
            status=VALID,
            emitted=emitted,
        )

        with self.storage.transaction():
            self.storage.insert_block(
                incoming.hash,
                incoming.parent,
                incoming.height,
                incoming.raw,
                incoming.cumulative_work,
                incoming.status,
                incoming.emitted,
            )
            return self._try_branch(
                common=common,
                path=side_path + [incoming],
                old_tip=tip_row,
                now=now,
                incoming_hash=block.block_hash,
            )

    def _try_branch(
        self,
        *,
        common: BlockRow,
        path: list[BlockRow],
        old_tip: BlockRow,
        now: int,
        incoming_hash: bytes,
    ) -> AcceptResult:
        old_rows = self.storage.active_rows_desc()
        to_disconnect = [row for row in old_rows if row.height > common.height]
        connected: list[BlockRow] = []

        try:
            for row in to_disconnect:
                self._disconnect(row)
            for row in path:
                try:
                    self._connect(row, now)
                except _InvalidBlock as exc:
                    raise _BranchInvalid(row.hash, exc.reason) from exc
                connected.append(row)

            new_tip = connected[-1]
            if new_tip.cumulative_work > old_tip.cumulative_work:
                return self._result(
                    ChainStatus.ACCEPTED,
                    "",
                    block_hash=incoming_hash,
                )

            # Ramo valido ma non piu' pesante: si torna alla catena di prima.
            for row in reversed(connected):
                self._disconnect(row)
            for row in reversed(to_disconnect):
                self._connect(row, now)
            return self._result(
                ChainStatus.ACCEPTED,
                "valid side branch",
                block_hash=incoming_hash,
            )
        except _BranchInvalid as exc:
            for row in reversed(connected):
                current = self.storage.get_block(row.hash)
                if current is not None and current.status == ACTIVE:
                    self._disconnect(row)
            self._mark_invalid(exc.block_hash)
            for row in reversed(to_disconnect):
                self._connect(row, now)
            return self._result(
                ChainStatus.INVALID,
                exc.reason,
                block_hash=incoming_hash,
            )

    def _mark_invalid(self, block_hash: bytes) -> None:
        pending = [block_hash]
        seen: set[bytes] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            self.storage.set_status(current, INVALID)
            for child in self.storage.children(current):
                if child.hash not in seen:
                    pending.append(child.hash)

    # -- connessione / disconnessione --------------------------------------

    def _connect(self, row: BlockRow, now: int) -> None:
        block = self._row_to_block(row)
        if block.block_hash != row.hash:
            raise _InvalidBlock("block hash mismatch", row.hash)

        parent_row = self.storage.get_block(block.header.prev_hash)
        if parent_row is None or parent_row.status != ACTIVE:
            raise _InvalidBlock("parent is not active", row.hash)
        if block.height != parent_row.height + 1:
            raise _InvalidBlock("height does not follow parent", row.hash)

        parent_block = self._row_to_block(parent_row)
        try:
            expected_target = asert_target(
                block.height,
                parent_block.header.timestamp,
                self.params.anchor,
                pow_limit=self.params.pow_limit,
            )
        except DifficultyError as exc:
            raise _InvalidBlock(str(exc), row.hash) from exc
        if block.header.target != expected_target:
            raise _InvalidBlock("target does not match ASERT", row.hash)
        if block.header.target > self.params.pow_limit:
            raise _InvalidBlock("target above pow_limit", row.hash)

        try:
            past = self._ancestor_timestamps(parent_row, MTP_WINDOW)
            validate_timestamp(block.header.timestamp, past, now)
        except (TimestampError, ValueError) as exc:
            raise _InvalidBlock(str(exc), row.hash) from exc

        try:
            block.validate_structure()
            block.header.check_pow()
        except (BlockValidationError, TxValidationError) as exc:
            raise _InvalidBlock(str(exc), row.hash) from exc

        checkpoint = self._checkpoint_at(block.height)
        if checkpoint is not None and checkpoint.hash != block.block_hash:
            raise _InvalidBlock("checkpoint mismatch", row.hash)

        changes = self._validate_block_transactions(block)
        allowed = block_subsidy(
            block.height, halving_interval=self.params.halving_interval
        )
        if changes.coinbase_value > allowed + changes.fees:
            raise _InvalidBlock("coinbase exceeds subsidy + fees", row.hash)
        emitted = parent_row.emitted + changes.coinbase_value
        if emitted > MAX_MONEY:
            raise _InvalidBlock("cumulative emission exceeds MAX_MONEY", row.hash)

        for utxo in changes.created:
            self.storage.put_utxo(utxo)
        for txid, vout in changes.spent_keys:
            self.storage.delete_utxo(txid, vout)
        self.storage.save_undo(block.block_hash, _undo_payload(changes))
        self.storage.update_emitted(block.block_hash, emitted)
        self.storage.set_status(block.block_hash, ACTIVE)

    def _disconnect(self, row: BlockRow) -> None:
        data = self.storage.load_undo(row.hash)
        if data is None:
            raise ChainError(f"missing undo for {row.hash.hex()}")
        try:
            for item in data.get("created", []):
                txid_hex, vout = item
                self.storage.delete_utxo(bytes.fromhex(txid_hex), int(vout))
            for item in data.get("restore", []):
                self.storage.put_utxo(_utxo_from_undo(item))
        except (KeyError, TypeError, ValueError) as exc:
            raise ChainError(f"corrupt undo for {row.hash.hex()}") from exc
        self.storage.delete_undo(row.hash)
        self.storage.set_status(row.hash, VALID)

    # -- validazione transazioni -------------------------------------------

    def _validate_block_transactions(self, block: Block) -> _BlockChanges:
        coinbase = block.transactions[0]
        coinbase_value = sum(txout.value for txout in coinbase.outputs)
        if coinbase_value > MAX_MONEY:
            raise _InvalidBlock("coinbase exceeds MAX_MONEY", block.block_hash)

        overlay = _Overlay(self.storage)
        created: list[UTXO] = []
        for vout, txout in enumerate(coinbase.outputs):
            utxo = UTXO(
                coinbase.txid(),
                vout,
                txout.value,
                txout.script_pubkey,
                block.height,
                True,
            )
            overlay.add(utxo)
            created.append(utxo)

        processed = self._process_regular_txs(
            block.transactions[1:], overlay, block.height
        )
        return _BlockChanges(
            created=tuple(created) + processed.created,
            spent_keys=processed.spent_keys,
            restore=processed.restore,
            fees=processed.fees,
            coinbase_value=coinbase_value,
        )

    def _process_regular_txs(
        self,
        txs: Iterable[Transaction],
        overlay: _Overlay,
        height: int,
    ) -> _TxProcessing:
        fees = 0
        ops = 0
        created: list[UTXO] = []
        spent_keys: list[tuple[bytes, int]] = []
        restore: list[UTXO] = []

        for tx in txs:
            try:
                total_in = check_tx_inputs(
                    tx,
                    overlay,
                    height,
                    network=self.params.network_tag,
                    coinbase_maturity=self.params.coinbase_maturity,
                )
            except TxInputError as exc:
                raise _InvalidBlock(str(exc)) from exc
            total_out = sum(txout.value for txout in tx.outputs)
            fees += total_in - total_out

            for txin in tx.inputs:
                utxo = overlay.get_utxo(txin.prev_txid, txin.prev_index)
                if utxo is None:  # pragma: no cover - check_tx_inputs lo esclude
                    raise _InvalidBlock("missing utxo")
                ops += _script_ops(txin.script_sig)
                ops += _script_ops(utxo.script)
                if ops > MAX_BLOCK_SCRIPT_OPS:
                    raise _InvalidBlock("block script ops limit exceeded")

            for txin in tx.inputs:
                key = (bytes(txin.prev_txid), int(txin.prev_index))
                utxo = overlay.get_utxo(*key)
                if utxo is None:  # pragma: no cover
                    raise _InvalidBlock("missing utxo")
                overlay.spend(key)
                spent_keys.append(key)
                if key not in overlay.created_keys:
                    restore.append(utxo)

            txid = tx.txid()
            for vout, txout in enumerate(tx.outputs):
                utxo = UTXO(
                    txid,
                    vout,
                    txout.value,
                    txout.script_pubkey,
                    height,
                    False,
                )
                overlay.add(utxo)
                created.append(utxo)

        return _TxProcessing(
            created=tuple(created),
            spent_keys=tuple(spent_keys),
            restore=tuple(restore),
            fees=fees,
            ops=ops,
        )

    # -- letture ------------------------------------------------------------

    def tip(self) -> Block:
        return self._row_to_block(self._tip_row())

    def get_block(self, block_hash: bytes) -> Block | None:
        row = self.storage.get_block(block_hash)
        return None if row is None else self._row_to_block(row)

    def get_block_by_height(self, height: int) -> Block | None:
        row = self.storage.get_active_block_by_height(height)
        return None if row is None else self._row_to_block(row)

    def get_utxo(self, txid: bytes, index: int) -> UTXO | None:
        return self.storage.get_utxo(txid, index)

    def balance_of(self, script: bytes) -> int:
        return self.storage.balance_of(script)

    def utxo_set_hash(self) -> bytes:
        return self.storage.utxo_set_hash()

    def tip_mtp(self) -> int:
        row = self._tip_row()
        return median_time_past(self._ancestor_timestamps(row, MTP_WINDOW))

    def locator(self) -> list[bytes]:
        """Locator stile Bitcoin: tip, poi distanze esponenziali, genesis."""
        tip = self._tip_row()
        hashes = [tip.hash]
        height = tip.height - 1
        step = 1
        while height > 0:
            row = self.storage.get_active_block_by_height(height)
            if row is not None:
                hashes.append(row.hash)
            step *= 2
            height -= step
        genesis = self.storage.get_active_block_by_height(0)
        if genesis is not None and hashes[-1] != genesis.hash:
            hashes.append(genesis.hash)
        return hashes

    # -- template -----------------------------------------------------------

    def build_template(
        self,
        coinbase_script: bytes,
        txs: Sequence[Transaction],
        now: int,
    ) -> Block:
        """Header e coinbase pronti per il miner, con target e fee correnti."""
        if not isinstance(now, int) or isinstance(now, bool) or now < 0:
            raise ChainError("now must be a non-negative int")
        if not isinstance(coinbase_script, (bytes, bytearray, memoryview)):
            raise ChainError("coinbase_script must be bytes")
        payout_script = bytes(coinbase_script)
        if len(payout_script) > 10_000:
            raise ChainError("coinbase_script too large")
        txs = tuple(txs)
        if any(not isinstance(tx, Transaction) for tx in txs):
            raise ChainError("txs must be Transactions")
        if any(tx.is_coinbase for tx in txs):
            raise ChainError("coinbase transaction not allowed in template")

        tip_row = self._tip_row()
        tip_block = self._row_to_block(tip_row)
        height = tip_row.height + 1
        try:
            target = asert_target(
                height,
                tip_block.header.timestamp,
                self.params.anchor,
                pow_limit=self.params.pow_limit,
            )
        except DifficultyError as exc:
            raise ChainError(str(exc)) from exc

        mtp = median_time_past(self._ancestor_timestamps(tip_row, MTP_WINDOW))
        timestamp = max(now, mtp + 1)
        if timestamp > now + MAX_FUTURE_DRIFT:
            raise ChainError("no valid timestamp for template")

        overlay = _Overlay(self.storage)
        try:
            processed = self._process_regular_txs(txs, overlay, height)
        except _InvalidBlock as exc:
            raise ChainError(exc.reason) from exc
        if processed.ops > MAX_BLOCK_SCRIPT_OPS:
            raise ChainError("block script ops limit exceeded")

        coinbase_value = block_subsidy(
            height, halving_interval=self.params.halving_interval
        ) + processed.fees
        if coinbase_value > MAX_MONEY:
            raise ChainError("coinbase value exceeds MAX_MONEY")
        script_sig = encode_coinbase_height(height)
        if len(script_sig) > MAX_COINBASE_SCRIPT_SIG:
            raise ChainError("coinbase script_sig too long")
        coinbase = Transaction(
            version=1,
            inputs=(TxIn(NULL_TXID, COINBASE_INDEX, script_sig),),
            outputs=(TxOut(coinbase_value, payout_script),),
        )

        transactions = (coinbase,) + txs
        header = BlockHeader(
            version=1,
            height=height,
            prev_hash=tip_row.hash,
            merkle_root=merkle_root([tx.txid() for tx in transactions]),
            timestamp=timestamp,
            target=target,
            nonce=0,
        )
        return Block(header, transactions)

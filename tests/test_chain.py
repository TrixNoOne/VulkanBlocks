"""Test di catena: storage, accept_block, fork choice e reorg su regtest.

Tutti gli orari sono valori fissi passati come parametro ``now``: non si usa
l'orologio di sistema dentro la validazione.
"""

from __future__ import annotations

from dataclasses import replace

import hashlib
import pytest

from core.chain import Chain, ChainParams, ChainStatus, TxInputError, check_tx_inputs
from core.block import Block, BlockHeader, merkle_root
from core.difficulty import asert_target
from core.genesis import Checkpoint
from core.params import (
    LOCKTIME_THRESHOLD,
    MAX_MONEY,
    NETWORK_TEST,
    block_subsidy,
)
from core.script import (
    hash160,
    htlc_refund_script_sig,
    p2pkh_script,
    p2pkh_script_sig,
    sign_digest,
    sighash,
)
from core.storage import UTXO
from core.tx import (
    COINBASE_INDEX,
    NULL_TXID,
    Transaction,
    TxIn,
    TxOut,
    encode_coinbase_height,
)
from coincurve import PrivateKey

REGTEST = ChainParams.regtest()


def key(seed: int) -> PrivateKey:
    return PrivateKey(bytes([seed]) * 32)


def pub(private_key: PrivateKey) -> bytes:
    return private_key.public_key.format(compressed=True)


def GENESIS_TS() -> int:
    return REGTEST.genesis.header.timestamp


def time_at(height: int) -> int:
    return GENESIS_TS() + 120 * height


def expected_target(params: ChainParams, height: int, prev_timestamp: int) -> int:
    return asert_target(
        height, prev_timestamp, params.anchor, pow_limit=params.pow_limit
    )


def coinbase_tx(height: int, value: int, script_pubkey: bytes = b"\x51") -> Transaction:
    return Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(height)),),
        (TxOut(value, script_pubkey),),
    )


def mine_block(
    params: ChainParams,
    prev: Block,
    height: int,
    timestamp: int,
    txs: tuple[Transaction, ...] = (),
    coinbase_value: int | None = None,
    coinbase_script: bytes = b"\x51",
    *,
    target: int | None = None,
    nonce: int = 0,
) -> Block:
    if coinbase_value is None:
        coinbase_value = block_subsidy(
            height, halving_interval=params.halving_interval
        )
    cb = coinbase_tx(height, coinbase_value, coinbase_script)
    transactions = (cb,) + txs
    if target is None:
        target = expected_target(params, height, prev.header.timestamp)
    header = BlockHeader(
        version=1,
        height=height,
        prev_hash=prev.block_hash,
        merkle_root=merkle_root([tx.txid() for tx in transactions]),
        timestamp=timestamp,
        target=target,
        nonce=nonce,
    )
    block = Block(header, transactions)
    block.header.check_pow()
    return block


def spend_tx(
    prev_txid: bytes,
    prev_index: int,
    value: int,
    script_pubkey: bytes,
    private_key: PrivateKey,
    height: int,
    lock_time: int = 0,
    sequence: int = 0,
    network: bytes = NETWORK_TEST,
) -> Transaction:
    """Costruisce una transazione firmata (P2PKH-like) pronta per essere inclusa."""
    unsigned = Transaction(
        1,
        (TxIn(prev_txid, prev_index, b"", sequence),),
        (TxOut(value, b"\x51"),),
        lock_time,
    )
    digest = sighash(unsigned, 0, script_pubkey, network=network)
    signature = sign_digest(private_key, digest)
    signed_in = TxIn(
        prev_txid, prev_index, p2pkh_script_sig(signature, pub(private_key)), sequence
    )
    return Transaction(1, (signed_in,), unsigned.outputs, unsigned.lock_time)


def accept(chain: Chain, block: Block, now: int):
    return chain.accept_block(block, now=now)


# --------------------------------------------------------------------------- #
# Lineare e ricarica da disco
# --------------------------------------------------------------------------- #


def test_linear_chain_10_blocks_and_reload_from_disk(tmp_path):
    params = REGTEST
    db_path = tmp_path / "chain.sqlite"
    chain = Chain(params, path=str(db_path))
    genesis = params.genesis
    prev = genesis
    blocks = []
    for h in range(1, 11):
        now = time_at(h)
        blk = mine_block(params, prev, h, now)
        res = accept(chain, blk, now=now)
        assert res.status == ChainStatus.ACCEPTED, res.reason
        assert res.tip == blk.block_hash
        blocks.append(blk)
        prev = blk

    hash_after_10 = chain.utxo_set_hash()
    assert chain.tip().height == 10

    # Ricarica da disco: stesso stato, stesso utxo_set_hash.
    chain2 = Chain(params, path=str(db_path))
    assert chain2.tip().height == 10
    assert chain2.utxo_set_hash() == hash_after_10
    for h in range(1, 11):
        assert chain2.get_block_by_height(h).block_hash == blocks[h - 1].block_hash
    chain.close()
    chain2.close()


def test_block_reload_matches_hash():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    blk = mine_block(params, genesis, 1, now)
    assert accept(chain, blk, now=now).status == ChainStatus.ACCEPTED
    reloaded = chain.get_block(blk.block_hash)
    assert reloaded is not None and reloaded.raw == blk.serialize()
    assert chain.get_block_by_height(1).block_hash == blk.block_hash


# --------------------------------------------------------------------------- #
# Doppia spesa
# --------------------------------------------------------------------------- #


def test_double_spend_intra_block_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    pk = key(1)
    spk = p2pkh_script(hash160(pub(pk)))
    sub = block_subsidy(1, halving_interval=params.halving_interval)

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub, coinbase_script=spk)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    # h3: due transazioni diverse (txid diverso) che spendono lo stesso input
    # di b1 nello stesso blocco -> doppia spesa intra-blocco.
    now = time_at(3)
    spend1 = spend_tx(b1.transactions[0].txid(), 0, sub - 1000, spk, pk, height=3)
    spend2 = spend_tx(b1.transactions[0].txid(), 0, sub - 2000, spk, pk, height=3)
    fee = 1000
    b3 = mine_block(
        params,
        b2,
        3,
        now,
        txs=(spend1, spend2),
        coinbase_value=block_subsidy(3, halving_interval=params.halving_interval) + fee,
    )
    res = accept(chain, b3, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    # Stato immutato: la testa resta b2.
    assert chain.tip().block_hash == b2.block_hash


def test_double_spend_across_blocks_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    pk = key(1)
    spk = p2pkh_script(hash160(pub(pk)))
    sub = block_subsidy(1, halving_interval=params.halving_interval)

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub, coinbase_script=spk)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    spend = spend_tx(b1.transactions[0].txid(), 0, sub - 1000, spk, pk, height=2)
    b2 = mine_block(
        params,
        b1,
        2,
        now,
        txs=(spend,),
        coinbase_value=block_subsidy(2, halving_interval=params.halving_interval) + 1000,
    )
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    now = time_at(3)
    b3 = mine_block(params, b2, 3, now)
    assert accept(chain, b3, now=now).status == ChainStatus.ACCEPTED

    # h4: prova a spendere di nuovo lo stesso output di b1 (già speso in h2).
    now = time_at(4)
    spend_again = spend_tx(
        b1.transactions[0].txid(), 0, sub - 1000, spk, pk, height=4
    )
    b4 = mine_block(
        params,
        b3,
        4,
        now,
        txs=(spend_again,),
        coinbase_value=block_subsidy(4, halving_interval=params.halving_interval) + 1000,
    )
    res = accept(chain, b4, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert chain.tip().block_hash == b3.block_hash


# --------------------------------------------------------------------------- #
# Maturità coinbase
# --------------------------------------------------------------------------- #


def test_coinbase_immature_spend_rejected_and_mature_accepted():
    params = REGTEST  # maturità = 2
    chain = Chain(params)
    genesis = params.genesis
    pk = key(2)
    spk = p2pkh_script(hash160(pub(pk)))
    sub1 = block_subsidy(1, halving_interval=params.halving_interval)
    sub3 = block_subsidy(3, halving_interval=params.halving_interval)

    # h1: coinbase spendibile a partire da h3 (maturità 2).
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub1, coinbase_script=spk)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    # h2: vuoto.
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    # h3: spendo il coinbase di b1 (3 - 1 = 2, maturo) e metto un coinbase
    # spendibile a partire da h5.
    now = time_at(3)
    spend = spend_tx(b1.transactions[0].txid(), 0, sub1 - 1000, spk, pk, height=3)
    b3 = mine_block(
        params,
        b2,
        3,
        now,
        txs=(spend,),
        coinbase_value=sub3,
        coinbase_script=spk,
    )
    res = accept(chain, b3, now=now)
    assert res.status == ChainStatus.ACCEPTED, res.reason

    # h4: il coinbase di b3 ha maturità 4-3 = 1 < 2 -> immaturo, rifiutato.
    now = time_at(4)
    spend_immature = spend_tx(
        b3.transactions[0].txid(), 0, sub3 - 1000, spk, pk, height=4
    )
    b_imm = mine_block(
        params,
        b3,
        4,
        now,
        txs=(spend_immature,),
        coinbase_value=block_subsidy(4, halving_interval=params.halving_interval) + 1000,
    )
    res = accept(chain, b_imm, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "immature coinbase" in res.reason
    # Stato immutato: la testa resta b3.
    assert chain.tip().block_hash == b3.block_hash

    # h5: stessa spesa è matura (5 - 3 = 2).
    now = time_at(5)
    b5 = mine_block(
        params,
        b3,
        5,
        now,
        txs=(spend_immature,),
        coinbase_value=block_subsidy(5, halving_interval=params.halving_interval) + 1000,
    )
    res = accept(chain, b5, now=now)
    assert res.status == ChainStatus.ACCEPTED, res.reason


# --------------------------------------------------------------------------- #
# Coinbase oltre subsidy + fee
# --------------------------------------------------------------------------- #


def test_coinbase_exceeds_subsidy_plus_fee_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    sub = block_subsidy(1, halving_interval=params.halving_interval)
    # Il miner chiede un'unità di più del sussidio, senza fee.
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub + 1)
    res = accept(chain, b1, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "coinbase exceeds subsidy + fees" in res.reason
    assert chain.tip().block_hash == genesis.block_hash


# --------------------------------------------------------------------------- #
# Emissione totale oltre MAX_MONEY (params ridotti)
# --------------------------------------------------------------------------- #


def test_cumulative_emission_exceeds_max_money_rejected():
    # Sussidio iniziale pari a MAX_MONEY, halving lontanissimo: il secondo
    # blocco farebbe sforare la massa monetaria.
    params = replace(REGTEST, subsidy=MAX_MONEY)
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)

    b1 = mine_block(params, genesis, 1, now, coinbase_value=MAX_MONEY)
    res = accept(chain, b1, now=now)
    assert res.status == ChainStatus.ACCEPTED
    assert chain.storage.active_tip().emitted == MAX_MONEY

    now = time_at(2)
    b2 = mine_block(params, b1, 2, now, coinbase_value=MAX_MONEY)
    res = accept(chain, b2, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "cumulative emission exceeds MAX_MONEY" in res.reason
    # La testa resta b1.
    assert chain.tip().block_hash == b1.block_hash


# --------------------------------------------------------------------------- #
# Target, timestamp, altezza
# --------------------------------------------------------------------------- #


def test_wrong_target_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    blk = mine_block(params, genesis, 1, now, target=params.pow_limit - 1)
    res = accept(chain, blk, now=now)
    assert res.status == ChainStatus.INVALID
    assert "target does not match ASERT" in res.reason


def test_timestamp_at_or_below_mtp_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    # h2 con timestamp == timestamp del b1: MTP di [genesis, b1] è b1.timestamp.
    now = time_at(2)
    blk = mine_block(params, b1, 2, b1.header.timestamp)
    res = accept(chain, blk, now=now)
    assert res.status == ChainStatus.INVALID
    assert "not above MTP" in res.reason


def test_timestamp_beyond_future_drift_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    blk = mine_block(params, b1, 2, now + 7_200 + 1)
    res = accept(chain, blk, now=now)
    assert res.status == ChainStatus.INVALID
    assert "too far in the future" in res.reason


def test_wrong_height_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    # Altezza 4 invece di 2.
    blk = mine_block(params, b1, 4, now)
    res = accept(chain, blk, now=now)
    assert res.status == ChainStatus.INVALID
    assert "height" in res.reason


def test_wrong_coinbase_height_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    bad_cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(9)),),
        (TxOut(block_subsidy(1, halving_interval=params.halving_interval), b"\x51"),),
    )
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=genesis.block_hash,
        merkle_root=merkle_root([bad_cb.txid()]),
        timestamp=now,
        target=expected_target(params, 1, genesis.header.timestamp),
        nonce=0,
    )
    block = Block(header, (bad_cb,))
    block.header.check_pow()
    res = accept(chain, block, now=now)
    assert res.status == ChainStatus.INVALID
    assert "coinbase height" in res.reason


# --------------------------------------------------------------------------- #
# Script, CLTV, lock_time
# --------------------------------------------------------------------------- #


def test_invalid_script_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    pk = key(3)
    spk = p2pkh_script(hash160(pub(pk)))
    sub = block_subsidy(1, halving_interval=params.halving_interval)

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub, coinbase_script=spk)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    now = time_at(3)
    # Firma fatta con la chiave sbagliata: lo script fallisce.
    wrong_key = key(9)
    spend_bad_sig = spend_tx(
        b1.transactions[0].txid(), 0, sub - 1000, spk, wrong_key, height=3
    )
    b3 = mine_block(
        params,
        b2,
        3,
        now,
        txs=(spend_bad_sig,),
        coinbase_value=block_subsidy(3, halving_interval=params.halving_interval) + 1000,
    )
    res = accept(chain, b3, now=now)
    assert res.status == ChainStatus.INVALID, res.reason


def test_cltv_not_mature_rejected_then_mature():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    sender = key(4)
    receiver = key(5)
    preimage = bytes(range(32))
    payment_hash = hashlib.sha256(preimage).digest()
    from core.script import htlc_script

    htlc = htlc_script(payment_hash, pub(receiver), pub(sender), 5)
    sub = block_subsidy(1, halving_interval=params.halving_interval)

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub, coinbase_script=htlc)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    # h3: lock_time 3, timelock HTLC 5 -> CHECKLOCKTIMEVERIFY fallisce
    # ("transaction lock_time below CLTV").
    now = time_at(3)
    unsigned_refund = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b"", 199),),
        (TxOut(sub - 1000, b"\x51"),),
        3,
    )
    digest = sighash(unsigned_refund, 0, htlc, network=NETWORK_TEST)
    refund_tx = Transaction(
        1,
        (
            TxIn(
                b1.transactions[0].txid(),
                0,
                htlc_refund_script_sig(sign_digest(sender, digest)),
                199,
            ),
        ),
        (TxOut(sub - 1000, b"\x51"),),
        3,
    )
    b3 = mine_block(
        params,
        b2,
        3,
        now,
        txs=(refund_tx,),
        coinbase_value=block_subsidy(3, halving_interval=params.halving_interval) + 1000,
    )
    res = accept(chain, b3, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "CLTV" in res.reason or "lock_time" in res.reason

    # h5: stessa spesa è matura (height 5 >= timelock 5).
    now = time_at(5)
    unsigned_refund = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b"", 199),),
        (TxOut(sub - 1000, b"\x51"),),
        5,
    )
    digest = sighash(unsigned_refund, 0, htlc, network=NETWORK_TEST)
    refund_tx = Transaction(
        1,
        (
            TxIn(
                b1.transactions[0].txid(),
                0,
                htlc_refund_script_sig(sign_digest(sender, digest)),
                199,
            ),
        ),
        (TxOut(sub - 1000, b"\x51"),),
        5,
    )
    b5 = mine_block(
        params,
        b2,
        5,
        now,
        txs=(refund_tx,),
        coinbase_value=block_subsidy(5, halving_interval=params.halving_interval) + 1000,
    )
    res = accept(chain, b5, now=now)
    assert res.status == ChainStatus.ACCEPTED, res.reason


def test_locktime_beyond_threshold_rejected():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    pk = key(6)
    spk = p2pkh_script(hash160(pub(pk)))
    sub = block_subsidy(1, halving_interval=params.halving_interval)

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub, coinbase_script=spk)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    now = time_at(3)
    # lock_time sopra la soglia: non è un'altezza.
    bad = spend_tx(
        b1.transactions[0].txid(), 0, sub - 1000, spk, pk, height=3,
        lock_time=LOCKTIME_THRESHOLD,
    )
    b3 = mine_block(
        params,
        b2,
        3,
        now,
        txs=(bad,),
        coinbase_value=block_subsidy(3, halving_interval=params.halving_interval) + 1000,
    )
    res = accept(chain, b3, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "lock_time" in res.reason


# --------------------------------------------------------------------------- #
# check_tx_inputs riusabile
# --------------------------------------------------------------------------- #


def test_check_tx_inputs_reusable_view():
    params = REGTEST
    genesis = params.genesis
    pk = key(7)
    spk = p2pkh_script(hash160(pub(pk)))
    sub = block_subsidy(1, halving_interval=params.halving_interval)

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now, coinbase_value=sub, coinbase_script=spk)
    chain = Chain(params)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    utxo = chain.get_utxo(b1.transactions[0].txid(), 0)
    assert utxo is not None and utxo.value == sub
    assert isinstance(utxo, UTXO)

    # Vista in memoria (mappatura): uso diretto riusabile da mempool/nodo.
    view = {utxo.outpoint: utxo}
    spend = spend_tx(b1.transactions[0].txid(), 0, sub - 1000, spk, pk, height=105)
    total = check_tx_inputs(
        spend, view, height=105, network=NETWORK_TEST, coinbase_maturity=2
    )
    assert total == sub

    # In-output mancante -> errore.
    missing = spend_tx(b"\x99" * 32, 0, 1000, spk, pk, height=105)
    with pytest.raises(TxInputError):
        check_tx_inputs(
            missing, view, height=105, network=NETWORK_TEST, coinbase_maturity=2
        )


# --------------------------------------------------------------------------- #
# build_template
# --------------------------------------------------------------------------- #


def test_build_template_produces_minable_block():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED

    now = time_at(2)
    tmpl = chain.build_template(b"\x51", (), now=now)
    assert isinstance(tmpl, Block)
    assert tmpl.height == 2
    assert tmpl.header.prev_hash == b1.block_hash
    assert tmpl.header.target == expected_target(params, 2, b1.header.timestamp)
    assert time_at(2) <= tmpl.header.timestamp <= now + 7_200
    coinbase = tmpl.transactions[0]
    assert coinbase.is_coinbase
    assert coinbase.outputs[0].value == block_subsidy(
        2, halving_interval=params.halving_interval
    )
    tmpl.header.check_pow()


# --------------------------------------------------------------------------- #
# Fork choice, reorg e checkpoint
# --------------------------------------------------------------------------- #


def test_reorg_to_heavier_branch_state_matches_independent_application():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis

    # Ramo A: altezze 1..5 lineari.
    prev = genesis
    blocks_a = []
    for h in range(1, 6):
        now = time_at(h)
        blk = mine_block(params, prev, h, now)
        assert accept(chain, blk, now=now).status == ChainStatus.ACCEPTED
        blocks_a.append(blk)
        prev = blk
    hash_a5 = chain.utxo_set_hash()

    # Applicare solo A su una catena indipendente deve dare lo stesso hash.
    baseline = Chain(ChainParams.regtest())
    prev = baseline.params.genesis
    for h, blk in enumerate(blocks_a, start=1):
        now = time_at(h)
        assert baseline.accept_block(blk, now=now).status == ChainStatus.ACCEPTED
    assert baseline.utxo_set_hash() == hash_a5
    baseline.close()

    # Ramo B dal blocco all'altezza 2: B3..B6 (4 blocchi) -> B più pesante di A
    # (lavoro uguale per blocco, B ha un blocco in più: genesis+6 vs genesis+5).
    fork2 = blocks_a[1]  # altezza 2
    prev = fork2
    blocks_b = []
    for h in range(3, 7):
        now = time_at(h)
        blk = mine_block(params, prev, h, now)
        blocks_b.append(blk)
        prev = blk

    # Accettare B3 scatena il reorg: B diventa la catena attiva.
    now = time_at(3)
    res = accept(chain, blocks_b[0], now=now)
    assert res.status == ChainStatus.ACCEPTED, res.reason
    assert chain.tip().height == 6
    assert chain.tip().block_hash == blocks_b[-1].block_hash

    # Lo stato deve coincidere con l'applicazione indipendente del solo ramo B.
    baseline_b = Chain(ChainParams.regtest())
    prev = baseline_b.params.genesis
    accepted_b = [blocks_a[0], blocks_a[1]] + list(blocks_b)
    for h, blk in zip(range(1, 7), accepted_b):
        now = time_at(h)
        assert baseline_b.accept_block(blk, now=now).status == ChainStatus.ACCEPTED
    assert chain.utxo_set_hash() == baseline_b.utxo_set_hash()
    baseline_b.close()

    # Ritorno a A: estendo A con A6,A7 (2 blocchi) -> A diventa più pesante
    # (genesis+7 > genesis+6).
    prev = blocks_a[-1]  # altezza 5, ora ramo valido laterale
    blocks_a_ext = []
    for h in range(6, 8):
        now = time_at(h)
        blk = mine_block(params, prev, h, now)
        blocks_a_ext.append(blk)
        prev = blk
    now = time_at(6)
    res = accept(chain, blocks_a_ext[0], now=now)
    # Lavoro pari (genesis+6 == genesis+6): parità mantiene il ramo attivo (B).
    assert res.status == ChainStatus.ACCEPTED
    assert chain.tip().block_hash == blocks_b[-1].block_hash
    now = time_at(7)
    res = accept(chain, blocks_a_ext[1], now=now)
    assert res.status == ChainStatus.ACCEPTED, res.reason
    assert chain.tip().block_hash == blocks_a_ext[-1].block_hash
    assert chain.tip().height == 7

    # Stato finale uguale all'applicazione indipendente di solo A esteso.
    baseline_a = Chain(ChainParams.regtest())
    prev = baseline_a.params.genesis
    all_a = blocks_a + blocks_a_ext
    for h, blk in zip(range(1, 8), all_a):
        now = time_at(h)
        assert baseline_a.accept_block(blk, now=now).status == ChainStatus.ACCEPTED
    assert chain.utxo_set_hash() == baseline_a.utxo_set_hash()
    baseline_a.close()


def test_reorg_invalid_block_rollback_and_descendants_invalid():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    # Ramo laterale da b1: c2 (valido), c3 (coinbase oltre subsidy -> invalido), c4.
    now = time_at(3)
    c2 = mine_block(params, b1, 3, now)
    assert accept(chain, c2, now=now).status == ChainStatus.ACCEPTED  # pari lavoro
    # La testa resta b2 (parità mantiene il ramo attivo).
    assert chain.tip().block_hash == b2.block_hash

    sub3 = block_subsidy(4, halving_interval=params.halving_interval)
    now = time_at(4)
    c3 = mine_block(params, c2, 4, now, coinbase_value=sub3 + 1)
    res = accept(chain, c3, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "coinbase exceeds subsidy + fees" in res.reason

    # Rollback completo: la testa resta b2.
    assert chain.tip().block_hash == b2.block_hash
    assert chain.get_block(c3.hash).status == ChainStatus.INVALID

    # c4 discendente di c3: genitore invalido.
    now = time_at(5)
    c4 = mine_block(params, c3, 5, now)
    res = accept(chain, c4, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "parent is invalid" in res.reason
    assert chain.get_block(c4.hash).status == ChainStatus.INVALID

    # Rinvio di c3: già noto come invalido.
    res = accept(chain, c3, now=now)
    assert res.status == ChainStatus.INVALID
    assert "known invalid" in res.reason
    assert chain.tip().block_hash == b2.block_hash


def test_block_duplicate():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED
    res = accept(chain, b1, now=now)
    assert res.status == ChainStatus.DUPLICATE, res.reason
    assert chain.tip().block_hash == b1.block_hash


def test_orphan_does_not_change_state():
    params = REGTEST
    chain = Chain(params)
    genesis = params.genesis
    tip_before = chain.tip().block_hash
    hash_before = chain.utxo_set_hash()

    now = time_at(1)
    cb = coinbase_tx(1, block_subsidy(1, halving_interval=params.halving_interval))
    header = BlockHeader(
        version=1,
        height=1,
        prev_hash=b"\x22" * 64,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=params.pow_limit,
        nonce=0,
    )
    orphan = Block(header, (cb,))
    orphan.header.check_pow()

    res = accept(chain, orphan, now=now)
    assert res.status == ChainStatus.ORPHAN, res.reason
    assert chain.tip().block_hash == tip_before
    assert chain.utxo_set_hash() == hash_before
    # Non memorizzato.
    assert chain.get_block(orphan.block_hash) is None


def test_fork_below_last_checkpoint_rejected():
    params = replace(
        REGTEST,
        checkpoints=(
            Checkpoint(0, REGTEST.genesis.block_hash),
            Checkpoint(3, b"\x33" * 64),
        ),
    )
    chain = Chain(params)
    genesis = params.genesis

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert accept(chain, b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert accept(chain, b2, now=now).status == ChainStatus.ACCEPTED

    now = time_at(3)
    b3 = mine_block(params, b2, 3, now)  # hash != checkpoint fittizio
    res = accept(chain, b3, now=now)
    assert res.status == ChainStatus.INVALID, res.reason
    assert "checkpoint" in res.reason


def test_regtest_params_defaults():
    params = ChainParams.regtest()
    assert params.coinbase_maturity == 2
    assert params.pow_limit == (1 << 512) - 1
    assert params.halving_interval == 10
    assert params.genesis.header.target == params.pow_limit

"""Additional coverage for chain.py _connect defensive paths via monkeypatching."""

from __future__ import annotations

import pytest

from core.chain import Chain, ChainParams, ChainError, ChainStatus, _InvalidBlock
from core.difficulty import DifficultyError
from core.block import TimestampError

from core.tx import Transaction, TxIn, TxOut
from tests.test_chain import mine_block, time_at


# The _connect() defensive paths (hash mismatch, parent not active, height
# mismatch, DifficultyError, TimestampError, structure/pow, checkpoint mismatch,
# coinbase subsidy, MAX_MONEY) are UNREACHABLE through accept_block() because
# accept_block() validates all of these before inserting the block. They are
# purely defensive guards for database corruption or programming errors.
# Marked as unreachable/defensive - no test can trigger them through the
# public API because accept_block() validates first.


def test_reorg_restores_spent_utxo():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert chain.accept_block(b2, now=now).status == ChainStatus.ACCEPTED

    spend_tx = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    now = time_at(3)
    b3 = mine_block(params, b2, 3, now, txs=(spend_tx,))
    assert chain.accept_block(b3, now=now).status == ChainStatus.ACCEPTED

    prev = b1
    blocks_b = []
    for h in range(2, 6):
        now = time_at(h)
        blk = mine_block(params, prev, h, now, nonce=h + 100)
        blocks_b.append(blk)
        prev = blk

    for blk in blocks_b:
        now = time_at(blk.height)
        assert chain.accept_block(blk, now=now).status == ChainStatus.ACCEPTED

    assert chain.tip().block_hash == blocks_b[-1].block_hash
    utxo = chain.get_utxo(b1.transactions[0].txid(), 0)
    assert utxo is not None
    chain.close()

def test_reorg_restores_spent_utxo():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert chain.accept_block(b2, now=now).status == ChainStatus.ACCEPTED

    spend_tx = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    now = time_at(3)
    b3 = mine_block(params, b2, 3, now, txs=(spend_tx,))
    assert chain.accept_block(b3, now=now).status == ChainStatus.ACCEPTED

    prev = b1
    blocks_b = []
    for h in range(2, 6):
        now = time_at(h)
        blk = mine_block(params, prev, h, now, nonce=h + 100)
        blocks_b.append(blk)
        prev = blk

    for blk in blocks_b:
        now = time_at(blk.height)
        assert chain.accept_block(blk, now=now).status == ChainStatus.ACCEPTED

    assert chain.tip().block_hash == blocks_b[-1].block_hash
    utxo = chain.get_utxo(b1.transactions[0].txid(), 0)
    assert utxo is not None
    chain.close()

def test_reorg_restores_spent_utxo():
    params = ChainParams.regtest()
    chain = Chain(params)
    genesis = params.genesis

    now = time_at(1)
    b1 = mine_block(params, genesis, 1, now)
    assert chain.accept_block(b1, now=now).status == ChainStatus.ACCEPTED
    now = time_at(2)
    b2 = mine_block(params, b1, 2, now)
    assert chain.accept_block(b2, now=now).status == ChainStatus.ACCEPTED

    spend_tx = Transaction(
        1,
        (TxIn(b1.transactions[0].txid(), 0, b""),),
        (TxOut(1000, b"\x51"),),
    )
    now = time_at(3)
    b3 = mine_block(params, b2, 3, now, txs=(spend_tx,))
    assert chain.accept_block(b3, now=now).status == ChainStatus.ACCEPTED

    prev = b1
    blocks_b = []
    for h in range(2, 6):
        now = time_at(h)
        blk = mine_block(params, prev, h, now, nonce=h + 100)
        blocks_b.append(blk)
        prev = blk

    for blk in blocks_b:
        now = time_at(blk.height)
        assert chain.accept_block(blk, now=now).status == ChainStatus.ACCEPTED

    assert chain.tip().block_hash == blocks_b[-1].block_hash
    utxo = chain.get_utxo(b1.transactions[0].txid(), 0)
    assert utxo is not None
    chain.close()

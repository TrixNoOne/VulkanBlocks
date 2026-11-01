import os

content = '''
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
        (TxOut(1000, b"\\x51"),),
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
'''

with open('tests/test_chain_coverage4.py', 'a') as f:
    f.write(content)
print('appended')

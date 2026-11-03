import sys
sys.path.insert(0, '.')
from core.chain import Chain, ChainParams, ChainStatus
from core.genesis import Checkpoint
from dataclasses import replace
from core.block import Block, BlockHeader, merkle_root
from core.tx import Transaction, TxIn, TxOut, NULL_TXID, COINBASE_INDEX, encode_coinbase_height
from core.params import block_subsidy
from core.difficulty import asert_target

base = ChainParams.regtest()
genesis = base.genesis
now = genesis.header.timestamp + 120

# Create b1
cb = Transaction(
    1,
    (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
    (TxOut(block_subsidy(1), b'\x51'),),
)
header = BlockHeader(
    version=1,
    height=1,
    prev_hash=genesis.block_hash,
    merkle_root=merkle_root([cb.txid()]),
    timestamp=now,
    target=base.pow_limit,
    nonce=0,
)
b1 = Block(header, (cb,))
b1.header.check_pow()
print(f'b1: {b1.block_hash.hex()[:16]}')

# Create b2
now2 = now + 120
cb2 = Transaction(
    1,
    (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(2)),),
    (TxOut(block_subsidy(2), b'\x51'),),
)
header2 = BlockHeader(
    version=1,
    height=2,
    prev_hash=b1.block_hash,
    merkle_root=merkle_root([cb2.txid()]),
    timestamp=now2,
    target=base.pow_limit,
    nonce=0,
)
b2 = Block(header2, (cb2,))
b2.header.check_pow()
print(f'b2: {b2.block_hash.hex()[:16]}')

# Create chain with checkpoint at height 2 = b2.hash
params = replace(base, checkpoints=(Checkpoint(0, base.genesis.block_hash), Checkpoint(2, b2.block_hash)))
chain = Chain(params, path=':memory:')
print(f'Accept b1: {chain.accept_block(b1, now=now).status}')
print(f'Accept b2: {chain.accept_block(b2, now=now2).status}')

# Create side block at height 1 from genesis
def mine_block(params, prev, height, timestamp, txs=(), coinbase_value=None, coinbase_script=b'\x51', nonce=0, target=None):
    if coinbase_value is None:
        coinbase_value = block_subsidy(height, halving_interval=params.halving_interval, initial_subsidy=params.subsidy)
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(height)),),
        (TxOut(coinbase_value, coinbase_script),),
    )
    transactions = (cb,) + txs
    if target is None:
        target = asert_target(height, prev.header.timestamp, params.anchor, pow_limit=params.pow_limit)
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

now3 = now + 120
side = mine_block(params, genesis, 1, now3, nonce=1)
print(f'side: {side.block_hash.hex()[:16]}, height: {side.height}')
res = chain.accept_block(side, now=now3)
print(f'Accept side: {res.status}, reason: {res.reason}')
print(f'Tip height: {chain.tip().height if chain.storage.active_tip() else None}')
chain.close()

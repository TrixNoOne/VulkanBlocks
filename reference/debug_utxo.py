import json
import sys
sys.path.insert(0, '.')
from core.block import Block
from core.chain import Chain, ChainParams, ChainStatus
from core.genesis import Checkpoint

data = json.load(open('vectors/scenarios/fork_below_checkpoint.json'))
params = ChainParams.regtest()
if 'checkpoints' in data:
    checkpoints = [Checkpoint(c['height'], bytes.fromhex(c['hash'])) for c in data['checkpoints']]
    params = ChainParams(genesis=params.genesis, pow_limit=params.pow_limit, subsidy=params.subsidy, coinbase_maturity=params.coinbase_maturity, network_tag=params.network_tag, anchor=params.anchor, halving_interval=params.halving_interval, checkpoints=checkpoints)

chain = Chain(params, path=':memory:')
for i, step in enumerate(data['steps']):
    block = Block.from_bytes(bytes.fromhex(step['block_hex']))
    now = block.header.timestamp
    res = chain.accept_block(block, now=now)
    actual_utxo = chain.utxo_set_hash().hex()
    expected_utxo = step.get('utxo_set_hash', 'N/A')
    match = actual_utxo == expected_utxo
    print(f'Step {i}: status={res.status.value} stored={res.status.value=="ACCEPTED"} actual_utxo={actual_utxo[:20]}... expected_utxo={expected_utxo[:20] if expected_utxo != "N/A" else "N/A"} match={match}')
chain.close()
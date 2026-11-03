import json
import sys
sys.path.insert(0, '.')
from core.block import Block
from core.chain import Chain, ChainParams, ChainStatus
from core.genesis import Checkpoint

data = json.load(open('vectors/scenarios/fork_below_checkpoint.json'))
print('Scenario step 0 utxo:', data['steps'][0].get('utxo_set_hash', 'N/A'))
print('Scenario step 1 utxo:', data['steps'][1].get('utxo_set_hash', 'N/A'))
print('Scenario step 2 utxo:', data['steps'][2].get('utxo_set_hash', 'N/A'))

# Build ChainParams with checkpoints (but without fixing checkpoint 0 hash since it already matches)
params = ChainParams.regtest()
checkpoints = [Checkpoint(c["height"], bytes.fromhex(c["hash"])) for c in data["checkpoints"]]
print('Checkpoint 0 height:', checkpoints[0].height)
print('Checkpoint 0 hash:', checkpoints[0].hash.hex())
print('Genesis hash:', params.genesis.block_hash.hex())
print('Hashes match:', checkpoints[0].hash == params.genesis.block_hash)

# Try constructing ChainParams - this should fail because checkpoint 0 hash doesn't match
# Actually, from the debug output earlier, the hashes DO match, so it should work
try:
    params2 = ChainParams(
        genesis=params.genesis,
        pow_limit=params.pow_limit,
        subsidy=params.subsidy,
        coinbase_maturity=params.coinbase_maturity,
        network_tag=params.network_tag,
        anchor=params.anchor,
        halving_interval=params.halving_interval,
        checkpoints=checkpoints,
    )
    print('ChainParams constructed successfully')
except Exception as e:
    print(f'ChainParams error: {e}')

chain = Chain(params, path=':memory:')
for i, step in enumerate(data['steps']):
    block = Block.from_bytes(bytes.fromhex(step['block_hex']))
    now = block.header.timestamp
    res = chain.accept_block(block, now=now)
    actual_utxo = chain.utxo_set_hash().hex()
    expected_utxo = data['steps'][i].get('utxo_set_hash', 'N/A')
    match = actual_utxo == expected_utxo
    print(f'Step {i}: actual={actual_utxo[:20]} expected={expected_utxo[:20] if expected_utxo != "N/A" else "N/A"} match={match}')
chain.close()
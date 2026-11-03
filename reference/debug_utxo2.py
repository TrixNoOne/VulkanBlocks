import json
import sys
sys.path.insert(0, '.')
from core.block import Block
from core.chain import Chain, ChainParams, ChainStatus
from core.genesis import Checkpoint

data = json.load(open('vectors/scenarios/fork_below_checkpoint.json'))
print("Scenario has checkpoints:", 'checkpoints' in data)
print("Scenario step 0 utxo:", data['steps'][0].get('utxo_set_hash', 'N/A')[:20] if data['steps'][0].get('utxo_set_hash') else 'N/A')
print("Scenario step 1 utxo:", data['steps'][1].get('utxo_set_hash', 'N/A')[:20] if data['steps'][1].get('utxo_set_hash') else 'N/A')
print("Scenario step 2 utxo:", data['steps'][2].get('utxo_set_hash', 'N/A')[:20] if data['steps'][2].get('utxo_set_hash') else 'N/A')

params = ChainParams.regtest()
if 'checkpoints' in data:
    checkpoints = [Checkpoint(c["height"], bytes.fromhex(c["hash"])) for c in data["checkpoints"]]
    # Check what the checkpoint 0 hash is
    print(f"Checkpoint 0 height: {checkpoints[0].height}, hash: {checkpoints[0].hash.hex()[:20]}...")
    print(f"Genesis hash: {params.genesis.block_hash.hex()[:20]}...")
    if checkpoints[0].height == 0:
        # The test fixes checkpoint 0 to match genesis
        checkpoints[0] = Checkpoint(0, params.genesis.block_hash)
    params = ChainParams(
        genesis=params.genesis,
        pow_limit=params.pow_limit,
        subsidy=params.subsidy,
        coinbase_maturity=params.coinbase_maturity,
        network_tag=params.network_tag,
        anchor=params.anchor,
        halving_interval=params.halving_interval,
        checkpoints=checkpoints,
    )

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
import json
data = json.load(open('vectors/scenarios/fork_below_checkpoint.json'))
for step in data['steps']:
    print(f"  {step['block_hash'][:16]}... status={step['status']} stored={step['stored']} reason={step['reason'][:30]}")
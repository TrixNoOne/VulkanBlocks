import json
data = json.load(open('vectors/scenarios/fork_below_checkpoint.json'))
for step in data['steps']:
    print(f"status={step['status']} stored={step['stored']} reason={step['reason'][:50]}")
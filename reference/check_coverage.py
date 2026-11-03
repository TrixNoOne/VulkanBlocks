import json
data = json.load(open('coverage.json'))
for fname in ['core\\script.py', 'core\\storage.py']:
    info = data['files'][fname]
    print(f'{fname}: missing_lines={sorted(info.get("missing_lines", []))}')
    print(f'{fname}: missing_branches={sorted(info.get("missing_branches", []))}')
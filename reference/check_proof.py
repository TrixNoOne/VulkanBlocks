import pathlib
path = pathlib.Path('core/chain.py')
lines = path.read_text().splitlines(keepends=True)
no_proof = []
for i, line in enumerate(lines, 1):
    if '# pragma: no cover' in line and '# PROOF:' not in line:
        no_proof.append(i)
print(f'Total pragma lines: {sum(1 for l in lines if "# pragma: no cover" in l)}')
print(f'Lines WITHOUT PROOF: {no_proof}')
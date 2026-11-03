import pathlib

# script.py line 498 - COVERED, remove pragma
path = pathlib.Path('core/script.py')
lines = path.read_text().splitlines(keepends=True)
for i, line in enumerate(lines, 1):
    if i == 498 and '# pragma: no cover' in line:
        lines[i-1] = line.replace('  # pragma: no cover - il parser filtra gli opcode', '') + '\n'
        print(f'Removed pragma from script.py line {i}')
path.write_text(''.join(lines))

# storage.py line 367 - COVERED, remove pragma
path = pathlib.Path('core/storage.py')
lines = path.read_text().splitlines(keepends=True)
for i, line in enumerate(lines, 1):
    if i == 367 and '# pragma: no cover' in line:
        lines[i-1] = line.replace('  # pragma: no cover - corruzione', '') + '\n'
        print(f'Removed pragma from storage.py line {i}')
path.write_text(''.join(lines))
print('Done removing covered pragmas')
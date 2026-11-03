import pathlib

path = pathlib.Path('core/chain.py')
lines = path.read_text().splitlines(keepends=True)

# Map line number -> PROOF reason (short form matching existing comments)
proofs = {
    238: "UNREACHABLE: MAX_TARGET makes any nonce pass PoW",
    240: "UNREACHABLE: MAX_TARGET makes any nonce pass PoW",
    290: "DEFENSIVE: invalid view type",
    310: "DEFENSIVE: utxo_view must expose get_utxo()",
    379: "DEFENSIVE: total_out capped by TxOut MAX_MONEY",
    389: "DEFENSIVE: verify_script catches parse errors",
    390: "DEFENSIVE: verify_script catches parse errors",
    429: "DEFENSIVE: params type check at Chain.__init__",
    442: "DEFENSIVE: requires different genesis in DB",
    445: "DEFENSIVE: requires genesis not active",
    480: "DEFENSIVE: requires corrupted DB",
    537: "DEFENSIVE: requires corrupted DB",
    631: "UNREACHABLE: asert_target doesn't raise for valid inputs",
    632: "UNREACHABLE: asert_target doesn't raise",
    642: "UNREACHABLE: ASERT clamps to pow_limit first",
    662: "DEFENSIVE: coinbase height mismatch caught by structure",
    663: "DEFENSIVE: coinbase height mismatch caught by structure",
    667: "DEFENSIVE: coinbase height mismatch caught by structure",
    686: "DEFENSIVE: fork below checkpoint rejected by accept_block",
    687: "DEFENSIVE: fork below checkpoint rejected by accept_block",
    705: "DEFENSIVE: fork below checkpoint rejected by accept_block",
    805: "DEFENSIVE: requires children traversal",
    833: "DEFENSIVE: asert_target doesn't raise for valid inputs",
    834: "DEFENSIVE: asert_target doesn't raise",
    836: "UNREACHABLE: ASERT clamps first",
    838: "UNREACHABLE: ASERT clamps to pow_limit first",
    843: "DEFENSIVE: accept_block validates first",
    844: "DEFENSIVE: accept_block validates first",
    849: "DEFENSIVE: accept_block validates first",
    850: "DEFENSIVE: accept_block validates first",
    854: "DEFENSIVE: accept_block validates first",
    891: "DEFENSIVE: requires corrupt undo",
    892: "DEFENSIVE: requires corrupt undo",
    902: "DEFENSIVE: TxOut validates value <= MAX_MONEY",
    958: "DEFENSIVE: check_tx_inputs verifies first",
    962: "DEFENSIVE: check_tx_inputs verifies first",
    968: "DEFENSIVE: check_tx_inputs verifies first",
    1084: "DEFENSIVE: requires ops limit exceeded",
    1092: "UNREACHABLE: coinbase_value <= MAX_MONEY always",
    1095: "UNREACHABLE: encode_coinbase_height maxes at 6 bytes",
}

changed = False
for i, line in enumerate(lines, 1):
    if i in proofs and "# pragma: no cover" in line:
        old = lines[i-1]
        # Add PROOF comment before the closing of the line
        # Format: ...  # pragma: no cover - reason
        # New: ...  # pragma: no cover - reason  # PROOF: reason
        if "# PROOF:" not in line:
            lines[i-1] = line.rstrip('\n') + f"  # PROOF: {proofs[i]}\n"
            changed = True

if changed:
    path.write_text(''.join(lines))
    print(f"Added PROOF comments to {changed} lines")
else:
    print("No changes needed")
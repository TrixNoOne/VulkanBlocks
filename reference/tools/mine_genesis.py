"""Cerca il nonce del genesis Vulcan e stampa header e costanti.

Uso:
    python tools/mine_genesis.py --network main
    python tools/mine_genesis.py --network test

Non usa orologio ne' float: solo SHA-512 e aritmetica intera. Il risultato va
incollato in ``core/params.py`` (GENESIS_NONCE_* e GENESIS_HASH_*).
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.block import double_sha512  # noqa: E402
from core.genesis import genesis_block  # noqa: E402
from core.params import (  # noqa: E402
    GENESIS_POW_LIMIT,
    NETWORK_MAIN,
    NETWORK_TEST,
)

UINT64_MAX = 0xFFFFFFFFFFFFFFFF
PROGRESS_STEP = 1 << 20


def mine(network: bytes, start_nonce: int = 0) -> tuple[int, bytes, bytes]:
    """Restituisce (nonce, hash, header) del primo header sotto il pow-limit."""
    if not 0 <= start_nonce <= UINT64_MAX:
        raise ValueError("start_nonce out of range")

    block = genesis_block(network, nonce=0)
    header = bytearray(block.header.serialize())
    target = GENESIS_POW_LIMIT
    nonce = start_nonce
    attempts = 0

    while nonce <= UINT64_MAX:
        struct.pack_into("<Q", header, 176, nonce)
        digest = double_sha512(bytes(header))
        if int.from_bytes(digest, "big") <= target:
            return nonce, digest, bytes(header)
        nonce += 1
        attempts += 1
        if attempts % PROGRESS_STEP == 0:
            print(f"  ... {attempts} tentativi, nonce {nonce}", file=sys.stderr)

    raise RuntimeError("nonce space exhausted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mina il genesis Vulcan")
    parser.add_argument("--network", choices=("main", "test"), default="main")
    parser.add_argument("--start-nonce", type=int, default=0)
    args = parser.parse_args(argv)

    network = NETWORK_MAIN if args.network == "main" else NETWORK_TEST
    label = "MAIN" if args.network == "main" else "TEST"
    nonce, digest, header = mine(network, args.start_nonce)

    block = genesis_block(network, nonce=nonce)
    if block.block_hash != digest:
        raise RuntimeError("header hash mismatch during mining")
    block.header.check_pow()
    block.validate_structure()

    print(f"network={args.network}")
    print(f"nonce={nonce}")
    print(f"hash={digest.hex()}")
    print(f"header={header.hex()}")
    print()
    print(f"GENESIS_NONCE_{label} = {nonce}")
    print(f'GENESIS_HASH_{label} = bytes.fromhex("{digest.hex()}")')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

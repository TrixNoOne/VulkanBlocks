"""Fuzz tests for Vulkan core using hypothesis.

Flipping one random byte in a valid block must never raise an unhandled
exception, and a rejected block must leave utxo_set_hash() unchanged.
"""

from __future__ import annotations

from hypothesis import given, strategies as st
from hypothesis.control import assume

from core.chain import Chain, ChainParams, ChainStatus
from core.block import Block
from core.params import MAX_BLOCK_SIZE


@given(
    seed=st.integers(min_value=0, max_value=255),
    byte_index=st.integers(min_value=0, max_value=183),
    flip_value=st.integers(min_value=0, max_value=255),
)
def test_flipping_header_byte_never_raises(seed: int, byte_index: int, flip_value: int):
    """Flipping one byte in a valid block's serialized form never crashes."""
    params = ChainParams.regtest()
    chain = Chain(params, path=":memory:")
    try:
        genesis = params.genesis
        now = genesis.header.timestamp + 120

        # Build a valid block at height 1.
        cb = Transaction_for_test(
            1,
            (TxIn_for_test(NULL_TXID_for_test(), COINBASE_INDEX_for_test(), encode_coinbase_height_for_test(1)),),
            (TxOut_for_test(subsidy_for_test(params, 1), b"\x51"),),
        )
        header = BlockHeader_for_test(
            version=1,
            height=1,
            prev_hash=genesis.block_hash,
            merkle_root=merkle_root_for_test([cb.txid()]),
            timestamp=now,
            target=params.pow_limit,
            nonce=seed,
        )
        block = Block(header, (cb,))
        block.header.check_pow()

        raw = bytearray(block.serialize())
        assume(len(raw) > byte_index)
        original_byte = raw[byte_index]
        raw[byte_index] = flip_value

        # Deserialize the mutated block.
        from core.block import Block as RealBlock

        try:
            mutated = RealBlock.from_bytes(bytes(raw))
        except Exception:
            # Deserialization failure is fine - it's a rejection, not a crash.
            chain.close()
            return

        # accept_block must not raise an unhandled exception.
        before_hash = chain.utxo_set_hash()
        res = chain.accept_block(mutated, now=now)
        # Any status is acceptable; the key is no unhandled exception.
        assert res.status in (
            ChainStatus.ACCEPTED,
            ChainStatus.ORPHAN,
            ChainStatus.DUPLICATE,
            ChainStatus.INVALID,
        )
        # A rejected block must not change the UTXO set.
        if res.status != ChainStatus.ACCEPTED:
            assert chain.utxo_set_hash() == before_hash
    finally:
        chain.close()


# Re-export names needed for block construction but imported lazily to avoid
# circular import issues at module load.
from core.block import (  # noqa: E402
    BlockHeader as BlockHeader_for_test,
)
from core.tx import (  # noqa: E402
    COINBASE_INDEX as COINBASE_INDEX_for_test,
    NULL_TXID as NULL_TXID_for_test,
    Transaction as Transaction_for_test,
    TxIn as TxIn_for_test,
    TxOut as TxOut_for_test,
    encode_coinbase_height as encode_coinbase_height_for_test,
)
from core.params import block_subsidy as subsidy_for_test
from core.block import merkle_root as merkle_root_for_test

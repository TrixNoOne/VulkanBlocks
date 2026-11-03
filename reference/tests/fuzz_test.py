"""Fuzz tests for Vulkan consensus stability.

Uses hypothesis to verify that:
1. Flipping one random byte in a valid block never raises an unhandled exception
2. A rejected block leaves utxo_set_hash() unchanged
"""
from __future__ import annotations

import random
import sys

import hypothesis
import hypothesis.strategies as st
import pytest

sys.path.insert(0, 'reference')

from core.block import Block
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from core.params import CP

@given(
    block_height=st.integers(min_value=1, max_value=1000),
    byte_flip_pos=st.integers(min_value=0, max_value=1000),
)
@example(block_height=1, byte_flip_pos=0)
def test_byte_flip_stability(block_height, byte_flip_pos):
    """Flipping one random byte in a valid block never raises an unhandled exception."""
    params = CP.regtest()
    chain = Chain(params, path=":memory:")
    
    # Build a valid block at the given height
    genesis = chain.genesis
    now = genesis.header.timestamp + (block_height * 120)
    
    # Mine a block (simplified - just use the chain's accept_block)
    # We need a valid block - use the chain's existing tip
    if chain.storage.active_tip():
        tip = chain.tip()
        # Create a block with the same prev as tip
        pass  # Will be handled by the test body
    
    # Actually, let's build a block from scratch
    from core.block import BlockHeader
    from core.tx import Transaction, TxIn, TxOut, NULL_TXID, COINBASE_INDEX, encode_coinbase_height
    from core.params import block_subsidy
    from core.difficulty import asert_target
    from core.crypto import merkle_root
    
    # Get previous block
    tip = chain.tip()
    prev_hash = tip.block_hash
    
    # Create coinbase
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(block_height)),),
        (TxOut(block_subsidy(block_height), b'\\x51'),),
    )
    
    # Create block header
    target = params.pow_limit
    header = BlockHeader(
        version=1,
        height=block_height,
        prev_hash=prev_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=target,
        nonce=0,
    )
    
    block = Block(header, (cb,))
    block.header.check_pow()
    
    # Flip a byte in the block bytes
    block_bytes = bytearray(block.serialize())
    if byte_flip_pos < len(block_bytes):
        block_bytes[byte_flip_pos] ^= 0xFF  # Flip bits
    
    # Try to accept the flipped block
    try:
        # Re-create block from modified bytes
        flipped_block = Block.from_bytes(bytes(block_bytes))
        now = flipped_block.header.timestamp
        res = chain.accept_block(flipped_block, now=now)
        # Should not raise an unhandled exception
        assert res.status is not None
    except Exception as e:
        # The test passes if the exception is handled (e.g., status is INVALID)
        # It fails if an unexpected exception type is raised
        if not isinstance(e, (ValueError, TypeError, ChainStatus)):
            raise  # Re-raise unexpected exceptions
    
    chain.close()


@given(
    block_height=st.integers(min_value=1, max_value=1000),
)
@example(block_height=1)
def test_rejected_block_utxo_hash_unchanged(block_height):
    """A rejected block leaves utxo_set_hash() unchanged."""
    params = CP.regtest()
    chain = Chain(params, path=":memory:")
    
    # Get the initial utxo_set_hash
    initial_hash = chain.utxo_set_hash().hex()
    
    # Build a valid block at the given height
    genesis = genesis = params.genesis
    now = genesis.header.timestamp + (block_height * 120)
    
    from core.tx import Transaction, TxIn, TxOut, NULL_TXID, COINBASE_INDEX, encode_coinbase_height
    from core.params import block_subsidy
    from core.difficulty import asert_target
    from core.block import BlockHeader
    from core.crypto import merkle_root
    
    # Create coinbase
    cb = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(block_height)),),
        (TxOut(block_subsidy(block_height), b'\\x51'),),
    )
    
    # Get previous tip hash
    tip = chain.tip()
    prev_hash = tip.block_hash if tip else params.genesis.block_hash
    
    # Create block header
    target = asert_target(block_height, 0, params.anchor, pow_limit=params.pow_limit)
    header = BlockHeader(
        version=1,
        height=block_height,
        prev_hash=prev_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=target,
        nonce=0,
    )
    
    block = Block(header, (cb,))
    block.header.check_pow()
    
    # Try to accept a block that will be rejected (invalid target)
    # Use a target that's too low (below minimum)
    flipped_target = max(1, params.pow_limit // 2)
    flipped_header = BlockHeader(
        version=1,
        height=block_height,
        prev_hash=prev_hash,
        merkle_root=merkle_root([cb.txid()]),
        timestamp=now,
        target=flipped_target,
        nonce=0,
    )
    flipped_block = Block(flipped_header, (cb,))
    flipped_block.header.check_pow()
    
    # Accept the block - it should be rejected
    res = chain.accept_block(flipped_block, now=now)
    assert res.status.value == "INVALID" or res.status != ChainStatus.ACCEPTED
    
    # The utxo_set_hash should be unchanged (block was rejected)
    final_hash = chain.utxo_set_hash().hex()
    assert final_hash == initial_hash, (
        f"utxo_set_hash changed after rejected block: {initial_hash} -> {final_hash}"
    )
    
    chain.close()

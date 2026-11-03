"""Replay all scenario vectors through the oracle and assert expected results."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.block import Block
from core.chain import Chain, ChainParams, ChainStatus
from core.genesis import Checkpoint


def _replay_scenario(path: Path):
    """Replay a scenario file and assert all expected results."""
    data = json.loads(path.read_text(encoding="utf-8"))
    # Build ChainParams from scenario data if checkpoints are provided.
    params = ChainParams.regtest()
    if "checkpoints" in data:
        checkpoints = [
            Checkpoint(c["height"], bytes.fromhex(c["hash"]))
            for c in data["checkpoints"]
        ]
        # Fix checkpoint 0 hash to match genesis if needed.
        # The ChainParams constructor validates that checkpoint 0 hash matches genesis.
        # If it already matches, no fixing needed. Otherwise, set it to the genesis hash.
        if checkpoints[0].height == 0 and checkpoints[0].hash != params.genesis.block_hash:
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
    chain = Chain(params, path=":memory:")
    for step in data["steps"]:
        block = Block.from_bytes(bytes.fromhex(step["block_hex"]))
        now = block.header.timestamp
        res = chain.accept_block(block, now=now)
        assert res.status.value == step["status"], (
            f"Scenario {data['name']}: expected {step['status']}, got {res.status.value} "
            f"for block {step['block_hash'][:16]}..."
        )
        assert res.reason == step["reason"], (
            f"Scenario {data['name']}: expected reason {step['reason']!r}, got {res.reason!r}"
        )
        # Check stored-or-not.
        stored = chain.get_block(block.block_hash) is not None
        assert stored == step["stored"], (
            f"Scenario {data['name']}: expected stored={step['stored']}, got {stored}"
        )
        # Check tip hash.
        tip = chain.storage.active_tip()
        if step["tip_hash"] is not None:
            assert tip is not None and tip.hash.hex() == step["tip_hash"], (
                f"Scenario {data['name']}: tip mismatch"
            )
        # Check utxo_set_hash if provided.
        if step.get("utxo_set_hash"):
            assert chain.utxo_set_hash().hex() == step["utxo_set_hash"], (
                f"Scenario {data['name']}: utxo_set_hash mismatch"
            )
    chain.close()


def test_all_scenarios():
    scenarios_dir = Path(__file__).resolve().parent.parent.parent / "vectors" / "scenarios"
    assert scenarios_dir.is_dir(), f"scenarios directory missing: {scenarios_dir}"
    scenario_files = sorted(scenarios_dir.glob("*.json"))
    assert len(scenario_files) > 0, "no scenario files found"
    for path in scenario_files:
        _replay_scenario(path)

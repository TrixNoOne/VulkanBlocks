"""Test ChainParams.mainnet() and testnet() constructors."""

from core.chain import ChainParams


def test_chainparams_mainnet():
    params = ChainParams.mainnet()
    assert params.network_tag == b"vulcan-main"
    assert params.coinbase_maturity == 100
    assert params.subsidy == 314_520_000


def test_chainparams_testnet():
    params = ChainParams.testnet()
    assert params.network_tag == b"vulcan-test"
    assert params.coinbase_maturity == 100
    assert params.subsidy == 314_520_000
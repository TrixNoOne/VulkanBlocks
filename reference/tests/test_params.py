"""Le costanti di consenso sono congelate in un solo modulo."""

import pytest

import core.block as block
import core.tx as tx
from core import params
from core.params import BLOCK_SUBSIDY, HALVING_INTERVAL, block_subsidy


def test_money_constants():
    assert params.UNITS_PER_VULCAN == 100_000_000
    assert params.BLOCK_SUBSIDY == 314_520_000
    assert params.HALVING_INTERVAL == 1_051_200
    assert params.MAX_MONEY == 32_000_000_000 * params.UNITS_PER_VULCAN
    assert params.MAX_MONEY < (1 << 63)  # deve stare in un int64
    assert isinstance(params.MAX_MONEY, int)
    assert not isinstance(params.MAX_MONEY, float)


def test_time_and_size_constants():
    assert params.COINBASE_MATURITY == 100
    assert params.MTP_WINDOW == 11
    assert params.MAX_FUTURE_DRIFT == 7_200
    assert params.MAX_BLOCK_SIZE == 1_000_000
    assert params.MAX_SCRIPT_SIZE == 10_000


def test_asert_constants():
    assert params.TARGET_SPACING == 120
    assert params.HALF_LIFE == 43_200
    # Il vecchio ritarget periodico non fa parte del consenso.
    assert not hasattr(params, "RETARGET_INTERVAL")
    assert not hasattr(params, "RETARGET_MAX_UP")
    assert not hasattr(params, "RETARGET_MAX_DOWN")
    assert not hasattr(params, "TARGET_BLOCK_TIME")


def test_target_bounds():
    assert params.MIN_TARGET == 1
    assert params.MAX_TARGET == (1 << 512) - 1


def test_genesis_constants():
    assert params.GENESIS_VERSION == 1
    assert params.GENESIS_TIMESTAMP == 1_793_318_400
    assert params.GENESIS_OUTPUT_VALUE == 0
    assert params.GENESIS_POW_LIMIT == params.MAX_TARGET >> 22
    assert params.MIN_TARGET <= params.GENESIS_POW_LIMIT < params.MAX_TARGET
    assert params.GENESIS_MESSAGE_MAIN != params.GENESIS_MESSAGE_TEST
    assert b"mainnet" in params.GENESIS_MESSAGE_MAIN
    assert b"testnet" in params.GENESIS_MESSAGE_TEST
    assert isinstance(params.GENESIS_NONCE_MAIN, int)
    assert isinstance(params.GENESIS_NONCE_TEST, int)
    assert params.GENESIS_NONCE_MAIN != params.GENESIS_NONCE_TEST
    assert len(params.GENESIS_HASH_MAIN) == 64
    assert len(params.GENESIS_HASH_TEST) == 64
    assert params.GENESIS_HASH_MAIN != params.GENESIS_HASH_TEST


def test_network_tags():
    assert params.NETWORK_MAIN == b"vulcan-main"
    assert params.NETWORK_TEST == b"vulcan-test"
    assert params.NETWORK_MAIN != params.NETWORK_TEST
    assert params.NETWORK_TAGS == {params.NETWORK_MAIN, params.NETWORK_TEST}
    assert params.SIGHASH_ALL == 1


def test_modules_reexport_the_same_objects():
    assert tx.MAX_MONEY is params.MAX_MONEY
    assert tx.MAX_SCRIPT_SIZE is params.MAX_SCRIPT_SIZE
    assert tx.COINBASE_MATURITY is params.COINBASE_MATURITY
    assert block.BLOCK_SUBSIDY is params.BLOCK_SUBSIDY
    assert block.MAX_TARGET is params.MAX_TARGET
    assert block.MTP_WINDOW is params.MTP_WINDOW
    assert block.MAX_FUTURE_DRIFT is params.MAX_FUTURE_DRIFT


# -- block_subsidy tests ---------------------------------------------------

def test_block_subsidy_at_genesis():
    assert block_subsidy(0) == BLOCK_SUBSIDY


def test_block_subsidy_just_before_first_halving():
    assert block_subsidy(HALVING_INTERVAL - 1) == BLOCK_SUBSIDY


def test_block_subsidy_at_first_halving():
    assert block_subsidy(HALVING_INTERVAL) == BLOCK_SUBSIDY >> 1
    assert block_subsidy(HALVING_INTERVAL) == BLOCK_SUBSIDY // 2


def test_block_subsidy_at_second_halving():
    assert block_subsidy(2 * HALVING_INTERVAL) == BLOCK_SUBSIDY >> 2
    assert block_subsidy(2 * HALVING_INTERVAL) == BLOCK_SUBSIDY // 4


def test_block_subsidy_zero_after_64_halvings():
    assert block_subsidy(64 * HALVING_INTERVAL) == 0
    assert block_subsidy(64 * HALVING_INTERVAL + 1) == 0
    assert block_subsidy(100 * HALVING_INTERVAL) == 0


def test_block_subsidy_last_nonzero_era():
    # L'era 63 produce BLOCK_SUBSIDY >> 63 = 0 perche' 314_520_000 < 2^63.
    # Cerchiamo l'ultima era con sussidio > 0.
    last_nonzero = None
    for era in range(64):
        if (BLOCK_SUBSIDY >> era) > 0:
            last_nonzero = era
    assert last_nonzero is not None
    assert block_subsidy(last_nonzero * HALVING_INTERVAL) > 0
    # Dopo di essa il sussidio e' 0.
    if last_nonzero + 1 < 64:
        assert block_subsidy((last_nonzero + 1) * HALVING_INTERVAL) == 0


def test_block_subsidy_all_eras_monotonically_decrease():
    subsidies = [block_subsidy(era * HALVING_INTERVAL) for era in range(65)]
    for i in range(len(subsidies) - 1):
        assert subsidies[i] >= subsidies[i + 1]
    assert subsidies[-1] == 0


def test_block_subsidy_custom_halving_interval():
    assert block_subsidy(0, halving_interval=10) == BLOCK_SUBSIDY
    assert block_subsidy(9, halving_interval=10) == BLOCK_SUBSIDY
    assert block_subsidy(10, halving_interval=10) == BLOCK_SUBSIDY >> 1
    assert block_subsidy(20, halving_interval=10) == BLOCK_SUBSIDY >> 2


def test_block_subsidy_only_integers():
    for height in [0, 1, HALVING_INTERVAL, 10 * HALVING_INTERVAL]:
        s = block_subsidy(height)
        assert isinstance(s, int)
        assert not isinstance(s, bool)


def test_block_subsidy_rejects_invalid_args():
    with pytest.raises(ValueError):
        block_subsidy(-1)
    with pytest.raises(ValueError):
        block_subsidy(True)
    with pytest.raises(ValueError):
        block_subsidy(0, halving_interval=0)
    with pytest.raises(ValueError):
        block_subsidy(0, halving_interval=-1)
    with pytest.raises(ValueError):
        block_subsidy(0, halving_interval=True)


# -- chain halving integration tests ---------------------------------------

def test_chain_rejects_stale_subsidy_after_halving():
    """Un blocco all'altezza di halving che usa il vecchio sussidio deve essere rifiutato."""
    from core.chain import Chain, ChainParams, ChainStatus
    from core.block import Block, BlockHeader, merkle_root
    from core.tx import Transaction, TxIn, TxOut, NULL_TXID, COINBASE_INDEX, encode_coinbase_height

    params_obj = ChainParams.regtest(halving_interval=1)
    chain = Chain(params_obj, path=":memory:")

    # Tip iniziale e' il genesis (height 0)
    tip = params_obj.genesis
    now = tip.header.timestamp + 120

    # Height 1 con halving_interval=1: era = 1 // 1 = 1 -> sussidio dimezzato!
    # Se il miner prova a reclamare BLOCK_SUBSIDY (vecchio sussidio), deve fallire.
    stale_coinbase = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(BLOCK_SUBSIDY, b"\x51"),),
    )
    txs = (stale_coinbase,)
    hdr = BlockHeader(
        version=1,
        height=1,
        prev_hash=tip.block_hash,
        merkle_root=merkle_root([tx.txid() for tx in txs]),
        timestamp=now,
        target=params_obj.pow_limit,
        nonce=0,
    )
    bad_block = Block(hdr, txs)
    res = chain.accept_block(bad_block, now=now)
    assert res.status == ChainStatus.INVALID
    assert "coinbase exceeds subsidy + fees" in res.reason

    # Se invece usa il sussidio dimezzato corretto, viene accettato
    correct_subsidy = block_subsidy(1, halving_interval=1)
    good_coinbase = Transaction(
        1,
        (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(1)),),
        (TxOut(correct_subsidy, b"\x51"),),
    )
    good_txs = (good_coinbase,)
    good_hdr = BlockHeader(
        version=1,
        height=1,
        prev_hash=tip.block_hash,
        merkle_root=merkle_root([tx.txid() for tx in good_txs]),
        timestamp=now,
        target=params_obj.pow_limit,
        nonce=0,
    )
    good_block = Block(good_hdr, good_txs)
    res_ok = chain.accept_block(good_block, now=now)
    assert res_ok.status == ChainStatus.ACCEPTED
    assert chain.storage.active_tip().emitted == correct_subsidy


def test_chain_regtest_cumulative_emission():
    """L'emissione cumulata lungo una serie di blocchi in regtest corrisponde alla somma attesa."""
    from core.chain import Chain, ChainParams, ChainStatus
    from core.block import Block, BlockHeader, merkle_root
    from core.tx import Transaction, TxIn, TxOut, NULL_TXID, COINBASE_INDEX, encode_coinbase_height

    # regtest con halving ogni 2 blocchi, costruiamo 5 blocchi
    halving_interval = 2
    params_obj = ChainParams.regtest(halving_interval=halving_interval)
    chain = Chain(params_obj, path=":memory:")

    expected_emission = 0
    tip_hash = params_obj.genesis.block_hash
    timestamp = params_obj.genesis.header.timestamp

    for h in range(1, 6):
        timestamp += 120
        sub = block_subsidy(h, halving_interval=halving_interval)
        expected_emission += sub
        cb = Transaction(
            1,
            (TxIn(NULL_TXID, COINBASE_INDEX, encode_coinbase_height(h)),),
            (TxOut(sub, b"\x51"),),
        )
        txs = (cb,)
        hdr = BlockHeader(
            version=1,
            height=h,
            prev_hash=tip_hash,
            merkle_root=merkle_root([tx.txid() for tx in txs]),
            timestamp=timestamp,
            target=params_obj.pow_limit,
            nonce=0,
        )
        blk = Block(hdr, txs)
        res = chain.accept_block(blk, now=timestamp)
        assert res.status == ChainStatus.ACCEPTED
        tip_hash = blk.block_hash

        active_tip = chain.storage.active_tip()
        assert active_tip.height == h
        assert active_tip.emitted == expected_emission

    # Verifica finale dell'emissione totale cumulata
    assert chain.storage.active_tip().emitted == expected_emission


"""Tests for Vulcan Base58Check address encoding."""

from core.address import (
    ADDRESS_VERSION_MAIN,
    ADDRESS_VERSION_TEST,
    AddressError,
    address_network,
    address_to_script_pubkey,
    decode_address,
    encode_address,
    hash160,
    is_valid_address,
    pubkey_to_address,
)
from core.params import NETWORK_MAIN, NETWORK_TEST
from coincurve import PrivateKey


def key(seed: int) -> PrivateKey:
    return PrivateKey(bytes([seed]) * 32)


def test_address_networks_differ():
    pub = key(1).public_key.format(compressed=True)
    main = pubkey_to_address(pub, NETWORK_MAIN)
    test = pubkey_to_address(pub, NETWORK_TEST)
    assert main != test
    assert address_network(main) == NETWORK_MAIN
    assert address_network(test) == NETWORK_TEST


def test_address_roundtrip():
    pub = key(2).public_key.format(compressed=True)
    addr = pubkey_to_address(pub, NETWORK_MAIN)
    network, payload = decode_address(addr)
    assert network == NETWORK_MAIN
    script = address_to_script_pubkey(addr)
    # script: 76 a9 14 <20-byte payload> 88 ac
    assert payload == script[3:23]
    assert is_valid_address(addr)


def test_address_script_pubkey_is_p2pkh():
    pub = key(3).public_key.format(compressed=True)
    addr = pubkey_to_address(pub, NETWORK_TEST)
    script = address_to_script_pubkey(addr)
    assert len(script) == 25
    assert script[:3] == bytes((0x76, 0xA9, 0x14))  # OP_DUP OP_HASH160 push20
    assert script[3:23] == hash160(pub)
    assert script[-2:] == bytes((0x88, 0xAC))  # OP_EQUALVERIFY OP_CHECKSIG


def test_wrong_checksum_rejected():
    pub = key(4).public_key.format(compressed=True)
    addr = pubkey_to_address(pub, NETWORK_MAIN)
    # Tamper the last base58 character (checksum area).
    tampered = addr[:-1] + ("9" if addr[-1] != "9" else "8")
    assert is_valid_address(tampered) is False
    try:
        decode_address(tampered)
    except AddressError:
        pass
    else:
        raise AssertionError("checksum mismatch not detected")


def test_wrong_network_rejected_with_expected_network():
    """Decoding a testnet address as mainnet must raise AddressError."""
    pub = key(5).public_key.format(compressed=True)
    test_addr = pubkey_to_address(pub, NETWORK_TEST)
    main_addr = pubkey_to_address(pub, NETWORK_MAIN)

    # Decoding with the wrong expected network must fail.
    try:
        decode_address(test_addr, expected_network=NETWORK_MAIN)
    except AddressError:
        pass
    else:
        raise AssertionError("testnet address accepted as mainnet")
    try:
        decode_address(main_addr, expected_network=NETWORK_TEST)
    except AddressError:
        pass
    else:
        raise AssertionError("mainnet address accepted as testnet")

    # Correct expected network still works.
    assert decode_address(test_addr, expected_network=NETWORK_TEST)[0] == NETWORK_TEST
    assert decode_address(main_addr, expected_network=NETWORK_MAIN)[0] == NETWORK_MAIN

    # is_valid_address and address_to_script_pubkey respect expected_network.
    assert is_valid_address(test_addr, expected_network=NETWORK_TEST)
    assert not is_valid_address(test_addr, expected_network=NETWORK_MAIN)
    assert is_valid_address(main_addr, expected_network=NETWORK_MAIN)
    assert not is_valid_address(main_addr, expected_network=NETWORK_TEST)

    try:
        address_to_script_pubkey(test_addr, expected_network=NETWORK_MAIN)
    except AddressError:
        pass
    else:
        raise AssertionError("testnet address script_pubkey accepted as mainnet")


def test_mainnet_node_helper_rejects_testnet_address():
    """Simulates a mainnet node-side helper that only accepts mainnet addresses."""

    def mainnet_only_script_pubkey(address: str) -> bytes:
        return address_to_script_pubkey(address, expected_network=NETWORK_MAIN)

    pub = key(6).public_key.format(compressed=True)
    main_addr = pubkey_to_address(pub, NETWORK_MAIN)
    test_addr = pubkey_to_address(pub, NETWORK_TEST)

    mainnet_only_script_pubkey(main_addr)  # OK
    try:
        mainnet_only_script_pubkey(test_addr)
    except AddressError:
        pass
    else:
        raise AssertionError("mainnet helper accepted a testnet address")


def test_unknown_version_rejected():
    # Build a raw address with a bogus version byte via the encoder internals.
    from core.address import _b58encode, double_sha256

    payload = b"\x11" * 20
    body = bytes((0xFF,)) + payload
    checksum = double_sha256(body)[:4]
    bogus = _b58encode(body + checksum)
    try:
        decode_address(bogus)
    except AddressError:
        pass
    else:
        raise AssertionError("unknown version not detected")


def test_encode_address_roundtrip():
    payload = b"\x22" * 20
    addr = encode_address(NETWORK_MAIN, payload)
    network, decoded = decode_address(addr)
    assert network == NETWORK_MAIN
    assert decoded == payload


def test_address_rejects_invalid_input():
    try:
        decode_address(123)  # type: ignore[arg-type]
    except AddressError:
        pass
    else:
        raise AssertionError("non-string input not rejected")
    assert is_valid_address("") is False
    assert is_valid_address("not an address!!!") is False

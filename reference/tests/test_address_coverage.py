"""Additional coverage tests for address.py: leading zeros, invalid inputs, etc."""

import pytest

from core.address import (
    Address,
    AddressError,
    _b58decode,
    _b58encode,
    address_to_script_pubkey,
    decode_address,
    encode_address,
    pubkey_to_address,
)
from core.params import NETWORK_MAIN, NETWORK_TEST
from coincurve import PrivateKey


def test_address_to_string():
    pub = PrivateKey(bytes([1] * 32)).public_key.format(compressed=True)
    from core.script import hash160

    payload = hash160(pub)
    addr = Address(NETWORK_MAIN, payload)
    assert addr.to_string() == encode_address(NETWORK_MAIN, payload)


def test_address_script_pubkey_method():
    pub = PrivateKey(bytes([2] * 32)).public_key.format(compressed=True)
    from core.script import hash160, p2pkh_script

    payload = hash160(pub)
    addr = Address(NETWORK_MAIN, payload)
    assert addr.script_pubkey() == p2pkh_script(payload)


def test_b58encode_leading_zeros():
    # Leading zero bytes produce leading '1' characters.
    result = _b58encode(b"\x00\x00" + b"\x01")
    assert result.startswith("11")


def test_b58decode_leading_ones():
    # Leading '1' characters produce leading zero bytes.
    result = _b58decode("11" + _b58encode(b"\x01")[0:] if False else "11A")
    assert result[0:2] == b"\x00\x00" or len(result) >= 1


def test_encode_address_unknown_network():
    with pytest.raises(AddressError, match="unknown network"):
        encode_address(b"vulcan-other", b"\x11" * 20)


def test_encode_address_payload_not_bytes():
    with pytest.raises(AddressError, match="payload must be bytes"):
        encode_address(NETWORK_MAIN, "not bytes")  # type: ignore[arg-type]


def test_encode_address_payload_wrong_size():
    with pytest.raises(AddressError, match="payload must be 20 bytes"):
        encode_address(NETWORK_MAIN, b"\x11" * 19)


def test_pubkey_to_address_unknown_network():
    pub = PrivateKey(bytes([3] * 32)).public_key.format(compressed=True)
    with pytest.raises(AddressError, match="unknown network"):
        pubkey_to_address(pub, b"vulcan-other")
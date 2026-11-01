"""Vulcan addresses: Base58Check-encoded P2PKH payloads.

Format::

    version:1 | hash160(compressed_pubkey):20 | checksum:4

``checksum`` is the first 4 bytes of ``sha256(sha256(version + payload))``.

The version byte doubles as the network prefix: mainnet and testnet use
different version bytes, so a Vulcan address is never mistaken for a Bitcoin
address (and never confused across Vulcan networks).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Tuple

from coincurve import PublicKey

from .params import NETWORK_MAIN, NETWORK_TEST, NETWORK_TAGS
from .script import hash160, p2pkh_script
from .tx import double_sha256

# Version bytes. Deliberately different from Bitcoin (mainnet 0x00, testnet
# 0x6F) so a Vulcan address is never confused with a foreign-chain address.
ADDRESS_VERSION_MAIN = 0x56  # 'V'
ADDRESS_VERSION_TEST = 0x74  # 't'

ADDRESS_VERSIONS = frozenset((ADDRESS_VERSION_MAIN, ADDRESS_VERSION_TEST))

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

# version(1) + hash160(20) + checksum(4)
ADDRESS_RAW_SIZE = 25


class AddressError(ValueError):
    """Address encoding or decoding error."""


@dataclass(frozen=True, slots=True)
class Address:
    """A parsed Vulcan address."""

    network: bytes
    payload: bytes  # 20-byte hash160 of the compressed public key

    def to_string(self) -> str:
        return encode_address(self.network, self.payload)

    def script_pubkey(self) -> bytes:
        """P2PKH script that pays to this address."""
        return p2pkh_script(self.payload)


def _b58encode(data: bytes) -> str:
    n = int.from_bytes(data, "big")
    pad = 0
    for b in data:
        if b == 0:
            pad += 1
        else:
            break
    digits = []
    while n > 0:
        n, r = divmod(n, 58)
        digits.append(BASE58_ALPHABET[r])
    return BASE58_ALPHABET[0] * pad + "".join(reversed(digits))


def _b58decode(text: str) -> bytes:
    n = 0
    for ch in text:
        if ch not in BASE58_ALPHABET:
            raise AddressError(f"invalid base58 character {ch!r}")
        n = n * 58 + BASE58_ALPHABET.index(ch)
    if n == 0:
        return b""
    length = (n.bit_length() + 7) // 8
    raw = n.to_bytes(length, "big")
    pad = 0
    for ch in text:
        if ch == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + raw


def encode_address(network: bytes, payload: bytes) -> str:
    """Base58Check-encode a 20-byte payload under a network version byte."""
    if network not in NETWORK_TAGS:
        raise AddressError("unknown network")
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise AddressError("payload must be bytes")
    payload = bytes(payload)
    if len(payload) != 20:
        raise AddressError("payload must be 20 bytes")
    version = ADDRESS_VERSION_MAIN if network == NETWORK_MAIN else ADDRESS_VERSION_TEST
    body = bytes((version,)) + payload
    checksum = double_sha256(body)[:4]
    return _b58encode(body + checksum)


def decode_address(
    text: str, expected_network: bytes | None = None
) -> Tuple[bytes, bytes]:
    """Decode a Base58Check address.

    Returns ``(network, payload)``. Validates the version byte, length and
    checksum; raises :class:`AddressError` on any problem. If
    ``expected_network`` is given, the decoded network must match it.
    """
    if not isinstance(text, str):
        raise AddressError("address must be a string")
    raw = _b58decode(text)
    if len(raw) != ADDRESS_RAW_SIZE:
        raise AddressError("address length mismatch")
    version = raw[0]
    payload = raw[1:21]
    checksum = raw[21:]
    if version not in ADDRESS_VERSIONS:
        raise AddressError("unknown address version")
    expected = double_sha256(bytes((version,)) + payload)[:4]
    if checksum != expected:
        raise AddressError("checksum mismatch")
    if version == ADDRESS_VERSION_MAIN:
        network = NETWORK_MAIN
    else:
        network = NETWORK_TEST
    if expected_network is not None and network != bytes(expected_network):
        raise AddressError(
            f"address network mismatch: expected {expected_network!r}, "
            f"got {network!r}"
        )
    return network, payload


def pubkey_to_address(pubkey: bytes, network: bytes = NETWORK_MAIN) -> str:
    """Encode a compressed public key as a P2PKH address."""
    if network not in NETWORK_TAGS:
        raise AddressError("unknown network")
    raw = PublicKey(bytes(pubkey)).format(compressed=True)
    payload = hash160(raw)
    return encode_address(network, payload)


def address_to_script_pubkey(
    address: str, expected_network: bytes | None = None
) -> bytes:
    """Return the P2PKH ``script_pubkey`` that pays to ``address``."""
    _, payload = decode_address(address, expected_network=expected_network)
    return p2pkh_script(payload)


def address_network(address: str) -> bytes:
    """Return the network tag an address belongs to."""
    network, _ = decode_address(address)
    return network


def is_valid_address(
    address: str, expected_network: bytes | None = None
) -> bool:
    try:
        decode_address(address, expected_network=expected_network)
        return True
    except AddressError:
        return False

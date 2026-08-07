"""Offline Ed25519 license verification — forgery, expiry, and tamper cases."""
import json
import time
import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import license as lic


def _b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture
def keypair(monkeypatch):
    """Ephemeral signing key; the module is pointed at its public half."""
    priv = Ed25519PrivateKey.generate()
    pub_hex = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(lic, "PUBLIC_KEY_HEX", pub_hex)
    return priv


def mint(priv, name="Test User", days=0):
    exp = int(time.time()) + days * 86400 if days else 0
    payload = json.dumps({"n": name, "e": "t@e.com", "x": exp, "p": "pro"},
                         separators=(",", ":")).encode()
    return _b64(payload) + "." + _b64(priv.sign(payload))


def test_valid_perpetual_key(keypair):
    info = lic.verify_key(mint(keypair))
    assert info and info["n"] == "Test User" and info["x"] == 0


def test_valid_time_limited_key(keypair):
    assert lic.verify_key(mint(keypair, days=14)) is not None


def test_expired_key_rejected(keypair):
    assert lic.verify_key(mint(keypair, days=-1)) is None


def test_tampered_payload_rejected(keypair):
    good = mint(keypair)
    payload_b64, sig_b64 = good.split(".", 1)
    forged = json.dumps({"n": "Forger", "e": "f@f.com", "x": 0, "p": "pro"},
                        separators=(",", ":")).encode()
    assert lic.verify_key(_b64(forged) + "." + sig_b64) is None


def test_wrong_signer_rejected(keypair):
    other = Ed25519PrivateKey.generate()
    assert lic.verify_key(mint(other)) is None


@pytest.mark.parametrize("garbage", ["", "no-dot-here", "a.b", "..", "x" * 500])
def test_garbage_keys_rejected(keypair, garbage):
    assert lic.verify_key(garbage) is None

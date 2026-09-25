"""Machine-bound keys must not travel with a copied app.

A key carrying "m" unlocks only the machine whose fingerprint hashes to it.
Keys without "m" stay valid everywhere, so every key issued before binding
keeps working.
"""
import base64
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

import license as lic


def _b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@pytest.fixture
def signer(monkeypatch):
    """Sign with a throwaway key and point the app's public key at it."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
    monkeypatch.setattr(lic, "PUBLIC_KEY_HEX", pub)

    def mint(**claims):
        payload = json.dumps(claims, separators=(",", ":")).encode()
        return _b64(payload) + "." + _b64(priv.sign(payload))
    return mint


def test_bound_key_unlocks_its_own_machine(signer, monkeypatch):
    monkeypatch.setattr(lic, "machine_id", lambda: "aaaabbbbccccdddd")
    key = signer(n="Jane", e="j@a.com", x=0, p="pro", m="aaaabbbbccccdddd")
    assert lic.verify_key(key)["n"] == "Jane"


def test_bound_key_is_dead_on_another_machine(signer, monkeypatch):
    """The point of the exercise: copying app + license.key must not work."""
    key = signer(n="Jane", e="j@a.com", x=0, p="pro", m="aaaabbbbccccdddd")
    monkeypatch.setattr(lic, "machine_id", lambda: "1111222233334444")
    assert lic.verify_key(key) is None


def test_bound_key_fails_closed_when_machine_is_unreadable(signer, monkeypatch):
    """No fingerprint must mean no unlock, or binding is trivially bypassed."""
    monkeypatch.setattr(lic, "machine_id", lambda: "")
    key = signer(n="Jane", e="j@a.com", x=0, p="pro", m="aaaabbbbccccdddd")
    assert lic.verify_key(key) is None


def test_unbound_key_still_works_anywhere(signer, monkeypatch):
    """Keys issued before machine binding must keep working."""
    key = signer(n="Old Buyer", e="o@a.com", x=0, p="pro")
    for mid in ("aaaabbbbccccdddd", "1111222233334444", ""):
        monkeypatch.setattr(lic, "machine_id", lambda mid=mid: mid)
        assert lic.verify_key(key)["n"] == "Old Buyer"


def test_expiry_still_enforced_on_bound_keys(signer, monkeypatch):
    monkeypatch.setattr(lic, "machine_id", lambda: "aaaabbbbccccdddd")
    key = signer(n="Trial", e="t@a.com", x=int(time.time()) - 60, p="pro",
                 m="aaaabbbbccccdddd")
    assert lic.verify_key(key) is None


def test_no_key_means_not_licensed(monkeypatch, tmp_path):
    """There must be no built-in fallback licence."""
    monkeypatch.setattr(lic, "LICENSE_FILE", str(tmp_path / "license.key"))
    monkeypatch.delenv("KEKA_LICENSE", raising=False)
    assert lic.load_license() == ""
    assert lic.license_info() is None
    assert lic.is_licensed() is False


def test_machine_id_is_hashed_not_raw(monkeypatch):
    """The raw OS id must never leave the machine."""
    monkeypatch.setattr(lic, "_raw_machine_id", lambda: "secret-host-uuid")
    mid = lic.machine_id()
    assert mid and "secret-host-uuid" not in mid and len(mid) == 16

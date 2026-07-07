#!/usr/bin/env python3
"""
SELLER ONLY — generate signed Auto-Keka license keys.

    python tools/gen_license.py --name "Jane Doe" --email jane@acme.com
    python tools/gen_license.py --name "Trial" --days 14        # time-limited
    python tools/gen_license.py --pubkey                        # just print the public key

On first run it creates tools/license_private.pem — the secret signing key.
KEEP IT SECRET and BACK IT UP: anyone with it can mint free licenses, and if you
lose it every key you've sold becomes unverifiable. It is git-ignored.

After creating the key once, paste the printed PUBLIC KEY into license.py's
PUBLIC_KEY_HEX, then ship the app. Give each buyer the printed LICENSE KEY.
"""

import os
import sys
import json
import time
import base64
import argparse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

HERE = os.path.dirname(os.path.abspath(__file__))
PRIV = os.path.join(HERE, "license_private.pem")


def _b64(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def load_or_create_key():
    if os.path.exists(PRIV):
        with open(PRIV, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=None)
    key = Ed25519PrivateKey.generate()
    with open(PRIV, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.PKCS8,
                                  serialization.NoEncryption()))
    os.chmod(PRIV, 0o600)
    print(f"[created a new private key at {PRIV} — keep it SECRET]\n", file=sys.stderr)
    return key


def public_hex(key):
    return key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def main():
    ap = argparse.ArgumentParser(description="Generate an Auto-Keka license key.")
    ap.add_argument("--name", help="buyer name (shown in the app)")
    ap.add_argument("--email", default="", help="buyer email")
    ap.add_argument("--days", type=int, default=0, help="validity in days (0 = perpetual)")
    ap.add_argument("--plan", default="pro", help="plan tag")
    ap.add_argument("--pubkey", action="store_true", help="just print the public key and exit")
    a = ap.parse_args()

    key = load_or_create_key()

    if a.pubkey or not a.name:
        print("PUBLIC KEY (paste into license.py → PUBLIC_KEY_HEX):")
        print("  " + public_hex(key))
        if not a.name and not a.pubkey:
            print("\n(give --name to also mint a license key)")
        return

    exp = int(time.time()) + a.days * 86400 if a.days else 0
    payload = json.dumps({"n": a.name, "e": a.email, "x": exp, "p": a.plan},
                         separators=(",", ":")).encode()
    sig = key.sign(payload)
    license_key = _b64(payload) + "." + _b64(sig)

    print("PUBLIC KEY (paste into license.py → PUBLIC_KEY_HEX):")
    print("  " + public_hex(key))
    print("\nLICENSE KEY (give to the buyer):")
    print("  " + license_key)
    if exp:
        print(f"\n(expires {time.strftime('%Y-%m-%d', time.localtime(exp))})")


if __name__ == "__main__":
    main()

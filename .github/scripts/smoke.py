"""Cross-platform smoke test — runs in CI on Linux, macOS, and Windows.

Verifies the parts that must work on every OS WITHOUT any real Keka account:
module import, tesseract OCR, BOM-safe .env parsing, and the platform helpers.
"""
import io
import os
import sys

sys.path.insert(0, os.getcwd())

import keka_common as kc
import keka_check as kck
import pytesseract
from PIL import Image, ImageDraw

print("platform     :", sys.platform)
print("tesseract_cmd:", pytesseract.pytesseract.tesseract_cmd)

# 1) tesseract OCR must actually run on this OS
img = Image.new("RGB", (170, 50), "white")
ImageDraw.Draw(img).text((14, 14), "AB7XK", fill="black")
txt = "".join(pytesseract.image_to_string(img, config="--psm 7").split())
print("OCR result   :", repr(txt))
assert txt, "tesseract produced no output — OCR broken on this OS"

# 2) PowerShell string escaping helper (Windows notifications)
assert kck._ps_str("a'b") == "'a''b'", "_ps_str escaping wrong"

# 3) headless-display helper: Linux w/o DISPLAY -> False; mac/Win -> True
disp = kck._has_display()
print("_has_display :", disp)
if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    assert disp is False, "headless Linux should report no display"

# 4) BOM-safe .env parsing (Windows editors/PowerShell add a UTF-8 BOM).
# _load_env reads kc.ENV_FILE (the per-user data dir) — point it at a scratch
# file so this never touches a real user's config when run locally.
import tempfile
bom_env = os.path.join(tempfile.mkdtemp(prefix="keka_smoke_"), ".env")
with io.open(bom_env, "w", encoding="utf-8-sig") as f:
    f.write("KEKA_BASE_URL=https://bom.keka.com\nKEKA_EMAIL=b@e.com\nKEKA_PASSWORD=p\n")
_orig_env_file = kc.ENV_FILE
kc.ENV_FILE = bom_env
try:
    parsed = kc._load_env()
finally:
    kc.ENV_FILE = _orig_env_file
assert parsed.get("KEKA_BASE_URL") == "https://bom.keka.com", f"BOM parse failed: {parsed}"
print("BOM .env parse: OK")

print("SMOKE OK")

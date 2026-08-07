"""Config (.env) parsing/merging and the history log (activity feed data)."""
import io
import os
import sys
import json

import keka_common as kc


# ── .env parsing ──────────────────────────────────────────────────────────────
def test_load_env_parses_and_strips(env_file):
    env_file.write_text(
        "# comment line\n"
        "KEKA_BASE_URL=https://acme.keka.com\n"
        'KEKA_EMAIL="quoted@acme.com"\n'
        "KEKA_PASSWORD='p@ss=word'\n"
        "MALFORMED LINE WITHOUT EQUALS\n"
        "\n",
        encoding="utf-8",
    )
    v = kc._load_env()
    assert v["KEKA_BASE_URL"] == "https://acme.keka.com"
    assert v["KEKA_EMAIL"] == "quoted@acme.com"
    assert v["KEKA_PASSWORD"] == "p@ss=word"      # '=' inside value preserved
    assert "MALFORMED LINE WITHOUT EQUALS" not in v


def test_load_env_survives_utf8_bom(env_file):
    with io.open(env_file, "w", encoding="utf-8-sig") as f:
        f.write("KEKA_BASE_URL=https://bom.keka.com\n")
    assert kc._load_env()["KEKA_BASE_URL"] == "https://bom.keka.com"


def test_load_env_missing_file_is_empty(env_file):
    assert kc._load_env() == {}


def test_update_env_merges_without_wiping(env_file):
    env_file.write_text("KEKA_EMAIL=a@b.com\nKEKA_PASSWORD=secret\n", encoding="utf-8")
    kc.update_env({"KEKA_IN_TIME": "11:00", "KEKA_PASSWORD": None})
    v = kc._load_env()
    assert v["KEKA_IN_TIME"] == "11:00"
    assert v["KEKA_PASSWORD"] == "secret"         # None must not overwrite
    assert v["KEKA_EMAIL"] == "a@b.com"


def test_update_env_creates_file_with_owner_only_perms(env_file):
    kc.update_env({"KEKA_ONBOARDED": "1"})
    assert kc._load_env()["KEKA_ONBOARDED"] == "1"
    if not sys.platform.startswith("win"):
        assert (os.stat(env_file).st_mode & 0o777) == 0o600


# ── history.jsonl ─────────────────────────────────────────────────────────────
def test_history_roundtrip(history_file):
    kc.log_history("in", "Clocked in")
    kc.log_history("out", "Clocked out")
    hist = kc.read_history()
    assert [h["kind"] for h in hist] == ["in", "out"]
    assert all({"ts", "time", "date", "msg"} <= set(h) for h in hist)


def test_history_skips_corrupt_lines(history_file):
    kc.log_history("in", "good entry")
    with open(history_file, "a", encoding="utf-8") as f:
        f.write("{corrupt json\n\n")
    kc.log_history("out", "after corruption")
    hist = kc.read_history()
    assert [h["msg"] for h in hist] == ["good entry", "after corruption"]


def test_history_tail_limit(history_file):
    for i in range(30):
        kc.log_history("info", f"entry {i}")
    hist = kc.read_history(n=10)
    assert len(hist) == 10
    assert hist[-1]["msg"] == "entry 29"          # newest kept, oldest dropped


def test_history_missing_file_is_empty(history_file):
    assert kc.read_history() == []

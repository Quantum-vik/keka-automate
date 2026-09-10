"""CLI dispatch in keka_ui.main() — the safe, side-effect-free flags that also
back the CI build smoke test. No GUI, no punch, no server here."""
import pytest

import keka_ui
import keka_common as kc


def _run(argv, monkeypatch):
    monkeypatch.setattr("sys.argv", ["auto-keka"] + argv)
    keka_ui.main()


def test_version_flag(capsys, monkeypatch):
    _run(["--version"], monkeypatch)
    out = capsys.readouterr().out.strip()
    assert out == f"Auto-Keka {kc.APP_VERSION}"


def test_version_short_flag(capsys, monkeypatch):
    _run(["-v"], monkeypatch)
    assert capsys.readouterr().out.strip() == f"Auto-Keka {kc.APP_VERSION}"


def test_help_flag(capsys, monkeypatch):
    _run(["--help"], monkeypatch)
    out = capsys.readouterr().out
    assert "Auto-Keka" in out
    assert "--serve" in out and "--punch" in out


def test_unknown_flag_exits_2_not_gui(capsys, monkeypatch):
    # The important guarantee: an unrecognized flag must NOT fall through to
    # launching the dashboard window (which used to hang headless contexts).
    with pytest.raises(SystemExit) as e:
        _run(["--bogus"], monkeypatch)
    assert e.value.code == 2
    assert "unknown option" in capsys.readouterr().err

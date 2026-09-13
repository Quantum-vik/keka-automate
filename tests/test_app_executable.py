"""Which file the app relaunches itself with (schedules, autostart, punch buttons).

A compiled onefile build used sys.executable, which Nuitka sets to
'<temp extraction dir>/python' — never a real file — so every schedule it wrote
silently never ran. These fake the layout with temp files; the release smoke
test checks the real compiled binaries on each OS.
"""
import os
from types import SimpleNamespace

import pytest

import keka_common as kc
import keka_ui


@pytest.fixture
def layout(tmp_path):
    """<home>/Apps/Auto-Keka (the launcher) + /tmp/onefile_1/keka_ui.bin."""
    apps = tmp_path / "Apps"
    apps.mkdir()
    launcher = apps / "Auto-Keka"
    launcher.write_text("")
    extract = tmp_path / "onefile_123"
    extract.mkdir()
    (extract / "keka_ui.bin").write_text("")
    return SimpleNamespace(apps=apps, launcher=str(launcher), extract=extract,
                           phantom=str(extract / "python"))   # Nuitka's sys.executable


def onefile(**kw):
    return SimpleNamespace(onefile=True, **kw)


def test_source_run_keeps_the_interpreter():
    assert kc._resolve_app_executable(False, None, "keka_ui.py", "/venv/bin/python") == "/venv/bin/python"


def test_onefile_uses_what_the_user_launched(layout):
    compiled = onefile(original_argv0=layout.launcher, containing_dir=str(layout.apps))
    got = kc._resolve_app_executable(True, compiled, str(layout.extract / "keka_ui.bin"), layout.phantom)
    assert got == layout.launcher
    assert got != layout.phantom


def test_onefile_never_returns_a_file_in_the_extraction_dir(layout):
    # Even if argv[0] names the (existing, but temporary) extracted binary.
    compiled = onefile(original_argv0=None, containing_dir=None)
    got = kc._resolve_app_executable(True, compiled, str(layout.extract / "keka_ui.bin"), layout.phantom)
    assert got == layout.phantom      # nothing better found → unchanged, not the temp binary


def test_relative_argv0_resolves_against_containing_dir(layout, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)       # cwd is not where the binary lives
    compiled = onefile(original_argv0="./Auto-Keka", containing_dir=str(layout.apps))
    assert kc._resolve_app_executable(True, compiled, "", layout.phantom) == layout.launcher


def test_bare_name_found_on_path(layout, monkeypatch):
    os.chmod(layout.launcher, 0o755)
    monkeypatch.setenv("PATH", f"{layout.apps}{os.pathsep}{os.environ.get('PATH', '')}")
    compiled = onefile(original_argv0="Auto-Keka", containing_dir=None)
    assert kc._resolve_app_executable(True, compiled, "", layout.phantom) == layout.launcher


def test_standalone_app_bundle_uses_argv0(tmp_path):
    exe = tmp_path / "Auto-Keka.app" / "Contents" / "MacOS" / "Auto-Keka"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    compiled = SimpleNamespace(onefile=False, original_argv0=None, containing_dir=str(tmp_path))
    phantom = str(exe.parent / "python")
    assert kc._resolve_app_executable(True, compiled, str(exe), phantom) == str(exe)


def test_app_path_flag_prints_it(capsys, monkeypatch):
    monkeypatch.setattr(kc, "APP_EXECUTABLE", "/opt/Auto-Keka")
    monkeypatch.setattr("sys.argv", ["auto-keka", "--app-path"])
    keka_ui.main()
    assert capsys.readouterr().out.strip() == "/opt/Auto-Keka"


def test_native_linux_schedule_launches_app_executable(fake_linux_tools, monkeypatch):
    monkeypatch.setattr(kc, "APP_EXECUTABLE", "/opt/Auto-Keka")
    monkeypatch.setattr(kc.sys, "platform", "linux")
    assert kc.install_schedule_native("09:00", "18:00") is True
    table = fake_linux_tools["crontab"].read_text()
    assert "/opt/Auto-Keka --punch in --scheduled" in table
    assert "python" not in table.split(">>")[0]

"""keka_doctor's native-window probe — faked `gi` modules, so it runs the same
on every OS and never touches GTK."""
import sys
import types

import keka_doctor


def _fake_gi(available):
    """A stand-in `gi` whose require_version accepts only (namespace, version)
    pairs in `available`, raising ValueError like PyGObject does otherwise."""
    gi = types.ModuleType("gi")

    def require_version(ns, v):
        if (ns, v) not in available:
            raise ValueError(f"Namespace {ns} not available for version {v}")
    gi.require_version = require_version
    return gi


def test_no_gi_means_no_native_window(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", None)     # import gi -> ImportError
    assert keka_doctor._native_window_backend() is None


def test_prefers_webkit2_41(monkeypatch):
    gi = _fake_gi({("Gtk", "3.0"), ("WebKit2", "4.1"), ("WebKit2", "4.0")})
    monkeypatch.setitem(sys.modules, "gi", gi)
    assert keka_doctor._native_window_backend() == "WebKit2 4.1"


def test_falls_back_to_webkit2_40(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", _fake_gi({("Gtk", "3.0"), ("WebKit2", "4.0")}))
    assert keka_doctor._native_window_backend() == "WebKit2 4.0"


def test_gi_without_webkit_typelib(monkeypatch):
    monkeypatch.setitem(sys.modules, "gi", _fake_gi({("Gtk", "3.0")}))
    assert keka_doctor._native_window_backend() is None

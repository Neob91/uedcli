"""Tests for `uedcli.tool_assets` — the PACKAGE-RELATIVE tool-install asset anchors
(dev/docs/direction/projects-and-config.md 2026-07-17 20:58 §6; replaced the deleted `repo_paths.py` repo-root machinery)."""
from pathlib import Path

from uedcli import tool_assets


def test_tool_root_is_the_dir_holding_the_package():
    root = tool_assets.tool_root()
    assert (root / "uedcli" / "tool_assets.py").is_file()   # …/Tools/uedcli/ holds the package


def test_uned_dir_is_under_the_tool_root():
    assert tool_assets.uned_dir() == tool_assets.tool_root() / "uned"
    assert (tool_assets.uned_dir() / "docker-compose.yml").is_file()   # the compose dir, for real


def test_umodel_dir_is_a_sibling_of_the_tool_root():
    # umodel deliberately ESCAPES the package-relative anchor: Tools/umodel_win32 is a SIBLING of
    # Tools/uedcli (the packaging item inherits this exception explicitly).
    assert tool_assets.umodel_dir() == tool_assets.tool_root().parent / "umodel_win32"


def test_anchors_are_cwd_independent(tmp_path, monkeypatch):
    # Acceptance §10.4 (offline): editor-driving verbs must find the compose dir/UED22/umodel from
    # ANY cwd — the anchors derive from __file__, never the cwd or an env var.
    before = (tool_assets.tool_root(), tool_assets.uned_dir(), tool_assets.umodel_dir())
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UEDCLI_REPO_ROOT", raising=False)   # retired env must not matter
    assert (tool_assets.tool_root(), tool_assets.uned_dir(), tool_assets.umodel_dir()) == before
    assert before[0].is_absolute()


def test_editor_compose_dir_uses_the_package_relative_anchor(tmp_path, monkeypatch):
    from uedcli import editor
    monkeypatch.chdir(tmp_path)                             # cwd-independent
    assert editor._compose_dir() == str(tool_assets.uned_dir())
    assert Path(editor._compose_dir()).is_dir()

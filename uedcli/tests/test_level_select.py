"""Unit tests for `level_select.resolve_level` — the ambient-level resolver. Since 2026-07-20 the
level is the environment variable `$UEDCLI_LEVEL` (a bare name), passed IN to `resolve_level`
(mirroring `config.resolve_project(env_project=…)`); the old machine-local `current-level` pointer +
`set_selected`/`get_selected` are gone (they were a cross-session race — decisions 2026-07-20)."""
import pytest

from uedcli import level_select
from uedcli.level_select import LevelSelectionError


def test_resolve_returns_the_env_level(tmp_path):
    maps = tmp_path / "maps"
    (maps / "20_AireGardens").mkdir(parents=True)
    assert level_select.resolve_level(env_level="20_AireGardens", maps_dir=maps) == "20_AireGardens"


def test_resolve_errors_when_env_unset(tmp_path):
    (tmp_path / "maps").mkdir()
    with pytest.raises(LevelSelectionError, match="no level"):
        level_select.resolve_level(env_level=None, maps_dir=tmp_path / "maps")


@pytest.mark.parametrize("blank", ["", "   ", "\t", "  \n"])
def test_resolve_treats_blank_env_as_unset(tmp_path, blank):
    (tmp_path / "maps").mkdir()
    with pytest.raises(LevelSelectionError, match="no level"):
        level_select.resolve_level(env_level=blank, maps_dir=tmp_path / "maps")


def test_resolve_strips_surrounding_whitespace(tmp_path):
    maps = tmp_path / "maps"
    (maps / "a").mkdir(parents=True)
    assert level_select.resolve_level(env_level="  a \n", maps_dir=maps) == "a"


def test_resolve_errors_on_a_nonexistent_level(tmp_path):
    (tmp_path / "maps").mkdir()
    with pytest.raises(LevelSelectionError, match="does not exist"):
        level_select.resolve_level(env_level="ghost", maps_dir=tmp_path / "maps")


@pytest.mark.parametrize("value", ["level/a", "a/b", "x\\y"])
def test_resolve_hints_the_bare_name_grammar_on_a_slash(tmp_path, value):
    # A common mistake is copying the flag's KIND/NAME shape into the bare-name env var; the error
    # names the grammar rather than the opaque "invalid level name".
    (tmp_path / "maps").mkdir()
    with pytest.raises(LevelSelectionError, match="bare level name, not KIND/NAME"):
        level_select.resolve_level(env_level=value, maps_dir=tmp_path / "maps")


@pytest.mark.parametrize("value", [".locks", "..", "."])
def test_resolve_rejects_a_dotted_or_traversal_name(tmp_path, value):
    # Dotted/`.`/`..` names are rejected by _check_safe_level (a dotted level would collide with the
    # self-ignored maps/.locks lock home).
    (tmp_path / "maps").mkdir()
    with pytest.raises(LevelSelectionError, match="invalid level name"):
        level_select.resolve_level(env_level=value, maps_dir=tmp_path / "maps")


def test_list_levels_still_enumerates_trunk_dirs(tmp_path):
    maps = tmp_path / "maps"
    for n in ("b", "A", "c"):
        (maps / n / "actors").mkdir(parents=True)
    (maps / ".locks").mkdir()                              # dotted lock home is skipped
    (maps / "not_a_level").mkdir()                         # no actors/ → not a level
    assert level_select.list_levels(maps) == ["A", "b", "c"]

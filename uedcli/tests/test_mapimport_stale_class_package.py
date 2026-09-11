"""`mapimport._resolve_actor_class` — the Unreal1/UT99 stale-import-package class fallback.

An original (1998/Gold) Unreal `.unr`'s own import table states some classes' home package as
`UnrealI` when the shipped System files actually define them in `UnrealShare.u` (`Eightball`,
`ASMD`, `Barrel`, `TriggerLight`, …). Genuine shipped content — every map on the retail corpus hits
it — not corruption; the real 1998 engine resolves it via a global by-name class lookup. Board item:
`dev/docs/board/done/unreal1-ut99-map-import-stale-class-package/overview.md`.

The unit tests below fake `pkg`/`index` so the fallback logic is checked without any package
bytes. The corpus test at the bottom decodes the real retail maps and is SKIPPED (not failed) where
the gitignored, user-supplied Unreal Gold assets aren't installed
(`dev/scripts/install-unreal-assets.sh --with-maps`).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli import mapimport
from uedcli.classindex import ClassIndex
from uedcli.upackage import SchemaError, load_package

from .conftest import unreal_maps_root, unreal_system_root

MAP_NAMES = ["Bluff", "DmDeck16", "DmCurse", "DmMorbias", "DmTundra", "Dig", "Dark", "DasaPass"]


# ── unit: the fallback logic in isolation ───────────────────────────────────────────────────────

class _FakePkg:
    """Stands in for `upackage.Package` — `_resolve_actor_class` only calls `object_path`."""

    def __init__(self, stated_fqcn):
        self._fqcn = stated_fqcn

    def object_path(self, _cls_ref):
        return self._fqcn


class _FakeIndex:
    """Stands in for `classindex.ClassIndex` — `_resolve_actor_class` only calls `class_exists`
    and `bare_to_fqcn`."""

    def __init__(self, *, exists=(), bare_map=None):
        self._exists = set(exists)
        self._bare = bare_map or {}

    def class_exists(self, fqcn):
        return fqcn in self._exists

    def bare_to_fqcn(self):
        return self._bare


def test_exact_package_match_is_returned_unchanged():
    pkg = _FakePkg("Engine.Light")
    index = _FakeIndex(exists={"Engine.Light"})
    assert mapimport._resolve_actor_class(pkg, index, 1) == "Engine.Light"


def test_stale_package_falls_back_to_the_unique_bare_match():
    pkg = _FakePkg("UnrealI.Eightball")
    index = _FakeIndex(bare_map={"eightball": {"UnrealShare.Eightball"}})
    assert mapimport._resolve_actor_class(pkg, index, 1) == "UnrealShare.Eightball"


def test_stale_package_ambiguous_collision_prefers_unrealshare():
    pkg = _FakePkg("UnrealI.TriggerLight")
    index = _FakeIndex(bare_map={
        "triggerlight": {"Engine.TriggerLight", "UnrealShare.TriggerLight"}})
    assert mapimport._resolve_actor_class(pkg, index, 1) == "UnrealShare.TriggerLight"


def test_ambiguous_collision_with_no_unrealshare_candidate_keeps_the_stated_path():
    """No observed real redirect lands anywhere but `UnrealShare`; an unmodeled ambiguity is left
    as the stated (still-wrong) path so the caller's own descent check fails loudly rather than
    guessing a class."""
    pkg = _FakePkg("UnrealI.Foo")
    index = _FakeIndex(bare_map={"foo": {"Engine.Foo", "SomeOther.Foo"}})
    assert mapimport._resolve_actor_class(pkg, index, 1) == "UnrealI.Foo"


def test_unresolvable_bare_name_keeps_the_stated_path():
    pkg = _FakePkg("UnrealI.Ghost")
    index = _FakeIndex()
    assert mapimport._resolve_actor_class(pkg, index, 1) == "UnrealI.Ghost"


def test_unresolvable_ref_returns_none():
    pkg = _FakePkg(None)
    index = _FakeIndex()
    assert mapimport._resolve_actor_class(pkg, index, 1) is None


def test_is_actor_export_checks_descent_against_the_resolved_class():
    """Proves the wiring, not just the helper: `_is_actor_export` must ask `descends_from` about
    the FALLBACK-resolved FQCN, never the stale stated one."""
    class Pkg:
        exports = [{"cls": 1}]

        def object_path(self, _ref):
            return "UnrealI.Eightball"

    class Index:
        def class_exists(self, fqcn):
            return False

        def bare_to_fqcn(self):
            return {"eightball": {"UnrealShare.Eightball"}}

        def descends_from(self, fqcn, base):
            assert fqcn == "UnrealShare.Eightball"
            assert base == mapimport.ENGINE_ACTOR
            return True

    assert mapimport._is_actor_export(Pkg(), Index(), 0) is True


# ── corpus: the real retail maps, skipped where the assets aren't installed ────────────────────

def _resolver(sys_root: Path):
    def resolve(name: str) -> str | None:
        p = sys_root / f"{name}.u"
        return str(p) if p.is_file() else None
    return resolve


def _class_index(sys_root: Path) -> ClassIndex:
    paths = {p.stem.casefold(): str(p) for p in sys_root.glob("*.u")}
    return ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})


@pytest.mark.parametrize("name", MAP_NAMES)
def test_retail_unreal_gold_maps_pass_the_actor_class_descent_gate(name):
    """Every map in the retail Unreal Gold corpus hits the stale-package redirect (a different
    class each time). `level import` must get PAST the class-descent gate for all of them — the
    unrelated, separately-tracked `brush_of` model decode gap (older package-v61 struct layout) is
    NOT in scope here and is tolerated."""
    sys_root = unreal_system_root()
    maps_root = unreal_maps_root()
    dx = maps_root / f"{name}.unr"
    if not (sys_root / "Engine.u").is_file() or not dx.is_file():
        pytest.skip("uned/UnrealAssets System/Maps not present "
                    "(dev/scripts/install-unreal-assets.sh --with-maps)")
    pkg = load_package(str(dx), name=name)
    index = _class_index(sys_root)
    schema = mapimport.ImportSchema(resolver=_resolver(sys_root))
    try:
        mapimport.import_map(pkg, index, schema)
    except SchemaError as e:
        msg = str(e)
        assert "does not descend from" not in msg, (
            f"{name}: still hits the class-descent gate — {e}")
        # The ONE known-acceptable residual: `brush_of`'s model decode has never been extended to
        # package v61 (Unreal Gold's map version). Any OTHER SchemaError here — e.g. a property
        # schema failure from render_actor resolving a wrong-package fqcn — is a real regression,
        # not a tolerated gap, so it must fail loudly rather than being masked by a loose check.
        assert "brush_of" in msg and "truncated map body" in msg, (
            f"{name}: hit an unexpected SchemaError, not the known package-v61 brush_of gap — {e}")

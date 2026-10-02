"""uedcli/effective_props_native.py -- gui-inspector-props-payload-redesign spec §1/§2's own
Python-side bridge (population walk + actor.props flattening + typed-field statedness), tested
against the same golden fixture the shared-rust-core item's own resolve_class_json/
resolve_actor_props_json tests use (uedcli/tests/fixtures/resolve_golden/nyc_bar.json)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import ued22_root

uedcli_native = pytest.importorskip("uedcli_native")

from uedcli import effective_props_native  # noqa: E402 -- after importorskip, matches
                                            # test_resolve_native.py's own convention.

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "resolve_golden" / "nyc_bar.json"
_SUBSET = (Path(__file__).resolve().parents[2] / "dev" / "docs" / "spikes"
           / "2026-09-06-nycbar-n59-light-apply-movers" / "golden" / "subset" / "maps"
           / "02_nyc_bar" / "actors")


def _resolver():
    root = ued22_root()
    files = {p.stem.casefold(): p for p in root.glob("*.u")}

    def resolve(name: str) -> str | None:
        p = files.get(name.casefold())
        return str(p) if p is not None else None
    return resolve


@pytest.mark.slow
def test_populate_for_class_pulls_in_the_transitive_import_closure():
    ctx = uedcli_native.PyResolutionContext()
    effective_props_native._populate_for_class("DeusEx.Karkian", ctx, _resolver())
    assert ctx.has_package("DeusEx")
    assert ctx.has_package("Engine")   # Karkian's Super chain crosses into Engine.Pawn/Engine.Actor
    assert ctx.has_package("Core")     # ...and Core.Object at the root


@pytest.mark.slow
def test_populate_for_class_raises_schema_error_for_a_missing_package():
    from uedcli.uprops import SchemaError

    ctx = uedcli_native.PyResolutionContext()
    with pytest.raises(SchemaError, match="NoSuchPackage"):
        effective_props_native._populate_for_class("NoSuchPackage.SomeClass", ctx, lambda name: None)


@pytest.mark.slow
def test_populate_for_class_failure_does_not_poison_the_shared_context_for_other_classes():
    """gui-inspector-props-payload-redesign spec §2's own long-lived, per-level resolve_ctx (Task
    3a) is shared across every actor in the level, and across every later /scene request against
    the same trunk generation. One actor's class transitively referencing a genuinely missing
    package must not degrade every OTHER actor sharing this ctx too -- `_populate_for_class` never
    calls `ctx.poison()` for exactly this reason (see its own docstring below); this pins that
    ruling as a regression test, not just prose."""
    from uedcli.uprops import SchemaError

    resolver = _resolver()

    def flaky_resolver(name: str) -> str | None:
        return None if name == "NoSuchPackage" else resolver(name)

    ctx = uedcli_native.PyResolutionContext()
    with pytest.raises(SchemaError, match="NoSuchPackage"):
        effective_props_native._populate_for_class("NoSuchPackage.SomeClass", ctx, flaky_resolver)

    # A different, resolvable class on the SAME ctx must still resolve normally afterward -- proof
    # the earlier failure left no cross-class blast radius.
    effective_props_native._populate_for_class("DeusEx.Karkian", ctx, flaky_resolver)
    assert ctx.has_package("DeusEx")
    cr = json.loads(uedcli_native.resolve_class_json(ctx, "DeusEx.Karkian"))
    assert cr["class"]["props"]


@pytest.mark.slow
def test_resolve_actor_props_native_matches_golden_actor():
    from uedcli.t3dtree import load_actor_body

    name = "PoolTableLight0"
    text = (_SUBSET / name / "actor.t3d").read_text()
    actor = load_actor_body(text, name)

    ctx = uedcli_native.PyResolutionContext()
    sparse, note = effective_props_native.resolve_actor_props_native(actor, ctx, _resolver(), {})

    golden = json.loads(_GOLDEN.read_text())
    assert note is None
    assert sparse == golden["actors"][name]["sparse"]


@pytest.mark.slow
def test_resolve_actor_props_native_degrades_on_unresolvable_class():
    from uedcli.model import Actor

    actor = Actor(name="Ghost0", cls="DeusEx.NoSuchClassAtAll", props=[])
    ctx = uedcli_native.PyResolutionContext()
    sparse, note = effective_props_native.resolve_actor_props_native(actor, ctx, _resolver(), {})

    assert sparse == {}
    assert note == ("actor 'Ghost0': schema unavailable (DeusEx.NoSuchClassAtAll) — cannot resolve "
                    "effective props (class not found: DeusEx.NoSuchClassAtAll)")


def test_resolve_actor_props_native_degrades_when_resolver_is_none():
    from uedcli.model import Actor

    actor = Actor(name="Ghost0", cls="DeusEx.Karkian", props=[])
    ctx = uedcli_native.PyResolutionContext()
    sparse, note = effective_props_native.resolve_actor_props_native(actor, ctx, None, {})

    assert sparse == {}
    assert note is not None and "class index has no schema resolver" in note


@pytest.mark.slow
def test_resolve_actor_props_native_memoizes_resolve_class_json_per_fqcn(monkeypatch):
    """Final fix wave, Finding 4: resolve_ctx's own per-FQCN Rust-side cache
    (resolutions_performed()) already amortizes across actors of a repeated class, but
    resolve_class_json's own JSON serialize+parse round-trip was still redone per ACTOR. A
    class_cache shared across actors must skip that round-trip on a repeated class -- pinned here
    by counting real calls into resolve_class_json directly, not just resolutions_performed()."""
    from uedcli.model import Actor

    calls: list[str] = []
    real_resolve_class_json = uedcli_native.resolve_class_json

    def counting_resolve_class_json(ctx, fqcn):
        calls.append(fqcn)
        return real_resolve_class_json(ctx, fqcn)

    monkeypatch.setattr(uedcli_native, "resolve_class_json", counting_resolve_class_json)

    ctx = uedcli_native.PyResolutionContext()
    resolver = _resolver()
    class_cache: dict = {}
    a1 = Actor(name="Karkian0", cls="DeusEx.Karkian", props=[])
    a2 = Actor(name="Karkian1", cls="DeusEx.Karkian", props=[])

    effective_props_native.resolve_actor_props_native(a1, ctx, resolver, class_cache)
    effective_props_native.resolve_actor_props_native(a2, ctx, resolver, class_cache)

    assert calls == ["DeusEx.Karkian"]   # the second actor's own class reused the cached parse

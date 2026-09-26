"""PyO3-binding tests for `resolve_class_json`/`resolve_actor_props_json` (`uedcli_native`) —
Task 7 of `.superpowers/sdd/shared-rust-core-for-class-schema-resolution/`. Compares the native
Rust resolver against `tests/fixtures/resolve_golden/nyc_bar.json`, the hand-audited real-corpus
golden fixture Task 6 built.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from .conftest import ued22_root   # a plain helper function, NOT a pytest fixture -- call directly.
from .fixtures.resolve_golden import build_golden   # `_flatten_actor_props`/`_flatten_struct_text` --
                                                       # see `test_resolve_actor_props_json_matches_
                                                       # golden_actor`'s docstring for why this test
                                                       # needs them too, beyond the Location/MainScale/
                                                       # PostScale correction.

uedcli_native = pytest.importorskip("uedcli_native")

_GOLDEN = Path(__file__).resolve().parent / "fixtures" / "resolve_golden" / "nyc_bar.json"

_SUBSET = (Path(__file__).resolve().parents[2] / "dev" / "docs" / "spikes"
           / "2026-09-06-nycbar-n59-light-apply-movers" / "golden" / "subset" / "maps"
           / "02_nyc_bar" / "actors")

_WASM_SCRIPT = Path(__file__).resolve().parent / "fixtures" / "resolve_golden" / "wasm_resolve_check.mjs"
_WASM_DIR = Path(__file__).resolve().parents[2] / "web" / "src" / "wasm"   # gitignored build output
                                                                            # (Task 9 Step 6);
                                                                            # `bin/ensure_wasm.sh`.


def _ctx_with_ued22() -> "uedcli_native.PyResolutionContext":
    root = ued22_root()
    ctx = uedcli_native.PyResolutionContext()
    ctx.add_package("DeusEx", (root / "DeusEx.u").read_bytes())
    ctx.add_package("Engine", (root / "Engine.u").read_bytes())
    ctx.add_package("Core", (root / "core.u").read_bytes())  # real on-disk name is lowercase
                                                              # `core.u` (confirmed via `ls
                                                              # uned/UED22/`); the PACKAGE NAME
                                                              # argument stays "Core".
    return ctx


def _typed_field_entries(actor) -> list[tuple[str, str]]:
    """The caller-side pre-computation the brief's "model.Actor crossing the PyO3 boundary" note
    (Step 4) puts on the CALLER, not `resolve_actor_props`/`resolve_actor_props_json` themselves:
    `Location`/`MainScale`/`PostScale` are parsed OUT of `actor.props` by `model.py`'s T3D parser
    (into `actor.location`/`actor.main_scale`/`actor.post_scale`), so they never appear in
    `actor.props` at all — reusing `effective_props._resolve_typed_fields` (the SAME per-axis/
    per-member STATEDNESS logic `normalize._stated_axes`/`_stated_scale_members` implements, and
    the same primitive `tests/fixtures/resolve_golden/build_golden.py`'s own `_typed_field_leaves`
    calls) to compute exactly the stated leaves and appending them to the flat props list BEFORE
    calling `resolve_actor_props_json` — never passing `actor.props` alone (see Task 7 brief's
    Step 6 correction: passing `actor.props` alone would drop every stated `Location=`/
    `MainScale=`/`PostScale=` leaf, and every actor in this golden subset states `Location=`, so
    the result would never match the golden).

    `default_value` (the OTHER thing `_resolve_typed_fields` computes) is not needed here — only
    `stored_value` feeds the flat list — so a throwaway `ClassCtx` supplies `load_defaults=lambda:
    {}` rather than resolving the class's real default tags (`load_schema`/`load_members`/
    `load_enums` are never invoked for these three fields either, matching `build_golden.py`'s own
    comment on `_typed_field_leaves`)."""
    from uedcli import effective_props
    from uedcli.propedit.base import ClassCtx

    ctx = ClassCtx(cls=actor.cls, load_schema=lambda: {}, load_defaults=lambda: {},
                   load_members=lambda p: [], load_enums=lambda p: ())
    typed_props = effective_props._resolve_typed_fields(actor, ctx, {})

    out: list[tuple[str, str]] = []

    def walk(prefix: str, ep) -> None:
        if isinstance(ep, effective_props.StructProp):
            for m in ep.members:
                walk(f"{prefix}.{m.name}", m)
        elif ep.stored_value is not None:
            out.append((prefix, ep.stored_value))

    for p in typed_props:
        walk(p.name, p)
    return out


@pytest.mark.slow   # real (non-fake) corpus test -- deselected by default (pytest.ini's own
                     # ruling, owner ruling 2026-09-12); run with `bin/test -m slow`.
def test_resolve_class_json_matches_golden_fragment():
    ctx = _ctx_with_ued22()
    result = json.loads(uedcli_native.resolve_class_json(ctx, "DeusEx.Karkian"))
    golden = json.loads(_GOLDEN.read_text())
    assert result == golden["classes"]["DeusEx.Karkian"]  # the WHOLE {class, types} object -- do
    # NOT hardcode a guessed prop (e.g. "props[0] is a Rotator") -- assert the WHOLE structure
    # (including `types`, Task 4 Step 5.5's closure) against Task 6's real, hand-audited golden
    # fragment for this class instead.


@pytest.mark.slow
def test_resolve_actor_props_json_matches_golden_actor():
    """`PoolTableLight0` (a `DeusEx.PoolTableLight`, real nyc_bar subset actor) states BOTH a
    `Location=` line AND a `Rotation=(Yaw=-16488)` line. Two DIFFERENT flattening gaps between raw
    `actor.props` and the `(dotted_path, leaf_text)` pairs `resolve_actor_props_json` requires
    showed up building this test, not just the one the Task 7 brief's own note flagged:

    1. `Location`/`MainScale`/`PostScale` (the brief's flagged gap) never appear in `actor.props`
       at all — `model.py`'s T3D parser pulls them OUT into `actor.location`/`actor.main_scale`/
       `actor.post_scale` + their `_text` siblings. Fixed per the task's ruling: reuse
       `effective_props._resolve_typed_fields` (`_typed_field_entries` below) to recompute the
       stated leaves and append them.

    2. ANY OTHER struct-typed top-level prop stated inline — e.g. `Rotation` here — stays IN
       `actor.props`, but as ONE raw blob under the bare key (`("Rotation", "(Yaw=-16488)")`), not
       pre-split into `("Rotation.Yaw", "-16488")`. `resolve_actor_props` (`resolve.rs`) does exact
       dotted-path lookups against the class's own `leaf_paths()` with NO struct-text parsing of
       its own (confirmed by reading `resolve.rs`'s `resolve_actor_props` — Task 5's own doc
       comment: "keep only `actor_props` entries whose path exists in that shape", nothing about
       splitting struct text) — so passing `actor.props` unflattened silently drops `Rotation.Yaw`
       (an "orphan path" skip, not an error), which a run against the real corpus surfaced as a
       genuine golden mismatch (measured: `result` missing `"Rotation.Yaw": "-16488"` that
       `golden["actors"]["PoolTableLight0"]["sparse"]` has). This is the SAME "caller pre-computes,
       `resolve_actor_props` stays agnostic to where an entry came from" architecture the brief's
       own note establishes for the typed fields — just not spelled out for the general case in
       the brief text. Fixed here by reusing `build_golden.py`'s own already-tested
       `_flatten_actor_props`/`_flatten_struct_text` (the exact functions that built this golden's
       `actors` section in the first place) against the class's own native-resolved shape
       (`resolve_class_json`), rather than re-deriving the flattening rule by hand.
    """
    from uedcli.t3dtree import load_actor_body

    name = "PoolTableLight0"
    text = (_SUBSET / name / "actor.t3d").read_text()
    actor = load_actor_body(text, name)

    ctx = _ctx_with_ued22()
    cr = json.loads(uedcli_native.resolve_class_json(ctx, actor.cls))
    flat = build_golden._flatten_actor_props(actor.props, cr)
    actor_props = list(flat.items()) + _typed_field_entries(actor)
    result = json.loads(
        uedcli_native.resolve_actor_props_json(ctx, actor.name, actor.cls, actor_props)
    )
    golden = json.loads(_GOLDEN.read_text())
    assert result == golden["actors"][name]


@pytest.mark.slow
def test_resolve_class_json_raises_resolution_error_for_unresolvable_class():
    ctx = _ctx_with_ued22()
    with pytest.raises(uedcli_native.ResolutionError):
        uedcli_native.resolve_class_json(ctx, "DeusEx.NoSuchClassAtAll")


@pytest.mark.slow
def test_resolve_actor_props_json_degrades_to_note_for_unresolvable_class():
    ctx = _ctx_with_ued22()
    result = json.loads(
        uedcli_native.resolve_actor_props_json(ctx, "SomeActor0", "DeusEx.NoSuchClassAtAll", [])
    )
    assert result["note"] is not None
    assert result["sparse"] == {}


@pytest.mark.slow
def test_resolving_same_class_n_times_walks_super_chain_once():
    root = ued22_root()
    ctx = uedcli_native.PyResolutionContext()
    ctx.add_package("DeusEx", (root / "DeusEx.u").read_bytes())
    ctx.add_package("Engine", (root / "Engine.u").read_bytes())
    ctx.add_package("Core", (root / "core.u").read_bytes())
    for _ in range(5):
        uedcli_native.resolve_class_json(ctx, "DeusEx.Karkian")
    assert ctx.resolutions_performed() == 1   # cache hit on calls 2-5, per Task 4 Step 1


@pytest.mark.slow
def test_repeated_scene_requests_reuse_context_without_reparsing():
    """Two `resolve_class_json`/`resolve_actor_props_json` calls against the SAME context --
    simulating two `/scene` requests in one server session -- must not re-add the package or
    re-walk the Super chain for a class already resolved on the first request."""
    ctx = _ctx_with_ued22()

    uedcli_native.resolve_class_json(ctx, "DeusEx.Karkian")
    uedcli_native.resolve_actor_props_json(ctx, "Karkian0", "DeusEx.Karkian", [])
    assert ctx.has_package("DeusEx")
    resolved_after_first_request = ctx.resolutions_performed()

    uedcli_native.resolve_class_json(ctx, "DeusEx.Karkian")
    uedcli_native.resolve_actor_props_json(ctx, "Karkian1", "DeusEx.Karkian", [])
    assert ctx.has_package("DeusEx")
    assert ctx.resolutions_performed() == resolved_after_first_request


@pytest.mark.slow
def test_wasm_resolve_class_matches_native_byte_for_byte():
    """spec §6's determinism requirement: the WASM path (Task 9, `resolveWasm.test.ts`) and the
    native PyO3 path (this file) must produce byte-identical JSON for the same `(fqcn, packages)`
    input. Shells out to `node` running `wasm_resolve_check.mjs` against the built
    `web/src/wasm/` artifact -- skipped (not failed) if `node` or that artifact aren't present,
    since this test crosses both the Python-extension and the Docker-WASM build boundaries,
    neither of which `pytest.importorskip("uedcli_native")` alone covers."""
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    if not (_WASM_DIR / "resolve_wasm_bg.wasm").exists():
        pytest.skip("resolve-wasm artifact not built -- run bin/ensure_wasm.sh")

    root = ued22_root()
    fqcn = "DeusEx.Karkian"
    result = subprocess.run(
        ["node", str(_WASM_SCRIPT), fqcn,
         str(root / "DeusEx.u"), str(root / "Engine.u"), str(root / "core.u")],
        capture_output=True, text=True,   # text=True -- capture_output alone yields bytes, never
    )                                      # `==` to resolve_class_json's str return.
    assert result.returncode == 0, result.stderr

    native = uedcli_native.resolve_class_json(_ctx_with_ued22(), fqcn)
    assert result.stdout.strip() == native

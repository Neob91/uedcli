"""Independent post-verify of a written .dx (spec: save/apply MUST re-read the bytes on disk).
The offline UCC `.dx`→Level export lives in store_export (one shared seam — base/theirs/seed/
post-verify all use it); `verify_dx_matches` asserts the export's `normalize.compare_view` equals
the intended level's.

The comparison is `compare_view`, NOT `canonical_level_hash`: the hash is a schema-free identity of
the authored bytes (and the preview build-cache key), while the compare must resolve BOTH sides to
their EFFECTIVE TYPED VALUES — every property's stored value if present, else the class default,
decoded by its declared type — because UnrealEd's export omits whatever equals the class default.
That needs the game's class schema + defaults, which is why `defaults` is a required argument with
no fallback (see `classdefaults`)."""
from __future__ import annotations

from dataclasses import dataclass

from .model import Level
from .normalize import CompareView, compare_view
from .store_export import export_dx_level, export_dx_t3d  # noqa: F401  (export_dx_t3d re-exported for callers/tests)
from .typedprops import key_text


@dataclass(frozen=True, kw_only=True)
class VerifyResult:
    ok: bool
    message: str = ""


def _first_diff(got: CompareView, expected: CompareView) -> str:
    """The FIRST concrete difference between the built map (`got`) and the intended level
    (`expected`), reading the SAME `compare_view` the equality check read — so the diagnostic can
    never point at noise the compare already ignores, nor miss a difference it does not. Turns
    'the levels differ' into an actionable 'actor X differs on property P: built … / intended …'
    (the black-box-materialize fix).

    It names the PROPERTY, not a line number, because the compare is over typed values rather than
    text; each side is shown as the text it authored, or — when it states nothing — as the class
    default it falls through to, which is usually the actual explanation."""
    g, e = got.actors, expected.actors
    only_e = sorted(set(e) - set(g))
    if only_e:
        return f"actor {only_e[0]!r} is in the intended level but MISSING from the built map"
    only_g = sorted(set(g) - set(e))
    if only_g:
        return f"actor {only_g[0]!r} is in the built map but NOT in the intended level"
    for n in sorted(g):
        gv, ev = g[n], e[n]
        if gv == ev:
            continue
        if gv.cls != ev.cls:
            return (f"actor {n!r} differs in CLASS: built {gv.cls!r} / intended {ev.cls!r}")
        key = gv.diff_key(ev)
        if key is not None:
            name = gv.spelled.get(key) or ev.spelled.get(key) or key_text(key)
            return (f"actor {n!r} differs on property {name}:\n"
                    f"    built:    {gv.describe(key, name)}\n"
                    f"    intended: {ev.describe(key, name)}")
        if gv.brush != ev.brush:
            gl, el = gv.brush.splitlines(), ev.brush.splitlines()
            for i in range(max(len(gl), len(el))):
                a = gl[i] if i < len(gl) else "<absent>"
                b = el[i] if i < len(el) else "<absent>"
                if a != b:
                    return (f"actor {n!r} differs in GEOMETRY at line {i + 1}:\n"
                            f"    built:    {a.strip()}\n    intended: {b.strip()}")
        # Defensive: unreachable while `ActorValues.__eq__` compares exactly cls + brush +
        # `diff_key`, all three checked above — it exists so a future compared field cannot turn a
        # real mismatch into a silent "the levels differ but nothing is different" message.
        return f"actor {n!r} differs"
    if got.order != expected.order:
        for i in range(max(len(got.order), len(expected.order))):
            a = got.order[i] if i < len(got.order) else "<absent>"
            b = expected.order[i] if i < len(expected.order) else "<absent>"
            if a != b:
                return f"actor ORDER differs at position {i}: built {a!r} vs intended {b!r}"
    return "the compare views differ but no per-actor/order diff found (a canonicalization mismatch?)"


def verify_dx_matches(*, container: str, dx_path: str, expected: Level, defaults,
                      qualify_driver=None) -> VerifyResult:
    """Compare the map actually written at `dx_path` against the `expected` level.

    `defaults` is a `classdefaults.ClassDefaults` — REQUIRED, no default and no fallback. Both
    sides resolve every property to its effective TYPED value against the real class schema +
    defaults; substituting "assume zero" for a class that cannot be resolved is the very bug the
    typed compare removes, so an unresolvable class raises `uprops.SchemaError` (naming the actor
    and the class) instead."""
    got = export_dx_level(container, dx_path)
    if qualify_driver is not None:
        from .qualify import (qualify_live_level,          # local import: qualify imports
                              requalify_classes_to_loaded,  # editor/driver, which verify.py
                              _read_loaded_classes)         # otherwise has no need of
        qualify_live_level(got, qualify_driver)
        # Reconcile `expected`'s classes to the SAME live loaded-class set — by BARE name, INCLUDING
        # an already-qualified class. Since offline ingest qualification (classindex) now stores an
        # FQCN in the trunk, `expected` arrives FQCN; the older `qualify_level_classes` would SKIP a
        # dotted class, leaving `expected` on the OFFLINE pick while `got` carries the LIVE pick — a
        # false mismatch if those ever differ. `requalify_classes_to_loaded` maps both sides to the
        # live pick, so H3 stays live-vs-live. It also still handles a LEGACY bare `expected` (older
        # stash/prefab content, or a `--tree` box hand-edited bare) — the backstop that made
        # auditing every creation site unnecessary (GPT-5.4 review, 2026-06-21).
        requalify_classes_to_loaded(expected, _read_loaded_classes(qualify_driver))
    got_view = compare_view(got, defaults=defaults)
    expected_view = compare_view(expected, defaults=defaults)
    if got_view == expected_view:
        return VerifyResult(ok=True)
    return VerifyResult(ok=False,
                        message=f"post-verify mismatch: on-disk {dx_path} does not match the "
                                f"intended level — {_first_diff(got_view, expected_view)}")

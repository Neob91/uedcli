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


def _drop_editor_cameras(got: Level, expected: Level) -> None:
    """The editor SPAWNS viewport `Engine.Camera` actors during the build (LIGHT APPLY / viewport
    setup) that the trunk never authored — a commandlet/GUI-editor artifact, not level content. Drop
    any `Camera` in `got` that `expected` does not contain: an authored camera IS in the trunk by
    name, so this removes only the editor's own spawns and never real content. Mutates `got`."""
    editor_spawned = [n for n, a in got.actors.items()
                      if (a.cls or "").rsplit(".", 1)[-1].casefold() == "camera"
                      and n not in expected.actors]
    for n in editor_spawned:
        del got.actors[n]
    if editor_spawned:
        got.order = [n for n in got.order if n in got.actors]


def decode_dx_level_offline(host_dx_path: str, *, index, schema) -> Level:
    """Decode a built `.dx`/`.unr` FILE into a `Level` OFFLINE — no editor. The map file already
    carries every qualifier the editor's `MAP EXPORT` strips: texture refs are qualified IMPORTS and
    each actor's class is a fully-qualified export ref, so `mapimport` reads them straight from the
    package tables. This is what lets the post-verify skip the fragile editor round-trip (`MAP EXPORT`
    + `OBJ DEPENDENCIES` texture-qualify, which can time out and mis-match a brush to its dump block).

    `index` is a `classindex.ClassIndex` over the game `.u` (typing/struct/array member decode);
    `schema` a `mapimport.ImportSchema`. Raises `upackage.SchemaError` on a corrupt/truncated map
    (naming the file), never a bare struct/IndexError."""
    from . import mapimport, upackage
    from .model import parse_t3d
    from .normalize import level_order, normalize_level
    from pathlib import Path
    pkg = upackage.load_package(host_dx_path, name=Path(host_dx_path).stem)
    level = parse_t3d(mapimport.import_map(pkg, index, schema))
    # `MAP EXPORT`/`import_map` write a BARE `Class=`; recover each actor's FQCN from the `.dx`'s own
    # export class ref (the class the editor actually built the actor with — authoritative).
    for i, e in enumerate(pkg.exports):
        if pkg.name_of_ref(e["cls"]) == "Class":
            continue
        name = pkg.names[e["nm"]]
        fqcn = pkg.object_path(e["cls"])
        if fqcn and name in level.actors:
            level.actors[name].cls = fqcn
    level.order = level_order(level)
    normalize_level(level)
    return level


def verify_dx_matches(*, dx_path: str, expected: Level, defaults, index, schema,
                      ignore: frozenset[tuple[str, str]] = frozenset()) -> VerifyResult:
    """Compare the map at HOST path `dx_path` against the `expected` level, decoding it OFFLINE
    (`decode_dx_level_offline` — no editor MAP EXPORT / OBJ DEPENDENCIES).

    `defaults` is a `classdefaults.ClassDefaults` — REQUIRED, no default and no fallback. Both sides
    resolve every property to its effective TYPED value against the real class schema + defaults;
    substituting "assume zero" for a class that cannot be resolved is the very bug the typed compare
    removes, so an unresolvable class raises `uprops.SchemaError` (naming the actor + class)."""
    got = decode_dx_level_offline(dx_path, index=index, schema=schema)
    _drop_editor_cameras(got, expected)
    got_view = compare_view(got, defaults=defaults, ignore=ignore)
    expected_view = compare_view(expected, defaults=defaults, ignore=ignore)
    if got_view == expected_view:
        return VerifyResult(ok=True)
    return VerifyResult(ok=False,
                        message=f"post-verify mismatch: on-disk {dx_path} does not match the "
                                f"intended level — {_first_diff(got_view, expected_view)}")

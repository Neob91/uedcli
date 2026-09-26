"""Production bridge from uedcli_native's resolve_class_json/resolve_actor_props_json (built by the
shared-rust-core item, already merged) to /scene's own per-actor sparse map --
gui-inspector-props-payload-redesign spec §1/§2. Supersedes effective_props.py's own
resolve_actor_props for the /scene route -- that function's whole-tree walk stays unused now (the
CLI/write-path/radii resolvers this pass explicitly leaves alone don't call it either; see this
plan's Global Constraints). Pure: takes a model.Actor + a uedcli_native.PyResolutionContext + a
package resolver, returns the sparse dict[str, str] /scene ships -- no FastAPI/scene-payload
knowledge here, mirroring effective_props.py's own module docstring."""
from __future__ import annotations

import json

from . import effective_props
from .propedit.base import ClassCtx, _dequote
from .propedit.paths import _text_key_ident
from .propedit.structtext import split_struct_text
from .typedprops import split_index
from .uprops import SchemaError


def _populate_for_class(fqcn: str, ctx, resolver) -> None:
    """Pushes fqcn's own package plus its transitive Class/Struct/Enum-typed import closure into
    ctx (spec §2/§3's `_populate_for_class`-shaped helper) -- an import-table read per newly
    discovered package, not resolution work (spec §4: "computing a closure is cheap"). Raises
    uprops.SchemaError when a needed package isn't on the search path; resolve_actor_props_native's
    own except-clause degrades this the same way effective_props.resolve_actor_props's class-level
    try/except already does today (`effective_props.py:208-224`).

    **Deliberately does NOT call `ctx.poison()` on this abort path** (controller ruling: `poison()`
    is a whole-context, permanent degrade -- once set, `has_package`/`add_package`/`resolve_class`
    all fail for EVERY package and class, not just the one whose closure walk aborted, per
    `uedcli-native/resolve-core/src/resolve.rs:352-362`'s own doc comment). Task 3a's `resolve_ctx`
    is a long-lived, per-level singleton shared across every actor and every later /scene request
    against the same trunk generation (Global Constraints) -- poisoning it for one actor's missing-
    package class would silently break props resolution for every OTHER actor in the level too, for
    the rest of the session, a real regression from today's per-class `ctx_cache` isolation. Safe
    to skip here specifically: this BFS only ever calls `ctx.package_imports(name)` (walking a
    package's own children into `frontier`) AFTER that package is already fully added, so aborting
    on a resolver miss never leaves an already-added package's own import closure half-walked --
    the concern `poison()`'s doc comment exists for. (`add_package`'s OWN internal parse-failure
    path, inside the already-built dependency, still poisons unconditionally on a genuinely
    malformed `.u` file -- that stays as-is; out of this plan's scope to change, and a different,
    more severe failure mode than an ordinary missing-package miss.) Pinned by
    `test_populate_for_class_failure_does_not_poison_the_shared_context_for_other_classes` below."""
    from .native_ext import import_native
    uedcli_native = import_native()

    pkg_name = fqcn.split(".", 1)[0]
    frontier = [pkg_name]
    seen = {pkg_name}
    while frontier:
        name = frontier.pop()
        if not ctx.has_package(name):
            path = resolver(name)
            if path is None:
                raise SchemaError(f"package {name!r} not found on the schema search path")
            with open(path, "rb") as f:
                buf = f.read()
            try:
                ctx.add_package(name, buf)
            except uedcli_native.ResolutionError as e:
                raise SchemaError(str(e)) from e
        for imp in ctx.package_imports(name):
            if imp not in seen:
                seen.add(imp)
                frontier.append(imp)


def _flatten_struct_text(prefix: str, text: str, struct_type: str, types: dict, out: dict) -> None:
    """One raw T3D struct-literal blob (e.g. `"(Yaw=-16488)"`) -> its own dotted-path leaves, walked
    against `types`' resolved shape. Real, member-wise text drilling -- `split_struct_text` is the
    same partial-literal parser `effective_props._raw_stored_text` already uses."""
    pairs = split_struct_text(text) or split_struct_text(_dequote(text))
    if pairs is None:
        return
    shape = types.get(struct_type)
    members = {m["name"].casefold(): m for m in shape["members"]} if shape else {}
    for k, v in pairs:
        base, idx = _text_key_ident(k)
        m = members.get(base)
        if m is None:
            continue
        mpath = f"{prefix}.{m['name']}"
        mkind = m["kind"]
        if mkind == "struct":
            _flatten_struct_text(mpath, v, m["struct_type"], types, out)
        elif mkind == "array":
            ip = f"{mpath}.{idx if idx is not None else 0}"
            etype_key = m["element_type"]
            etype_shape = types.get(etype_key)
            if etype_shape is not None and etype_shape.get("kind") == "struct":
                _flatten_struct_text(ip, v, etype_key, types, out)
            else:
                out[ip] = v
        elif "array_dim" in m:
            out[f"{mpath}.{idx if idx is not None else 0}"] = v
        else:
            out[mpath] = v


def _flatten_actor_props(props: list[tuple[str, str]], cr: dict) -> dict[str, str]:
    """actor.props' raw (bare-key, T3D-text) pairs -> the flat dotted-path pairs
    resolve_actor_props_json needs -- one raw struct-text blob (`Rotation=(Yaw=-16488)`) becomes one
    entry per real leaf (`Rotation.Yaw`), walked against `cr`'s own resolved shape
    (`json.loads(resolve_class_json(...))`). An orphan top-level name (not on this class's own
    schema) is silently skipped, matching spec §2's rule."""
    out: dict[str, str] = {}
    top = {p["name"].casefold(): p for p in cr["class"]["props"]}
    for k, v in props:
        base, idx = split_index(k)
        p = top.get(base.casefold())
        if p is None:
            continue
        kind = p["kind"]
        if kind == "struct":
            _flatten_struct_text(p["name"], v, p["struct_type"], cr["types"], out)
        elif kind == "array":
            i = idx if idx is not None else 0
            path = f"{p['name']}.{i}"
            if "element_kind" in p:
                out[path] = v
            else:
                etype_key = p["element_type"]
                etype_shape = cr["types"].get(etype_key)
                if etype_shape is not None and etype_shape.get("kind") == "struct":
                    _flatten_struct_text(path, v, etype_key, cr["types"], out)
                else:
                    out[path] = v
        else:
            out[p["name"]] = v
    return out


def _typed_field_entries(actor) -> list[tuple[str, str]]:
    """Location/MainScale/PostScale's own STATED leaves -- these three never appear in actor.props
    at all (model.py's T3D parser pulls them into actor.location/main_scale/post_scale instead), so
    `_flatten_actor_props` (which only walks actor.props) never sees them. Reuses
    effective_props._resolve_typed_fields (the same per-axis/per-member statedness logic
    normalize._stated_axes/_stated_scale_members implements) to compute exactly the stated leaves --
    the STATEDNESS half the spec says stays Python, moved to this caller (spec §2). A throwaway
    ClassCtx supplies only load_defaults=lambda: {} since only stored_value feeds this list here --
    resolve_class_json already supplies the real per-class default for whatever's left unstated."""
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


def resolve_actor_props_native(actor, resolve_ctx, resolver, class_cache: dict
                               ) -> tuple[dict[str, str], str | None]:
    """/scene's own entry point (spec §2): resolves actor.cls's shape (via resolve_class_json,
    populated by _populate_for_class), flattens actor.props against it (_flatten_actor_props) plus
    the typed-field statedness half (_typed_field_entries), then resolves the flat sparse map via
    resolve_actor_props_json. A whole-class failure (missing package, unresolvable class, malformed
    schema, or -- the same convention `_class_ctx_for`'s own missing-resolver guard used in
    `serve/scene.py` -- no resolver at all) degrades to ({}, note) instead of raising, matching
    effective_props.py:208-224's own contract byte-for-byte (single quotes around actor_name via
    Python's own !r, never Rust's debug format).

    `class_cache` memoizes resolve_class_json's PARSED result per FQCN: resolve_ctx already caches
    the underlying Rust-side class resolution per FQCN internally, but the JSON serialize (Rust) +
    json.loads (Python) round-trip was still repeated for every ACTOR of a repeated class -- measured
    ~47% of the per-actor cost on a real class (55KB of JSON). Caller-owned, same lifetime as
    resolve_ctx itself (`serve/app.py`'s `LevelContext.class_cache_ref`, reset alongside
    `resolve_ctx_ref`) -- never a process-global."""
    from .native_ext import import_native
    uedcli_native = import_native()

    try:
        if resolver is None:
            raise SchemaError(f"{actor.cls}: class index has no schema resolver -- cannot resolve "
                              f"effective props")
        _populate_for_class(actor.cls, resolve_ctx, resolver)
        cr = class_cache.get(actor.cls)
        if cr is None:
            cr = json.loads(uedcli_native.resolve_class_json(resolve_ctx, actor.cls))
            class_cache[actor.cls] = cr
    except (SchemaError, uedcli_native.ResolutionError) as e:
        return {}, (f"actor {actor.name!r}: schema unavailable ({actor.cls}) — cannot resolve "
                    f"effective props ({e})")
    flat = _flatten_actor_props(actor.props, cr)
    flat.update(_typed_field_entries(actor))
    actor_props = list(flat.items())
    result = json.loads(uedcli_native.resolve_actor_props_json(
        resolve_ctx, actor.name, actor.cls, actor_props))
    return result["sparse"], result["note"]

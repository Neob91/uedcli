"""One-off corpus-capture script: builds `nyc_bar.json`, the hand-audited golden fixture Tasks 7
and 10 compare `resolve_class_json`/`resolve_actor_props_json` (native) and `resolveClass` (WASM)
against, field-for-field. See `.superpowers/sdd/shared-rust-core-for-class-schema-resolution/
task-6-brief.md` for the full spec this implements -- this is real glue code hand-assembling the
Rust port's wire shape from EXISTING, already-working Python primitives
(`uprops.uclass.resolve_class_properties`, `uprops.values.resolve_class_defaults`/
`_decode_struct_bin_at`, `propedit.effective_value`'s sibling primitives), not a new resolver and
not a byte-exact reimplementation of `resolve.rs`.

Run: `.venv/bin/python3 uedcli/tests/fixtures/resolve_golden/build_golden.py` from the repo root.
Writes `nyc_bar.json` next to this script.
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(_ROOT))

from uedcli import effective_props
from uedcli.effective_props_native import _flatten_actor_props, _flatten_struct_text
from uedcli.normalize import is_computed_key
from uedcli.propedit.base import ClassCtx, HARD_REJECT, _dequote
from uedcli.t3dtree import load_actor_body
from uedcli.uprops import SchemaError
from uedcli.uprops.uclass import resolve_class_properties
from uedcli.uprops.ufield import enum_values, struct_members
from uedcli.uprops.values import (
    CLI_STYLE, PT_STRUCT, _decode_struct_bin_at, _pkg_for_owner,
    render_default_tag, resolve_class_default_tags, resolve_class_defaults,
    resolve_enum_names, resolve_type_export, struct_member_schema,
)
from uedcli.upackage import load_package

# ── corpus wiring ────────────────────────────────────────────────────────────────────────────

_UED22 = _ROOT / "uned" / "UED22"
_SUBSET = (_ROOT / "dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/golden/subset/"
                   "maps/02_nyc_bar/actors")
_OUT = Path(__file__).resolve().parent / "nyc_bar.json"

_PATHS = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}


def _resolver(name: str) -> str | None:
    return _PATHS.get(name.casefold())


def _load(pkg_name: str, pkgs: dict) -> "uedcli.upackage.Package":
    if pkg_name not in pkgs:
        path = _resolver(pkg_name)
        if path is None:
            raise SchemaError(f"package {pkg_name!r} not found on the schema search path")
        pkgs[pkg_name] = load_package(path, name=pkg_name)
    return pkgs[pkg_name]


# ── shared vocabulary (mirrors resolve-core/src/resolve.rs and effective_props.py exactly) ─────

_SCALAR_KIND = {
    "IntProperty": "int", "FloatProperty": "float", "BoolProperty": "bool",
    "ByteProperty": "byte", "NameProperty": "name", "StrProperty": "string",
}

_EXCLUDED_TOP_KINDS = ("ArrayProperty", "PointerProperty", "ObjectProperty", "ClassProperty")

_EXCLUDED_STRUCT_MEMBER_KINDS = ("ObjectProperty", "ClassProperty")

_TYPED_FIELD_ORDER = ("location", "mainscale", "postscale")


class ClassResolveError(Exception):
    """Task 4 Step 6.5's own hard-fail rule: one unresolvable leaf fails the WHOLE class resolve.
    Wraps the real `SchemaError` so the outer per-class loop can record it in
    `whole_class_failures` instead of letting it look like a script bug."""


# ── struct/enum type identity (Task 4 Step 5's outer-based rule; Step 1.5's bug-bypass) ────────

def _type_identity_key(tp, ti: int) -> str:
    """`package.outer.name`, `outer` read off the type's OWN export record (never
    `prop.owner.split(".", 1)[0]`, `serve/scene.py`'s `_struct_members_via`/`_enum_names_via` own
    bug for a struct-nested-in-struct case) -- mirrors `resolve.rs`'s `type_identity_key` exactly.
    `nm` is read as a raw name-table index (never `Package.name_of_ref`, which resolves a signed
    OBJECT ref and silently misreads a raw index -- the v4 spec's own documented tool-use bug);
    `outer` IS a signed ref, so `name_of_ref` is correct there."""
    e = tp.exports[ti - 1]
    bare_name = tp.names[e["nm"]]
    outer_ref = e["outer"]
    outer_name = tp.name_of_ref(outer_ref) if outer_ref != 0 else None
    if outer_name is not None and outer_name != "Object":
        return f"{tp.name}.{outer_name}.{bare_name}"
    return f"{tp.name}.{bare_name}"


def _collect_enum_type(tp, ti: int, types_out: dict) -> str:
    key = _type_identity_key(tp, ti)
    if key not in types_out:
        types_out[key] = {"kind": "enum", "values": list(enum_values(tp, ti))}
    return key


def _collect_struct_type(prop, container_pkg, pkgs: dict, types_out: dict,
                         in_progress: set) -> str:
    """`prop` is a `StructProperty` (top-level or a struct member) -- inserts its own struct type
    (and, transitively, every struct/enum type reached through ITS members, Task 4 Step 5.5) into
    `types_out`, keyed by `_type_identity_key`. `container_pkg` is the package `prop` itself was
    decoded from (the fallback `_pkg_for_owner` needs for a bare, struct-member `owner`) -- the
    SAME correct resolution `uprops.values.struct_member_schema` already uses; Step 1.5's bug lives
    only in `serve/scene.py`'s OWN reimplementation of this, which this script never calls."""
    dp = _pkg_for_owner(prop.owner, container_pkg, resolver=_resolver, _pkgs=pkgs)
    tp, ti = resolve_type_export(dp, prop.type_ref, "Struct", resolver=_resolver, _pkgs=pkgs)
    key = _type_identity_key(tp, ti)
    if key in types_out:
        return key
    if key in in_progress:
        raise SchemaError(f"cyclic struct member reference at {key}")
    in_progress.add(key)
    members = struct_members(tp, ti, owner=prop.type_name or prop.name)
    type_members = []
    for m in members:
        tm = _member_type_shape(m, tp, pkgs, types_out, in_progress)
        if tm is not None:
            type_members.append(tm)
    types_out[key] = {"kind": "struct", "members": type_members}
    return key


def _member_type_shape(m, container_pkg, pkgs: dict, types_out: dict,
                       in_progress: set) -> dict | None:
    """One struct member's own `TypeMember` (Task 4 Step 5.5) -- `None` for an excluded kind
    (dropped from the type's own shape the same way it's dropped from a decoded default)."""
    if m.kind in _EXCLUDED_STRUCT_MEMBER_KINDS:
        return None
    if m.kind == "StructProperty":
        key = _collect_struct_type(m, container_pkg, pkgs, types_out, in_progress)
        if m.array_dim > 1:
            return {"kind": "array", "name": m.name, "array_dim": m.array_dim, "element_type": key}
        return {"kind": "struct", "name": m.name, "struct_type": key}
    if m.kind == "ByteProperty" and m.type_ref != 0:
        dp = _pkg_for_owner(m.owner, container_pkg, resolver=_resolver, _pkgs=pkgs)
        tp, ti = resolve_type_export(dp, m.type_ref, "Enum", resolver=_resolver, _pkgs=pkgs)
        key = _collect_enum_type(tp, ti, types_out)
        if m.array_dim > 1:
            return {"kind": "array", "name": m.name, "array_dim": m.array_dim, "element_type": key}
        return {"kind": "enum", "name": m.name, "enum_type": key}
    if m.kind in _SCALAR_KIND:
        out = {"kind": _SCALAR_KIND[m.kind], "name": m.name}
        if m.array_dim > 1:
            out["array_dim"] = m.array_dim
        return out
    raise SchemaError(f"unsupported struct member kind {m.kind} ({m.name})")


# ── Step 4.6: struct/array default_value -- the bare-keyed JSON tree, NOT T3D text ─────────────

def _decode_bare_tree_at(value_pkg, members_pkg, members, raw: bytes, start: int, *, pkgs: dict):
    """Reduced-port sibling of `uprops.values._decode_struct_bin_at`/`_struct_tree_at` targeting
    the bare-keyed JSON tree shape Task 4 Step 4.6 specifies (never `render_default_tag`'s
    T3D-spelled `Name(i)=...` text): a scalar/enum member keys under its bare name; a member with
    `array_dim > 1` keys under ONE bare-name key to a JSON list (one entry per element, never
    collapsed); a nested struct member recurses to a nested dict; an excluded-kind member
    (`_EXCLUDED_STRUCT_MEMBER_KINDS`) still has its bytes consumed (cursor correctness) but its
    pair is dropped from the assembled dict."""
    out: dict = {}
    p = start
    for m in members:
        if m.kind == "StructProperty":
            tp, inner = struct_member_schema(members_pkg, m, resolver=_resolver, _pkgs=pkgs)
            if m.array_dim > 1:
                items = []
                for _ in range(m.array_dim):
                    sub, p = _decode_bare_tree_at(value_pkg, tp, inner, raw, p, pkgs=pkgs)
                    items.append(sub)
                out[m.name] = items
            else:
                sub, p = _decode_bare_tree_at(value_pkg, tp, inner, raw, p, pkgs=pkgs)
                out[m.name] = sub
            continue
        excluded = m.kind in _EXCLUDED_STRUCT_MEMBER_KINDS
        one = m if m.array_dim == 1 else dataclasses.replace(m, array_dim=1)
        if m.array_dim > 1:
            items = []
            for _ in range(m.array_dim):
                pairs, p = _decode_struct_bin_at(value_pkg, members_pkg, [one], raw, p,
                                                 resolver=_resolver, _pkgs=pkgs, style=CLI_STYLE)
                items.append(pairs[0][1])
            if not excluded:
                out[m.name] = items
        else:
            pairs, p = _decode_struct_bin_at(value_pkg, members_pkg, [one], raw, p,
                                             resolver=_resolver, _pkgs=pkgs, style=CLI_STYLE)
            if not excluded:
                out[m.name] = pairs[0][1]
    return out, p


# ── Step 1's own zero-value fallback (per-kind, NOT a uniform "0"/"") ───────────────────────────

def _zero_default(prop, container_pkg, pkgs: dict):
    if prop.kind == "BoolProperty":
        return "False"
    if prop.kind in ("IntProperty", "FloatProperty"):
        return "0"
    if prop.kind == "ByteProperty":
        if prop.type_ref != 0:
            dp = _pkg_for_owner(prop.owner, container_pkg, resolver=_resolver, _pkgs=pkgs)
            names = resolve_enum_names(prop, dp, resolver=_resolver, _pkgs=pkgs)
            return names[0] if names else "0"
        return "0"
    if prop.kind in ("NameProperty", "ObjectProperty", "ClassProperty"):
        return "None"
    if prop.kind == "StrProperty":
        return ""
    if prop.kind == "StructProperty":
        tp, members = struct_member_schema(container_pkg, prop, resolver=_resolver, _pkgs=pkgs)
        out = {}
        for m in members:
            if m.kind in _EXCLUDED_STRUCT_MEMBER_KINDS:
                continue
            z = _zero_default(m, tp, pkgs)
            out[m.name] = [z] * m.array_dim if m.array_dim > 1 else z
        return out
    raise SchemaError(f"unsupported prop kind for zero default: {prop.kind} ({prop.name})")


# Location/Scale/SheerRate/SheerAxis's SEPARATE hardcoded fallback table (Step 1, restated) --
# NOT the generic `_zero_default` rule above.
def _typed_field_fallback_tree(name_lower: str) -> dict:
    if name_lower == "location":
        return {"X": "0", "Y": "0", "Z": "0"}
    if name_lower in ("mainscale", "postscale"):
        return {"Scale": {"X": "1", "Y": "1", "Z": "1"}, "SheerRate": "0", "SheerAxis": "SHEER_ZX"}
    raise AssertionError(f"not a TYPED_FIELDS name: {name_lower}")


def _canonicalize_typed_scale_sheer_axis(tree: dict, prop, container_pkg, pkgs: dict) -> dict:
    """`MainScale`/`PostScale`'s own `SheerAxis` member: a *real* declared default decodes through
    the generic per-member struct decode above, which (matching `CLI_STYLE`) renders a struct
    BYTE member as its plain ordinal, never an enum name. This is the one deliberate exception
    (spec's `Engine.Brush.MainScale` worked example) -- canonicalize IN PLACE, no-op if the member
    is absent, its text isn't a bare ordinal, or the ordinal is out of the enum's own range."""
    text = tree.get("SheerAxis")
    if not isinstance(text, str) or not text.strip().lstrip("-").isdigit():
        return tree
    ordinal = int(text.strip())
    tp, members = struct_member_schema(container_pkg, prop, resolver=_resolver, _pkgs=pkgs)
    m = next((mm for mm in members if mm.name.casefold() == "sheeraxis"), None)
    if m is None:
        return tree
    dp = _pkg_for_owner(m.owner, tp, resolver=_resolver, _pkgs=pkgs)
    names = resolve_enum_names(m, dp, resolver=_resolver, _pkgs=pkgs)
    if ordinal < len(names):
        tree = dict(tree)
        tree["SheerAxis"] = names[ordinal]
    return tree


# ── Task 4 Steps 4/4.5/6/8/9: one class's own `{"class": ..., "types": ...}` ────────────────────

def _leaf_default(prop, name_lower: str, idx: int, container_pkg, tags: dict, pkgs: dict):
    entry = tags.get((name_lower, idx))
    if entry is None:
        return _zero_default(prop, container_pkg, pkgs)
    tag_pkg, tag = entry
    if prop.kind == "StructProperty":
        if tag.ptype != PT_STRUCT:
            raise SchemaError(f"{prop.name}: expected a struct default, got ptype {tag.ptype}")
        tp, members = struct_member_schema(tag_pkg, prop, resolver=_resolver, _pkgs=pkgs)
        tree, pos = _decode_bare_tree_at(tag_pkg, tp, members, tag.raw, 0, pkgs=pkgs)
        if pos != len(tag.raw):
            raise SchemaError(f"{prop.name}: struct default did not consume exactly")
        return tree
    return render_default_tag(tag_pkg, tag, prop, resolver=_resolver, _pkgs=pkgs, style=CLI_STYLE)


def _render_prop(prop, class_pkg, tags: dict, pkgs: dict, types_out: dict, in_progress: set) -> dict:
    category = prop.category or "Uncategorized"
    name_lower = prop.name.casefold()
    if prop.array_dim > 1:
        if prop.kind == "StructProperty":
            key = _collect_struct_type(prop, class_pkg, pkgs, types_out, in_progress)
            field = ("element_type", key)
        elif prop.kind == "ByteProperty" and prop.type_ref != 0:
            dp = _pkg_for_owner(prop.owner, class_pkg, resolver=_resolver, _pkgs=pkgs)
            tp, ti = resolve_type_export(dp, prop.type_ref, "Enum", resolver=_resolver, _pkgs=pkgs)
            field = ("element_type", _collect_enum_type(tp, ti, types_out))
        elif prop.kind in _SCALAR_KIND:
            field = ("element_kind", _SCALAR_KIND[prop.kind])
        else:
            raise SchemaError(f"unexpected array element kind {prop.kind} ({prop.name})")
        default_value = [_leaf_default(prop, name_lower, i, class_pkg, tags, pkgs)
                         for i in range(prop.array_dim)]
        return {"kind": "array", "name": prop.name, "category": category,
                "array_dim": prop.array_dim, field[0]: field[1], "default_value": default_value}
    if prop.kind == "StructProperty":
        key = _collect_struct_type(prop, class_pkg, pkgs, types_out, in_progress)
        dv = _leaf_default(prop, name_lower, 0, class_pkg, tags, pkgs)
        return {"kind": "struct", "name": prop.name, "category": category,
                "struct_type": key, "default_value": dv}
    if prop.kind == "ByteProperty" and prop.type_ref != 0:
        dp = _pkg_for_owner(prop.owner, class_pkg, resolver=_resolver, _pkgs=pkgs)
        tp, ti = resolve_type_export(dp, prop.type_ref, "Enum", resolver=_resolver, _pkgs=pkgs)
        key = _collect_enum_type(tp, ti, types_out)
        dv = _leaf_default(prop, name_lower, 0, class_pkg, tags, pkgs)
        return {"kind": "enum", "name": prop.name, "category": category,
                "enum_type": key, "default_value": dv}
    if prop.kind in _SCALAR_KIND:
        dv = _leaf_default(prop, name_lower, 0, class_pkg, tags, pkgs)
        return {"kind": _SCALAR_KIND[prop.kind], "name": prop.name, "category": category,
                "default_value": dv}
    raise SchemaError(f"unexpected top-level property kind {prop.kind} ({prop.name})")


def _render_typed_field(name_lower: str, merged: list, tags: dict, class_pkg, pkgs: dict,
                        types_out: dict, in_progress: set) -> dict | None:
    prop = next((p for p in merged if p.name.casefold() == name_lower
                and p.kind == "StructProperty"), None)
    if prop is None:
        return None
    category = prop.category or "Uncategorized"
    struct_type = _collect_struct_type(prop, class_pkg, pkgs, types_out, in_progress)
    entry = tags.get((name_lower, 0))
    if entry is not None:
        tag_pkg, tag = entry
        if tag.ptype != PT_STRUCT:
            raise SchemaError(f"{prop.name}: scalar-shaped default for a TYPED_FIELDS struct")
        tp, members = struct_member_schema(tag_pkg, prop, resolver=_resolver, _pkgs=pkgs)
        tree, pos = _decode_bare_tree_at(tag_pkg, tp, members, tag.raw, 0, pkgs=pkgs)
        if pos != len(tag.raw):
            raise SchemaError(f"{prop.name}: struct default did not consume exactly")
        if name_lower in ("mainscale", "postscale"):
            tree = _canonicalize_typed_scale_sheer_axis(tree, prop, class_pkg, pkgs)
    else:
        tree = _typed_field_fallback_tree(name_lower)
    return {"kind": "struct", "name": prop.name, "category": category,
            "struct_type": struct_type, "default_value": tree}


def resolve_class_for_golden(fqcn: str, pkgs: dict) -> dict:
    merged = resolve_class_properties(fqcn, resolver=_resolver)
    tags = resolve_class_default_tags(fqcn, resolver=_resolver, _pkgs=pkgs)
    pkg_name = fqcn.split(".", 1)[0]
    class_pkg = _load(pkg_name, pkgs)
    types_out: dict = {}
    in_progress: set = set()
    props = []
    for name_lower in _TYPED_FIELD_ORDER:
        try:
            rp = _render_typed_field(name_lower, merged, tags, class_pkg, pkgs, types_out,
                                     in_progress)
        except SchemaError as e:
            raise ClassResolveError(f"member {name_lower}: {e}") from e
        if rp is not None:
            props.append(rp)
    typed_names = set(_TYPED_FIELD_ORDER)
    for p in merged:
        nl = p.name.casefold()
        if nl in HARD_REJECT or nl in typed_names or is_computed_key(nl):
            continue
        if p.kind in _EXCLUDED_TOP_KINDS:
            continue
        try:
            props.append(_render_prop(p, class_pkg, tags, pkgs, types_out, in_progress))
        except SchemaError as e:
            raise ClassResolveError(f"member {p.name}: {e}") from e
    return {"class": {"props": props}, "types": types_out}


# ── the `actors` half: leaf paths from a built class entry, actor raw text flattened onto them ─

def _collect_struct_leaf_paths(prefix: str, struct_type: str, types: dict, out: dict) -> None:
    shape = types.get(struct_type)
    if shape is None or shape.get("kind") != "struct":
        return
    for m in shape["members"]:
        path = f"{prefix}.{m['name']}"
        mkind = m["kind"]
        if mkind == "struct":
            _collect_struct_leaf_paths(path, m["struct_type"], types, out)
        elif mkind == "enum":
            out[path] = m["enum_type"]
        elif mkind == "array":
            etype_key = m["element_type"]
            etype_shape = types.get(etype_key)
            for i in range(m["array_dim"]):
                ip = f"{path}.{i}"
                if etype_shape is not None and etype_shape.get("kind") == "struct":
                    _collect_struct_leaf_paths(ip, etype_key, types, out)
                else:
                    out[ip] = etype_key
        elif "array_dim" in m:
            for i in range(m["array_dim"]):
                out[f"{path}.{i}"] = None
        else:
            out[path] = None


def _collect_array_leaf_paths(prefix: str, array_dim: int, p: dict, types: dict, out: dict) -> None:
    for i in range(array_dim):
        path = f"{prefix}.{i}"
        if "element_kind" in p:
            out[path] = None
        else:
            etype_key = p["element_type"]
            etype_shape = types.get(etype_key)
            if etype_shape is not None and etype_shape.get("kind") == "struct":
                _collect_struct_leaf_paths(path, etype_key, types, out)
            else:
                out[path] = etype_key


def _leaf_paths(cr: dict) -> dict:
    """Every real (scalar/enum) leaf `cr`'s own shape can produce, keyed by the exact dotted-path
    convention `resolve.rs`'s `leaf_paths` builds -- mirrors it directly, operating on this
    script's own JSON dict instead of Rust structs (structurally identical)."""
    out: dict = {}
    for p in cr["class"]["props"]:
        kind = p["kind"]
        if kind == "struct":
            _collect_struct_leaf_paths(p["name"], p["struct_type"], cr["types"], out)
        elif kind == "array":
            _collect_array_leaf_paths(p["name"], p["array_dim"], p, cr["types"], out)
        elif kind == "enum":
            out[p["name"]] = p["enum_type"]
        else:
            out[p["name"]] = None
    return out


def _canonicalize_stated_enum(dequoted: str, enum_type: str, types: dict) -> str:
    shape = types.get(enum_type)
    if shape is None or shape.get("kind") != "enum":
        return dequoted
    if dequoted.strip().isdigit():
        i = int(dequoted.strip())
        values = shape["values"]
        if i < len(values):
            return values[i]
    return dequoted


def _class_defaults_for(fqcn: str, pkgs: dict, cache: dict) -> dict:
    """`resolve_class_defaults`'s own T3D-joined-text dict (a DIFFERENT shape from
    `resolve_class_default_tags`'s raw tags this script's `classes` half uses) -- the exact shape
    `effective_props._resolve_typed_fields`'s own `ctx.defaults()` calls expect
    (`_member_default`'s `split_struct_text` walk). Cached per class: 59 actors span 28 classes."""
    if fqcn not in cache:
        cache[fqcn] = resolve_class_defaults(fqcn, resolver=_resolver, _pkgs=pkgs)
    return cache[fqcn]


def _typed_field_leaves(actor, class_defaults: dict) -> dict:
    """`Location`/`MainScale`/`PostScale`'s own stated leaves -- `model.py`'s T3D parser pulls
    these three OUT of `actor.props` into `actor.location`/`location_text`, `actor.main_scale`/
    `main_scale_text`, `actor.post_scale`/`post_scale_text` (see `model.py:105-131,220-249`), so
    `_flatten_actor_props` above (which only walks `actor.props`) never sees them at all. Reuses
    the EXISTING, already-tested `effective_props._resolve_typed_fields` directly -- the same
    per-axis/per-member stated-vs-not-stated rule (`normalize._stated_axes`/
    `_stated_scale_members`) production code already applies -- rather than reimplementing that
    statedness logic by hand. A throwaway `ClassCtx` supplies only `load_defaults` (the one thing
    `_resolve_typed_fields` actually calls, `ctx.defaults()`); `load_schema`/`load_members`/
    `load_enums` are never invoked for these three fields."""
    ctx = ClassCtx(cls=actor.cls, load_schema=lambda: {}, load_defaults=lambda: class_defaults,
                  load_members=lambda p: [], load_enums=lambda p: ())
    typed_props = effective_props._resolve_typed_fields(actor, ctx, {})
    out: dict = {}

    def walk(prefix: str, ep) -> None:
        if isinstance(ep, effective_props.StructProp):
            for m in ep.members:
                walk(f"{prefix}.{m.name}", m)
        elif ep.stored_value is not None:
            out[prefix] = ep.stored_value

    for p in typed_props:
        walk(p.name, p)
    return out


def build_actor_entry(actor, golden_classes: dict, whole_class_reason: dict, pkgs: dict,
                      defaults_cache: dict) -> dict:
    fqcn = actor.cls
    if fqcn in whole_class_reason:
        note = (f"actor {actor.name!r}: schema unavailable ({fqcn}) — cannot resolve effective "
                f"props ({whole_class_reason[fqcn]})")
        return {"cls": fqcn, "sparse": {}, "note": note}
    cr = golden_classes[fqcn]
    leaves = _leaf_paths(cr)
    flat = _flatten_actor_props(actor.props, cr)
    flat.update(_typed_field_leaves(actor, _class_defaults_for(fqcn, pkgs, defaults_cache)))
    sparse: dict = {}
    for path, raw in flat.items():
        if path not in leaves:
            continue
        canon = leaves[path]
        dequoted = _dequote(raw)
        value = (_canonicalize_stated_enum(dequoted, canon, cr["types"])
                if canon is not None else dequoted)
        sparse[path] = value
    return {"cls": fqcn, "sparse": sparse, "note": None}


def _build_divergences(golden_classes: dict) -> list:
    """Step 3: name each intentional divergence from today's `effective_props.py` behavior. Three
    kinds (spec §6): the `SheerAxis` canonicalization fix, the `Core.Scale.ESheerAxis` key (instead
    of the hardcoded `typedprops.ESheerAxis` string), and the `_struct_members_via`/
    `_enum_names_via` struct/enum-nested-in-struct owning-package bug fix (Step 1.5) -- each
    surfaced here per distinct (containing type, member) pair actually exercised in this golden,
    not silently folded into the resolved output with no explanation."""
    out = []
    sheeraxis_fixed_classes = []
    key_seen = False
    key_class = None
    nested_pairs: dict[tuple[str, str], str] = {}
    for fqcn in sorted(golden_classes):
        cr = golden_classes[fqcn]
        for p in cr["class"]["props"]:
            if p["name"] in ("MainScale", "PostScale") and p["kind"] == "struct":
                dv = p["default_value"]
                if isinstance(dv, dict) and dv.get("SheerAxis") not in ("SHEER_ZX", None):
                    sheeraxis_fixed_classes.append((fqcn, p["name"]))
                if not key_seen:
                    key_seen = True
                    key_class = fqcn
        for type_key, shape in cr["types"].items():
            if shape.get("kind") != "struct":
                continue
            for m in shape["members"]:
                if m["kind"] in ("struct", "enum"):
                    pair = (type_key, m["name"])
                    nested_pairs.setdefault(pair, fqcn)

    if sheeraxis_fixed_classes:
        cls, field = sheeraxis_fixed_classes[0]
        out.append({
            "class": cls,
            "what": "SheerAxis canonicalization",
            "why": (f"today's effective_props.py's _resolve_typed_fields never calls "
                    f"_canonicalize_enum_text for MainScale/PostScale's SheerAxis default (it reads "
                    f"_member_default off the CLI_STYLE-rendered whole-struct text, which never "
                    f"canonicalizes) -- this port fixes it, e.g. {cls}.{field}.SheerAxis. "
                    f"gui-inspector-props-payload-redesign/spec.md §1's Engine.Brush.MainScale "
                    f"worked example."),
        })
    if key_class is not None:
        out.append({
            "class": key_class,
            "what": "Core.Scale.ESheerAxis key",
            "why": ("today's _resolve_typed_fields hardcodes ctx_by_type key "
                    "\"typedprops.ESheerAxis\" for MainScale/PostScale's SheerAxis enum; this port "
                    "resolves the real export's own outer-based identity key, Core.Scale.ESheerAxis "
                    "-- the SAME key the generic schema walk would give the same real enum. Applies "
                    "uniformly to every class's MainScale/PostScale (all carry this leaf, Step 8/9)."),
        })
    for (type_key, member_name), fqcn in sorted(nested_pairs.items()):
        out.append({
            "class": fqcn,
            "what": f"_struct_members_via/_enum_names_via owning-package bug fix: {type_key}.{member_name}",
            "why": (f"serve/scene.py's _struct_members_via/_enum_names_via derive a struct/enum "
                    f"member's owning package via prop.owner.split('.', 1)[0], which is wrong "
                    f"whenever the member is reached through a struct (a struct member's owner is "
                    f"the bare, unqualified struct name) -- {type_key}'s own member {member_name} "
                    f"is exactly this case. This port resolves the owning package via the member "
                    f"type's own export-record outer field instead (uprops.values._pkg_for_owner/"
                    f"resolve_type_export, already bug-free), matching Task 4 Step 5's Rust code."),
        })
    return out


# ── main ─────────────────────────────────────────────────────────────────────────────────────

def main() -> None:
    actor_dirs = sorted(p for p in _SUBSET.iterdir() if p.is_dir())
    actors = []
    for d in actor_dirs:
        text = (d / "actor.t3d").read_text()
        actors.append(load_actor_body(text, d.name))

    class_set = sorted({a.cls for a in actors} | {"DeusEx.Karkian", "DeusEx.Rat"})

    pkgs: dict = {}
    golden_classes: dict = {}
    whole_class_failures: list = []
    whole_class_reason: dict = {}
    for fqcn in class_set:
        try:
            golden_classes[fqcn] = resolve_class_for_golden(fqcn, pkgs)
        except ClassResolveError as e:
            reason = str(e)
            whole_class_failures.append({"class": fqcn, "reason": reason})
            whole_class_reason[fqcn] = reason

    golden_actors = {}
    defaults_cache: dict = {}
    for actor in actors:
        golden_actors[actor.name] = build_actor_entry(actor, golden_classes, whole_class_reason,
                                                       pkgs, defaults_cache)

    divergences = _build_divergences(golden_classes)

    golden = {
        "classes": golden_classes,
        "actors": golden_actors,
        "divergences": divergences,
        "whole_class_failures": whole_class_failures,
    }
    _OUT.write_text(json.dumps(golden, indent=2, sort_keys=True) + "\n")

    print(f"wrote {_OUT} -- {len(golden_classes)} classes, {len(golden_actors)} actors, "
          f"{len(divergences)} divergences, {len(whole_class_failures)} whole-class failures",
          file=sys.stderr)
    if whole_class_failures:
        print("WHOLE-CLASS FAILURES (Task 4 Step 6.5's hard-fail rule fired on real corpus data):",
              file=sys.stderr)
        for f in whole_class_failures:
            print(f"  {f['class']}: {f['reason']}", file=sys.stderr)


if __name__ == "__main__":
    main()

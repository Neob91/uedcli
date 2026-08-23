"""The orchestration: `set`/`unset` planning against a copy of the actor's props, keyed `get` and
dump-all, and `find --prop` effective-value matching — plus the leaf-scalar validators this layer is
the sole consumer of."""
from __future__ import annotations

from dataclasses import dataclass

from ..normalize import is_computed_key
from ..uprops import Prop
from .base import (ClassCtx, HARD_REJECT, PropEditError, _INT_RE, _PAREN_KEY_RE, _dec_finite,
                   _dequote)
from .paths import ResolvedPath, _member_map, _text_key_ident, resolve_path
from .structtext import (_maybe_comma_sugar, _set_member_in_text, _unset_member_in_text,
                         emit_struct_text, full_struct_text, split_struct_text, zero_value)
from .tokens import PropToken, check_hard_reject, check_overlaps


# ── leaf value validation (same deliberately-partial stance as before) ───────────────────────

def validate_leaf_value(leaf: Prop, enum_names: tuple[str, ...], value: str,
                        *, label: str) -> None:
    """None-or-raise: enum membership and Int/Float/Bool/plain-Byte scalars are enforced;
    struct/object/class/name/str/array values pass on type (their grammar is too rich to
    validate offline without false-rejects). Numerics must be FINITE and engine-representable
    (review: `nan`/`inf`/`1e999` previously passed and crashed or ballooned the trunk)."""
    v = _dequote(value)
    if enum_names:
        if v.casefold() not in {e.casefold() for e in enum_names} and \
                not (v.isdigit() and int(v) < len(enum_names)):
            raise PropEditError(f"{label}={value}: not a valid {leaf.type_name or 'enum'} value "
                                f"(expected one of: {', '.join(enum_names)})")
        return
    if leaf.kind == "IntProperty":
        try:
            iv = int(v)
        except ValueError:
            raise PropEditError(f"{label}={value}: expected an integer") from None
        if abs(iv) > 0x7FFFFFFF:
            raise PropEditError(f"{label}={value}: out of the engine int32 range")
    elif leaf.kind == "FloatProperty":
        _dec_finite(v, label)
    elif leaf.kind == "BoolProperty":
        if v.casefold() not in {"true", "false", "0", "1"}:
            raise PropEditError(f"{label}={value}: expected True or False")
    elif leaf.kind == "ByteProperty":
        if leaf.type_ref == 0 and not (v.isdigit() and 0 <= int(v) <= 255):
            raise PropEditError(f"{label}={value}: expected a byte (0-255)")


def _canonicalize_enum(prop: Prop, ctx: ClassCtx, text: str) -> str:
    """A stored enum ordinal → its NAME (keyed get is the effective view, spec §4); anything
    else verbatim. An un-enumerable enum keeps the ordinal."""
    if prop.kind == "ByteProperty" and text.strip().isdigit():
        names = ctx.enums(prop)
        i = int(text.strip())
        if i < len(names):
            return names[i]
    return text


def _stored_map(actor) -> dict[tuple[str, int], str]:
    """The actor's stored props keyed like the defaults dict: (casefold base, index) → value.
    A plain `Key` line is index 0 (T3D treats an unindexed array line as element 0); `Key(N)`
    is element N. LAST occurrence wins (T3D import semantics for duplicate lines)."""
    out: dict[tuple[str, int], str] = {}
    for k, v in actor.props:
        m = _PAREN_KEY_RE.match(k)
        if m is not None:
            out[(m.group(1).casefold(), int(m.group(2)))] = v
        else:
            out[(k.casefold(), 0)] = v
    return out


def effective_value(actor, rp: ResolvedPath, ctx: ClassCtx) -> str:
    """The effective value at `rp` (spec §4): stored → class default → zero, rendered
    canonically; paths drill in; whole arrays render the full-dim one-line tuple."""
    stored = _stored_map(actor)
    prop = rp.prop
    bf = prop.name.casefold()

    def element_text(i: int) -> str:
        s = stored.get((bf, i))
        if prop.kind == "StructProperty":
            return full_struct_text(prop, i, s, ctx)
        if s is not None:
            return _canonicalize_enum(prop, ctx, _dequote(s))
        d = ctx.defaults().get((bf, i))
        if d is not None:
            return d
        return zero_value(prop, ctx)

    if rp.index is None and prop.array_dim > 1 and not rp.members:
        return emit_struct_text([(str(i), element_text(i)) for i in range(prop.array_dim)])
    idx = rp.index if rp.index is not None else 0
    text = element_text(idx)
    for step in rp.members:                          # drill into the (fully merged) form
        pairs = split_struct_text(text)
        if pairs is None:
            raise PropEditError(f"{rp.canonical}: stored value is not a struct "
                                f"literal: {text!r}")
        want_ident = (step.prop.name.casefold(), step.index)
        hit = next((v for k, v in pairs
                    if _text_key_ident(k) == want_ident), None)
        if hit is None and step.index is None and step.prop.array_dim > 1:
            # whole member-array requested: gather its elements into a tuple
            elems = {i: v for k, v in pairs
                     for (kb, i) in [_text_key_ident(k)]
                     if kb == step.prop.name.casefold() and i is not None}
            mz = zero_value(step.prop, ctx)
            return emit_struct_text([(str(i), elems.get(i, mz))
                                     for i in range(step.prop.array_dim)])
        if hit is None:
            hit = zero_value(step.prop, ctx)         # absent even in the merged full form
        text = hit
        if step.prop.kind == "ByteProperty":
            text = _canonicalize_enum(step.prop, ctx, text)
    return text


@dataclass
class Plan:
    props: list[tuple[str, str]]
    # Per-typed-field updates to apply on success: `{attr: new_value}` (e.g. `{"location": (…)}`,
    # `{"main_scale": FScale(…)}`). The caller `setattr`s each onto the actor. Empty when no typed
    # field was touched.
    typed_updates: dict[str, object]
    warnings: list[str]


def plan_edit(actor, tokens: list[PropToken], mode: str, ctx: ClassCtx,
              typed_fields: dict) -> Plan:
    """Validate + apply `set`/`unset` tokens against a COPY of the actor's props (the caller
    mutates the model only on full success — validate-before-mutate). `typed_fields` is the
    registry (casefold field name → TypedField/ScaleField)."""
    warnings: list[str] = []
    check_overlaps(tokens)
    props = list(actor.props)
    typed_updates: dict[str, object] = {}

    def stored_key(prop: Prop, index: int | None) -> str:
        return prop.name if index is None else f"{prop.name}({index})"

    def matching_indices(prop: Prop, index: int | None) -> list[int]:
        """Indices into `props` whose key addresses (prop, index). For an ARRAY element 0 an
        unindexed `Key` line counts too (T3D treats it as element 0 — review finding); a
        duplicate-keyed line list returns every occurrence (set replaces the LAST, T3D's
        winner, and removes the rest; unset removes all — review finding)."""
        out = []
        for i, (k, _v) in enumerate(props):
            kb, ki = _text_key_ident(k)
            if kb != prop.name.casefold():
                continue
            if index is None:
                if ki is None:
                    out.append(i)
            else:
                if ki == index or (ki is None and index == 0):
                    out.append(i)
        return out

    def replace_stored(prop: Prop, index: int | None, value: str) -> None:
        hits = matching_indices(prop, index)
        entry = (stored_key(prop, index), value)
        if not hits:
            props.append(entry)
            return
        keep = hits[-1]                              # T3D last-wins: edit the winner...
        props[keep] = entry
        for i in reversed(hits[:-1]):                # ...and drop the shadowed duplicates
            del props[i]

    def remove_stored(prop: Prop, index: int | None) -> None:
        for i in reversed(matching_indices(prop, index)):
            del props[i]

    def remove_all_elements(prop: Prop) -> None:
        bf = prop.name.casefold()
        props[:] = [(k, v) for k, v in props if _text_key_ident(k)[0] != bf]

    def stored_text(prop: Prop, index: int | None) -> str | None:
        hits = matching_indices(prop, index)
        return props[hits[-1]][1] if hits else None

    for tok in tokens:
        check_hard_reject(tok)
        tf = typed_fields.get(tok.base.casefold())
        if tf is not None:
            current = typed_updates.get(tf.attr, getattr(actor, tf.attr))
            typed_updates[tf.attr] = tf.apply(tok, mode, current)
            # drop any stray stored line shadowing the typed field
            props[:] = [(k, v) for k, v in props if k.casefold() != tok.base.casefold()]
            continue
        rp = resolve_path(tok, ctx)
        prop, leaf = rp.prop, rp.leaf
        if is_computed_key(prop.name):
            warnings.append(f"{prop.name}: computed/derived — will not persist as authored "
                            "content")
        # (MainScale/PostScale no longer warn here — they are typed model fields routed above, and
        # scale IS now applied in uedcli's measurement.)

        if mode == "unset":
            if rp.is_whole:
                if prop.array_dim > 1:
                    remove_all_elements(prop)        # whole-array unset clears EVERY element
                else:
                    remove_stored(prop, None)
                continue
            if not rp.members:                       # element unset
                remove_stored(prop, rp.index)
                continue
            text = stored_text(prop, rp.index)
            if text is None:
                continue                             # prop/element not stored: silent success
            changed, new_text = _unset_member_in_text(_dequote(text), rp.members,
                                                      rp.canonical)
            if not changed:
                continue                             # member not stored: leave the line ALONE
            if new_text is None:
                remove_stored(prop, rp.index)
            else:
                replace_stored(prop, rp.index, new_text)
            continue

        # mode == "set"
        value = tok.value
        assert value is not None
        if rp.is_whole and prop.name.casefold() == "numkeys":
            # NumKeys goes through the SAME bounded setter `mover key count` uses (spec
            # 2026-07-20): validate 2..8 (error names the value) and keep the omit-when-2
            # canonical form. resolve_path above already proved NumKeys is on this class, so a
            # non-mover set is rejected by the schema before reaching here.
            from .. import movers
            try:
                n = int(_dequote(value))
            except ValueError:
                raise PropEditError(f"{prop.name}={value}: expected an integer") from None
            try:
                movers.check_num_keys(n)
            except ValueError as e:
                raise PropEditError(str(e)) from None
            remove_stored(prop, None)
            if n != movers.MIN_KEYS:
                props.append((prop.name, str(n)))
            continue
        if rp.is_whole:
            if prop.array_dim > 1:                   # whole static array: tuple form only
                pairs = split_struct_text(_dequote(value))
                if pairs is None:
                    raise PropEditError(
                        f"{prop.name} is a static array: set the whole array with "
                        f"{prop.name}=(0=V,…) or one element with {prop.name}.N=V")
                if not pairs:
                    raise PropEditError(f"{prop.name}=(): empty tuple — clear the array with "
                                        f"`unset {prop.name}` instead")
                seen_i: set[int] = set()
                new_elems: list[tuple[int, str]] = []
                for k, v in pairs:
                    if not _INT_RE.match(k) or int(k) < 0:
                        raise PropEditError(f"{prop.name}={value}: tuple keys must be element "
                                            f"indices, got {k!r}")
                    iv = int(k)
                    if iv >= prop.array_dim:
                        raise PropEditError(f"{prop.name}.{iv}: index out of bounds "
                                            f"(array size {prop.array_dim})")
                    if iv in seen_i:
                        raise PropEditError(f"{prop.name}={value}: index {iv} repeated")
                    seen_i.add(iv)
                    if prop.kind != "StructProperty":
                        validate_leaf_value(prop, ctx.enums(prop), v,
                                            label=f"{prop.name}.{iv}")
                    new_elems.append((iv, v))
                remove_all_elements(prop)            # tuple = whole-value replace (spec §3.1)
                for iv, v in new_elems:
                    props.append((f"{prop.name}({iv})", _dequote(v)))
                continue
            v = _maybe_comma_sugar(prop, value)
            if prop.kind != "StructProperty":
                validate_leaf_value(prop, ctx.enums(prop), v, label=prop.name)
            replace_stored(prop, None, _dequote(v))
            continue
        if not rp.members:                           # element set
            if prop.kind != "StructProperty":
                validate_leaf_value(prop, ctx.enums(prop), value, label=rp.canonical)
            replace_stored(prop, rp.index, _dequote(value))
            continue
        # member set: base = stored value if present, else the effective default materialized
        # explicitly (spec §3.1 — never silently zero siblings the default had non-zero)
        if leaf.kind != "StructProperty":
            validate_leaf_value(leaf, ctx.enums(leaf), value, label=rp.canonical)
        idx = rp.index if rp.index is not None else 0
        text = stored_text(prop, rp.index)
        if text is not None:
            base_text = _dequote(text)
        else:
            base_text = full_struct_text(prop, idx, None, ctx)
            if split_struct_text(base_text) is None:
                base_text = "()"
        new_text = _set_member_in_text(base_text, rp.members, _dequote(value), rp.canonical)
        replace_stored(prop, rp.index, new_text)

    return Plan(props=props, typed_updates=typed_updates, warnings=warnings)


# ── get / dump-all ───────────────────────────────────────────────────────────────────────────

def get_lines(actor, tokens: list[PropToken], ctx: ClassCtx, typed_fields: dict,
              *, kv: bool) -> list[str]:
    """Keyed `get`: one line per token, argument order, all tokens validated BEFORE any output
    (spec §2.3). Bare values by default; `KEY=VALUE` canonical lines with `kv`."""
    resolved: list[tuple[str, str]] = []             # (canonical key, value)
    for tok in tokens:
        check_hard_reject(tok)
        tf = typed_fields.get(tok.base.casefold())
        if tf is not None:
            resolved.append(tf.get(tok, getattr(actor, tf.attr)))
            continue
        rp = resolve_path(tok, ctx)
        resolved.append((rp.canonical, effective_value(actor, rp, ctx)))
    return [f"{k}={v}" if kv else v for k, v in resolved]


def dump_all_lines(actor, ctx: ClassCtx, typed_fields: dict) -> list[str]:
    """Dump-all — the verbatim STORED view (spec §2.3): the typed Location field first, then
    every stored prop in stored order, keys canonicalized to dot spelling (an unindexed
    static-array line prints as element 0, so every line round-trips into `set`), values
    verbatim. A stored prop the schema does not know is a HARD error (ruling R4);
    hard-rejected bookkeeping keys are skipped (not `actor prop` surface)."""
    lines: list[str] = []
    for tf in typed_fields.values():
        value = getattr(actor, tf.attr)
        if value is None and not tf.dump_always:     # a scale field only dumps when carried
            continue
        key, val = tf.get(None, value)
        lines.append(f"{key}={val}")
    schema: dict[str, Prop] | None = None
    for k, v in actor.props:
        base, idx = _text_key_ident(k)
        m = _PAREN_KEY_RE.match(k)
        base_name = m.group(1) if m is not None else k
        if base in HARD_REJECT:
            continue
        if base in typed_fields:
            continue                                 # the field is authoritative; stray line
        if schema is None:
            schema = ctx.schema()
        prop = schema.get(base)
        if prop is None:
            raise PropEditError(f"stored property {base_name} is not in the class schema of "
                                f"{ctx.cls} (foreign or stale trunk?)")
        if idx is not None:
            key = f"{prop.name}.{idx}"
        elif prop.array_dim > 1:                     # unindexed array line == element 0
            key = f"{prop.name}.0"
        else:
            key = prop.name
        lines.append(f"{key}={v}")
    return lines


# ── find --prop: effective-value matching ────────────────────────────────────────────────────

def _canon_scalar(leaf: Prop, enum_names: tuple[str, ...], text: str):
    """A comparable canonical form per leaf kind (spec §7): bools case-insensitive, numerics
    numeric, enums name≡ordinal, names case-folded, strings/objects exact."""
    t = _dequote(text)
    if leaf.kind == "BoolProperty":
        return t.casefold() in ("true", "1")
    if enum_names:
        if t.isdigit() and int(t) < len(enum_names):
            return enum_names[int(t)].casefold()
        return t.casefold()
    if leaf.kind in ("IntProperty", "FloatProperty", "ByteProperty"):
        try:
            return float(t)
        except (ValueError, OverflowError):
            return t
    if leaf.kind == "NameProperty":
        return t.casefold()
    return t                                          # str/object/class: exact


def values_match(leaf: Prop, ctx: ClassCtx, a: str, b: str) -> bool:
    """Effective-value comparison: struct texts compare member-wise (each side filled to the
    full form first by the caller), scalars per `_canon_scalar`."""
    if leaf.kind == "StructProperty":
        pa, pb = split_struct_text(a), split_struct_text(b)
        if pa is None or pb is None:
            return a.strip() == b.strip()
        members = _member_map(ctx.members(leaf))
        da = {_text_key_ident(k): v for k, v in pa}
        db = {_text_key_ident(k): v for k, v in pb}
        for key in set(da) | set(db):
            m = members.get(key[0])
            va, vb = da.get(key), db.get(key)
            if va is None or vb is None:
                zm = zero_value(m, ctx) if m is not None else "0"
                va, vb = va if va is not None else zm, vb if vb is not None else zm
            if m is not None and m.kind == "StructProperty":
                if not values_match(m, ctx, va, vb):
                    return False
            else:
                en = ctx.enums(m) if m is not None else ()
                if _canon_scalar(m or leaf, en, va) != _canon_scalar(m or leaf, en, vb):
                    return False
        return True
    return _canon_scalar(leaf, ctx.enums(leaf), a) == _canon_scalar(leaf, ctx.enums(leaf), b)


def effective_match(actor, tok: PropToken, ctx: ClassCtx, typed_fields: dict) -> bool | None:
    """Does `actor` match `tok` (KEY[.path]=VALUE) on its EFFECTIVE value (spec §7)? Returns
    None when the actor's class does not declare the key (per-class no-match, ruling R3) — the
    caller distinguishes 'no considered class declares it' (exit 2) from ordinary no-match.
    Any OTHER path/value error (bad member, out-of-bounds index, a value that can never
    match) raises — a malformed token is a hard error, not a silent no-match."""
    check_hard_reject(tok)
    tf = typed_fields.get(tok.base.casefold())
    if tf is not None:
        return tf.match(tok, getattr(actor, tf.attr))
    if ctx.schema().get(tok.base.casefold()) is None:
        return None
    rp = resolve_path(tok, ctx)
    actual = effective_value(actor, rp, ctx)
    want = tok.value if tok.value is not None else ""
    leaf = rp.leaf

    # whole static array: expand the want tuple to the same full-dim form `get` renders
    if rp.index is None and rp.prop.array_dim > 1 and not rp.members:
        pairs = split_struct_text(_dequote(want))
        if pairs is None:
            raise PropEditError(f"{tok.raw}: a whole static array compares against the tuple "
                                f"form {rp.prop.name}=(0=V,…) — or match one element with "
                                f"{rp.prop.name}.N=V")
        by_idx: dict[int, str] = {}
        for k, v in pairs:
            if not _INT_RE.match(k) or int(k) < 0 or int(k) >= rp.prop.array_dim:
                raise PropEditError(f"{tok.raw}: tuple key {k!r} is not a valid element index")
            by_idx[int(k)] = v
        stored = _stored_map(actor)
        bf = rp.prop.name.casefold()

        def fallback(i: int) -> str:
            d = ctx.defaults().get((bf, i))
            return d if d is not None else zero_value(rp.prop, ctx)

        actual_pairs = split_struct_text(actual) or []
        actual_by_idx = {int(k): v for k, v in actual_pairs}
        for i in range(rp.prop.array_dim):
            wa = by_idx.get(i, fallback(i))
            va = actual_by_idx.get(i, fallback(i))
            if rp.prop.kind == "StructProperty":
                wa = full_struct_text(rp.prop, i, wa, ctx)
                if not values_match(rp.prop, ctx, va, wa):
                    return False
            else:
                en = ctx.enums(rp.prop)
                if _canon_scalar(rp.prop, en, va) != _canon_scalar(rp.prop, en, wa):
                    return False
        return True

    if leaf.kind == "StructProperty":
        want = _maybe_comma_sugar(leaf, want)        # find adopts set's grammar (spec §7)
        if not rp.members:
            want = full_struct_text(leaf, rp.index or 0, _dequote(want), ctx)
    else:
        _validate_query_value(leaf, ctx.enums(leaf), want, label=tok.raw)
    return values_match(leaf, ctx, actual, want)


def _validate_query_value(leaf: Prop, enum_names: tuple[str, ...], value: str,
                          *, label: str) -> None:
    """A `find --prop` value that can NEVER match any actor is a typo → error, not a silent
    empty result (review finding). LOOSER than set's validation on purpose: the §7 compare is
    numeric (`4`≡`4.0`), so a byte query of `128.0` is legitimate."""
    v = _dequote(value)
    if enum_names:
        if v.casefold() not in {e.casefold() for e in enum_names} and \
                not (v.isdigit() and int(v) < len(enum_names)):
            raise PropEditError(f"{label}: {value!r} is not a value of "
                                f"{leaf.type_name or 'the enum'} "
                                f"({', '.join(enum_names)}) — it can never match")
        return
    if leaf.kind in ("IntProperty", "FloatProperty", "ByteProperty"):
        try:
            float(v)
        except (ValueError, OverflowError):
            raise PropEditError(f"{label}: {value!r} is not numeric — it can never match "
                                f"a {leaf.kind}") from None
    elif leaf.kind == "BoolProperty":
        if v.casefold() not in ("true", "false", "0", "1"):
            raise PropEditError(f"{label}: {value!r} is not a boolean — it can never match")

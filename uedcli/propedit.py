"""`actor prop set|unset|get` — the pure verb logic: dot-path grammar, whole-value vs
targeted-edit planning, effective-value reads (stored → class default → type zero), dump-all,
and the `find --prop` effective-value matcher.

Spec in board item `materialize-post-verify-fails-when-the-trunk`; direction/packages.md 2026-07-18 10:02 +
10:30 UTC. Everything here is model-side and schema-driven; the class schema / defaults /
struct-member / enum lookups arrive through a lazy `ClassCtx` bundle so that tokens which never
need the schema (hard-rejects, typed-field-only invocations) run without the v68 install
(spec §2.4), and `cli.resources` owns the FOUR seams (`class_schema` / `class_defaults` /
`struct_members` / `enum_names`) that tests mock.

Grammar (spec §3):
    TOKEN   := KEY [PATH] ("=" VALUE)?
    PATH    := ("." SEGMENT)+
    SEGMENT := decimal integer (array index) | identifier (struct member)
An index segment may index the base prop (`MultiSkins.2`) or a STRUCT MEMBER that is itself a
static array (`Nest.Marks.1` — stored/rendered as `Marks(1)=` inside the struct text). The T3D
`KEY(N)` spelling is rejected with a hint; the STORED T3D keeps its native `Key(N)=` form (this
is CLI grammar only).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Callable

from . import typedprops
from .normalize import is_computed_key
from .uprops import Prop, SchemaError

# The ONLY hard rejects, applied to ALL THREE subcommands (spec §2.1): the actor Name
# (identity), the internal Brush binding, and the mover-key GEOMETRY/view bookkeeping (author
# those with `mover key`). `NumKeys` is NOT rejected — it is a first-class settable count, routed
# through the shared `movers.set_num_keys` bounds/canonical-form setter (spec 2026-07-20), so
# `actor prop set NumKeys=` and `mover key count` are identical in effect. Case-folded (FName).
HARD_REJECT = frozenset({"name", "brush", "keypos", "keyrot", "keynum"})

# §3.1 probe RESULT (live 2026-07-18, spikes/2026-07-18-partial-value-import-semantics/):
# the editor's T3D import is MEMBER-WISE ONTO THE CLASS DEFAULT — members unmentioned in a
# stored-partial struct value, and elements unmentioned in a sparse static array, resolve to
# the CLASS DEFAULT (not zero). `get`'s full-form rendering and member fall-through follow it.
# (The constant anchors the probe result; "zero" was the pre-probe placeholder and the
# alternative the probe REFUTED — kept as a named switch so the semantics stay greppable.)
STRUCT_FILL = "default"

# float32 representability bound (the engine stores floats): a numeric value beyond this can
# never be a meaningful engine value, and an unbounded Decimal would balloon the trunk file
# (review finding: `Location=1e999,0,0` wrote a ~1000-digit line).
_NUM_BOUND = Decimal("3.4e38")

_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")
_INT_RE = re.compile(r"^-?\d+$")
_PAREN_KEY_RE = re.compile(r"^([A-Za-z_]\w*)\((\d+)\)$")
_PAREN_ANY_RE = re.compile(r"([A-Za-z_]\w*)\((\d+)\)")


class PropEditError(Exception):
    """A named, user-facing prop-verb error (exit 2 at dispatch — never a traceback)."""


def _dequote(s: str) -> str:
    """Strip ONE genuine wrapping quote pair — a leading+trailing quote strips only when the
    interior holds no quote characters (review B10: `"a" and "b"` must keep ALL its quotes —
    its outer quotes belong to different words, not a wrapper; only `"whole value"`
    dequotes)."""
    t = s.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"' and '"' not in t[1:-1]:
        return t[1:-1]
    return t


def _dec_finite(text: str, label: str) -> Decimal:
    """Parse a REQUIRED finite, engine-representable number (review: `nan`/`inf` pass
    `Decimal()` and traceback later in emit/normalize; absurd exponents balloon the trunk)."""
    try:
        d = Decimal(_dequote(text))
    except InvalidOperation:
        raise PropEditError(f"{label}: expected a number, got {text!r}") from None
    if not d.is_finite():
        raise PropEditError(f"{label}: expected a finite number, got {text!r}")
    if abs(d) > _NUM_BOUND:
        raise PropEditError(f"{label}: {text!r} is out of the engine float range (±3.4e38)")
    return d


@dataclass(frozen=True)
class PropToken:
    base: str                            # the property name as typed
    segs: tuple[object, ...]             # path segments: int (index) or str (member name)
    value: str | None                    # None for unset/get tokens
    raw: str                             # the original token, for error messages


@dataclass
class ClassCtx:
    """Lazy per-class schema bundle. `schema()`/`defaults()` load-and-memoize on first use so
    typed-field-only and hard-reject paths never touch the install; `members(prop)` resolves a
    StructProperty's ordered member Props; `enums(prop)` resolves enum value names
    cross-package (an UNRESOLVABLE imported enum degrades to `()` — spec §4: get prints the
    ordinal, set accepts on type, matching the deliberately-partial validation stance)."""
    cls: str
    load_schema: Callable[[], dict[str, Prop]]
    load_defaults: Callable[[], dict[tuple[str, int], str]]
    load_members: Callable[[Prop], list[Prop]]
    load_enums: Callable[[Prop], tuple[str, ...]]
    _schema: dict[str, Prop] | None = None
    _defaults: dict[tuple[str, int], str] | None = None
    _members: dict[int, list[Prop]] = field(default_factory=dict)
    _enums: dict[int, tuple[str, ...]] = field(default_factory=dict)

    def schema(self) -> dict[str, Prop]:
        if self._schema is None:
            self._schema = self.load_schema()
        return self._schema

    def defaults(self) -> dict[tuple[str, int], str]:
        if self._defaults is None:
            self._defaults = self.load_defaults()
        return self._defaults

    def members(self, prop: Prop) -> list[Prop]:
        key = id(prop)
        if key not in self._members:
            self._members[key] = self.load_members(prop)
        return self._members[key]

    def enums(self, prop: Prop) -> tuple[str, ...]:
        if prop.kind != "ByteProperty" or prop.type_ref == 0:
            return ()                                # nothing to resolve — never load a package
        if prop.enum_value_names:                    # local enum, decoded eagerly
            return prop.enum_value_names
        key = id(prop)                               # imported enum → cross-package resolve
        if key not in self._enums:
            try:
                self._enums[key] = self.load_enums(prop)
            except SchemaError:                      # unresolvable enum: un-enumerable, not fatal
                self._enums[key] = ()
        return self._enums[key]


# ── token grammar ────────────────────────────────────────────────────────────────────────────

def parse_token(text: str, *, expect_value: bool) -> PropToken:
    """One CLI token → a `PropToken`. `expect_value` (set) demands `KEY=VALUE`; get/unset
    forbid `=`."""
    if expect_value:
        if "=" not in text:
            raise PropEditError(f"expected KEY=VALUE, got: {text!r}")
        key, value = text.split("=", 1)
    else:
        if "=" in text:
            raise PropEditError(f"unexpected '=' in {text!r} (only `set` takes values)")
        key, value = text, None
    key = key.strip()
    if _PAREN_ANY_RE.search(key):
        hint = _PAREN_ANY_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)}", key)
        raise PropEditError(f"{key}: the (N) index form is not accepted — "
                            f"use the dot form: {hint}")
    parts = key.split(".")
    base = parts[0]
    if not _IDENT_RE.match(base):
        raise PropEditError(f"bad property key: {key!r}")
    segs: list[object] = []
    for seg in parts[1:]:
        if _INT_RE.match(seg):
            iv = int(seg)
            if iv < 0:
                raise PropEditError(f"{key}: negative array index {iv} is invalid")
            segs.append(iv)
        elif _IDENT_RE.match(seg):
            segs.append(seg)
        else:
            raise PropEditError(f"bad path segment {seg!r} in {key!r}")
    return PropToken(base=base, segs=tuple(segs), value=value, raw=text)


def check_hard_reject(tok: PropToken) -> None:
    if tok.base.casefold() in HARD_REJECT:
        raise PropEditError(f"property {tok.base} cannot be accessed via `actor prop` "
                            "(Name/Brush are internal; author mover keys with `mover key`)")


def check_overlaps(tokens: list[PropToken]) -> None:
    """Intra-invocation conflict rule (set/unset only, spec §3.1): two tokens whose targets
    overlap — same base with one path a prefix of the other (or equal) — exit 2."""
    seen: list[tuple[PropToken, tuple]] = []
    for t in tokens:
        ident = (t.base.casefold(),) + tuple(
            s if isinstance(s, int) else s.casefold() for s in t.segs)
        for prev, pid in seen:
            short, long_ = (pid, ident) if len(pid) <= len(ident) else (ident, pid)
            if long_[:len(short)] == short:
                raise PropEditError(f"conflicting tokens in one invocation: "
                                    f"{prev.raw!r} and {t.raw!r}")
        seen.append((t, ident))


# ── struct-text helpers ──────────────────────────────────────────────────────────────────────

def split_struct_text(text: str) -> list[tuple[str, str]] | None:
    """`(A=1,B=(C=2))` → [("A","1"), ("B","(C=2)")]; None if not a parenthesized K=V list.
    Keys may be identifiers, integers (the array tuple form), or `Name(N)` (a struct member
    that is a static array).

    The member split and the name/value `=` both come from `typedprops`
    (`split_struct_members` / `top_level_eq`) — the SAME quote- and depth-aware code the typed
    compare path uses — so the two struct-literal parsers in the codebase cannot disagree. That
    is what makes a quoted comma or a quoted `=` inside a member value safe: `(Msg="a,b",N=1)`
    is two members, not three, and `(Msg="x=y")` has value `"x=y"`.

    This one differs from `typedprops.parse_struct_text` ONLY in its result shape: an ORDERED
    list with the key's authored case preserved, because `emit_struct_text` writes the members
    back out and a struct's member order and spelling are part of the emitted T3D."""
    items = typedprops.split_struct_members(text)
    if items is None:
        return None
    out: list[tuple[str, str]] = []
    for item in items:
        eq = typedprops.top_level_eq(item)
        if eq is None:
            return None
        out.append((item[:eq].strip(), item[eq + 1:].strip()))
    return out


def emit_struct_text(pairs: list[tuple[str, str]]) -> str:
    return "(" + ",".join(f"{k}={v}" for k, v in pairs) + ")"


# ── path resolution against the schema ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class MemberStep:
    prop: Prop                           # the member Prop (canonical spelling in .name)
    index: int | None                    # element index when the MEMBER is a static array

    @property
    def text_key(self) -> str:
        """The member's spelling inside a struct-text value (`Marks(1)` for an indexed
        member-array element, else the bare name)."""
        return self.prop.name if self.index is None else f"{self.prop.name}({self.index})"


@dataclass(frozen=True)
class ResolvedPath:
    prop: Prop                           # the base property
    index: int | None                    # base-level array index, if any
    members: tuple[MemberStep, ...]      # the struct member chain after the (optional) index
    canonical: str                       # canonical dot spelling, e.g. "Nest.Marks.1"

    @property
    def leaf(self) -> Prop:
        return self.members[-1].prop if self.members else self.prop

    @property
    def is_whole(self) -> bool:
        return self.index is None and not self.members


def resolve_path(tok: PropToken, ctx: ClassCtx) -> ResolvedPath:
    """Validate `tok`'s base + path against the class schema; returns canonical spellings and
    the leaf Prop. Raises `PropEditError` naming the failing segment. State machine: an int
    segment indexes the CURRENT slot when it is an un-indexed static array (the base prop or a
    member array); an identifier segment requires the current slot to be a struct."""
    schema = ctx.schema()
    prop = schema.get(tok.base.casefold())
    if prop is None:
        raise PropEditError(f"unknown property {tok.base} on class {ctx.cls}")
    segs = list(tok.segs)
    index: int | None = None
    if segs and isinstance(segs[0], int):
        if prop.array_dim <= 1:
            raise PropEditError(f"{prop.name} is not a static array (cannot index "
                                f"{tok.base}.{segs[0]})")
        if segs[0] >= prop.array_dim:
            raise PropEditError(f"{tok.base}.{segs[0]}: index out of bounds "
                                f"(array size {prop.array_dim}, valid 0..{prop.array_dim - 1})")
        index = segs.pop(0)
    members: list[MemberStep] = []
    cur = prop
    for seg in segs:
        if isinstance(seg, int):
            last = members[-1] if members else None
            if last is not None and last.index is None and last.prop.array_dim > 1:
                if seg >= last.prop.array_dim:
                    raise PropEditError(
                        f"{tok.raw}: index {seg} out of bounds for {last.prop.name} "
                        f"(array size {last.prop.array_dim})")
                members[-1] = MemberStep(prop=last.prop, index=seg)
                continue
            raise PropEditError(f"{tok.raw}: unexpected index .{seg} "
                                f"({cur.name} is not an indexable static array here)")
        if cur.kind != "StructProperty":
            raise PropEditError(f"{cur.name} is not a struct (cannot take member .{seg})")
        last = members[-1] if members else None
        if last is not None and last.prop.array_dim > 1 and last.index is None:
            raise PropEditError(f"{tok.raw}: {last.prop.name} is a static array — index it "
                                f"({last.prop.name}.N) before taking member .{seg}")
        mlist = ctx.members(cur)
        m = next((mm for mm in mlist if mm.name.casefold() == seg.casefold()), None)
        if m is None:
            valid = ", ".join(mm.name for mm in mlist)
            raise PropEditError(f"unknown member {seg} of {cur.type_name or cur.name} "
                                f"(valid: {valid})")
        members.append(MemberStep(prop=m, index=None))
        cur = m
    canonical = prop.name
    if index is not None:
        canonical += f".{index}"
    for step in members:
        canonical += f".{step.prop.name}"
        if step.index is not None:
            canonical += f".{step.index}"
    return ResolvedPath(prop=prop, index=index, members=tuple(members), canonical=canonical)


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


# ── zero synthesis + effective values ────────────────────────────────────────────────────────

def zero_value(prop: Prop, ctx: ClassCtx) -> str:
    """The type's ZERO in canonical form (spec §2.3): what the engine uses when neither the
    actor nor any class default mentions the prop."""
    if prop.kind == "BoolProperty":
        return "False"
    if prop.kind in ("IntProperty", "FloatProperty"):
        return "0"
    if prop.kind == "ByteProperty":
        names = ctx.enums(prop)
        return names[0] if names else "0"
    if prop.kind in ("NameProperty", "ObjectProperty", "ClassProperty"):
        return "None"
    if prop.kind == "StrProperty":
        return ""
    if prop.kind == "StructProperty":
        pairs: list[tuple[str, str]] = []
        for m in ctx.members(prop):
            if m.array_dim > 1:                      # member static array: per-element spelling
                mz = zero_value(m, ctx)
                pairs.extend((f"{m.name}({i})", mz) for i in range(m.array_dim))
            else:
                pairs.append((m.name, zero_value(m, ctx)))
        return emit_struct_text(pairs)
    return ""                                        # Array/Pointer: empty (out of scope, §3)


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


def _member_map(members: list[Prop]) -> dict[str, Prop]:
    return {m.name.casefold(): m for m in members}


def _text_key_ident(k: str) -> tuple[str, int | None]:
    m = _PAREN_KEY_RE.match(k)
    if m is not None:
        return m.group(1).casefold(), int(m.group(2))
    return k.casefold(), None


def merge_struct_texts(prop: Prop, base_text: str, over_text: str, ctx: ClassCtx) -> str:
    """Merge `over_text`'s members onto `base_text`'s, RECURSIVELY for struct-typed members
    (review finding: a stored partial NESTED member must not wholesale-replace the default's
    nested struct — the engine merges member-wise at every depth, per the §9 probe). Member
    order follows the base; over-only members append. Unparseable sides pass through."""
    bp = split_struct_text(base_text)
    op = split_struct_text(over_text)
    if bp is None or op is None:
        return over_text                             # un-mergeable over side passes through
    members = _member_map(ctx.members(prop)) if prop.kind == "StructProperty" else {}
    over_by_ident = { _text_key_ident(k): v for k, v in op }
    merged: list[tuple[str, str]] = []
    seen: set[tuple[str, int | None]] = set()
    for k, v in bp:
        ident = _text_key_ident(k)
        seen.add(ident)
        ov = over_by_ident.get(ident)
        if ov is None:
            merged.append((k, v))
            continue
        m = members.get(ident[0])
        if m is not None and m.kind == "StructProperty":
            merged.append((k, merge_struct_texts(m, v, ov, ctx)))
        else:
            merged.append((k, ov))
    for k, v in op:
        if _text_key_ident(k) not in seen:
            merged.append((k, v))
    return emit_struct_text(merged)


def full_struct_text(prop: Prop, index: int, stored_text: str | None, ctx: ClassCtx) -> str:
    """The EFFECTIVE full-member struct text for `prop[index]`: stored members merged
    RECURSIVELY over the class default, over the zero struct (every member explicit — spec §4).
    With no stored value: default over zero."""
    zero = zero_value(prop, ctx)
    dflt = ctx.defaults().get((prop.name.casefold(), index))
    base = merge_struct_texts(prop, zero, dflt, ctx) if dflt is not None else zero
    if stored_text is None:
        return base
    return merge_struct_texts(prop, base, _dequote(stored_text), ctx)


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


# ── set/unset planning ───────────────────────────────────────────────────────────────────────

_VR_STRUCTS = {"vector", "rotator"}


def _maybe_comma_sugar(prop: Prop, value: str) -> str:
    """Vector/Rotator comma sugar (spec §2.1, ruling R1): interpreted ONLY when the schema says
    the prop is a Vector/Rotator struct; on every other prop a comma value is verbatim text."""
    if prop.kind != "StructProperty" or (prop.type_name or "").casefold() not in _VR_STRUCTS:
        return value
    t = _dequote(value)
    if t.startswith("(") or "," not in t:
        return value
    parts = [p.strip() for p in t.split(",")]
    if len(parts) != 3:
        raise PropEditError(f"{prop.name}={value}: {prop.type_name} comma form needs exactly "
                            f"3 components, got {len(parts)}")
    for p in parts:
        _dec_finite(p, f"{prop.name}={value}")
    axes = ("X", "Y", "Z") if (prop.type_name or "").casefold() == "vector" \
        else ("Pitch", "Yaw", "Roll")
    return emit_struct_text(list(zip(axes, parts)))


def _set_member_in_text(base_text: str, steps: tuple[MemberStep, ...], value: str,
                        label: str) -> str:
    """Set the (possibly nested) member chain inside a struct text, preserving every other
    member as stored. Member-array elements address their `Name(N)` entry."""
    pairs = split_struct_text(base_text)
    if pairs is None:
        raise PropEditError(f"{label}: stored value is not a struct literal: {base_text!r}")
    step = steps[0]
    rest = steps[1:]
    want = (step.prop.name.casefold(), step.index)
    hit_i = next((i for i, (k, _v) in enumerate(pairs)
                  if _text_key_ident(k) == want), None)
    if rest:
        inner = pairs[hit_i][1] if hit_i is not None else "()"
        new_inner = _set_member_in_text(inner if inner.strip().startswith("(") else "()",
                                        rest, value, label)
        entry = (step.text_key, new_inner)
    else:
        entry = (step.text_key, value)
    if hit_i is not None:
        pairs[hit_i] = entry
    else:
        pairs.append(entry)
    return emit_struct_text(pairs)


def _unset_member_in_text(base_text: str, steps: tuple[MemberStep, ...],
                          label: str) -> tuple[bool, str | None]:
    """Remove the member chain from a struct text. Returns (changed, new_text|None) — None
    when the struct becomes empty (→ the whole stored line is removed, spec §3.1); changed
    False when the member wasn't stored (silent success MUST NOT rewrite the trunk — review
    finding: a no-op used to re-emit the normalized text)."""
    pairs = split_struct_text(base_text)
    if pairs is None:
        raise PropEditError(f"{label}: stored value is not a struct literal: {base_text!r}")
    step = steps[0]
    rest = steps[1:]
    want = (step.prop.name.casefold(), step.index)
    hit_i = next((i for i, (k, _v) in enumerate(pairs)
                  if _text_key_ident(k) == want), None)
    if hit_i is None:
        return False, base_text
    if rest:
        changed, inner = _unset_member_in_text(pairs[hit_i][1], rest, label)
        if not changed:
            return False, base_text
        if inner is None:
            del pairs[hit_i]
        else:
            pairs[hit_i] = (pairs[hit_i][0], inner)
    else:
        del pairs[hit_i]
    if not pairs:
        return True, None
    return True, emit_struct_text(pairs)


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
            from . import movers
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


# ── the typed-field registry (spec §6) ───────────────────────────────────────────────────────

def _fmt_dec(d) -> str:
    """A Decimal/number → trimmed canonical text (`4`, `-17`, `32.5`). A non-finite value
    (only reachable from a hand-authored trunk) renders as its raw text rather than raising."""
    try:
        dd = Decimal(str(d))
        if not dd.is_finite():
            return str(d)
        if dd == dd.to_integral_value():
            return str(int(dd))
        return format(dd.normalize(), "f")
    except (InvalidOperation, ValueError):
        return str(d)


@dataclass(frozen=True)
class TypedField:
    """A typed model field routed through the prop verbs (Location today; one registry entry
    per future field — spec §6). Pure vector semantics: whole-value set ZERO-FILLS unmentioned
    axes (ruling R2), member set bases on the current value, member unset zeroes the axis,
    whole unset resets to the zero (origin). `attr` names the `model.Actor` attribute the registry
    routes through; `dump_always` keeps Location in the `get` dump even when unset (a scale field is
    dumped only when the actor actually carries it)."""
    name: str                                        # canonical spelling ("Location")
    axes: tuple[str, ...] = ("X", "Y", "Z")
    attr: str = "location"                           # the model.Actor attribute this field routes to
    dump_always: bool = True

    def _axis_of(self, tok: PropToken) -> str | None:
        """The single member axis of `tok`'s path (None = whole field). Validates the path."""
        if not tok.segs:
            return None
        if len(tok.segs) > 1:
            raise PropEditError(f"{tok.raw}: {self.name} takes at most one member segment")
        seg = tok.segs[0]
        if isinstance(seg, int):
            raise PropEditError(f"{tok.raw}: {self.name} is not a static array")
        hit = next((a for a in self.axes if a.casefold() == seg.casefold()), None)
        if hit is None:
            raise PropEditError(f"unknown member {seg} of {self.name} "
                                f"(valid: {', '.join(self.axes)})")
        return hit

    def _tuple(self, location) -> tuple:
        return location if location is not None else (Decimal(0),) * len(self.axes)

    def text(self, location) -> str:
        vals = self._tuple(location)
        return emit_struct_text([(a, _fmt_dec(v)) for a, v in zip(self.axes, vals)])

    def get(self, tok: PropToken | None, location) -> tuple[str, str]:
        """(canonical key, value text) — the whole field, or one axis bare."""
        if tok is None:
            return self.name, self.text(location)
        axis = self._axis_of(tok)
        if axis is None:
            return self.name, self.text(location)
        vals = dict(zip([a.casefold() for a in self.axes], self._tuple(location)))
        return f"{self.name}.{axis}", _fmt_dec(vals[axis.casefold()])

    def _parse_whole(self, value: str) -> tuple:
        """A whole-value text → the axis tuple. Struct form `(X=1)` ZERO-FILLS unmentioned
        axes (ruling R2); the bare positional comma form requires every axis. Components must
        be finite, engine-range numbers."""
        t = _dequote(value)
        pairs = split_struct_text(t)
        if pairs is not None:
            vals = {a.casefold(): Decimal(0) for a in self.axes}
            for k, v in pairs:
                if k.casefold() not in vals:
                    raise PropEditError(f"unknown member {k} of {self.name} "
                                        f"(valid: {', '.join(self.axes)})")
                vals[k.casefold()] = _dec_finite(v, f"{self.name}.{k}")
            return tuple(vals[a.casefold()] for a in self.axes)
        parts = [p.strip() for p in t.split(",")]
        if len(parts) != len(self.axes):
            raise PropEditError(f"{self.name}={value}: expected (X=..,Y=..,Z=..) or the "
                                f"positional X,Y,Z form (all {len(self.axes)} components)")
        return tuple(_dec_finite(p, self.name) for p in parts)

    def apply(self, tok: PropToken, mode: str, location):
        """Apply a set/unset token; returns the new location tuple (None == origin reset)."""
        axis = self._axis_of(tok)
        if mode == "unset":
            if axis is None:
                return None                          # whole unset → origin
            vals = list(self._tuple(location))
            vals[[a.casefold() for a in self.axes].index(axis.casefold())] = Decimal(0)
            return tuple(vals)
        assert tok.value is not None
        if axis is None:
            return self._parse_whole(tok.value)
        v = _dec_finite(tok.value, tok.raw)
        vals = list(self._tuple(location))
        vals[[a.casefold() for a in self.axes].index(axis.casefold())] = v
        return tuple(vals)

    def match(self, tok: PropToken, location) -> bool:
        """`find --prop` comparison for the typed field: numeric, member-wise. A value that
        cannot parse RAISES (a never-matchable token is a typo, not an empty result — review
        finding)."""
        assert tok.value is not None
        axis = self._axis_of(tok)
        if axis is None:
            want = self._parse_whole(tok.value)
            return tuple(self._tuple(location)) == tuple(want)
        vals = dict(zip([a.casefold() for a in self.axes], self._tuple(location)))
        return vals[axis.casefold()] == _dec_finite(tok.value, tok.raw)


@dataclass(frozen=True)
class ScaleField:
    """A typed `MainScale`/`PostScale` field (a `transform.FScale`: `Scale` FVector + `SheerRate` +
    `SheerAxis`) routed through the prop verbs (spec §10). Paths: whole; `.Scale`, `.Scale.X|Y|Z`;
    `.SheerRate`; `.SheerAxis`. Member set bases on the current value; member unset reverts that
    member to its class default (scale 1.0, rate 0, axis SHEER_ZX); whole unset resets to identity.
    The stored value is a `transform.FScale` (or None == identity/absent). Shares the TypedField
    interface (`get`/`apply`/`match`, `attr`, `dump_always`)."""
    name: str                                        # "MainScale" / "PostScale"
    attr: str                                        # "main_scale" / "post_scale"
    dump_always: bool = False                        # dump only when the actor carries the field

    def _fs(self, value):
        from .transform import IDENTITY
        return value if value is not None else IDENTITY

    def _member(self, tok: PropToken):
        """The lowercased member chain of the path (validated). () = whole field."""
        segs = tok.segs
        if not segs:
            return ()
        if any(isinstance(s, int) for s in segs):
            raise PropEditError(f"{tok.raw}: {self.name} has no static-array member")
        low = tuple(s.casefold() for s in segs)
        if low[0] == "scale":
            if len(low) == 1:
                return ("scale",)
            if len(low) == 2 and low[1] in ("x", "y", "z"):
                return ("scale", low[1])
            raise PropEditError(f"{tok.raw}: {self.name}.Scale members are X, Y, Z")
        if low[0] in ("sheerrate", "sheeraxis") and len(low) == 1:
            return (low[0],)
        raise PropEditError(f"unknown member {segs[0]} of {self.name} "
                            f"(valid: Scale, Scale.X/Y/Z, SheerRate, SheerAxis)")

    def _whole_text(self, fs) -> str:
        sx, sy, sz = (_fmt_dec(c) for c in fs.scale)
        return (f"(Scale=(X={sx},Y={sy},Z={sz}),"
                f"SheerRate={_fmt_dec(fs.sheer_rate)},SheerAxis={fs.sheer_axis})")

    def get(self, tok: PropToken | None, value) -> tuple[str, str]:
        fs = self._fs(value)
        chain = () if tok is None else self._member(tok)
        if chain == ():
            return self.name, self._whole_text(fs)
        if chain == ("scale",):
            sx, sy, sz = (_fmt_dec(c) for c in fs.scale)
            return f"{self.name}.Scale", f"(X={sx},Y={sy},Z={sz})"
        if chain[0] == "scale":
            idx = {"x": 0, "y": 1, "z": 2}[chain[1]]
            return f"{self.name}.Scale.{chain[1].upper()}", _fmt_dec(fs.scale[idx])
        if chain == ("sheerrate",):
            return f"{self.name}.SheerRate", _fmt_dec(fs.sheer_rate)
        return f"{self.name}.SheerAxis", fs.sheer_axis

    def _parse_whole(self, value: str):
        """A whole-value text → a validated `FScale`. Struct form `(Scale=(…),SheerRate=,SheerAxis=)`
        validates every member (unknown member / non-numeric → PropEditError, never a silent
        identity); the bare comma form is the Scale axes. Shared by set + find-match so a garbage
        value is a NAMED error, not a silent no-op (CLAUDE.md: errors name the offending value)."""
        from .transform import DEFAULT_SHEER_AXIS, FScale
        pairs = split_struct_text(_dequote(value))
        if pairs is None:                                # bare comma form → Scale axes
            return FScale(self._parse_scale_vec(value), Decimal(0), DEFAULT_SHEER_AXIS)
        scale, rate, axis = [Decimal(1), Decimal(1), Decimal(1)], Decimal(0), DEFAULT_SHEER_AXIS
        for k, v in pairs:
            kl = k.casefold()
            if kl == "scale":
                scale = list(self._parse_scale_vec(v))
            elif kl == "sheerrate":
                rate = _dec_finite(v, f"{self.name}.SheerRate")
            elif kl == "sheeraxis":
                av = _dequote(v).strip()
                if not av.upper().startswith("SHEER_"):
                    raise PropEditError(f"{self.name}.SheerAxis must be a SHEER_* value, got {v!r}")
                axis = av.upper()
            else:
                raise PropEditError(f"unknown member {k} of {self.name} "
                                    f"(valid: Scale, SheerRate, SheerAxis)")
        return FScale(tuple(scale), rate, axis)

    def _parse_scale_vec(self, value: str) -> tuple:
        pairs = split_struct_text(_dequote(value))
        if pairs is not None:
            vals = {"x": Decimal(1), "y": Decimal(1), "z": Decimal(1)}
            for k, v in pairs:
                if k.casefold() not in vals:
                    raise PropEditError(f"unknown member {k} of {self.name}.Scale (valid: X, Y, Z)")
                vals[k.casefold()] = _dec_finite(v, f"{self.name}.Scale.{k}")
            return (vals["x"], vals["y"], vals["z"])
        parts = [p.strip() for p in _dequote(value).split(",")]
        if len(parts) != 3:
            raise PropEditError(f"{self.name}.Scale={value}: expected (X=..,Y=..,Z=..) or X,Y,Z")
        return tuple(_dec_finite(p, f"{self.name}.Scale") for p in parts)

    def apply(self, tok: PropToken, mode: str, value):
        from .transform import IDENTITY, FScale
        fs = self._fs(value)
        chain = self._member(tok)
        if mode == "unset":
            if chain == ():
                return IDENTITY
            if chain == ("scale",):
                return FScale((Decimal(1),) * 3, fs.sheer_rate, fs.sheer_axis)
            if chain[0] == "scale":
                sc = list(fs.scale); sc[{"x": 0, "y": 1, "z": 2}[chain[1]]] = Decimal(1)
                return FScale(tuple(sc), fs.sheer_rate, fs.sheer_axis)
            if chain == ("sheerrate",):
                return FScale(fs.scale, Decimal(0), fs.sheer_axis)
            return FScale(fs.scale, fs.sheer_rate, "SHEER_ZX")
        assert tok.value is not None
        if chain == ():
            return self._parse_whole(tok.value)          # validates (no silent identity on garbage)
        if chain == ("scale",):
            return FScale(self._parse_scale_vec(tok.value), fs.sheer_rate, fs.sheer_axis)
        if chain[0] == "scale":
            sc = list(fs.scale)
            sc[{"x": 0, "y": 1, "z": 2}[chain[1]]] = _dec_finite(tok.value, tok.raw)
            return FScale(tuple(sc), fs.sheer_rate, fs.sheer_axis)
        if chain == ("sheerrate",):
            return FScale(fs.scale, _dec_finite(tok.value, tok.raw), fs.sheer_axis)
        axis = _dequote(tok.value).strip()
        if not axis.upper().startswith("SHEER_"):
            raise PropEditError(f"{tok.raw}: SheerAxis must be a SHEER_* value, got {tok.value!r}")
        return FScale(fs.scale, fs.sheer_rate, axis.upper())

    def match(self, tok: PropToken, value) -> bool:
        """`find --prop` comparison for the FScale field: numeric member-wise, axis case-fold."""
        assert tok.value is not None
        chain = self._member(tok)
        fs = self._fs(value)
        want = _dequote(tok.value).strip()

        def _d(x) -> Decimal:
            return x if isinstance(x, Decimal) else Decimal(str(x))

        if chain == ():
            w = self._parse_whole(tok.value)             # validates: garbage → error, not no-match
            return (tuple(_d(c) for c in fs.scale) == tuple(_d(c) for c in w.scale)
                    and _d(fs.sheer_rate) == _d(w.sheer_rate)
                    and fs.sheer_axis.casefold() == w.sheer_axis.casefold())
        if chain == ("scale",):
            return tuple(_d(c) for c in fs.scale) == tuple(_d(c) for c in self._parse_scale_vec(want))
        if chain[0] == "scale":
            return _d(fs.scale[{"x": 0, "y": 1, "z": 2}[chain[1]]]) == _dec_finite(tok.value, tok.raw)
        if chain == ("sheerrate",):
            return _d(fs.sheer_rate) == _dec_finite(tok.value, tok.raw)
        return fs.sheer_axis.casefold() == want.casefold()


TYPED_FIELDS: dict[str, TypedField | ScaleField] = {
    "location": TypedField(name="Location"),
    "mainscale": ScaleField(name="MainScale", attr="main_scale"),
    "postscale": ScaleField(name="PostScale", attr="post_scale"),
}


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

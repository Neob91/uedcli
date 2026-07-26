"""Per-invocation, memoized CLASS INFO — the declared property types plus the class defaults the
typed compare needs.

**Why this exists.** UnrealEd's T3D export is *member-precise default-diffing*: it omits a whole
property equal to the class default, and omits an individual struct member equal to the default
member (`dev/docs/unrealed/t3d.md` "Partial struct/array property values", live-confirmed
2026-07-18). uedcli USED TO test against ZERO — this module is what replaced that. The two coincide
for almost every class, which is why the divergence hid for so long, and they parted company in two
ways:

* uedcli wrote a spelling the editor never writes -> the H3 post-verify aborted the build with
  nothing written (a *loud* failure);
* uedcli OMITTED a property whose class default is NOT zero -> the engine substitutes its default,
  so the built map was WRONG, and post-verify PASSED because both compare sides shared the mistake
  (a *silent* failure).

This module supplies BOTH halves the compare needs per class: the decoded **defaults** and the
declared **types** (as `typedprops.Field` trees), so `normalize.compare_view` can compute each
actor's *effective typed value* per property — the stored value if present, else the class default —
instead of comparing text. It is used ONLY on the throwaway compare copy — never on the durable
trunk emit, whose bytes must not depend on which packages happen to be installed (see
`normalize.canonical_actor_t3d`).

**No fallback default, ever.** Fabricating `(0,0,0)` for an unresolvable class is precisely the
zero-based bug this module exists to remove, and it would reintroduce it on the one path whose job
is to catch wrongness. `for_class` raises; callers surface it as a clean exit-2 (repo rule: no
silent half-answers, and no Python exception reaching the CLI user).
"""
from __future__ import annotations

from . import typedprops, uprops
from .typedprops import Field

# `uprops.Prop.kind` (the UProperty subclass) -> the compare-side `Field.kind`. `ByteProperty` is
# resolved separately: with an enum it is an ENUM (compared by ordinal), without one a plain BYTE.
_KIND_BY_PROPERTY = {
    "FloatProperty": typedprops.FLOAT,
    "IntProperty": typedprops.INT,
    "BoolProperty": typedprops.BOOL,
    "NameProperty": typedprops.NAME,
    "StrProperty": typedprops.STRING,
    "ObjectProperty": typedprops.OBJECT,
    "ClassProperty": typedprops.OBJECT,
    "StructProperty": typedprops.STRUCT,
}


class ClassInfo:
    """One class's compare-side type + default knowledge, resolved once and shared by every actor
    of that class on BOTH compare sides.

    * `fields` — `casefold(prop name) -> typedprops.Field`, the declared type of each property
      (recursively for struct members). A property missing here is compared untyped (its text
      shape), never against a synthesized zero.
    * `defaults` — `(casefold(prop name), array index) -> default TEXT`, exactly as
      `uprops.resolve_class_defaults` renders it.
    * `typed_default(key)` — the memoized effective value of a property NO actor states: the class
      default decoded through its `Field`, else the type's zero, else `typedprops.ABSENT`.
    """

    def __init__(self, fqcn: str, fields: dict[str, Field],
                 defaults: dict[tuple[str, int], str]):
        self.fqcn = fqcn
        self.fields = fields
        self.defaults = defaults
        self._typed: dict[tuple[str, int], object] = {}

    def field(self, name: str) -> Field:
        """The declared type of the property named `name` (casefolded), or the UNKNOWN field.

        `Location`/`MainScale`/`PostScale` fall back to the layout the MODEL itself assumes
        (`typedprops.MODEL_TYPED_FIELDS`) when the schema has no usable entry, because they are
        parsed out of the property list into typed model fields and the compare re-renders them from
        there. Both compare sides go through THIS one lookup — the stating side to decode its value
        and the omitting side via `typed_default` — so they can never end up typed differently,
        which for those three would be a permanently unpassable post-verify."""
        f = self.fields.get(name)
        if f is None or (f.kind == typedprops.STRUCT and not f.members):
            fallback = typedprops.MODEL_TYPED_FIELDS.get(name)
            if fallback is not None:
                return fallback
        return f if f is not None else typedprops.UNKNOWN_FIELD

    def typed_default(self, key: tuple[str, int]):
        """The effective value of `key` for an actor that does not state it."""
        hit = self._typed.get(key)
        if hit is None:
            f = self.field(key[0])
            text = self.defaults.get(key)
            if text is not None:
                hit = typedprops.typed_value(text, f)
            else:
                hit = typedprops.zero_value(f)
            self._typed[key] = hit
        return hit


class ClassDefaults:
    """Memoized `fqcn -> ClassInfo` over ONE shared package map.

    Sharing the `_pkgs` dict across the whole level is the entire performance story: a cold class
    resolution costs ~0.1-0.3 s (a package load, the Super-chain property walk, the defaults decode
    and every struct/enum layout), but ~0.01-0.03 s amortized once the packages are loaded once.
    A level has 5-60
    DISTINCT classes across hundreds of actors, so the memo turns a per-actor cost into a per-class
    one — and the compare then resolves each distinct class exactly ONCE.

    Callers resolve every class of a level UP FRONT, before spinning up the editor, so an
    unresolvable class costs ~0.1 s instead of failing after a ~100 s build — see
    `apply._level_defaults`, which walks the level's ACTORS (not a bare class list) precisely so its
    error can name the offending actor as well as its class. Everything a compare needs — property
    types, enum value names, struct member layouts, defaults — is resolved there and then, so the
    compare itself can never fail on a missing package after the build.
    """

    def __init__(self, resolver):
        self._resolver = resolver
        self._pkgs: dict = {}
        self._memo: dict[str, ClassInfo] = {}
        self._structs: dict[tuple, Field] = {}
        self._resolving: set[tuple] = set()   # struct types mid-decode (self-reference guard)
        self.resolutions = 0     # distinct classes decoded; read by the perf regression test

    def for_class(self, fqcn: str) -> ClassInfo:
        """The class's compare-side info. Raises `uprops.SchemaError` if it cannot be resolved
        (bare/unqualified name, missing package, class not in package, decode failure)."""
        key = fqcn.casefold()
        hit = self._memo.get(key)
        if hit is None:
            hit = self._memo[key] = self._resolve(fqcn)
            self.resolutions += 1
        return hit

    # ── resolution ──────────────────────────────────────────────────────────────────────────────

    def _resolve(self, fqcn: str) -> ClassInfo:
        # ONE package map for all three passes. `resolve_class_defaults` has to `load_package` every
        # package on the chain anyway, so seeding the same dict into `resolve_class_properties`
        # (whose `_cache` then takes its pre-seeded live-decode branch instead of the persistent
        # schema cache) costs nothing and saves a second read of bytes already in memory.
        props = uprops.resolve_class_properties(fqcn, resolver=self._resolver, _cache=self._pkgs)
        schema = {p.name.casefold(): p for p in props}
        defaults = uprops.resolve_class_defaults(fqcn, resolver=self._resolver, schema=schema,
                                                 _pkgs=self._pkgs)
        fields = {name: self._field_for(p) for name, p in schema.items()}
        return ClassInfo(fqcn, fields, defaults)

    def _package(self, name: str):
        pkg = self._pkgs.get(name)
        if not isinstance(pkg, uprops.Package):
            path = self._resolver(name)
            if path is None:
                raise uprops.SchemaError(
                    f"package {name!r} not found on the schema search path (needed to type its "
                    f"properties)")
            pkg = self._pkgs[name] = uprops.load_package(path, name=name)
        return pkg

    def _field_for(self, prop, pkg=None) -> Field:
        """Compile one `uprops.Prop` into a `typedprops.Field`, resolving a ByteProperty's enum
        names and a StructProperty's member layout (recursively) through the shared package map.

        `pkg` is the package the prop's `type_ref` resolves against: a CLASS property's own
        declaring package (derived from `prop.owner`, an FQCN), or — for a STRUCT MEMBER, whose
        `owner` is the bare struct name — the package the struct type itself was decoded from."""
        kind = _KIND_BY_PROPERTY.get(prop.kind)
        if prop.kind == "ByteProperty":
            if prop.type_ref == 0:
                return Field(typedprops.BYTE)
            names = uprops.resolve_enum_names(prop, pkg or self._package(_pkg_name(prop.owner)),
                                              resolver=self._resolver, _pkgs=self._pkgs)
            return Field(typedprops.ENUM, enum=tuple(names)) if names else Field(typedprops.BYTE)
        if kind == typedprops.STRUCT:
            if prop.type_ref == 0:
                return Field(typedprops.STRUCT)
            return self._struct_field(prop, pkg or self._package(_pkg_name(prop.owner)))
        return Field(kind) if kind else typedprops.UNKNOWN_FIELD

    def _struct_field(self, prop, pkg) -> Field:
        """A StructProperty's member layout as a `Field`, memoized per `(package, struct name)` —
        `FVector` alone is reached by dozens of properties per class."""
        tp, ti = uprops.resolve_type_export(pkg, prop.type_ref, "Struct",
                                             resolver=self._resolver, _pkgs=self._pkgs)
        cache_key = (tp.name, (prop.type_name or "").casefold(), ti)
        hit = self._structs.get(cache_key)
        if hit is None:
            if cache_key in self._resolving:
                raise uprops.SchemaError(
                    f"struct {prop.type_name or prop.name} contains itself (corrupt package)")
            self._resolving.add(cache_key)
            try:
                members = uprops.struct_members(tp, ti, owner=prop.type_name or prop.name)
                hit = self._structs[cache_key] = Field(
                    typedprops.STRUCT,
                    members=tuple((m.name.casefold(), self._field_for(m, tp)) for m in members))
            finally:
                self._resolving.discard(cache_key)
        return hit


def _pkg_name(owner: str) -> str:
    return owner.split(".", 1)[0]

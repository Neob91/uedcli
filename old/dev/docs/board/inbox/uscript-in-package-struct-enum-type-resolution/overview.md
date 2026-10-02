+++
priority = "p3"
kind = "investigate"
summary = "uscript: in-package struct/enum type resolution incomplete for cross-sibling declarations"
+++

# uscript: in-package struct/enum type resolution incomplete for cross-sibling declarations

Found in code review of the `SamePkgInheritedDefault` fix (round landing `SeanMutator`/
`ProtectSeanMutator`/`VampireSeanMutator`). `_PkgSigGraph` (`compile.py`) overrides `class_sig()` and
`enum_ordinal()` to also see an in-progress package's own classes (no compiled bytes yet for the
disk-backed `ClassGraph` to read) — but NOT `is_struct_name`/`is_enum_name`/`struct_member_type`.

**Concretely:** `_super_field_order`'s new in-package fallback (`compile.py`, `members_of`/
`type_label`) mislabels a struct- or enum-TYPED inherited field as `object:x` when the struct/enum is
declared in a DIFFERENT in-package sibling class (not the field's own declaring class, not a disk
package). Example: sibling A declares `enum EFoo {...}`; same-package super B has `var EFoo Kind;`;
subclass C overrides `Kind=SomeValue` in `defaultproperties`. `type_label` can't see A's enum via
`graph`, so `Kind` is mislabeled `object:efoo` — `_emit_inherited_defaults` then either raises a
misleading `NotImplementedError` for an enum-constant value, or (worse, silently) emits a wrong
zero-object-ref tag for an explicit `Foo=None` struct default.

`ClassGraph.struct_member_type` has the same gap and is worse: it fails SILENTLY (returns `None`)
rather than raising.

**Not fixed here**: no current corpus package exercises this shape (`pkg_SamePkgInheritedDefault`
only covers a plain `int` field); fixing needs `ClassSig` to track each in-package class's own
struct/enum TYPE names (not just enum tags, which `enums` already covers), threaded through
`_prepass_signatures` and new `_PkgSigGraph.is_struct_name`/`is_enum_name`/`struct_member_type`
overrides mirroring the existing `enum_ordinal` pattern. Settle with a controlled cross-sibling
struct/enum fixture + live UCC before landing.

**Also flagged, not acted on** (simplification, not correctness): `_super_field_order`'s new
in-package branch re-derives a field-type map via `members_of()` from scratch instead of reusing
`ClassSig.members`/`member_owner` that `_prepass_signatures` already computed; the new
`_Build.in_pkg_decls` index is redundant with the pre-existing `in_pkg_class_names` for everything
this function needs; and the in-package/disk-decode branches hand-roll the same casefold/seen/append
dedup twice. Worth a cleanup pass if this area gets touched again.

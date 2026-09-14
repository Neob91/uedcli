+++
priority = "p3"
kind = "unknown"
summary = "uscript: struct-member access on a LOCALLY-declared struct is untested"
+++

# uscript: struct-member access on a LOCALLY-declared struct is untested

Found reviewing the struct-member identity fix (`dev/docs/board/done/
uscript-struct-member-access-confuses-a-local/`). `lower._struct_member_ident` always qualifies an
`EX_StructMember` token's identity as `smem:<Struct>.<Field>`, resolved via an import
(`compile._add_struct_member_import`). That's correct for every struct type this compiler currently
resolves — all cross-package (`Vector`/`Rotator`/`IpAddr`/etc, via
`_func_prop_type`/`_resolve_array_type`/`_resolve_var_type`'s `_add_struct_import`).

No fixture exercises a struct DECLARED LOCALLY in the compiling package/class, then a member of it
accessed. Real UCC likely exports a local struct's own field members (same-package, no import needed)
rather than importing them — same shape as the local-vs-cross-package split this compiler already
models for classes/enums. Not confirmed either way; the current always-qualified path would need
checking (and likely a same-package export branch added, mirroring the class-literal/enum-tag
same-package fallbacks already in `_sibling_export_ref`/`ClassGraph`) if a real or controlled fixture
ever exercises it.

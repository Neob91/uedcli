+++
priority = "p2"
kind = "implement"
summary = "uscript: struct-member access confuses a local/param name with the field name"
+++

# uscript: struct-member access confuses a local/param name with the field name

FIXED 2026-09-14. `EX_StructMember`'s obj identity was the bare field name; `resolve_inv`'s
local-then-import lookup order let a same-named param/local (real UT99 `IpAddr Addr`'s own
`Addr.Addr`) shadow the struct field's import. `lower._struct_member_ident` now always qualifies it
`smem:<Struct>.<Field>` (mirrors `func:`/`mem:`), stripped in `canon()`. Regression: `UscIpAddrProbe`'s
param reverted to `Addr` (the real `IpServer` shape) against a fresh UT99 UCC golden. This was
`IpServer`'s last blocker — it now reaches `perm_gate` as a real corpus win
(`fixtures/uscript/ut99/IpServer/`). See `USCRIPT-COMPILER.md`.

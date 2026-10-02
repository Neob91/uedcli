+++
priority = "p3"
kind = "investigate"
summary = "uscript: local-struct-member map collides across same-package sibling classes"
+++

# uscript: local-struct-member map collides across same-package sibling classes

Found in code review of the `Ignore` fixture's local-struct-member fix. `_local_struct_member_map`
(`compile.py`) keys its export map by bare `"<Struct>.<Field>"` (no class qualifier), even though
`b.structs` itself is stored under class-prefixed keys in a multi-class compile. Two sibling classes
each declaring a same-named local struct with a same-named field (legal UnrealScript — struct
declarations are scoped to their declaring class) collide: whichever is processed second silently
overwrites the first's entry, and `resolve_inv` then resolves the first class's `smem:` token to the
second class's export — a wrong object reference with no exception.

Not fixed here — no current corpus package hits this shape (needs two DIFFERENT same-package classes
each with an identically-named struct+field). Fixing needs class-qualifying the map's keys AND the
`smem:` identity `lower._ex_member` tags (which currently only carries the bare struct name, since
`type_label`/`is_struct_name` are a flat namespace lookup with no per-class scoping) — a real change
to how local struct types are threaded, not a quick patch.

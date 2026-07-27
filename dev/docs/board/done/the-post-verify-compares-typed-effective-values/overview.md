+++
priority = "p?"
kind = "unknown"
summary = "The post-verify compares TYPED effective values; contraction DELETED — BUILT 2026-07-25 02:15 UTC"
+++

# The post-verify compares TYPED effective values; contraction DELETED — BUILT 2026-07-25 02:15 UTC

The compare seam stopped canonicalizing text and started comparing values: every
property of both sides resolves to the stored value if stated, else the class default, decoded by
its DECLARED type (`typedprops.py` = pure value semantics; `classdefaults.ClassDefaults` compiles
the decoded `.u` schema + defaults into it, one resolution per distinct class). Two actors are
equal iff they would import to the same object. `normalize.contract_actor`,
`normalize._is_all_zero_struct`, `classdefaults.values_equal` and
`rotation.canonical_rotation_value` are gone — one mechanism, not two. Fixes three things
contraction could not: `4.0` == `4` (typed float, at float32); an omitted struct member takes the
DEFAULT member, not zero (`Engine.Camera`'s `Location=(X=100,Y=200)` is Z=300, carried through
`parse_t3d` by the self-invalidating `Actor.location_text` side-channel, which keeps the parser
schema-free); and an explicit zero SCALAR/bool compares equal to an omitted line via the type's
zero from the schema, while a `StrProperty` reading `0` still does not. Also generalizes the
member-diff to EVERY struct prop and normalizes enum name-vs-ordinal. `verify._first_diff` now
names the differing PROPERTY and both values (or the class default the omitting side falls
through to). Decision `decisions.md` 2026-07-25 02:15 UTC; `unrealed/t3d.md` "Partial
struct/array property values"; `architecture.md` "The compare view vs the identity hash".
**Remnant** (filed on `inbox.md`, p2): ingest still WRITES a partial `Location` back zero-filled.

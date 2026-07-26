# `actor prop` internals — why the property editor is built this way

Engineering decisions about `uedcli/propedit.py` (the pure `actor prop set|unset|get` logic) and
its shared seams with `uedcli/typedprops.py` (the value-semantics layer the H3 post-verify compare
also uses).

## One struct-literal member split, in `typedprops`, used by both parsers

**What a struct literal is:** a T3D property value of the form `(A=1,B=(X=2),Msg="a,b")` — a
parenthesised, comma-separated list of `member=value` pairs, where a value may itself be a nested
literal or a quoted string.

**Why it is this way:** the codebase had **two** independent splitters for that one grammar and
they did not agree. `typedprops.parse_struct_text` (the compare path) tracked quotes; the older
`propedit.split_struct_text` (the `actor prop` path) split on **any** depth-0 comma, so a member
whose value legitimately contains a comma — `(Msg="a,b",Count=1)` — was torn into bogus members and
`actor prop get/set/find` errored on a value the engine writes routinely. Two hand-written parsers
for one grammar diverge by default; the fix is to have one.

So `typedprops` now owns both primitives — `split_struct_members` (the quote- and depth-aware split
into raw member texts) and `top_level_eq` (the index of the `=` separating a member's name from its
value, likewise quote- and paren-aware) — and both parsers call them. What survives in `propedit`
is only the **result shape**: an ordered list of `(key, value)` with the author's capitalisation
preserved, because `emit_struct_text` writes the members back into T3D and a struct's member order
and spelling are part of the emitted text. `typedprops.parse_struct_text` keeps its casefolded dict,
which is what a compare wants.

The shared splitter is also **stricter than the old compare-side one**: an unbalanced literal (an
unclosed `(` , a `)` past the end, an unclosed quote) now yields `None` — "not a struct literal" —
instead of a dict of half-parsed members. That was already `propedit`'s behaviour; adopting it on
both sides is what "the two cannot disagree" means.

**Rejected:**

- **Having `propedit.split_struct_text` call `typedprops.parse_struct_text` directly** — it returns
  a casefolded dict, which loses both member ORDER and the authored capitalisation that
  `emit_struct_text` writes back out. The shared unit has to be the split, not the whole parse.
- **Adding quote tracking to `propedit`'s own loop** — it fixes today's bug and leaves two parsers
  to drift again on the next corner (escapes, comments, an array-index key).
- **Moving the whole struct grammar into `propedit`** and having `typedprops` import it —
  backwards: `typedprops` is the lower layer (pure value semantics, no CLI verb logic), and
  `propedit` already depends on it conceptually.

**Refs:** `uedcli/typedprops.py` (`split_struct_members`, `top_level_eq`, `parse_struct_text`) ·
`uedcli/propedit.py` (`split_struct_text`) · `uedcli/tests/test_propedit.py` ·
`uedcli/tests/test_actor_prop.py` (the quoted-comma verb-level regression)

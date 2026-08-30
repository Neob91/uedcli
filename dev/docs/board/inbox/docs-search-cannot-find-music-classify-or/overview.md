+++
priority = "p1"
kind = "docs"
summary = "docs search cannot find `music classify` or `prefab list`/`drop`"
+++

# docs search cannot find `music classify` or `prefab list`/`drop`

`music classify {set,unset,status,tags}` (`docs/usage.md`) and `prefab list`/`prefab drop`
(`docs/usage.md:1373-1377`) are real, implemented, and documented in prose — but `uedcli docs search
"music classify"` and `uedcli docs search "prefab list"` (also `"prefab drop"`) all return **0
match(es)**, verified live.

Root causes, one per family:

- **`music classify`**: the synopsis block spells out `sound classify set/unset/status/tags`
  verbatim (`docs/usage.md:1899-1903`), then says `music` verbs "mirror `class classify` /
  `class search`" in prose (`docs/usage.md:1927`) without ever spelling `music classify` as a
  literal substring anywhere in the file.
- **`prefab list` / `prefab drop`**: the per-verb synopsis interleaves the flag between noun and
  verb — `prefab [--prefab-dir DIR] list` / `prefab [--prefab-dir DIR] drop  <name>`
  (`docs/usage.md:1373-1377`) — so the literal substring `prefab list` / `prefab drop` never
  occurs in the file either.

Same failure class as the `brush measure relation` gap fixed today (`docs/usage.md`,
`uedcli/relation.py`): a real feature invisible to an agent's documented discovery path
(`docs search`), recurring in an adjacent command family. This is a find, not a build — no fix
implemented here. Fix path is presumably either restating each verb pair in full at least once, or
making `docs search` tokenize past bracketed optional flags — worth a spec before picking one.

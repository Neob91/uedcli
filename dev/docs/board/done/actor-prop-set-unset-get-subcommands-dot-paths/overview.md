+++
priority = "p?"
kind = "unknown"
summary = "`actor prop set|unset|get` subcommands + dot-paths + class-default fallback + unified package core"
+++

# `actor prop set|unset|get` subcommands + dot-paths + class-default fallback + unified package core

— BUILT + 3-reviewer-gated 2026-07-18 (same day as the spec). Ships: `upackage.py` (the
ONE low-level UE1 package reader; `uprops` migrated onto it — `utexture`/`dxpkg` migration is a
separate inbox chore), the `SerializeExpr` bytecode walker + UClass-tail DEFAULTS decoder
(1914/1914 DX classes corpus-clean; `unrealed/class-schema.md` "UClass body"), `propedit.py`
(dot-path grammar, whole-value vs targeted edits, effective-value get, dump-all, typed-field
registry with Location zero-fill), retirement of `actor get` + the `--set/--unset` flags,
`actor find --prop` EFFECTIVE-value matching + `actor build --prop` validation, and the §9 live
probe result (partial values are member-wise onto the CLASS DEFAULT —
`spikes/2026-07-18-partial-value-import-semantics/`, `unrealed/t3d.md`). Live E2E against the
real v68 install ran green (set/get/unset/find + real enum errors). Spec (ephemeral):
board item `materialize-post-verify-fails-when-the-trunk`; durable record decisions.md 2026-07-18 10:02 +
10:30 UTC; folded into `architecture.md` "Class-property schema, DEFAULTS & the actor prop
verbs". **Remnant flags (inbox):** store-explicit struct edits + `--kv` round-trips manufacture
the explicit-default shapes the two open H3 post-verify items trip on — their practical
priority rises now.

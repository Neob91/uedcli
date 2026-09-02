+++
priority = "p3"
kind = "debug"
summary = "texture search derives colours for the whole corpus even when colours are unused"
+++

# texture search derives colours for the whole corpus even when colours are unused

`texture search <term>` takes ~2 min on the Deus Ex corpus (4393 textures). Roughly two-thirds of
that is dead work: `_run_search` (`uedcli/cli/commands/texture.py:212`) calls `_colors_for` for
every candidate texture, which runs `texture_colors.derive_colors` on the decoded pixels — but for
plain output (no `--json`, no `--color`) the derived colours are never read.

Measured on this corpus (resolve results cached per instance, so no double-decode):
- decode-all (`_ref_facts`, needed for identity/tags): 38.5 s
- derive_colors-all: 80.4 s  ← discarded in the plain path

So a plain `texture search brick` spends ~80 s deriving colours it throws away.

Fix: only compute colours when they are used — `want_colors` is set OR `args.json`. Cuts plain
search from ~118 s to ~40 s. `_run_list` already gates its decode via `need_decode`; mirror that.
(Identity/decode itself is inherent to a corpus-wide tag/description ranking and out of scope here.)

Found by profiling during black-box exploration, 2026-08-23.

+++
priority = "p3"
kind = "chore"
summary = "no-op texture prewarm --force, class --all shim, latent SheerAxis default 0 vs SHEER_ZX"
+++

# small cleanups: no-op flag, migration shim, latent wrong default

Three unrelated small items, grouped.

1. `texture prewarm --force` is a verified no-op. `cli/parsers/texture.py:103-105` defines it;
   `cli/commands/texture.py:235-245` (`_run_prewarm`) never reads `args.force`. Violates "no no-op
   flags." (Contrast `class prewarm --force`, which threads `force=args.force`.) Remove the flag.

2. `class list`/`class show --all` is a hidden (`argparse.SUPPRESS`) migration-error shim:
   `cli/parsers/classes.py:57-59,89-90` define it, `cli/commands/classes.py:565-568,626-627` raise
   "--all was split/renamed — use …". Literally the rejected "flag defined only to raise X was
   renamed" pattern. In-code comments argue it's a UX nicety over a bare argparse error — whether the
   exception stands is the OWNER's call. Ask before removing.

3. `native/props.py:141-143` — an omitted `SheerAxis` in a `Scale` struct encodes as `SHEER_None`
   (0), but the codebase's identity default is `SHEER_ZX` (5) (`transform.DEFAULT_SHEER_AXIS`).
   Currently LATENT: the only live caller always emits `SheerAxis=` explicitly. Would misfire only on
   a partial `Scale` struct text stating `SheerRate=` but omitting `SheerAxis=` (a legal T3D form).
   Fix the default to 5 and add a regression test so it can't regress if a new caller appears.

Items 1 and 3 confirmed by direct read; item 2 needs an owner ruling before action.

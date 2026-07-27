+++
priority = "p3"
kind = "chore"
summary = "Migrate `utexture.py` + `dxpkg.py` onto the unified `upackage.py` core"
+++

# Migrate `utexture.py` + `dxpkg.py` onto the unified `upackage.py` core

p3 **Migrate `utexture.py` + `dxpkg.py` onto the unified `upackage.py` core** (once the
`actor prop` subcommands build lands it — spec `specs/2026-07-18-actor-prop-subcommands.md` §5.1/
§10, decision 2026-07-18 10:02 §7). Both are byte-validated decoders, so the migration is a
deliberate separate pass with the texture-corpus revalidation, not part of the feature change.
UNBLOCKED 2026-07-18 — the `upackage.py` core landed with the actor-prop build.

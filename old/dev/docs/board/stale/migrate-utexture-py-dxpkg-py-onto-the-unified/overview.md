+++
priority = "p3"
kind = "chore"
summary = "migrate utexture.py + dxpkg.py onto the unified upackage.py core"
+++

# migrate utexture.py + dxpkg.py onto the unified upackage.py core

Superseded by `unify-ue1-package-read-primitives-into-one-rust`, which absorbs this migration
(same 3 behavioral deltas analyzed in this item's `spec.md`, kept here for reference) onto a
Rust-backed core instead of a pure-Python one. Its parked question
(`questions/keep-version-allowlist.md`) is answered: drop the allowlist.

Originally unblocked 2026-07-18 by the `upackage.py` core landing with the actor-prop build
(`materialize-post-verify-fails-when-the-trunk` §5.1/§10, decision 2026-07-18 10:02 §7).

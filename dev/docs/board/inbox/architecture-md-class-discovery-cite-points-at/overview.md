+++
priority = "p3"
kind = "docs"
summary = "architecture.md class-discovery cite points at qualify.md, but the module is classindex.py"
+++

# architecture.md class-discovery cite points at qualify.md, but the module is classindex.py

During the migration-ledger removal, `architecture.md:1305` (class discovery, old ledger date
2026-07-17 19:37) was repointed to `rationale/qualify.md` as the owner's repoint map specified.
Review flagged a content mismatch: `qualify.md` documents `qualify.py`'s live-editor readback
(`OBJ LIST CLASS`/`OBJ DEPENDENCIES`), while the cited subject is the header-only offline
`classindex.py` — the two modules do not reference each other.

Implemented as instructed. The same line already co-cites the precise home,
board item `offline-class-discovery-qualify-and-validate`, so a reader still reaches it. Owner to
decide whether the secondary `qualify.md` pointer should stay, drop, or move to a `classindex`
rationale topic.

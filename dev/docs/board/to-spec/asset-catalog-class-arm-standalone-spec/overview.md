+++
priority = "p2"
kind = "implement"
summary = "Standalone spec for the asset-catalog CLASS arm, split from the 4-kind engine; awaits owner gate."
depends-on = ["unified-asset-catalog"]
+++

# asset-catalog class arm — standalone spec

The owner ruled (2026-08-01) to **SPLIT** the unified 4-kind catalog and give the CLASS arm a
fresh, self-contained spec rather than a third re-gate of the shared engine. This item holds that
spec ([`spec.md`](spec.md)).

The spec defines the class arm as a self-contained feature — the minimal engine core it needs
(class enumeration, a file-fact `show`, a class-shard classification store, `class preview`) with no
dependency on the texture or audio arms — and folds the four changes from board item
`the-asset-catalog-class-arm-needs-four-changes` in as concrete design.

**Needs an owner gate before build.** The spec's `## Owner decisions to rule on` section lists the
calls the gate must accept or revise (signed-extents output format, the `mount:`/`faces:` tag
namespace, and the value/craft framing). Those are proposals, not settled facts.

Siblings in the split: engine + texture arm (board item `unified-asset-catalog`), audio arm
(board item `sound-corpus-remeasure`), and the four-changes source (board item
`the-asset-catalog-class-arm-needs-four-changes`).

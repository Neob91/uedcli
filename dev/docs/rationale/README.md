# rationale/ — why the code is the way it is

One doc per module or subsystem, **revised in place**: no supersession, no dated history, no ledger.
Git keeps the past.

**Agents maintain this tree on their own** — no confirmation needed. That is the difference from
`../direction/`, which holds what *the owner* decided and may never be written without his yes
(`CLAUDE.md` "Direction docs"). The axis is **who decided**, not what it is about: a tolerance, a
scope limit, a format choice is yours; product intent and process rulings are theirs.

## Shape

Every entry carries all three parts. `Rejected` is not optional — it is the reason this tree exists,
and dropping it lets a future session re-propose a design that was already killed:

```markdown
## <the decision>

**Why it is this way:** …
**Rejected:** <alternative> — because …
**Refs:** `spikes/<file>`, `uedcli/<module>.py`
```

A `Refs` target that no longer exists is **dropped**, or replaced by the code/spike site that does
— never carried forward dangling. Many old ledger refs pointed at ephemeral specs that were deleted
when their work landed.

Point a durable doc here for rationale. Never point one at a spec — specs are ephemeral.

## Where the history went

Decisions made before 2026-07-26 lived in an append-only ledger at `dev/docs/decisions.md`, which
this tree replaces. It is frozen and being retired topic by topic. Once removed:

```sh
git log --follow -- dev/docs/decisions.md
```

`MIGRATION.md` in this directory records what happened to every one of its 227 entries — which topic
it folded into, or why it was dropped. It outlives the migration, because it is the only map from an
old dated citation (`decisions.md 2026-07-21 12:06 UTC`) to where that reasoning now lives.

# actor label

add / remove / clear / get

Alongside the single-path folder, each actor carries a **set of labels** — flat tokens
(`lighting`, `flammable`, `hero`) that answer "what is this about", the cross-cutting axis one
hierarchy can't express (a torch is at `castle.tower` AND is `lighting` AND `interactive`). Like
folders, labels are **uedcli-side only**: they live in a per-actor trunk sidecar, are **never emitted
to the built map**, and are **orthogonal** to the folder, the T3D `Group=` prop, and the T3D `Tag=`
prop (named `label`, not `tag`, to avoid colliding with `Engine.Actor.Tag`). An actor may carry any
number of labels. A label token is `[A-Za-z0-9_+-]`, no `.`, no leading `-`; stored as authored
(case preserved) and matched case-insensitively.

- **Set at creation:** on the **generator** — `brush build … --label L` / `actor build … --label L`
  (repeatable) — which emits a `// uedcli-labels:` carrier; `actor add` persists it (no `--label` of its
  own). `actor show` emits the same carrier, so a show → add round-trips.
- **Manage:** `actor label add --label L <names…|->` (set union), `actor label remove --label L
  <names…|->` (set difference), `actor label clear <names…|->` (drop all), `actor label get
  <names…|->`. There is **no `set`** — compose `clear` then `add`. `add`/`remove`/`clear` are
  PRODUCERS (touched Names → stdout, a summary → stderr) and **validate-all-then-apply**: a bad
  `--label` or an unknown name leaves every actor untouched (exit 2 naming the offender).
- **Query:** `actor find --label <glob>` (repeatable = OR) / `--no-label` (see [`actor find`](find.md)).

Matching is a **flat `*`-glob** (no path structure): an actor matches if ANY of its labels matches
the pattern; `*` is the ONLY wildcard (`dup-*` finds a duplicate batch, `lighting` matches that exact
label), and `?`/`[`/`]` are rejected. Repeat `--label` to OR patterns; it ANDs across the other
`find` dimensions. `--no-label` (mutually exclusive with `--label`) matches only unlabelled actors —
the only way to query them.

```bash
uedcli actor find --subclass-of Engine.Light | uedcli actor label add --label lighting -
uedcli actor find --label 'dup-*' | uedcli actor move -   # re-address a duplicated batch
```

Labels are **trunk-only** this release: every label surface (`actor label …`, `actor find
--label`/`--no-label`, the generators' `--label`, and `actor duplicate`) rejects `--tree stash|prefab`
(exit 2). `actor duplicate` inherits the source's labels plus a fresh `dup-<rand>` batch label — see
[`actor duplicate`](duplicate.md).

See also: [`actor folder`](folder.md), [`actor find`](find.md).

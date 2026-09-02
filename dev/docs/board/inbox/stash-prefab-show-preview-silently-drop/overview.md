+++
priority = "p2"
kind = "debug"
summary = "stash/prefab show|preview silently drop unmatched actor names, exit 0"
+++

# stash/prefab show|preview silently drop unmatched actor names

`cli/commands/stash.py:182-189`:

```python
chosen = args.names or order
print("\n".join(actors_t3d[n] for n in chosen if n in actors_t3d))
```

The `if n in actors_t3d` filter silently skips names that don't resolve. Same pattern in
`cli/commands/prefab.py:51-61` and both `preview` sub-verbs via the shared filter in
`cli/rendering.py:510-519`.

Trigger: `stash show <id> TypoedName` prints nothing, no stderr note, exits 0.

Violates "no silent half-answers." `cli/commands/docs.py:75-85` already does the right thing —
collects every unresolved name and raises `CommandError` naming them all before any output — so the
correct pattern exists in-tree and is applied inconsistently.

Fix: collect unmatched names and exit 2 naming them (mirror `docs.py`). Regression test.

Confirmed by direct read.

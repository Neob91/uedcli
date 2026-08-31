# actor duplicate

`actor duplicate <names…|-> (--by DX,DY,DZ | --at X,Y,Z) [--label L…] [--folder PATH]` — copy
actors with fresh names, offset by `--by` or anchored by `--at` (one is REQUIRED); copies inherit
the source's labels plus a fresh `dup-<rand>` batch label. Always appends (no `--order`). Prints
allocated names to stdout.

Requires **exactly one** of `--by DX,DY,DZ` (a relative per-actor offset) or `--at X,Y,Z` (anchor
the copied set's bounding-box minimum corner); neither is an error (exit 2), and `--by 0,0,0`
overlaps the originals in place. Copies **inherit their source's labels** plus **one fresh
`dup-<rand>` batch label**, so `actor find --label dup-<rand>` re-addresses the whole batch after
the pipeline ends (the token is echoed to stderr). `--label L` (repeatable) is **additive** —
stamped on top of the inherited labels and the `dup-<rand>` token. `--folder PATH` overrides each
original's folder. Trunk-only (rejects `--tree stash|prefab`).

See also: [`actor add`](add.md), [`actor label`](label.md).

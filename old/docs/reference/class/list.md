# class list

Browse actor classes as an indented inheritance tree (rooted at `Engine.Actor`), offline, reading
the game `.u` packages.

```bash
uedcli class list [--depth N|all] [--subclass-of Package.Class] [--package P]
                  [--flat] [--include-non-actor] [--include-abstract]
                  [--classified | --unclassified] [--json]
```

`class list` auto-fits ~60 lines; abstract classes are marked `*`, a collapsed node shows its
hidden direct-subclass count as `(N)`. `--flat` gives a pipeable one-`Package.Class`-per-line list;
`--subclass-of` reroots (e.g. `--subclass-of Engine.Mover`); `--depth all` for the whole tree.
`--classified` / `--unclassified` filter the `--flat` list to classes that do / don't have a stored
classification shard (they **require** `--flat` — a tree can't be per-node filtered — else exit 2).
`--json` emits one object per class (`{ref, classified, preview}`); `preview` is an already-cached
thumbnail path or `null` (`list` never renders — only `class preview` does).

See also: [`class show`](show.md), [`class search`](search.md).

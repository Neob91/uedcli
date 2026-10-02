# music list

`music list` enumerates every music module on the composed package path — full dotted ref
(`Package.Group.Name`, or `Package.Name` for a root object), one per line, count to stderr. No
default filter.

```bash
uedcli music list [--package NAME]… [--classified | --unclassified] [--json]
```

- Narrow with a pipe or **`--package NAME`**, which takes an **exact** package stem (not a glob)
  and is **repeatable** (`--package A --package B` = the union); an unknown package **exits 2**
  naming it.
- `--classified` / `--unclassified` keep only objects that do / don't have a stored classification
  shard.
- `--json` emits one object per line: `{ref, identity, group, classified, title, format}` — see
  [`music show`](show.md) for what **identity**, **title**, and **format** mean.

See also: [`music show`](show.md), [`music search`](search.md).

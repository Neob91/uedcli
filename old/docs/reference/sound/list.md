# sound list

`sound list` enumerates every sound object on the composed package path — full dotted ref
(`Package.Group.Name`, or `Package.Name` for a root object), one per line, count to stderr. No
default filter.

```bash
uedcli sound list [--package NAME]… [--classified | --unclassified] [--json]
```

- Narrow with a pipe (`sound list | grep -v '^DeusExConAudio'`) or **`--package NAME`**, which
  takes an **exact** package stem (not a glob) and is **repeatable** (`--package A --package B` =
  the union); an unknown package **exits 2** naming it.
- `--classified` / `--unclassified` keep only objects that do / don't have a stored classification
  shard.
- `--json` emits one object per line: `{ref, identity, group, classified}` — see [`sound
  show`](show.md) for what **identity** means when a bare name collides across groups.

See also: [`sound show`](show.md), [`sound search`](search.md).

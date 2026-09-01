# music show

`music show <ref>… | -` prints each module's facts (package, group, identity, embedded title,
format) and stored classification.

```bash
uedcli music show <ref>… | -   [--json]
```

- **Ref and identity.** `music list` prints each object's full dotted ref (`Package.Group.Name`,
  or `Package.Name` for a root object). An object's **identity** — the shard key — is
  `Package.Name` when that bare name is unique in its package, else the full dotted
  `Package.Group.Name` (one package can hold the same bare name in two groups). `show`/`classify`
  accept **either** spelling; both resolve to the same object. A ref that is unknown, or a 2-part
  name that is ambiguous because it collides across groups, **exits 2** naming it (use the full
  dotted ref).
- **`music show` / `music list --json`** carry the module's **embedded title** and **format**,
  read live from the `.umx`. The format is `IT`, `S3M`, `XM`, or `unknown`; a module with no
  readable title reports `title: null` with the format still named, never a blank that reads as
  "no module".
- `--json` emits one JSON object per ref instead of the human block.

See also: [`music list`](list.md), [`music classify`](classify.md).

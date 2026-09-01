# sound show

`sound show <ref>… | -` prints each object's facts (package, group, identity) and stored
classification.

```bash
uedcli sound show <ref>… | -   [--json]
```

- **Ref and identity.** `sound list` prints each object's full dotted ref (`Package.Group.Name`,
  or `Package.Name` for a root object). An object's **identity** — the shard key — is
  `Package.Name` when that bare name is unique in its package, else the full dotted
  `Package.Group.Name` (one package can hold the same bare name in two groups). `show`/`classify`
  accept **either** spelling; both resolve to the same object. A ref that is unknown, or a 2-part
  name that is ambiguous because it collides across groups, **exits 2** naming it (use the full
  dotted ref).
- `--json` emits one JSON object per ref instead of the human block.

See also: [`sound list`](list.md), [`sound classify`](classify.md).

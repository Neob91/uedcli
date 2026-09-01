# sound search

`sound search <term>…` is RANKED discovery over the sound corpus: objects whose name / stored tags
/ description match the terms, best first.

```bash
uedcli sound search <term>… [--tag T] [--json]
```

- Mirrors `class search`: **terms are required** — a term-less `search` **exits 2** pointing at
  [`sound list`](list.md) (the enumerator). Ranks by exact leaf name > exact tag > ref substring >
  tag substring > description substring.
- `--tag T` (repeatable) keeps only objects carrying that exact stored tag.
- `--json` emits one JSON object per match (JSONL), best first.
- With no composed package path, `search` **exits 2** (`no package search path`).

See also: [`sound list`](list.md), [`sound classify`](classify.md).

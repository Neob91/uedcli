# music classify

set / unset / status / tags

Records what a music module IS — the tool stores the classification it is handed, never infers it.

```bash
# record what an object IS (the class must be on the composed package path)
uedcli music classify set <ref> --tags a,b --description "…"
uedcli music classify set <ref> --force --tags a,b --description "…"   # replace wholesale
uedcli music classify set -            # read JSONL rows {ref, tags, description} from stdin

# inspect / undo a classification
uedcli music classify unset <ref>… | -  [--tags[=A,B] | --description | --all]
uedcli music classify status [--json]   # how many objects on the path are classified, of the total
uedcli music classify tags [--json]     # the tag vocabulary in use, with counts
```

- **`set` refuses to overwrite.** A `set` over an already-classified object **exits 2** naming the
  ref and printing the stored payload; **`--force`** replaces the shard **wholesale** — it does not
  merge, so a `--force` that omits `--tags`/`--description` drops the stored value. `set -` reads
  JSONL rows `{ref, tags?, description?}` from stdin, all-or-nothing (one bad row writes nothing;
  `--force` governs every row); empty stdin is a clean no-op. Shards live under
  `classified/music/…`, holding exactly `{kind, ref, tags, description}`.
- **`classify unset`**, **`classify status`**, **`classify tags`**, and [`music
  search`](search.md) mirror `class classify` / `class search`. With no composed package path,
  every verb **exits 2** (`no package search path`).

See also: [`music list`](list.md), [`music search`](search.md).

# class classify

set / unset / status / tags

The tool stores the classification an LLM hands it; it never infers meaning. Each class gets one
git-tracked shard under the catalog dir (`classified/class/<package>/<class>.json`, path casefolded),
holding exactly `{kind, ref, tags, description}`. Concurrent agents classifying different classes
never touch the same file.

```bash
# record tags + a description (the class must be on the composed package path)
uedcli class classify set DeusEx.BarStool --tags chair,mount:floor,faces:+z \
    --description "bar stool; DX places these along the DiveBar counter"

# batch: one JSON object per line on stdin, one shard write per row
printf '%s\n' '{"ref":"DeusEx.BarStool","tags":["chair"],"description":"a stool"}' \
    | uedcli class classify set -
```

- **`set`** merges: on re-set, `--tags` **union** onto the stored tags through a strip / lowercase /
  de-dupe normalizer, so re-running never loses a tag. A **different non-empty** `--description`
  **exits 2** printing the stored text; pass `--replace` to overwrite; identical text is a no-op. An
  unknown class, or a ref that is not `Package.Class`, **exits 2** naming it.
- **`mount:` and `faces:` are reserved tag namespaces.** A `faces:` tag needs an axis token —
  `+x -x +y -y +z -z` (case-normalized, so `faces:+X` is fine); any other value **exits 2** naming
  it. A `mount:` tag needs a non-empty value (free text, e.g. `mount:wall`). Only the **shape** is
  checked — what the value *means* is authored, never computed. They are ordinary tags otherwise
  (they show up in `classify tags` and filter via search).
- **`set -`** reads JSONL rows `{ref, tags, description}` from stdin, one shard write per row. It is
  **all-or-nothing**: every row is validated first, and a single bad row **exits 2** naming it with
  nothing written. Empty stdin is a clean no-op (exit 0).
- **`unset <Package.Class>… | -`** undoes classification: `--tags A,B` removes those tags, bare
  `--tags` clears the whole tags field, `--description` clears the description, and `--all` deletes
  the shard. `-` reads a newline ref list from stdin (empty stdin is a clean no-op). A ref with no
  shard **exits 2** naming it.
- **`status [--json]`** reports how many classes on the path have a shard, of the total.
  **`tags [--json]`** lists the tag vocabulary in use with occurrence counts, to curb drift.
- Every `classify` verb needs the composed package path (to know the class exists); with none it
  **exits 2** (`no package search path`).

See also: [`class list`](list.md), [`class search`](search.md).

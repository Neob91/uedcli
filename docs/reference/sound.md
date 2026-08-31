# sound

`sound` catalogs the substrate's audio the way `class` catalogs its actor classes — enumerate,
inspect, search, and record a classification — offline, reading the game's own `.uax`/`.u`
packages, no editor or level. This is **phase (a)**: no sample decoding yet, so there is no `sound
preview` (spectrogram), duration, or export.

```bash
# enumerate every object, one full dotted ref per line (count to stderr); NO default filter
uedcli sound list [--package NAME]… [--classified | --unclassified] [--json]

# facts (package, group, identity) + stored classification
uedcli sound show <ref>… | -   [--json]

# RANKED discovery: objects whose name / stored tags / description match the terms, best first
uedcli sound search <term>… [--tag T] [--json]

# record what an object IS (the class must be on the composed package path)
uedcli sound classify set <ref> --tags a,b --description "…"
uedcli sound classify set <ref> --force --tags a,b --description "…"   # replace wholesale
uedcli sound classify set -            # read JSONL rows {ref, tags, description} from stdin

# inspect / undo a classification
uedcli sound classify unset <ref>… | -  [--tags[=A,B] | --description | --all]
uedcli sound classify status [--json]   # how many objects on the path are classified, of the total
uedcli sound classify tags [--json]     # the tag vocabulary in use, with counts
```

- **Ref and identity.** `list` prints each object's full dotted ref (`Package.Group.Name`, or
  `Package.Name` for a root object). An object's **identity** — the shard key — is `Package.Name`
  when that bare name is unique in its package, else the full dotted `Package.Group.Name` (one
  package can hold the same bare name in two groups). `show`/`classify` accept **either** spelling;
  both resolve to the same object. A ref that is unknown, or a 2-part name that is ambiguous because
  it collides across groups, **exits 2** naming it (use the full dotted ref).
- **`list` prints its whole set** — one ref per line, count to stderr — with **no default filter**.
  Narrow with a pipe (`sound list | grep -v '^DeusExConAudio'`) or **`--package NAME`**, which takes
  an **exact** package stem (not a glob) and is **repeatable** (`--package A --package B` = the
  union); an unknown package **exits 2** naming it. `--classified` / `--unclassified` keep only
  objects that do / don't have a shard. `--json` emits one object per line: `{ref, identity, group,
  classified}`.
- **`classify set` refuses to overwrite.** A `set` over an already-classified object **exits 2**
  naming the ref and printing the stored payload; **`--force`** replaces the shard **wholesale** —
  it does not merge, so a `--force` that omits `--tags`/`--description` drops the stored value. `set
  -` reads JSONL rows `{ref, tags?, description?}` from stdin, all-or-nothing (one bad row writes
  nothing; `--force` governs every row); empty stdin is a clean no-op. Shards live under
  `classified/sound/…`, holding exactly `{kind, ref, tags, description}`.
- **`classify unset`**, **`classify status`**, **`classify tags`**, and **`search`** mirror `class
  classify` / `class search`: `search` requires at least one term (term-less **exits 2** pointing at
  `list`) and ranks by exact leaf name > exact tag > ref substring > tag substring > description
  substring. With no composed package path, every verb **exits 2** (`no package search path`).

See also: [`music`](music.md) (same catalog shape, plus title/format), [`class`](class/README.md).

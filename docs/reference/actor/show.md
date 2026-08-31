# actor show

`actor show <name|-> [--t3d-only]` — print named actors' full canonical T3D blocks.

`actor show <name>` takes ONE actor name (case-insensitive) — **not a glob**: patterns belong to
[`actor find`](find.md), and `actor find 'Light*' | actor show -` prints the whole matched set. A
name that matches no actor errors (exit 2). Reads a stdin name list with `-` (empty stdin is a clean
no-op, exit 0). By default each block carries the uedcli-side sidecars as comments — a `// uedcli-folder:`
line for a foldered actor and a `// uedcli-labels:` line for a labelled one — so
`actor show A | actor add -` round-trips both; `--t3d-only` suppresses them for a byte-exact editor
export.

The T3D that `actor show` prints — and the trunk stores — is faithful, not abbreviated: it states
every authored property explicitly, including ones equal to the class default
(`Location=(X=0.000000,Y=0.000000,Z=0.000000)`, `Rotation=(Pitch=0,Yaw=0,Roll=0)`, a `Tag` the
editor stamped). UnrealEd's own export omits those, so its export is shorter than the trunk — the
build's post-verify compares the two by value, not text: each property resolves to what it would
import as (the stored value, or the class default when the line is absent), so the two spellings are
the same level. Never hand-delete such a line to "clean up" the trunk: an omitted property means the
class default, which is non-zero for some classes.

See also: [`actor find`](find.md), [`actor add`](add.md).

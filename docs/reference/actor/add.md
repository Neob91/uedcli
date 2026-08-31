# actor add

`actor add <file|-> [--order POS]` — add the actor(s) in a T3D snippet (point → IMPORTADD, brush →
PASTE); a pure carrier-consumer — persists any `// uedcli-folder:`/`// uedcli-labels:` carrier in
the T3D (folder/label are set on the generator or later via `actor folder set`/`actor label`);
prints allocated names to stdout.

A point actor enters via `MAP IMPORTADD`, a brush via `EDIT PASTE` (only paste/ADD brushes are later
selectable — uedcli handles this and compensates the +32uu paste drift). `--folder PATH` stamps
every added actor's folder (overrides any `// uedcli-folder:` carrier). `--label L` (repeatable)
stamps labels on every added actor, likewise overriding any `// uedcli-labels:` carrier; absent, the
carrier (from `actor show`) sets the labels, else the actor is unlabelled. `--order
first|last|before=NAME|after=NAME` (default `last`) places the added actor(s) in CSG order; multiple
actors land as a block preserving input order (level target only — rejected on `--tree
stash|prefab`).

See also: [`actor show`](show.md), [`actor duplicate`](duplicate.md).

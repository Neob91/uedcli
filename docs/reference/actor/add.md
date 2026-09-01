# actor add

`actor add <file|-> [--order POS]` — add the actor(s) in a T3D snippet (point → IMPORTADD, brush →
PASTE); a pure carrier-consumer — persists any `// uedcli-folder:`/`// uedcli-labels:` carrier in
the T3D (folder/label are set on the generator or later via `actor folder set`/`actor label`);
prints allocated names to stdout.

A point actor enters via `MAP IMPORTADD`, a brush via `EDIT PASTE` (only paste/ADD brushes are later
selectable — uedcli handles this and compensates the +32uu paste drift). `actor add` has no
`--folder`/`--label` of its own — folder/label are set on the generator (`brush build`/`actor build
--folder`/`--label`, which emit `// uedcli-folder:`/`// uedcli-labels:` carriers) or via `actor show`,
and `actor add` persists whatever carrier is present in the T3D; absent a carrier, the actor lands
unfoldered/unlabelled. Change folder/label afterward with [`actor folder set`](folder.md) /
[`actor label`](label.md). `--order first|last|before=NAME|after=NAME` (default `last`) places the
added actor(s) in CSG order; multiple actors land as a block preserving input order (level target
only — rejected on `--tree stash|prefab`).

See also: [`actor show`](show.md), [`actor duplicate`](duplicate.md), [`actor folder`](folder.md),
[`actor label`](label.md).

# actor folder

get / set / unset / rename

Actors are organized into a **tree of folders** — a per-actor dotted **path** (`castle.tower.roof`),
so logical subsets are addressable. A folder is **uedcli-side only**: it lives in a trunk sidecar
beside the actor, is **never emitted to the built map**, and is a **separate dimension** from the T3D
`Group=` property (retained unchanged). One folder per actor.

- **Set at creation:** on the **generator** — `brush build … --folder <path>` / `actor build … --folder
  <path>` — which emits a `// uedcli-folder:` carrier in the T3D; `actor add` persists it (it has no
  `--folder` of its own). `actor show` emits the same carrier, so `actor show A | actor add -` round-trips.
- **Manage:** `actor folder set --to <path> <names…|->`, `actor folder unset <names…|->`,
  `actor folder get <names…|->`, `actor folder rename <old-path> <new-path>` (re-parent/rename a whole
  subtree: rewrites the `old` prefix to `new` on every actor filed at `old` or under it; `old`
  matching no actor is an error). `set`/`unset`/`rename` are PRODUCERS (touched Names → stdout, a summary →
  stderr), so they chain: `uedcli actor find --subclass-of Engine.Light | uedcli actor folder set
  --to castle.lights - | uedcli actor prop set - LightBrightness=200`.
- **Query:** `actor find --folder <pattern>` (see [`actor find`](find.md)).

Pattern matching is **globstar** with one asymmetry:
- A **wildcard-free** pattern (`castle`) selects that folder **and its whole subtree**.
- `*` matches exactly one segment; `**` matches any depth.
- A **wildcarded** pattern is a *pure glob with NO subtree extension* — `**.roof` matches roof NODES
  only, not their contents (use `--folder '**.roof' --folder '**.roof.**'` for "every roof and
  everything inside").
- `--no-folder` matches only unfoldered actors (the only way to query them).

See also: [`actor label`](label.md), [`actor find`](find.md).

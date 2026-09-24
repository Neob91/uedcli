+++
priority = "p1"
kind = "implement"
summary = "SceneActor special-cases Location/Rotation instead of exposing them as generic props"
+++

# SceneActor special-cases Location/Rotation instead of exposing them as generic props

`uedcli/serve/scene.py`'s `SceneActor` carries dedicated `location`/`rotation` fields, separate from
its generic `props` list. `StagingStore` (`uedcli/serve/snapshots.py`) mirrors this: it stages
`Location` moves specifically, with baseline/conflict machinery keyed to that one field.

The model/CLI layer already treats these uniformly — `actor prop set` reaches `Location` via
`propedit`'s typed-field registry (`uedcli/propedit/fields.py:275`) and `Rotation` as an ordinary
struct-typed prop (not even in that registry) — there is no model-side reason for the GUI backend to
fork them apart. Owner ruling: this is existing debt, not a pattern to keep extending (see memory
`gui_backend_no_special_cased_props`).

**Fix**: fold `location`/`rotation` into `SceneActor`'s generic `props`, and replace `StagingStore`'s
Location-specific staging with a generic per-prop staging mechanism. Ripples into `/scene`, `/rebuild`,
staged-move code (`uedcli/serve/edits.py`), and whatever FE code currently reads
`SceneActor.location`/`.rotation` directly — real scope, not a one-file rename.

Raised while speccing `gui-builder-brushes` (`dev/docs/board/to-spec/gui-builder-brushes/`), which is
deliberately NOT fixing this itself. That spec's builder brush IS exposed as a genuine `SceneActor`
(reused as-is, not a bespoke shape — an earlier draft tried a bespoke response shape specifically to
dodge this issue, then dropped it once "transparent, ordinary actor" became the actual design), so it
inherits this special-casing exactly like every other actor — no better, no worse. Fixing it here
would ripple beyond the builder-brush feature's own scope.

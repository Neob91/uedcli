+++
priority = "p2"
kind = "implement"
summary = "GET /status and /lightmap never call _get_trunk(), so the automatic initial Load never fires if either is the first route hit"
+++

# GET /status and /lightmap never call _get_trunk(), so the automatic initial Load never fires if either is the first route hit

Found by review of `gui-explicit-rebuild-pinned-build-state-mode` (2026-09-15). That item's spec/plan
describe "the automatic initial Load" as firing on "the very first access to `_get_trunk()` from any
route, whether that's `/scene`, `/status`, `/rebuild`, or an explicit `/load`" — but `/status`'s actual
implementation (`uedcli/serve/app.py`) never calls `_get_trunk()` at all, so if it's the first route a
client hits in a fresh process, `build_status` stays stuck at `"no_build"` (even with a valid on-disk
pointer) until some other route is hit. `/lightmap` skipping `_get_trunk()` is a deliberate,
documented, tested characteristic (it only needs geometry); `/status`'s omission is not tested or
called out anywhere.

In practice a real GUI client always fetches `/scene` first, so this is narrow — not blocking the
item's merge. Worth a small fix (have `/status` call `_get_trunk()` too, matching its own spec text)
or an explicit doc correction if the owner decides the current behavior is fine as-is.

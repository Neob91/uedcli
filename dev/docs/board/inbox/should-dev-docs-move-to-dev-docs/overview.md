+++
priority = "p3"
kind = "owner-question"
summary = "Should `dev/docs/` move to `dev/docs/`? (raised 2026-07-21 when `install-deusex-assets.sh` moved to `dev/scripts/`.)"
+++

# Should `dev/docs/` move to `dev/docs/`? (raised 2026-07-21 when `install-deusex-assets.sh` moved to `dev/scripts/`.)

The script move created a top-level `dev/` tree, so now "dev-facing stuff"
lives in two places: `dev/scripts/` (new) and `dev/docs/` (existing). Moving `dev/docs/` → `dev/docs/`
would ostensibly consolidate everything dev-facing under one `dev/` root. **My recommendation: DON'T,
UNLESS it's step 1 of a full product-vs-dev reorg** (see last point). Churn/`git blame` cost is NOT
the objection (Andrzej doesn't mind it); the substantive reasons are: (1) **The consolidation is
illusory.** Dev machinery is already scattered and stays scattered — `bin/` (`test`, `_venv.sh`),
`uned/` (`bake_ued22.sh`, `wine_ctl.py`, `entrypoint.sh`), `tests/`, `uedcli-native/`. Moving
`dev/docs/` adds a THIRD dev location (`dev/docs` + `dev/scripts` AND still `bin/`+`uned/`+`tests/`),
it doesn't unify. (2) **`docs/` is already a clean audience-split doc root, one level down:** `usage.md`
+ `leveldesign/` (user) vs `dev/` (dev), with `docs/README.md` the authoritative router. Pulling `dev/`
out relocates one arm of an existing clean split to a farther root and ORPHANS `docs/README.md` (it
now routes across roots). (3) **The name misdescribes the content.** `dev/docs` = "the dev section of
the docs" (accurate: the corpus is fundamentally documentation — architecture, decisions, unrealed
knowledge, board, specs, plans); `dev/docs` = "the docs corner of dev" inverts what the thing is.
(4) It isn't pure docs anyway — `dev/docs/spikes/` holds ~209 committed `.py` harness files; `dev/docs`
honestly frames it as "dev knowledge base incl. evidence," `dev/docs` promises docs then hides scripts.
**When it WOULD make sense:** as step 1 of a real top-level split — **product** (`uedcli/`,
`uedcli-native/`, `bin/uedcli`) vs **development-of-product** (everything else: docs, spike harnesses,
`bin/test`, the `uned/` build scripts, `tests/` all under `dev/**`). Then `dev/docs` is coherent and
reason (3) weakens. So the decision is about SCOPE, not effort: one-off doc relocation (no) vs commit
to pulling ALL dev machinery under `dev/` (yes — then do the whole reorg, don't half-move). Andrzej:
keep/drop/expand-scope — your call.

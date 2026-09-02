+++
priority = "p?"
kind = "unknown"
summary = "Batch `actor add`/`stash capture` no longer silently drop duplicate-Named actors + `brush build`/`actor build` `--name`→`--base-name`"
+++

# Batch `actor add`/`stash capture` no longer silently drop duplicate-Named actors + `brush build`/`actor build` `--name`→`--base-name`

— 2026-07-12 (branch `uedcli-impl`). Root
cause: `model.parse_t3d` keys actors in a `dict[Name]`, so user-concatenated T3D (e.g. 14
`brush build --base-name Merlon | actor add`) lost all-but-last *at parse*, before the uniquify
loop ran. Fix: new `model.parse_t3d_actors` (ordered, duplicate-preserving); `parse_t3d`
refactored to build its dict from it. Both raw-ingest points use it — `actor add` mints a
distinct `<stem>_<rand>` per actor (and now prints `added N actor(s)`); `stash capture`
filters-by-name-first then uniquifies the chosen set. Separately, the generator name flag became
`--base-name` (a stem — the Name always gets a `_<rand>` suffix at add) on both `brush build`
(renamed from `--name`, hard break, no alias) and `actor build` (new — previously every point
actor was named after its class → collapsed on batch add). Spec:
`spec.md`; decisions 2026-07-12 12:15 UTC (both
entries); folded into `architecture.md` (generator verbs + the model-side ingest invariant) and
`usage.md`. Tests: `parse_t3d_actors` dup-preservation, `actor add` 14-merlon + mixed regressions
+ the count print, `stash capture` dup + filter-then-uniquify, CLI `--base-name`/no-legacy-`--name`.
Offline suite green (the only 2 failures are a pre-existing env-permission issue on a repo-pinned
texture lock dir, untouched by this change). Reviewed by two cold subagents at spec AND build; all
findings resolved (the filter-then-uniquify order came from a spec-review finding).

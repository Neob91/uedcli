# Spec DRAFT — skills-plugin distribution via repo-as-its-own-marketplace

## Goal

Ship uedcli's level-design skills as a Claude Code plugin, distributed with the uedcli repo acting as
its own marketplace: `/plugin marketplace add <repo-url>` → `/plugin install uedcli@…`. Outward-facing
distribution — the actual publish is owner-gated (box rules).

## Current state

- No plugin/marketplace files exist in the tree yet (`git ls-files | grep -iE 'skill|plugin'` → only
  board items).
- Design already **decided by the owner** — `dev/docs/decisions.md:5495-5533` ("level-design docs +
  AI-skills plugin") and the `:5535-5549` addendum. Do not re-litigate these; record them.
- Parent effort: `to-plan` item `level-design-best-practices-docs-ai-skills` — this is its deliverable C.
- Hard dependency: `to-spec` item `extract-uedcli-into-its-own-standalone-git-repo` (p2). Blocked on it.

## Decided (owner, verbatim from decisions.md — carry into `direction/packages.md` on build)

- Plugin at `claude/plugins/uedcli/`: `.claude-plugin/plugin.json` + `skills/<name>/SKILL.md`. Grouped
  under a non-hidden `claude/` dir, a sibling of the `uedcli/` Python package (ships via git, not the
  wheel — no packaging change).
- `.claude-plugin/marketplace.json` at the **repo root**, listing the plugin by a repo-root-relative
  `source`.
- Thin per-task skills (~15 lines) that cite the `leveldesign/` guides — one source of truth in the
  docs. Named set: build-water, build-mover, zone-a-level, light-a-scene, texture-surfaces,
  build-skybox, grid-discipline.
- Craft docs live **inside** the plugin via a **within-repo symlink** to the canonical
  `dev/docs/unrealed/leveldesign/` — a marketplace-installed plugin runs from a cache and cannot read
  `../` outside the plugin dir; same-marketplace symlink targets are dereferenced into the cache.
- Marketplace repo is the **new standalone CLI repo**, not `dx_lum` (addendum supersedes the original
  entry): `/plugin marketplace add` on `dx_lum` would clone ~3.3 GB to deliver a few KB of skills.
- Interim dev install: symlink the plugin's `skills/` into `.claude/skills/`. No marketplace registration.
- **Rejected:** (a) bundling the plugin into the pipx/Nuitka binary (onefile temp-unpack can't be
  pointed at); (b) a separate dedicated plugin repo (the CLI repo doubles as its marketplace);
  (c) one monolithic skill (per-task skills load on demand); (d) a `--plugin-dir` path-print install.

## Approach / what is left to spec (post-move)

The design is set; the open work is mechanical and gated on the extraction landing:

1. `marketplace.json` `source` value: after extraction the `Tools/uedcli/` prefix is gone, so the CLI
   repo root holds `marketplace.json` and `source` becomes `./claude/plugins/uedcli`.
2. `plugin.json` fields (name, version, description, author) and a version-bump policy.
3. Confirm the symlink target travels: `dev/docs/**` moves with the extraction (per that item), so the
   canonical `leveldesign/` dir the plugin symlinks to lands in the new repo.
4. Skill inventory materializes only after deliverables A (verb-first guide rewrite) and B (human-scale
   measurement spike) of the parent item land — skills are wrappers over those guides.

## Recommendation

Stay **blocked** on `extract-uedcli-into-its-own-standalone-git-repo`. Pre-stage the plugin dir and
skills inside the repo (they travel with the extraction), but do **not** add the root
`marketplace.json` while still in `dx_lum` — its presence invites `/plugin marketplace add` on the
3.3 GB repo, the exact failure the addendum names. Add the root manifest only once the repo is standalone.

## Test

Offline parse/resolve check: `plugin.json` and `marketplace.json` are valid JSON with the required
keys, and the plugin's docs symlink resolves to a path **inside** the plugin dir (the `../`-blocked
constraint). The live `/plugin marketplace add` flow is manual and owner-gated.

## Open questions

- Repo URL / hosting for the public marketplace, and go-ahead to publish (outward-facing) — see
  `questions/publish-channel-and-go-ahead.md`.
- Plugin versioning scheme (independent of the CLI version, or pinned to it?).

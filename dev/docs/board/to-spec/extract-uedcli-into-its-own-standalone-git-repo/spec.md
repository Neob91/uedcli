# Spec — extract uedcli into its own standalone repo (migration plan)

## Goal

Give uedcli a home matching its identity — a globally-installed, generic-UE1 CLI that operates on
many projects, not a tool living inside one content repo (`direction/projects-and-config.md`,
`direction/scope.md`). Enumerate what moved, what remains coupled, and the outward-facing
process/ownership decisions the owner still has to make.

## Current state — the physical extraction has already happened

This working tree **is** the standalone repo, and it is already published:

- `git remote -v` → `origin git@github.com:Neob91/uedcli.git`; `HEAD == origin/master`
  (`a018a55`), 213 commits, first commit `8c9ead3 "Initial"` dated 2026-07-25.
- It was seeded as a **fresh copy, not a `filter-repo`/subtree extraction** — the dx_lum history was
  not carried (the first commit is a bare "Initial"). Because the repo is already pushed, the
  global "never rewrite published history" rule now applies to *this* repo too, so re-seeding it to
  recover dx_lum history would be a forbidden history rewrite. See
  `questions/confirm-fresh-repo-no-history.md`.
- Layout at root: `uedcli/` (the package, 16M), `uedcli-native/` (Rust crate — native mesh decode:
  `Cargo.toml`, `src/`, its own `pyproject.toml`), `uned/` (compose dir + committed UED22 substrate +
  gitignored `DeusExAssets/`, 105M), `bin/` (`uedcli`, `test`, `board`, `_venv.sh`), `dev/docs/**`
  (incl. the board + `spikes/`), `docs/` (user-facing), `pyproject.toml`, `pytest.ini`, `CLAUDE.md`,
  `README.md`. Offline `bin/test` runs host-native here.

So the item is **not** "move the code out" — that is done. What remains is (a) finishing the physical
remnants that still assume the old `dx_lum` layout, and (b) the logistics/ownership decisions the
board note flagged and that were never actually made.

## Remnants still coupled to the old `dx_lum` layout

Code:

- `uedcli/tool_assets.py` — `tool_root()` = the dir holding the package = the repo root here, but the
  docstrings still say `Tools/uedcli/`. **`umodel_dir()` returns `tool_root().parent /
  "umodel_win32"`** = `/workspace/umodel_win32`, which **does not exist** — no `umodel_win32`
  anywhere on the system. In the old tree umodel was a sibling of `Tools/uedcli/`; in the standalone
  repo that sibling is gone, so stub building (which needs umodel) resolves a broken path. This is
  the one remnant that breaks a real (integration) path, not just prose. Decide where umodel ships
  and re-anchor.
- Container/image name `dx-lum-uned` is hardcoded in test helpers (`tests/editor_oracle.py:111`,
  `tests/builder_parity_cases.py:59`, `tests/test_actor_name_resolution.py`) and referenced across
  `dev/docs/` — a `dx_lum`-flavored name for what is now a standalone tool's editor container.

Docs / prose (all developer-tree or user `README.md`, so agent-editable prose but owner-approval for
`dev/docs/` non-board edits):

- `README.md` — quickstart still says `export PATH="$PWD/Tools/uedcli/bin:$PATH"` and describes the
  `dx-lum-uned` container; points at `docs/superpowers/specs/...` which no longer exists at root.
- `dev/docs/architecture.md`, `parallel-editors.md`, `README.md`, `decisions.md` — many
  `Tools/uedcli`, `dx-lum-uned`, "LUM repo", `uedcli/maps/`, `Prefabs/` references framed as if
  inside the mod tree.
- `uned/DeusExAssets` + `dev/games/` stay gitignored (copyrighted content) — correct, no change.

None of the prose remnants block the tool; they are a cleanup pass. `umodel_dir()` and the container
name are the load-bearing ones.

## Design — sequencing

Ordered so nothing outward-facing happens before the owner rules:

1. **Owner decisions first** (the three question files) — consumption model, release/asset shipping,
   and the no-history confirmation. Everything below depends on them.
2. **Fix the load-bearing code remnants** (no owner gate beyond the release-model answer):
   re-anchor `umodel_dir()` to wherever the release model puts umodel (its own repo dir vs a
   downloaded asset); decide and apply the container/image rename (or keep `dx-lum-uned`).
3. **Prose cleanup pass** across `README.md` (agent-editable) and the `dev/docs/**` remnants
   (each `dev/docs/` non-board edit needs the owner's yes per `CLAUDE.md`). Propose the exact
   edits; do not rewrite `direction/`.
4. **Unblock the dependent item** `skills-plugin-distribution-via-repo-as-its-own`, which the
   overview names as downstream of this one.

The board pipeline, tests, and CI already live in this repo, so there is no cross-repo board
migration to do — that concern in the original note is already resolved by the fresh-copy seed.

## Migration options (for the decisions, not to pick unilaterally)

- **How the dx_lum mod repo consumes uedcli now** — pipx global install (matches
  `direction/projects-and-config.md` "one install, many games"; the mod becomes just another project
  with a `uedcli.toml`) / git submodule / pinned dependency / fully decoupled (mod holds nothing).
  Recommendation: pipx global + a `uedcli.toml` in the mod repo — it is exactly the model the
  direction doc already commits to. Owner + outward-facing. See
  `questions/how-mod-repo-consumes-uedcli.md`.
- **Release + asset shipping** — pipx-from-git vs PyPI vs the Nuitka standalone binary the README
  promises; and how the non-wheel assets ship (`uned/` UED22 substrate + compose, `umodel_win32`,
  the `uedcli-native` Rust crate). `pyproject.toml` currently ships **no** package data (substrate/
  editor live in the Docker image + mounts, not the wheel), and `tool_assets` resolves them
  package-relative — so the release story must say where they come from under an installed binary.
  This overlaps a separate packaging board item; scope here is to **confirm the split**, not
  redesign packaging. See `questions/release-and-asset-shipping.md`.
- **Git-history handling** — already de facto decided (fresh copy, no history) and now effectively
  locked by publication. Confirm it is accepted. See `questions/confirm-fresh-repo-no-history.md`.

## Edge cases & risks

- Redoing the extraction to preserve history would rewrite `origin/master` — forbidden, and would
  break anyone who already cloned. The window closed at first push.
- A prose cleanup that edits `dev/docs/` without the owner's yes violates `CLAUDE.md`; propose text,
  wait.
- `umodel_dir()` pointing at a non-existent path is silent until an integration stub build runs —
  fix it as part of the release-model answer so it fails loud if unset, not silently.

## Tests

- `tests/test_tool_assets.py` already pins the anchors; update it when `umodel_dir()` is re-anchored,
  and add an assertion that the resolved umodel path exists (or a clean error names it if the release
  model makes it optional).
- Offline `bin/test` must stay green through every remnant fix; the container-name and umodel changes
  touch integration-only helpers, so guard against a rename desyncing the deselected suite.

## Open questions

- `questions/how-mod-repo-consumes-uedcli.md` — consumption model (outward-facing).
- `questions/release-and-asset-shipping.md` — release + non-wheel asset shipping.
- `questions/confirm-fresh-repo-no-history.md` — accept the no-history fresh seed.

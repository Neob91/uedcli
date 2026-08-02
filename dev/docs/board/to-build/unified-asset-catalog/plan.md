# Plan: asset catalog — the TEXTURE arm

Buildable slices for `spec.md`. Read before starting: `dev/docs/rules/building-features.md`,
`dev/docs/rules/tests.md`, `dev/docs/rules/worktrees.md`, `spec.md`, `dev/docs/direction/asset-catalog.md`.
Build in a **feature worktree**, commit per slice, update `docs/usage.md` in the same commit, keep
`bin/test` green (no new skips). Each slice lists its tests and how to verify it by hand. Reuse the
class arm; build only the texture delta (`spec.md` §1).

**Precedent to mirror:** `uedcli/class_catalog.py` (store), `uedcli/cli/commands/classes.py` +
`uedcli/cli/parsers/texture.py` (CLI). **Decode seam:** `uedcli/utexture.py` (`TextureResolver`,
`DecodedTexture`, `TextureError`) — reused, but its class filter is widened to `Engine.Texture`
descendants (T0b).

## T0 — Enumerate `Engine.Texture` descendants

Add a texture enumerator: per package on `config.composed_search_files`, every export whose class
descends from `Engine.Texture` → its ref `Package[.Group].Name` (group = export Outer). Use
`utexture.class_fqcn_of_export` + `resources.class_index(project).descends_from(fqcn, "Engine.Texture")`.
A `None` fqcn (locally-defined class, `class_fqcn_of_export` `:353-354`) is not a texture — skip it,
never pass `None` to `descends_from` (`None.casefold()` crashes). Add an `ENGINE_TEXTURE` constant
beside `ENGINE_ACTOR` in `classindex`.

- **Tests:** a synthetic package with a `Texture`, a `FireTexture` (descendant), and a non-texture
  export → the first two enumerate, the third does not; refs are `Package.Name` / `Package.Group.Name`;
  sorted; an undecodable export still enumerates.
- **Verify:** `texture list` (built in T3) lists a known package's textures incl. a `FireTexture`.

## T0b — Widen the decode seam to `Engine.Texture` descendants

The exact `pkg.class_of_export(i) == "Texture"` test lives only in `utexture.textures` (`:341`);
`_texture_named` (`:875`) and `_decode_ref` (`:952`) hold no class test — both delegate via
`for i in textures(pkg)`. So a `FireTexture`/`ScriptedTexture` subclass returns `unknown-texture`,
never `no-mip-data` — killing the procedural name-key path and making show/preview/classify/`exists`
on any `Engine.Texture` descendant exit 2. Widen `textures()` alone: its signature gains the class
index, replacing the `== "Texture"` test with
`descends_from(class_fqcn_of_export(pkg, i), "Engine.Texture")`. That cascades to both delegating
callers (they pass the index through); `textures()` has no other callers, so the change is contained.
Skip a `None` fqcn (`class_fqcn_of_export` returns `None` for a locally-defined class, `:353-354`) —
treat it as not a texture, never feed `None` to `descends_from` (`None.casefold()` crashes). A real
`utexture.py` edit, not reuse; do it before T1 so the procedural path exists.

- **Tests:** `_decode_ref`/`exists` resolve a `FireTexture` export (→ `no-mip-data`, not
  `unknown-texture`); a non-texture export still misses; a plain `Texture` still resolves.
- **Verify:** `texture show <FireTexture ref>` reports the no-bitmap note, not exit 2.

## T1 — Layer-1 identity + Layer-2 facts (library)

`identity(DecodedTexture) -> hex` = `sha256(uint32_le(w) ‖ uint32_le(h) ‖ rgb)`; a procedural
(`TextureError.case == "no-mip-data"`) → casefolded `Package.Name`. Layer-2 facts helper: `group`
(Outer), `masked` (`b_masked`), `w`, `h`, `format` (`layout`/`format_code`).

`DecodedTexture` carries no outer/group/export index (`utexture.py` §`DecodedTexture`), so the facts
helper takes `(package, export_index)`: `group = package.name_of_ref(export["outer"])` needs the
export. The T0 enumerator has it; per-ref `show`/`list --json` must re-open the package to supply it.
`masked`/`w`/`h`/`format` come from the `DecodedTexture` alone.

- **Tests:** the frozen identity golden (fixed w/h/RGB → pinned hex); mask change leaves identity
  unchanged; identical pixels, different names → same identity; procedural → name identity; `masked`
  reports tag-else-default-else-null; `group` is the Outer or null on a 2-part ref.
- **Verify:** a scratch script prints identity + facts for a real ref.

## T2 — The identity-keyed shard store (rewrite `texture_catalog.py`)

Delete the legacy manifest module and rewrite `uedcli/texture_catalog.py` mirroring `class_catalog.py`:
payload `{kind:"texture", identity, ref, tags, description, colors}`; path fan-out per `spec.md` §3;
atomic write + per-shard flock; `load_all_shards`, `classified_identities`, `tag_vocabulary` (reused
shape), `score`. Set semantics: **exists ⇒ refuse** (`--force` replaces); write-once `ref`.
`unset` field-clears incl. `--colors`.

`score`: copy `class_catalog.score`'s tiers but fix the leaf extraction — its `ref.split(".",1)[-1]`
yields `Group.Name` for a 3-part texture ref, so the exact-name tier (5) never fires; use
`rsplit(".",1)[-1]` (or the bare Name).

- **Tests:** round-trip; path fan-out (hash vs name-keyed); set-over-existing raises (the CLI turns it
  into exit 2), `--force` replaces; the write-once `ref` survives a same-identity re-set attempt;
  `unset` clears tags/description/colors/all; unreadable shard skipped, path collected.
- **Verify:** `python -c` round-trips a shard to a tmp catalog dir.

## T3 — `texture list` / `show` (rewrite the noun)

Rewrite `cli/commands/texture.py` + `cli/parsers/texture.py` mirroring `classes.py`. Delete `sync`,
`--stale`, `--removed`, and every legacy import. `list` enumerates (T0), sorts, one ref per line;
`--json`/`--classified`/`--unclassified`/`--group`/`--masked` decode each ref (T1) to get identity +
facts; `show` prints facts + identity + stored classification, `--json`. `-` reads a newline ref list.

Deleting `sync` orphans the container-export module — only the `sync` handler calls
`texture.batchexport_textures` (`cli/commands/texture.py:102`). Per no-back-compat-cruft, delete
`uedcli/texture.py`, `uedcli/tests/test_texture.py`, and `uedcli/tests/test_texture_integration.py`
in this same change. Rewrite/remove the legacy `texture sync`/`classify`/`Manifest`/`TextureEntry`
cases in `uedcli/tests/test_dispatch.py` (~:924-1072 — the `_tex_project` fixture, the `sync` tests
from ~941, and the `classify`/`Manifest`/`TextureEntry` cases) so `bin/test` stays green.

- **Tests:** `list` refs one-per-line; `--json` row shape `{ref, identity, classified, group, masked, preview:null}`;
  `--group`/`--masked`/`--classified` filter; `show` human + `--json` shapes; a bad ref exits 2 naming
  it; empty stdin → exit 0; no `sync`/`--stale`/`--removed` parser entries remain.
- **Verify:** `texture list --package <P>`, `texture show <ref> --json`, `--masked` on a masked package.

## T4 — Colours (§6)

Fixed named palette + nearest-colour share ranking → ordered names. Wire into `show`/`list --json`
(derived when unclassified), the `set` pre-fill (row without `colors`), and `search --color`.

- **Tests:** pre-fill order matches a golden for a known image; `--color` matches a classified stored
  colour and live-derives for an unclassified texture; an LLM `colors` overrides the pre-fill.
- **Verify:** `texture search --color brown` over a real package returns brown textures with an empty
  classification store.

## T5 — `texture preview`

Mirror `class preview`: `resolve` → Pillow RGB image (mip 0, mask not applied) → `rendering.write_png`.
`<ref>\t<path>`; `--skeleton` → JSONL `{ref, preview, tags:[], description:"", colors:[…]}` (colours
pre-filled). `TextureError` disposition per `spec.md` §5 (per-ref exit 2 naming the case; procedural =
named no-bitmap note; `ambiguous-alpha` states the limit).

- **Tests:** PNG of the right size, mask not applied; `--skeleton` JSONL carries the path + pre-filled
  colours; per-ref procedural/undecodable exits 2 naming the case; `ambiguous-alpha` text states the
  limit.
- **Verify:** `texture preview <ref> --out /tmp` opens to the expected image; `--skeleton | head`.

## T6 — `classify set·unset·status·tags` + `search` + `prewarm`

Wire the classify sub-verbs (single + JSONL `-` batch, all-or-nothing) onto T2, mirroring
`classes.py`'s handlers; `set` refuses-over-existing with `--force`. `status` = intersection of
on-path identities with shards (decodes). `tags` reuses `tag_vocabulary`. `search` reuses `score`,
terms-required (term-less exits 2 → `list`), with `--tag`/`--color`/`--group`/`--masked`/`--package`
filters. `prewarm` decodes every texture (warms ref→identity), `--package`/`--force`, progress → stderr.

- **Tests:** `set` single + `-` JSONL (N shards, all-or-nothing on a bad row); refuse-over-existing +
  `--force`; `unset` variants; `status` counts + `--json`; `tags`; `search` ranking golden over a
  zero-classification corpus, term-less exit 2, each filter; `prewarm` decodes and reports.
- **Verify:** the §5a agent loop end-to-end — `texture list --unclassified --package P | texture preview
  - --skeleton > work.jsonl; texture classify set - < work.jsonl; texture show <ref>`.

## T7 — Docs + review

Update `docs/usage.md` (the new `texture` verbs; remove `sync`/`--stale`/`--removed`) in the touching
commits. Sweep `docs/leveldesign/` only if a user-facing recipe references the old catalog. One subagent
reviews `git diff base...HEAD` (prompt it to read `dev/docs/unrealed/t3d.md`, `direction/asset-catalog.md`,
`direction/conventions.md`, and this spec first); fix confirmed findings, re-test.

- **Verify:** `bin/test` green; formatter/linter/type-checker clean on touched files; `-h` on every new
  verb reads as self-explanatory.

## Deferred (own board items, not this plan)

`--similar`/phash; the content-addressed preview pool; the derived per-`(kind,package)` index; the
shard-index roll-up; `classify prune`/`list-outdated` (blocked on board item
`texture-classify-rekey-and-prune`, `questions/rekey-across-a-pixel-edit.md`). Not started here.

## Sequencing note

T0–T2 are library-level (no CLI); T3 first exposes the noun. T4/T5 are independent of each other and
can swap order. The frozen-identity golden (T1) must land before any shard is written (T2), because it
is every shard's filename.

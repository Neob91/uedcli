# Ready to build

The **on-deck queue**: plans that are reviewed and ready to execute *now*. Each entry links its
full plan in `../plans/` (ephemeral detail) — this file is the stable "build this next" index.

How this relates to the other board docs (see [`README.md`](README.md) for the full flow):
- The upstream queues — **[inbox.md](inbox.md)** (raw capture) → **[to-spec.md](to-spec.md)** →
  **[to-spike.md](to-spike.md)** → **[to-plan.md](to-plan.md)** — hold the broader, noisier backlog.
- **to-build.md** (this) — the short list of *reviewed, ready-to-go* work, pointing at the plan.
- **[inbox.md](inbox.md)** — the capture pool: ideas/gaps/bugs/chores + anything flagged for Andrzej.

When a plan here is built, delete its entry ([`done.md`](done.md) keeps a short recently-done tail).

---

## Native texture decode for any UE1 package (spec + plan self-contained, 2026-07-25)

- [ ] `p1` **Decode every UE1 texture layout natively; layout read off the DATA, not a format table.**
  Plan: [`../plans/2026-07-25-native-texture-formats-plan.md`](../plans/2026-07-25-native-texture-formats-plan.md).
  Spec: [`../specs/2026-07-25-native-texture-formats.md`](../specs/2026-07-25-native-texture-formats.md).

  **These two files are SELF-CONTAINED — read them and build. No other document needs opening.**
  They inline the binding decisions with their rejected alternatives, the on-disk `UTexture`/
  `FMipmap` byte layout, the house rules (test command, commit conventions, no-back-compat,
  no-silent-half-answers), every corpus path with its committed/not status, and every measured
  number with the root it was measured against. Provenance pointers are for the record only.

  **Why it matters here and now:** `utexture.py` decodes one layout (`fmt==0`), so a `UTexture`'s
  second mip array (`CompMips`) makes the body parse overrun — **30 textures in the project's own
  `LUM/Textures/LUM_CoreTex.utx` are invisible to uedctl today** and render as a checkerboard.
  This is a live bug on this substrate, not generic-UE1 hygiene.

  **Seven slices:** `S1` CompMips + fixture builder → `S2` typed error results → `S3` layout
  detection → `S4` BC1 → `S5` BC2/BC3 → `S6` integration sweep + engine-fact pins → `S7` docs/board.

  **Gates** slice `S8a` of the asset-catalog plan below. Land it **before any texture is
  classified**: catalog shards are named `sha256(w,h,RGB)`, a frozen identity, so a later decode
  change silently re-keys and orphans them.

  **Two items were builder-decided under delegation ("do whatever it takes") and are reversible:**
  a data-vs-`Format` disagreement is a named `format-disagreement` error rather than a note
  (measured to fire on 0 of 18,176 exports today), and decode emits the mask the data carries
  without consulting `bMasked`/`bAlphaTexture` (which `Engine.Texture` defaults to `False`, so
  gating on them would silently switch block alpha off corpus-wide).

---

## Unified asset catalog — one engine, four kinds (spec + plan reviewed, 2026-07-25)

- [ ] `p2` **The unified asset catalog: texture / class / sound / music.** Plan:
  [`../plans/2026-07-25-unified-asset-catalog-plan.md`](../plans/2026-07-25-unified-asset-catalog-plan.md).
  Spec: [`../specs/2026-07-25-unified-asset-catalog.md`](../specs/2026-07-25-unified-asset-catalog.md).
  Decisions: `decisions.md` 2026-07-25 03:40 + 05:10. **Four review rounds total** — two on the spec,
  two on the plan, all findings folded.

  **Governing principle:** the tool **lists, reports file facts, produces pictures, and stores the
  classification it is handed — it never infers meaning.** The LLM works out what an asset is and
  where it is used, and hands the answer back. The one deliberate exception is texture colours,
  pre-filled from that texture's own pixels and ordered by importance, so colour search works before
  any classification exists. *(This reframe, Andrzej 2026-07-25, deleted a tool-computed stock-map
  usage index, a class placement histogram, derived `placeable`, AND a whole build prerequisite.)*

  **Sequencing** (value-first; each slice a commit, `usage.md` updated in the same commit, no new
  test skips versus baseline):
  `P0` schema_cache v2 (raw default tags — gates S2 onward) → `S1` engine core →
  `S2` adapters → `S3` list/show (class, sound, music) → `S4` object-ref validation *(fixes a live
  bug that silently ships broken levels)* → `S5` classification store → `S6` search + ranking →
  `S7` class arm (mesh decoder → `uedctl/`, `class preview`, size facts) → `S8a` texture adapter
  (library-level) → `S8b` repoint the noun + delete the legacy subsystem → `S9` `.umx` title sniffer
  → `S10` lifecycle → `S11` doc sweep.

  **Blocking prerequisite NOT yet on the board:** `P1` **native non-P8 texture decoders** is still an
  untriaged `inbox` item (`[spike/implement] p2`) and **gates `S8a` only** — triage it through
  `to-spec`/`to-plan` before scheduling the texture slices. Everything else proceeds without it.

  **Two things the builder must NOT decide alone:** (1) `S7` measures whether the existing Rust
  rasterizer can render meshes — if it can, the ~300 ms/render figure underpinning decisions 7
  (never render in `list`/`search`) and 11 (single `iso` angle) is a Python artifact, and any change
  goes back to Andrzej as a **superseding `decisions.md` entry**, not a mid-slice judgement call;
  (2) the texture identity function `sha256(w,h,RGB)` is **frozen** and pinned by a committed golden
  in `S8a` — it is every tracked shard's filename, so any decode change silently re-keys and orphans
  authored classifications.

## Unattended build queue (curated 2026-07-18) — ✅ ALL 12 ITEMS DONE (see `done.md`)

The 2026-07-18 Andrzej-picked queue (bugs → small features → geometry → analysis → CLI audit) is
**fully drained**: builds #1-#5 shipped items 1-11, and the item-12 CLI consistency audit was
delivered as `../reviews/2026-07-19-cli-consistency-audit.md` (report-only). Its accepted-worthy
fixes are new `inbox.md` items awaiting Andrzej's triage. Entries live in `done.md`.

---

## 7. BSP-issue detector (D0 + the P0 spike + `level doctor --rebuilt` + D0-b)

**Status:** PARKED mid-spike (2026-06-25). Spec reviewed (6 rounds), plan reviewed (3 rounds).
**Plan (full detail):** [`../plans/2026-06-24-uedctl-bsp-detector-plan.md`](../plans/2026-06-24-uedctl-bsp-detector-plan.md)
**Spec:** [`../specs/2026-06-24-uedctl-offline-bsp-engine-design.md`](../specs/2026-06-24-uedctl-offline-bsp-engine-design.md) ·
**Decision:** `../decisions.md` 2026-06-24 12:40 UTC

**What it is.** Catch the *build-emergent* BSP problems (slivers, hall-of-mirrors, invisible walls,
fall-through) that the already-shipped static `level doctor` structurally can't.

**Build order (the near-term scope — D1-b and all D2 engine slices are OUT/deferred):**
1. **`UModel`-parser feasibility spike (first, alone)** — the value gate: decides whether the
   located-issue tier (`--built`) is even buildable. One session, on a *built* `.dx`.
2. **Promote D0** — the validated drop-warning parser → a new `uedctl/bsp/editorlog.py` + helpers +
   offline golden tests. (Offline, pure, touches no shared code.)
3. **`level doctor --rebuilt`** — the MVP: rebuild the level in an ephemeral editor, read the
   drop-warnings, report (a CI tripwire). Self-contained — wraps the injected `rebuild` callable, so
   it does **not** modify the shared `materialize()`/`level apply` path. `--built` added only if
   step 1 is go.
4. **D0-b measurement** — run over real maps to decide whether D1 is worth building (needs the
   gitignored install content; content-blocked → tracked TODO).

**Footprint (mostly additive):** a new `uedctl/bsp/` module + an opt-in `level doctor --rebuilt`
flag. The static `level doctor` and `level apply` are left as-is; `doctor.py` gets only a cosmetic
stale-string fix. The one change that would touch a load-bearing feature (surfacing build-health on
`level apply`, step 3b) is **deferred, optional, warn-only, and never alters `apply`/`materialize`
behavior**.

**Where the spike is parked:** See
[`../spikes/2026-06-25-umodel-serialize-format.md`](../spikes/2026-06-25-umodel-serialize-format.md)
for findings and next steps. The working harness is `_scratch/bspspike/umodel_parser.py`.
The parser handles everything up through the zone data. The next blocker is `_skip_array_0xa8`:
`0x1010c160` reads 3 × 4 raw bytes (not 1 ci) — fix is one line; downstream arrays may need
further verification.

**Done when:** step 1 go/no-go recorded; step 2 landed (suite green); step 3 shipped per the spike
answer (docs current); step 4 measurement recorded or content-blocked TODO. D1-b proceeds only on a
green spike, as its own plan.

---

---

## CLI usability-probe fixes (2026-07-19, `dev/docs/reviews/2026-07-19-cli-usability-probe.md`)

Mechanical fixes triaged from the usability probe (design-y ones went to `to-spec.md`). Small, self-contained; no plan needed.


---

## Promoted from F/H triage (2026-07-19)

Andrzej-approved ready items promoted from `inbox.md` into the build queue. Each is stage-less
(a chore/debug or a self-contained implement) or, for `usage.md`, a chosen DO-SOON doc rewrite.

---

## 8. `level import` — native (editor-less) `.dx`/`.unr` → T3D-tree ingestion

**Status:** Spec + plan written, **two cold-review rounds passed** (findings resolved inline).
**Plan (full detail):** [`../plans/2026-07-24-level-import.md`](../plans/2026-07-24-level-import.md)
**Spec:** [`../specs/2026-07-24-level-import.md`](../specs/2026-07-24-level-import.md) (v3) ·
**Decisions:** `../decisions.md` 2026-07-24 16:48 / 16:59 / 17:19 / 18:49 UTC

**What it is.** The inverse of `level materialize`: natively decode a compiled map file (no editor, no
UCC in the shipping path) into a queryable/diffable/remixable T3D trunk or stash. Decode REUSES the
production value decoder (`uprops.render_default_tag`); new code is `mapimport.py` + a StateFrame/FPoly
promotion + dynamic-array schema plumbing + the verb. UCC-fidelity lives at DECODE time (member-stripped
structs + 6dp floats), so the schema-free hash path is untouched; strict `qualify_and_validate` on
import.

**Build gate — Slice 0 DONE (2026-07-24), build unblocked.** The actor-ORDER spike resolved the
`Engine.Level` Actors layout (`[i32 Num][i32 Max]` + `Num` compact refs, `0`=null, `Actors[0]==LevelInfo`;
export-table order does NOT match, so decode the array). Verified on 3 retail maps; pinned by
`test_engine_facts.test_level_actors_array_is_int_num_max_then_compact_refs`; folded into spec §5.1.
Remaining slices: decode primitives (promote + pin) → UCC-exact render → `import_map` → verb/write path
→ goldens+integration → docs. Now buildable end-to-end.

---

## Promoted from the cheap-item board review (2026-07-24)

Andrzej triaged the ten-item cheap shortlist in chat; his calls are recorded in `../decisions.md`
2026-07-24 21:58 UTC. Three items changed shape rather than just queue (class-show, the ditched
stash-`CalledProcessError` item, and `--png`). Two items did NOT come here: the `ensure_editor`
`CalledProcessError` leak was **ditched** (native intersect/deintersect deletes that code path), and
nothing was sent to `to-spec.md`.

---

## 11. `docs` command — serve the user-facing docs from the CLI (self-documenting binary)

Add `uedctl docs list|show|search` serving `docs/` minus `dev/docs/**`, so a shipped Claude skill
routes to the docs by **querying the tool** — the skill/plugin ships zero doc copies. **The spec
doubles as the plan** (implementation-detailed; review gate passed 2026-07-24, two cold reviewers,
findings folded): `specs/2026-07-24-docs-command.md`. Key points baked in: `show` resolves via the
enumerated served-set (kills path-traversal + dev-tree leak structurally, no raw path-join); resolver
= `UEDCTL_DOCS_DIR` → source tree → packaged `uedctl/_docs` (**source-first** so a stale local build
can't shadow live dev docs); a `README.md` folds to its directory topic (root → `index`); errors reuse
`_SelectionExit` (clean exit 2, no new type). **Deferred, NOT this item:** the Nuitka/wheel `_docs`
generation + `.gitignore` + `--include-data-dir=uedctl/_docs=uedctl/_docs` + drift-CI — added only when
packaging exists, with no command-code change. **Docs to update on landing:** `docs/usage.md` gains a
`docs` section (the reference file the command serves); `architecture.md`. (Andrzej, 2026-07-24.)

---

## Codebase-review chore batch (2026-07-25, session `uedctl:review`)

A coherent batch of small, independent fixes surfaced by a 5-agent codebase review and directed by
Andrzej. **Build together, then run ONE build-review gate over the accumulated diff** (per `CLAUDE.md`
"BATCH small changes into one round"). Each is confirmed not already on the board. The two larger
findings from the same review are specced separately — trunk write safety
([`../specs/2026-07-25-trunk-write-safety.md`](../specs/2026-07-25-trunk-write-safety.md)) and uniform
Decimal map coordinates
([`../specs/2026-07-25-decimal-map-coordinates.md`](../specs/2026-07-25-decimal-map-coordinates.md)) —
and are NOT part of this batch.

- [ ] `p2` **`clip --coord` → `--offset`, routed through a shared scalar-Decimal validator.**
  `cli.py` `clip.add_argument("--coord", type=Decimal, …)` uses the bare `Decimal` constructor as the
  argparse `type`. argparse only converts `ValueError`/`TypeError`; `Decimal("abc")` raises
  `decimal.InvalidOperation` (an `ArithmeticError`), which escapes as a raw traceback (verified live) —
  breaks "never let a Python exception reach the CLI user". Fix: (a) add a shared `parse_decimal`
  helper (single scalar; rejects non-numeric AND non-finite `nan`/`inf`, wrapping the parse in
  `try/except InvalidOperation → ArgumentTypeError`), (b) rename `--coord` → `--offset` outright (no
  alias — unreleased; Andrzej 2026-07-25) with help "plane offset along --axis (world)", (c) route it
  through `parse_decimal`. **Also fold in the already-logged `parse_coord`/`parse_pan` non-finite gap**
  (`inbox.md`) so all coordinate parsers reject `nan`/`inf` through the one validator. Update
  `docs/usage.md` for the rename.

- [ ] `p2` **`propedit.split_struct_text` is not quote-aware — make it reuse the quote-aware parser.**
  `propedit.split_struct_text` splits struct members on any depth-0 comma, so a StructProperty member
  whose value contains a quoted comma (`(Msg="a,b",Count=1)`) fails to parse (`actor prop get/set/find`
  errors), while the sibling `typedprops.parse_struct_text` handles it quote-aware. Fix: have
  `split_struct_text` delegate to (or share) `typedprops`'s quote-aware member split so the two
  struct-literal parsers agree. Add a regression with a quoted-comma member.

- [ ] `p2` **Truncated/corrupt `.u` must exit non-zero with a named error, not a traceback.**
  `dxpkg.parse_header` does raw `struct.unpack_from` / `_read_compact_index` with no guard; on a
  truncated package it raises `struct.error`/`IndexError`. Its offline caller path
  (`stub_closure.direct_packages` → the stub handler at `dispatch.py`) catches only
  `(RuntimeError, ValueError)`, so those escape as a bare traceback. Fix: wrap `dxpkg.parse_header`'s
  parse in a named error (mirror `upackage.load_package`, which raises `SchemaError` on
  `struct.error`/`IndexError`/`ValueError`) so a corrupt `.u` names the offending file and exits 2.
  (The logged `to-spec.md` "migrate `dxpkg` onto the unified core" would fix it incidentally but is
  framed as a refactor and does not call out the no-traceback contract — this closes the contract gap
  now.) Add a corrupt-`.u` regression.

- [ ] `p2` **Ditch globs on `actor show`; make it a pure name resolver (Andrzej 2026-07-25).**
  `query.show_actor` accepts `*?[` and returns `""` (→ a blank stdout line at `dispatch.py`) on zero
  matches. `actor find` already does pattern→names and `actor find … | actor show -` composes, so the
  glob on `show` is redundant with the compose philosophy. Fix: remove the glob branch from
  `show_actor` — a token that names no actor raises the house `Actor not found: <name>` (exit 2) like
  every other consumer; delete the empty-glob `""` path (this also removes the spurious blank line at
  `dispatch.py`). Confirm no other verb relies on `show`'s glob. Update `docs/usage.md`. Sweep tests.

- [ ] `p3` **Preserve the dead `Driver`/`editor`/`xfer` surface in a spike harness, then delete from
  prod (Andrzej 2026-07-25).** ~17 zero-caller `Driver` methods (`click`, `edit_copy`, `dexec_bash`,
  `screenshot`, `map_load_dx`, `rmode`, `jumpto`, `camera_align`, `selectname`, `select_inside/none`,
  `actor_delete`, `brush_moveto`, `map_sendto`, `select_by_csg`, `brush_export`, `brush_import`), plus
  `xfer.cp_in`, `editor.novnc_url`, and `EditorBusyError` (caught in `apply.py`/`dispatch.py`, raised
  nowhere → unreachable busy path). Several docstrings claim live use by the editor-preview flow
  deleted 2026-07-16 (`click`, `camera_align`) — actively misleading. Fix: **copy the removed methods
  into a committed spike harness** under `dev/docs/spikes/<slug>/harness/` (so the editor-driving
  knowledge isn't lost — per `CLAUDE.md` "Commit the harness"), then delete them + the dead
  `EditorBusyError` catch/raise from prod. Distinct symbol set from the completed `canonicalize_mover`
  deletion and the `to-spec.md` dead-code item.

- [ ] `p3` **Bound the non-driver container waits (the part outside the logged `driver.py` chore).**
  The logged chore (`inbox.md`) covers only `driver.py`'s 8 calls + `xfer.remove`. Still unbounded and
  surviving the texture-catalog rework: `editor._wait_ready` (per-poll `docker exec`, defeats its own
  deadline loop), `editor._is_running` / `_spin_up` / `_reap_container` / `stop_editor`,
  `xfer.cp_in`/`cp_out`, and `store_export.export_dx_t3d`'s three `check=True` execs. Sibling
  `preview_game.stop_game` already bounds its `docker rm -f` at 60 s — apply the same discipline. Give
  `_wine_ctl`-class long verbs their own generous bound; short probes a short one. **Also add
  `store_export.export_dx_t3d` a `try/finally`** so an export failure doesn't strand the `/work` dir
  (its sibling `texture.batchexport_textures` already does). NOTE: `texture.py`'s `batchexport` is NOT
  here — the unified-asset-catalog rework deletes it outright.

- [ ] `p3` **Two `config.py` lows.** (a) `load_user_config` splits `paths` and checks `isabs` at load
  time, so a pasted Windows path (`C:\DX\System`) errors `dir must be absolute: 'C'` — the dedicated
  `_WIN_DRIVE` "Windows-style drive?" error lives only in `resolve_dirs` (compose time), which never
  runs first; share/raise it in the load-time loop. (b) `walk_up_root`'s `except OSError: continue`
  climbs *past* a permission-denied marker dir, contradicting its own docstring rule ("unreadable
  marker is NOT climbed past") and risking binding a nested repo to an outer project — treat an
  unstatable marker as a stop, not a skip.

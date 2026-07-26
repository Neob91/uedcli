# Decisions log

> **FROZEN 2026-07-26 — DO NOT APPEND.** This append-only ledger is being retired and will be
> deleted. New decisions go to a **revised-in-place** topic doc instead: Andrzej's to
> `direction/<topic>.md` (only with his explicit yes — `CLAUDE.md` "Direction docs"), yours to
> `rationale/<topic>.md`. See [`direction/README.md`](direction/README.md),
> [`rationale/README.md`](rationale/README.md), and
> [`specs/2026-07-25-docs-restructure.md`](specs/2026-07-25-docs-restructure.md). Entries below
> migrate topic by topic; `rationale/MIGRATION.md` records where each one went.

The **durable** record of design decisions Andrzej made. Specs and plans
(`specs/`, `plans/`) are ephemeral and get deleted once their work lands; the
decisions made inside them must NOT die with them.

What belongs here is the part topic docs (`architecture.md`, `unrealed/*.md`)
don't carry: the **choice, the alternatives rejected, and why**. Topic docs
describe what the system *is now*; this log preserves *why it is that way and
what it isn't*. When a durable doc or spec would otherwise say "see
`specs/<thing>-design.md` for the rationale and rejected alternatives", point it
at an entry here instead — that reference survives the spec's deletion.

Append new entries at the bottom. **Prefer supersession over rewriting:** when a
decision is reversed, add a new entry that supersedes it (and link back) rather
than editing the old one in place. Two kinds of entry MAY be pruned once they are
dead — git preserves the history either way:
1. an entry a later one has **wholly** superseded (nothing in it is still the
   operative decision). Keep *partially*-superseded entries — their live half
   still governs.
2. spike-result / feasibility-**"gate"** notes whose durable evidence lives in
   `spikes/` (e.g. "X proved feasible", "the gate is cleared") — the ledger
   records *choices*, not experiment outcomes; the spike is the durable record.

Everything else stays: an active decision is never reworded or deleted, only
superseded.

## Format

Heading carries the **date and UTC time** (`HH:MM UTC`) so same-day entries order
unambiguously and supersession is precise. (Entries before 2026-06-23 13:39 UTC predate
this rule and carry the date only — left as-is, never reworded.)

```
## YYYY-MM-DD HH:MM UTC — <short title>

**Decision:** what was chosen.
**Context:** the question/forces that prompted it.
**Rejected:** the alternatives considered and why each lost.
**Refs:** spec/spike/code that elaborates (may be ephemeral).
```

---

<!-- entries below -->

## 2026-06-21 — Container filesystem isolation (drop the `/repo` mount)

**Decision:** No container ever gets a broad read-write `/repo` bind mount. Three
domains instead: (1) **substrate baked into the image** (`UED22/`, `entrypoint.sh`,
`wine_ctl.py` → `/opt/uned/...`); (2) **content via narrow read-only mounts** —
`DeusExAssets/ → /deusex:ro` and the repo-authored content trees → `/content/...:ro`;
(3) **mutable exchange via `docker cp` into a container-local `/work` dir** that dies
with the container. `packages._remap_to_container` maps a host-resolved package file
onto its container-visible root; `ensure_load` always `OBJ LOAD`s (only
`_ALWAYS_LOADED` Engine/Core/Editor skipped). `xfer.py` is the sole owner of `/work`
path generation and the `docker cp` boundary (uuid-suffixed paths). Apply's result
crosses back by `MAP SAVE` to `/work` → H3 verify in the editor container → `cp_out`
to host `.uedcli/tmp/` → atomic `os.replace` onto the target (EXDEV fallback for an
out-of-repo target).

**Context:** The old `/repo` mount let every container write anywhere in the tracked
tree. We point-fixed individual seams toward `_scratch/` repeatedly, but the
*capability* remained, so the next forgotten seam re-polluted the tree; UnrealEd's
frequent crashes also stranded `MAP SAVE`/swap temps (`.uedcli-tmp.dx`) in `Maps/`
that `finally` cleanup couldn't be trusted to remove. Goal: make repo pollution
structurally impossible, not a convention to remember.

**Rejected:**
- *Keep the `/repo` mount, keep redirecting writes to `_scratch/`* — leaves the
  write *capability* intact; the next seam silently re-pollutes. The whole point was
  to remove the capability.
- *Cross content packages by per-package `cp_in` into a `/work/pkgs` four-way split*
  (the original proposal's content-resolution scheme) — rejected for D4's read-only
  `/content`+`/deusex` mounts: reuses the existing host-path-remap path with near-zero
  change, no per-spin-up copy, and stays read-only so containers still never write the
  repo.
- *A tmpfs `/work`* — `docker cp` writes the file UNDER the tmpfs mountpoint on the
  overlay where it is shadowed and invisible to a live `exec` (verified 2026-06-21);
  `/work` is a plain entrypoint-created overlay dir instead.

**Refs:** the (now-deleted) ephemeral spec
`specs/2026-06-21-uedcli-container-fs-isolation-design.md` and its plan; the durable
mechanism now lives in `architecture.md` ("Container filesystem isolation",
"Substrate") and `unrealed/quirks.md` ("Containers / package resolution").

## 2026-06-21 — Deus Ex package "stubbing" (v68→v69 round-trip, integrated into uedcli)

**Decision:** uedcli gains an on-demand pipeline that converts a level's Deus Ex `.u`
**code** dependencies (Unreal package version 68, from the user's gitignored install)
into UED22-loadable **version-69 "stub" packages**, preserving mesh/texture assets, and
runs it **lazily at the package-resolution stage** for any code package not already v69
(committed substrate or built cache), printing a stdout notice and caching results under
`<repo>/.uedcli/cache/stubs/` (gitignored — copyright-derived). The round-trip is:
`UED22/UCC.exe batchexport class uc` + `batchexport texture pcx` (decompile) → `umodel`
(VertMesh `.3d` + authoritative `MESHMAP SCALE`) → rewrite `#exec` import dirs + rename
group-prefixed PCX → `UED22/UCC.exe make` → v69 `.u`. Replaces the hacky
`Tools/recompile_for_ued2` + `Tools/unrclsprs/main.py`.

**Context:** LUM mission maps, the retail cinematics, `20_Lenz`, and any map pulling a
not-yet-stubbed code package can't materialize because UED22 (UT-lineage, v69-only) can't
load v68 Deus Ex code. The user wanted a mesh-preserving, automatic stubber for any v68
code dep. A live spike validated every leg
(`spikes/2026-06-21-deusex-package-stubbing-roundtrip.md`).

**Decisions made (choice → rejected):**
- *Decompiler = the committed UED22 v469 UCC*, NOT the v68 Deus Ex SDK `UCC.exe`. Rejected
  the SDK UCC (the prototype's apparent `$system/UCC.exe`): the v68 toolset has **no export
  commandlet** — `batchexport` is a UT-era `Editor.u` commandlet that Deus Ex predates; the
  v469 UCC reads v68 packages and exports their source by name. Rejected the v68
  `UnrealEd.exe` "Export All" (GUI-only, needs a display, fragile). Getting the free DeusEx
  SDK (user's instruction) still paid off — it proved the v68 toolset lacks an exporter.
- *Decompile requires the full dependency closure loadable* — code deps as v69
  (substrate/cache, recurse to bottom out on the committed substrate), content deps
  (`.utx`) on `[Core.System] Paths`. ("Effects" is `Effects.utx`, content, not code.)
- *Trigger = lazy at the closure-resolution stage*, before any editor lock — NOT in
  `packages.ensure_load` (runs later, inside the lock, on an already-resolved manifest, with
  v68 excluded from its search dirs). With a per-build stdout notice (user). Rejected
  explicit-verb-only (not "automatic") and a separate pre-flight step.
- *v68 inputs via a separate `install_system_root()` (`DeusExAssets/System`), kept OUT of
  `substrate_search_dirs`* — so the normal load path never tries to `OBJ LOAD` v68 `.u` (the
  incompatibility the substrate split exists to prevent).
- *Pipeline = raw offline `docker exec UCC` in an ephemeral build container* (like
  `store_export.py`), NOT via `Driver`/editor-lock/the standing substrate container.
- *Cache = `<repo>/.uedcli/cache/stubs/`* (user), keyed by v68 `source_sha` + dep stub shas
  + substrate id + toolchain id (so a rebuilt dep / re-stripped substrate / toolchain bump
  invalidates dependents). Rejected writing into the committed `UED22` (mixes generated +
  committed, risks committing copyright).
- *umodel delivered by bind-mount into the build container* (it lives outside the `uned/`
  Docker build context). Rejected baking it (needs moving umodel into the context; deferred).
- *Stripped-symbol decompile failures fail loudly* (e.g. `Extension` →
  `Engine.PlayerPawn.PostRenderFlash`); never emit a broken stub. Un-stripping engine symbols
  and first-party `LUM_Core.u` (compiled from repo source, not decompiled) are out of scope.

**Refs:** `specs/2026-06-21-uedcli-package-stubbing-design.md` (ephemeral) and its grounding
spike `spikes/2026-06-21-deusex-package-stubbing-roundtrip.md` (durable). The replaced
prototype: `Tools/recompile_for_ued2`, `Tools/unrclsprs/main.py`.

## 2026-06-22 — Package stubbing: body-stripping, temp-name, shallow closure (refines 2026-06-21)

Refines the 2026-06-21 stubbing entry above (does not reverse it — the decompiler choice stands
and was re-verified, see below).

**Decision:**
- *The stub is made by **stripping every function/state/replication body***, keeping only the
  class declaration + `#exec`s + enums + structs + variables + `defaultproperties` (the
  prototype's `render_stub`). This erasure — not the `#exec` rewrite — is what lets the v69 UCC
  link the class against UT's DLLs; the decompiled bodies call DeusEx natives UT can't resolve.
- *`make` builds under a **throwaway temp package name**, then renames the output to `<P>.u`*
  (the prototype's `temp_package_for_ued2` indirection). The class names inside stay real; only
  the package wrapper is temporary.
- *The closure resolves **direct deps only** (one hop); **no recursion into a dependency's
  dependencies***. It bottoms out on the committed v69 substrate. The one case that could force
  going deeper — a stubbed dep whose `defaultproperties`/mesh references an asset in another
  package — is **flagged at processing and deferred**, not chased.

**Context:** Andrzej's directives while fixing the spec's review findings — "throwaway temporary
package is a good thing" and "we do not need a dependency's dependencies … unless [a recompiled
dep references a sound/texture/mesh from another package], we should be able to flag this … not
sure if we need to handle that edge case now." Plus a review finding (C1) that the spec described
only the `#exec` rewrite and omitted the body-stripping that is the stub's whole point.

**Rejected:**
- *Compiling `make` directly under the real package name `P`* — the spike validated `make` only
  under a fresh, non-colliding name (`StubMesh`); under the real name it can collide with a
  resident `P` (the v68 original on `Paths`, or `P`'s own committed v69 under `--force`) and
  no-op or bind to the wrong package. Note: rename-then-load-as-`<P>` is itself not yet
  spike-verified — flagged as a phase-2 gate.
- *A deep transitive stub-the-deps-of-deps engine with topo sort + cycle detection* (the prior
  draft) — over-built for a closure that bottoms out on the substrate; the user ruled it out. A
  must-stub dep that itself needs an only-v68 dep is surfaced as a named hard error, not chased.
- *Auto-resolving cross-package asset references now* — deferred per the user; flagged, build
  proceeds.

**Decompiler re-verified (challenged 2026-06-22, decision unchanged):** Andrzej pushed back that
the SDK was required and UED22 UCC would fail. A fresh fetch of `DeusExSDK1112f.exe`
(`sha256 a54e166…`) confirmed it ships no `batchexport` (no `Editor.u`); a live run confirmed
UED22 UCC *does* export v68 **classes** + **textures** (proven by hiding the v69 substrate copy
to force a genuine `Ver: 68` load) but has **no mesh exporter** at all
(`No 3d exporter found for LodMesh`), so meshes come from umodel — the existing design. This
strengthens, not reverses, the 2026-06-21 decompiler choice.

**Refs:** same spec + spike as the 2026-06-21 entry (spike has the 2026-06-22 live additions);
`uned/deusex-assets-setup.md` for the SDK/installer extraction.

## 2026-06-22 — noVNC viewport drag: an x11vnc `-pipeinput` abs→rel bridge

**Decision:** Make an in-browser RMB-drag rotate the UnrealEd viewport sanely by routing
interactive VNC pointer input through an external abs→rel bridge (`uned/vnc_input_bridge.py`)
declared as x11vnc's `-pipeinput` command (only when not view-only; baked into the image,
wired in `entrypoint.sh`). x11vnc stops injecting input itself under `-pipeinput`; the bridge
re-injects via one long-lived `xdotool -`: RELATIVE motion (`mousemove_relative`) while a button
is held (so the editor's per-frame cursor-warp reads the clean intended delta), ABSOLUTE motion
(`mousemove x y`) on hover and on every button-state change (so clicks land and the cursor
re-syncs after a warp). Press/release ordering is load-bearing — an absolute reposition while a
button is held injects a phantom drag delta, so position-before-press only from idle and
resync-after-release only once nothing is held.

**Context:** UnrealEd warps the captured cursor to a fixed anchor every frame during a viewport
drag and derives the camera delta as `commanded_abs − anchor`; RFB carries only absolute
positions, so a browser drag is measured against the far anchor → unbounded over-rotation (a
150 px drag slams pitch to the 90° clamp). The 2026-06-18 findings had concluded this was
unfixable at the VNC layer — but that only considered an x11vnc *flag* for abs→rel and never
tried `-pipeinput`, which lets an external program do the conversion RFB can't express.

**Rejected:**
- *"No fix; treat noVNC as view/inspect-only for rotation"* (the 2026-06-18 conclusion) —
  overturned; `-pipeinput` is the clean lever. The user explicitly wanted the client usable.
- *`-pipeinput UINPUT`* (x11vnc's built-in relative-injection mode) — needs the Linux `uinput`
  evdev device, unavailable under Xvfb (no evdev); the `uned-docker-driver` memory note already
  records XTEST, not synthetic/uinput events, as the working path.
- *`-viewonly -pipeinput bridge`* (let viewonly suppress x11vnc injection, bridge injects) —
  works, but then EVERY event is flagged viewonly-discarded (negative client#), forcing the
  bridge to inject events it should drop; bare `-pipeinput` already makes x11vnc sole-non-injector
  (verified: `-pipeinput cat` moves nothing), so viewonly is unnecessary and muddier.
- *Per-event `xdotool` spawns* — too slow for a drag's dozens of events/sec; one persistent
  `xdotool -` executes lines in order (button/motion ordering preserved without `--sync`).

**Accepted caveat:** a button-held drag over a non-viewport widget that expects absolute tracking
(a scrollbar/slider in a browser pane) gets relative motion too and misbehaves — acceptable since
noVNC is a navigation/inspect aid and the editor is driven by the console.

**Refs:** `specs/2026-06-18-uedcli-viewport-drag-sensitivity-findings.md` ("The VNC fix" section,
with the live A/B measurements and the captured pipeinput line format); `uned/vnc_input_bridge.py`;
`uedcli/tests/test_vnc_input_bridge.py` (guards the press/release ordering regression).

## 2026-06-22 — Full `texture` tool: an offline, hash-versioned texture catalog

**Decision:** Build the texture tool as a **session-free, fully offline** catalog over the
substrate's packages — the live editor is never touched. Verbs: `texture sync` (discover every
package on the substrate path, UCC-batchexport its textures to PNG under gitignored
`.uedcli/textures/<package>/`, and build/refresh a **tracked** per-package manifest
`texture-catalog/<package>.json`), `texture list`/`search`/`tags` (offline manifest reads),
`texture classify status`/`set` (record LLM/human metadata). Manifest entry = objective fields
auto-filled by `sync` (`ref` as 2-part `Package.Name`, `image`, WxH, `format`, `image_hash`,
auto-extracted dominant `colors`) + classification (`tags[]`, `description`) + state (`stale`,
`removed`); `classified` is derived. `sync` gates re-export on the **raw `.u` file sha256**
(`package_hash`) and per-texture `image_hash`: changed image → keep classification, mark `stale`;
new → empty entry; gone → mark `removed` (classification never silently lost). `classify set`
replaces each provided field and clears `stale`. `search` ranks over name+tags+description with
exact `--tag`/`--colors`/`--package` filters and prints refs for piping into `poly set --texture`;
`texture tags` lists the tag vocabulary to curb drift. Color extraction is **host-side (Pillow)**.

**Context:** `poly set --texture` exists but there's no way to discover textures, see them, or
record what they are. `texture export` (2026-06-21) dumped one package's images with no index or
metadata. Andrzej specced this arc end-to-end on 2026-06-22.

**Rejected:**
- *Fixed `material`/`surface`/`usage` taxonomy* — open `tags[]` + `description` subsume those
  facets with zero schema commitment; a taxonomy is guessing which facets matter and forces a
  `misc` escape hatch. Faceted precision is recoverable later without migration (promote a hot tag
  to a facet); `texture tags` exposes the vocabulary to curb drift. Andrzej chose tags+description.
- *Live `OBJ LIST CLASS=Texture` to build the manifest* — yields fully-qualified
  `Package.Group.Name` but needs the crash-prone editor and isn't offline; 2-part refs already
  bind, so the group is droppable. Manifest is built offline from batchexport instead.
- *`EditPackages` ini / uedcli's session `main/packages` as the discovery source* — the catalog is
  substrate-wide, not session-scoped; Andrzej chose to enumerate **all packages on the substrate
  path** (broadest, substrate-correct).
- *`dxpkg` parse for change detection* — rejects the version-61 packages; a raw `.u` file hash is
  format-agnostic and works for all.
- *Everything under gitignored `.uedcli/`* — classification is expensive LLM/human work and must
  survive a clean, so metadata is **tracked** (`texture-catalog/`) while only the regenerable
  images are gitignored. Combined single `textures.json` rejected for noisy whole-file diffs;
  per-package files give small, hash-scoped diffs.
- *Catalog under `Tools/uedcli/`* — ties DeusEx-specific data into the portable tool tree; rooted
  at the repo level instead, path configurable.
- *`annotate` alias / additive `--add-tag`/`--remove-tag`* — Andrzej first liked `annotate`, then
  settled on `classify set` replacing provided fields, **no alias**. Reinstatable trivially.
- *In-container ImageMagick `convert` histogram for colors* — host-side Pillow chosen so color
  logic is unit-testable host-side with the rest of `sync`.
- *Keeping `texture export` as a one-off* — dropped; `sync --package P` supersedes it (export +
  manifest in one).
- *Dockerized web viewer + `texture view` in this spec* — deferred to a follow-on spec reading the
  same catalog; `view` is the viewer's entry point and ships with it.

**Refs:** `specs/2026-06-22-uedcli-texture-tool-design.md`;
`specs/2026-06-19-uedcli-surface-flags-texturing-design.md` (the `poly set --texture` consumer +
2-part-ref binding); `uedcli/texture.py` (the batchexport primitive `sync` reuses).

## 2026-06-22 — Texture catalog: review-driven refinements (extends the entry above)

Folds in decisions made fixing two cold spec reviews of
`specs/2026-06-22-uedcli-texture-tool-design.md`. Does not reverse the entry above.

**Decision:**
- *`sync` operates on the **resolved package file with its real extension**, never an assumed
  `.u`.* Texture packages are `.utx` content files; the old `texture export` primitive hardcoded
  `f"{package}.u"` and would have cataloged almost nothing. `sync` adds
  `packages.enumerate_substrate_packages` (the sweep `packages.py` lacked — it only *resolved*
  caller-supplied names) and hashes/batchexports the actual file.
- *`image_hash` is over **decoded pixels** (Pillow `tobytes()` + dims/mode), not the PNG file
  bytes.* PNG re-encoding isn't byte-deterministic, so hashing the file would mark every texture
  `stale` on every re-export and churn the tracked manifest.
- *Decode is **host-side via Pillow**, dropping the in-container ImageMagick `convert`.* `sync`
  `cp_out`s the raw PCX and Pillow produces the viewable PNG + hash + dims + colors — testable
  host-side and free of encoder nondeterminism. (Refines the earlier "host-side Pillow for colors"
  into "host-side Pillow for the whole decode".)
- *`image_hash` is the durable identity that **carries classification across a rename*** — a new
  texture name whose pixels match a removed/absent entry inherits its tags/description (as `stale`).
- *The `stale`/`removed`/`classified`/`unclassified` buckets are a **partition** by precedence
  removed > stale > classified > unclassified; setting `removed` clears `stale`; `removed` entries
  are excluded from the `classify status --full` worklist; `classify set` **rejects** a `removed`
  texture (you can't classify what's gone).*
- *The image path is **derived by convention, not stored** in the tracked manifest* (a stored
  gitignored path would dangle); consumers check existence and error "run `texture sync`".
- *`search` ranking is a **fixed tiered score** (exact name > exact tag > name-substr > tag-substr
  > description-substr; multi-term AND; ties by ref); `--color` filters by **RGB distance ≤ 48**,
  not exact hex (exact would never hit an auto palette); tags are **case-folded + de-duped on
  write*** to curb drift.
- *Catalog writes are **atomic** (temp + `os.replace`) under a **per-package `flock`*** — the repo
  runs N parallel agents (D5/D7), and a truncated tracked manifest would lose classification.

**Rejected:**
- *Reuse the `texture export` primitive as-is* — its `.u` hardcode is the central data-source bug;
  it had to be refactored, not reused.
- *Hash the exported PNG bytes* — encoder-nondeterministic → mass false `stale`.
- *Keep ImageMagick `convert` in the texture path* — host-side Pillow does decode+hash+color+PNG in
  one deterministic, testable place.
- *Store the image path in the manifest* — dangles against the gitignored image tree; derived
  instead.
- *Exact-hex `--color` match* — an auto dominant palette almost never equals an arbitrary query
  hex; nearest-within-threshold is the usable contract.
- *Naive read-modify-write JSON* — races N concurrent agents; atomic replace + per-package flock.

**Refs:** `specs/2026-06-22-uedcli-texture-tool-design.md` (revised 2026-06-22, "Spikes"/"Concerns"
carry the residual unknowns); `uedcli/packages.py` (`_PKG_EXTS`, `_first_match`, the new
`enumerate_substrate_packages`); `uedcli/texture.py` (the refactored primitive).

## 2026-06-22 — Bake UED22 directly to `/opt/UED22`, drop the boot-time assembly

**Decision:** Bake the committed UED22 substrate straight to its final runtime location
`/opt/UED22` in the `Dockerfile` (`COPY UED22/ /opt/UED22/`) and delete `entrypoint.sh`'s
boot-time symlink-farm assembly (`UED_STUB_DIR`/`UED_DIR`/`SRC_DIR`, the `rm -rf`+`mkdir`, the
symlink-binaries/copy-inis `for` loop). The editor runs straight from the baked dir; its writes
(`Editor.log`, `Running.ini`, `make` output) land on the per-container COW overlay. The
entrypoint keeps only the DX-assets `Paths=` wiring (now hoisted to run UNCONDITIONALLY — a
no-GUI build/UCC container needs content `Paths` too) and unconditional log truncation
(`: > Editor.log`; reset `Running.ini`) so each boot starts clean without the deleted `rm -rf`.
The GUI launch stays gated on `LAUNCH_UED==1` (UED_EXE guard + `wine unrealed.exe -log` +
PID record + `wmctrl` maximize) so a no-GUI container never aborts on a missing `unrealed.exe`.
The scripts stay baked at `/opt/uned/`.

**Context:** The assembly never *built* anything — it made a writable working copy "so the editor
never writes back into the baked source." That rationale is vestigial from the old read-write
`/repo` mount era, where editor writes into its dir polluted the tracked tree. Post-D4
(container-fs isolation) there is no `/repo` mount; the baked dir is exposed via a per-container
COW overlay, so editor writes are already ephemeral. The Python side already treats `/opt/UED22`
as canonical (`packages._BAKED_UED22`/`_EDITOR_INI`, `driver.py`/`store_export.py`/`texture.py`);
only the `Dockerfile` COPY and the entrypoint assembly still referenced the source path
`/opt/uned/UED22`. The container runs as root (no `USER` directive), so root-`COPY`'d inis are
writable at runtime.

**Rejected:**
- *Keep the symlink-farm assembly* — pure overhead post-D4: it re-derives at every boot a
  writable copy that the COW overlay already provides for free, and references a now-redundant
  second source path.
- *Accept losing the per-boot `rm -rf` clean slate silently* — mitigated instead by unconditional
  log truncation on every boot, and `docker compose up -d --force-recreate` remains the documented
  full reset. A long-lived standing container's overlay keeps `make`/scratch output across mere
  restarts, but ephemeral build/session containers are unaffected.

**Refs:** the (ephemeral) plan `plans/2026-06-22-uedcli-direct-bake-ued22-plan.md`. Supersedes
the boot-time assembly described in the 2026-06-21 container-fs-isolation entry above (the three
domains stand; only the substrate's "assembled at boot" detail changes). Retires the round-11
`entrypoint.sh` hoist in `specs/2026-06-21-uedcli-package-stubbing-design.md` (a direct bake makes
`/opt/UED22/UCC.exe` + a writable ini exist unconditionally, GUI or not).

## 2026-06-22 — Texture catalog: a fixed named-color palette (supersedes the hex color bits)

Supersedes the color specifics in the two 2026-06-22 texture entries above (the auto dominant-
palette-as-hex and the `--color` RGB-distance-≤48 filter). The rest of those entries stands.

**Decision:** `colors` is a **fixed controlled vocabulary of 12 names** — `black white grey red
orange yellow green blue purple pink brown tan` — each with a reference RGB, defined as one module
constant in `texture_catalog.py` (the single source for derivation, validation, and search). `sync`
still **auto-derives** them host-side (Pillow): quantize the image, snap each weighted swatch to the
nearest palette name, keep the **top 3 distinct names by dominance**. `classify set --colors` takes
**palette names** (validated; unknown → error listing the valid set, the `poly set` flag-name
discipline) and overrides the derived list. `search --color NAME` is an **exact** palette-name match
(repeatable, OR; no threshold).

**Context:** Andrzej, refining the spec: "just have some basic named colors, limited to maybe a
dozen." Hex palettes + a fuzzy RGB-distance search filter were more machinery than the use case
(an LLM/human discovering "the brown wall texture") needs, and arbitrary hex is the wrong grain for
a discovery facet.

**Rejected:**
- *Auto dominant palette stored as hex + `--color HEX` nearest-within-RGB-distance-48* (the prior
  texture entries) — superseded; a closed named set is simpler to search (exact match), validate,
  and reason about, and colors are genuinely a closed vocabulary (the one place a fixed taxonomy
  fits, unlike the open `tags`).
- *Human/LLM-set colors only (no auto-derivation)* — Andrzej kept the free first-pass; `sync`
  snaps to names so the facet is populated from the first sync, still overridable.
- *A larger palette (add silver/gold)* or *a smaller ~8-name set* — 12 names, cap 3, chosen as the
  balance (silver/gold blur into grey/yellow; dropping pink/purple/tan loses real distinctions).

**Refs:** `specs/2026-06-22-uedcli-texture-tool-design.md` ("Named-color derivation");
`texture_catalog.py` (the palette constant).

## 2026-06-22 — Texture catalog: round-2 review fixes (stem identity, color provenance)

Extends the three 2026-06-22 texture entries above after a second pair of cold spec reviews. No
reversals; these resolve gaps the round-1 spec left.

**Decision:**
- *Manifest entries are keyed by the **PCX stem** (`Group.Name`, or bare `Name`), not the bare
  texture name.* `UCC batchexport … Texture pcx` writes **group-prefixed** filenames
  (`Skins.Wood.pcx`, evidenced on 185 PCX in
  `spikes/2026-06-21-deusex-package-stubbing-roundtrip.md`). `name` = the last component, `group` =
  the prefix. The user-facing `ref` stays **2-part `Package.Name`**, except a genuine intra-package
  **cross-group same-`Name` collision** (two stems → one 2-part ref) emits the **3-part
  `Package.Group.Name`** for both, so the catalog never hands `poly set` an ambiguous ref. The
  derived PNG path keys on the stem too.
- *`colors` carries a `colors_source` ("auto" | "set"); `classify set --colors` sets it to "set",
  after which `sync` never re-derives colors for that entry* — the same "don't clobber human work"
  guarantee `tags`/`description` already had (a round-1 hole: colors were "objective auto-filled",
  so a re-`sync` would overwrite a curated override).
- *`image_hash` is over `convert("RGB").tobytes()` + dims*, not the paletted `tobytes()` (which
  would miss a palette-only recolor) and not PNG file bytes. `format` is **dropped** from the
  manifest (every PCX decodes to the same paletted mode — a constant carrying nothing).
- *Color derivation is a deterministic NEAREST-resample histogram*, not `quantize`/median-cut
  (whose output isn't stable across Pillow versions): RGB → resize 64×64 NEAREST → snap each pixel
  to the nearest of the 12 names → keep names ≥12% share, cap 3. Pillow is pinned to a version floor
  so the decode can't drift under the golden test. Documented as a coarse browse aid (off-palette
  hues / near-greys / sub-threshold accents are lossy; `--colors` overrides).
- *Reconcile is a single deterministic pass over sorted stems; each prior entry's classification is
  inherited by **at most one** successor* (so a rename plus an old-name-reuse in one sync can't both
  claim it).
- *`search`'s positional `<query>` is **optional*** — `search --color grey --tag metal` lists every
  matching ref, so color/tag discovery works on a fully-unclassified catalog (a bare `search` with
  no query/filter is a no-op error).
- *`sync` `os.makedirs(exist_ok=True)` the catalog dir and the `.uedcli/locks/` dir before any
  `flock`* (first-run race safety); the lock is intra-clean best-effort. `sync` takes the standard
  `--container` and a `--catalog-dir`/`UEDCLI_TEXTURE_CATALOG`; the image root is fixed under
  `.uedcli/textures/` (not configurable — gitignored/regenerable).

**Rejected:**
- *Key by bare name + raise on same-name collision* — group-prefixed files mean the collision can't
  even occur at the file level, and raising would lose textures; stem-keying keeps both, 3-part ref
  disambiguates.
- *Keep `colors` as a pure objective field* — re-`sync` would clobber human overrides; provenance
  flag fixes it.
- *Hash paletted indices or PNG bytes* — misses palette recolors / churns on encoder noise; RGB
  decode is the faithful, stable identity.
- *`quantize(MEDIANCUT)` for colors* — not version-stable, breaks the "deterministic golden test"
  claim; NEAREST-resample histogram + pinned Pillow floor instead.
- *Mandatory `search` query* — leaves color-only discovery on an unclassified catalog with no
  runnable command.

**Refs:** `specs/2026-06-22-uedcli-texture-tool-design.md` (revised; "Texture identity", "Named-color
derivation", "Spikes"); `spikes/2026-06-21-deusex-package-stubbing-roundtrip.md` (the group-prefixed
filename evidence).

## 2026-06-23 — Drop `level apply --reapply` and `--continue`

**Decision:** Remove both flags from `level apply`. The session remains terminal-and-stop, but
the two needs that terminality created are now served by existing primitives instead of bespoke
flags:
- **Continue after an apply** → `session start <the-resulting-.dx>` (or, once new-level
  authoring lands, the resulting T3D tree) to mint a fresh successor session, exactly as
  `--continue` did internally. No flag needed.
- **Recover a lost/clobbered `.dx`** → restore it from `backups/<level>/<sid>-<apply-uuid>.dx`
  and run `level apply` again. The backup is already written before every apply; recovery is a
  file restore plus a normal apply, not a special re-materialize path.

`run_apply` loses its `reapply` param and the `_reapply` function; `_level_apply` loses the
`--continue` successor-seeding block (the shared `_seed_session_from_dx` helper stays — `session
start <dx>` still uses it). The terminal guard message now points at these two recovery routes.

**Context:** Reviewing the flags during the new-level-authoring (`apply --out`) spec. Both were
extra surface area that duplicated what `session start` + the backup already do. `--reapply`'s
original reason — the store can't rebuild a binary `.dx`, so a lost artifact needed a stored-
result re-materialize — is weaker now: the backup covers a lost `.dx`, and the planned T3D-tree
trunk would make the authored level recoverable straight from git. Andrzej: lighting/geometry-
rebuild loss on a re-apply is explicitly a non-concern (lightmaps/BSP are regenerable build
output, not authored state).

**Rejected:**
- *Keep `--reapply` for artifact recovery* — the per-apply backup already makes recovery a
  restore-then-apply; a dedicated deterministic re-materialize verb earns its complexity only if
  the backup were unavailable, which it isn't.
- *Keep `--continue` as a convenience* — `session start <resulting-.dx>` is one command and is
  the honest model (a new work unit off the new trunk state), without a flag that silently mints
  and binds a session as a side effect of apply.

**Refs:** removed `apply._reapply` + the `run_apply(reapply=…)` param + `_level_apply`'s
`--continue` block; `architecture.md` `level apply` bullet (recovery/continue routes).

## 2026-06-23 — New-level authoring: `level apply --out`, dual-mode target, name guards

**Decision:** Add `level apply --out <path>` to write an (unbound, from-scratch) session's
authored level onto a destination, and generalize the apply target to **either a `.dx` OR a
T3D tree** (the `{actors/, order, packages}` directory shape, here named the "**T3D tree**").

- *Verb = a `--out` flag on `apply`*, NOT a `session rebind` verb. `--out` is **ephemeral**:
  recorded in the apply event's `target`, but does NOT update `latest_open()` (the session's
  binding is unchanged). Continue after apply by `session start`ing the result.
- *Mode auto-detected by path shape:* ends in `.dx` and is a file or absent → binary mode
  (materialize → MAP SAVE → H3 verify → atomic swap, parent dir auto-created); ends in `.dx`
  but is a directory → error; anything else → T3D-tree mode (no editor: 3-way merge → write the
  tree → `git add` + squash commit `Apply session <id> (<N> commands)`). Info-log when the
  target doesn't exist yet.
- *T3D-tree pre-flight:* must be inside a git repo (override `--allow-outside-git`); must have
  NO uncommitted changes in the target path (NO override — unrecoverable once clobbered). The
  granular per-command history stays in `.uedcli/store/`; the trunk commit is a squash carrying
  the session id.
- *Lighting/geometry-rebuild loss is explicitly a non-concern* (Andrzej) — lightmaps/BSP are
  regenerable build output, not authored state; T3D-tree mode produces no `.dx` at all.
- *Level name = an optional recorded apply identity, kept VERBATIM with extension* (Andrzej
  reversed an earlier "strip the extension"). Derived from the path at `session start`
  (`AireGardens.dx`); a from-scratch session has none. A T3D tree stores its own `name` file
  (intrinsic identity, independent of the dir it sits in); a `.dx`'s name is its filename. A
  first-write names the new target from the `--out` basename. Not separately settable (no
  `--name` flag) — from-scratch sessions are for creating levels; editing an existing one is
  reached by `session start`ing it.
- *Two anti-clobber guards:* **A (name-presence)** — a nameless (from-scratch) session may only
  first-write a NEW target, never write onto an existing `.dx`/tree. **B (name-match)** — a
  named session applying onto an existing target whose recorded name differs → error, override
  `--allow-name-mismatch`.

**Context:** `session start` with no `.dx` already mints an unbound authoring session, but
`apply` had no way to write it out. Specced 2026-06-23; direction first noted 2026-06-20
(board/to-spec.md). Andrzej also raised retaining ALL historic session history in a git-committed T3D
trunk — captured as future direction, out of scope here.

**Rejected:**
- *A `session rebind <file>` verb* (the alternative to a `--out` flag) — a flag on `apply` keeps
  the single-writer model and avoids a second target-mutating verb. (`session rebind` infra
  was already partly present — `EVENT_VERBS`/`latest_open` accept it — but unneeded.)
- *Commit-by-commit replay of the session log into the trunk* (granular history in `git log`) —
  replaying onto a diverged base needs per-step conflict resolution with no good non-interactive
  answer; Andrzej chose a squash with the session id (history findable in `.uedcli/store/`, not
  inline). "A" in the A/B framing.
- *Stripping the extension from the recorded level name + making the name mandatory + requiring
  `session start` from scratch to supply one* — Andrzej proposed then reversed all three: keep
  the extension, name optional, no from-scratch name required. The anti-clobber protection moved
  from a mandatory-name-match to guard A (nameless → first-write only).
- *Allowing `--continue`/`--reapply`-style flows here* — both flags were removed the same day
  (see the 2026-06-23 removal entry); continue = `session start` the result, recover = restore
  from `backups/` and re-apply.

**Refs:** `specs/2026-06-23-uedcli-new-level-authoring-design.md` (ephemeral); folds into
`architecture.md` (`level apply`, the session store tree shape) on implementation.

## 2026-06-23 — New-level authoring: uniform state-tree format + explicit commit choice (extends above)

Extends the 2026-06-23 new-level-authoring entry after Andrzej reviewed the spec. No
reversals of that entry's other points.

**Decision:**
- *`base/`, `main/`, and an externally written T3D tree have the EXACT same format* —
  `{actors/<name>.t3d, order, packages, name}`. The `name` file (the optional level-name
  identity, verbatim with extension) becomes a uniform member of the state-tree format
  carried by `write_state_tree`/`read_state_tree`, not an external-tree-only artifact. The
  session's current name is `main/name`; a written tree is re-readable by the same
  `read_state_tree` and can directly seed a session. `name` is metadata like `packages` —
  excluded from `canonical_level_hash` (actors+order only).
- *T3D-tree mode REQUIRES an explicit `--commit` or `--no-commit`* (mutually exclusive, no
  default). `--commit` writes the tree atomically (staging dir → move) then `git commit --
  <path>` (pathspec-scoped for the N-agent shared index); `--no-commit` writes the tree and
  leaves it uncommitted for the user. Both run the git repo + dirty pre-flight (the
  dirty-check protects existing work regardless of who commits); the store `apply` event +
  snapshots are recorded for both (the apply happened; session terminal either way).

**Context:** Andrzej's two directives on spec review: "main, base and the externally written
t3d tree must have the exact same format" and "require explicit --commit OR --no-commit."

**Rejected:**
- *`name` as an external-tree-only file with `base`/`main` keeping a 3-file shape* (the
  spec's first cut) — Andrzej wants one uniform format across all three, so a written tree
  IS a valid session seed with no special-casing.
- *A default commit behaviour (always-commit, or commit-if-in-repo)* — the choice to land a
  trunk commit on the user's current branch is consequential enough to always be explicit.

**Open (flagged for Andrzej):** whether `.dx` mode (a binary swap, tracked content in
`Maps/`) should also gain/require the commit choice, or stay swap-only. Spec assumes
swap-only for `.dx`.

**Refs:** `specs/2026-06-23-uedcli-new-level-authoring-design.md` (revised).

## 2026-06-23 — New-level authoring: drop the bound target, `name` is the sole identity (extends above)

Extends the two 2026-06-23 new-level-authoring entries. The dual-mode target, guards A/B,
atomic write, and pre-flight all stand; this changes target *resolution*.

**Decision:**
- *`level apply` always requires `--out <path>`* — there is no implicit bound target and no
  `latest_open()`-based target resolution. The common "`session start <foo.dx>` → edit →
  apply back" flow now passes `--out <foo.dx>` every time (accepted; the level-name guard
  keeps it safe).
- *The `open`/`rebind` event drops its `dx_path`/`container` metadata* — `open` survives only
  as the seed/lifecycle marker (records the seed `level_hash`); `rebind` is gone (it only
  existed to change a bound target). `latest_open()` is no longer consulted for a target.
- *`name` (the state-tree `name` file, in `base`/`main`/written-tree alike) replaces that
  metadata* as the session's only durable identity, used purely by the apply guards.
- *Flags renamed `--git-commit` / `--no-git-commit`* (from `--commit`/`--no-commit`) — explicit
  that the action is a git commit.

**Context:** Andrzej's directives on the second spec review: "--git-commit or --no-git-commit"
and "ditch open/rebind meta - name replaces that." On the follow-up disambiguation he chose
"name = identity only; --out always required" over "name = the target path (defaults --out)"
and over keeping a separate bound path.

**Rejected:**
- *`name` holds the target path and defaults `--out`* (preserves the no-`--out` convenience) —
  Andrzej chose identity-only; `name` is a basename-style identity for the guards, not a
  locator, and the destination is always explicit.
- *Keep a separate optional bound path alongside `name`* — explicitly the "meta" being ditched;
  one identity field only.

**Refs:** `specs/2026-06-23-uedcli-new-level-authoring-design.md` (revised).

## 2026-06-23 — New-level authoring: explicit `--to-map-file`/`--to-t3d-tree` mode flags

Extends the 2026-06-23 new-level-authoring entries. Replaces the path-shape auto-detection.

**Decision:** The apply output mode is selected by a **mutually-exclusive, REQUIRED** flag
pair — `--to-map-file` (binary map file) or `--to-t3d-tree` (T3D tree directory) — never
inferred from the `--out` path shape. `--to-map-file` accepts `.dx` and `.unr` map
extensions and errors on an existing directory / unknown extension; `--to-t3d-tree` errors
on an existing non-directory file. This removes the prior "fat-finger silently creates a
tree" sharp edge: a mistyped `--out` now errors on the shape mismatch instead of guessing.

**Context:** Andrzej: "we should be explicit about dx/t3d tree. Use mutually exclusive flags
--to-t3d-tree Or --to-map-file."

**Rejected:** *Auto-detect mode from the path* (`.dx`-suffix → map, else tree) — the earlier
spec cut; rejected because a path typo silently produced the wrong target kind, and the
flag-name discipline the tool already uses elsewhere makes explicit intent the norm.

**Refs:** `specs/2026-06-23-uedcli-new-level-authoring-design.md` (revised).

## 2026-06-23 — uedcli is a generic UnrealEngine-1 tool (DeusEx is a baked-in substrate, not the scope)

**Decision:** uedcli targets **all UnrealEngine 1.0 games**, with Deus Ex-specific behavior
**baked in as one substrate** rather than as the tool's identity. New/fresh code, flags,
verbs, and naming MUST avoid implying the tool is Deus Ex-only — prefer game-generic terms
(`--to-map-file`, "map file", "T3D tree") over DeusEx-specific ones. Map-file handling must
accept **`.unr`** (stock Unreal / UT) alongside **`.dx`** (Deus Ex). This is **forward-
looking guidance, not a refactoring mandate**: existing DeusEx-named code is not to be
churned now; only fresh things must adhere.

**Context:** Andrzej, while specifying the mode flags: "This tool should be generic for all
UnrealEngine 1.0 games (with some custom stuff baked in for DeusEx) and should avoid names
that suggest it's for deus ex only. It should accept `.unr` files too. Don't change things
now, but fresh things should adhere to this." Aligns with the long-standing portability goal
already noted in `board/README.md` (pick helper classes/packages per-substrate, don't hardcode
DeusEx class names).

**Rejected:** *Treating uedcli as a Deus Ex tool* — the substrate split (code vs content,
per-substrate helper classes) and the UE1-generic T3D/console-verb surface already make the
core game-agnostic; naming and new extensions should reflect that rather than re-entrench a
DeusEx-only framing.

**Refs:** `board/README.md` "Portability goal"; `architecture.md` "Substrate";
`specs/2026-06-23-uedcli-new-level-authoring-design.md` (`.unr` acceptance, generic mode
naming as the first adherence).

## 2026-06-23 — Terminology: "level" = content, "map file" = the binary artifact

**Decision:** A consistent two-term split (not one word for everything): **"level"** is the
authored content and uedcli's domain object / verb namespace (`level apply`, `Level`,
`level_hash`, "level name") — substrate-agnostic; **"map file"** is the binary on-disk
artifact only (`.dx`/`.unr`), matching the engine's `MAP SAVE`/`MAP EXPORT` verbs and the
`.unr` = "Unreal map" extension. The directory form is the **"T3D tree"**. "level" is never
used for the file; "map" is never used for the abstract content.

**Context:** Andrzej asked to keep terms consistent and which word is better. Collapsing to
one breaks something either way: "map" everywhere fights the entrenched `level apply`/`Level`
surface; "level" everywhere forces the awkward "level file" for a `.unr`. The split is the
natural fit and matches the engine's own usage (a loaded `Level` is `MAP SAVE`d to a map
file).

**Rejected:** *one term everywhere* — see above. *"map" as the domain term* — would require
renaming the existing `level` verb group and `Level` model (out of scope, and "you apply a
level" reads correctly). 

**Refs:** `specs/2026-06-23-uedcli-new-level-authoring-design.md` ("Terminology").

## 2026-06-23 — New-level authoring: four-reviewer-fleet resolutions

Resolves the design forks a four-reviewer fleet surfaced on the new-level spec. Extends the
prior 2026-06-23 new-level entries; no reversals.

**Decisions (Andrzej):**
- *Per-target serialization: add a target-path `flock`* keyed on the resolved `--out` abspath
  (reusing the `editor_lock` flock helper, fail-fast), held across read-THEIRS→merge→write —
  `editor_lock` is per-session and didn't stop two sessions racing the same target
  (last-writer-wins; the dirty-check was TOCTOU). *Lock files namespaced by type:*
  `.uedcli/locks/session/<uuid>.lock` (existing per-session lock moves here) and
  `.uedcli/locks/target/<hash>.lock` (new).
- *`--no-git-commit` recovery = the store's `apply/<uuid>/result` snapshot* (re-emit it; the
  dirty-check already guarantees the prior committed state is in git). No separate `backups/`
  copy for tree mode.
- *`--allow-name-mismatch` covers only the RENAME case* (different name, **shared ancestor**).
  Writing onto an **unrelated** level (`base ∩ THEIRS = ∅`) is refused regardless of the flag —
  splits the one override that previously meant both "rename" and "clobber an unrelated map."
- *`--git-commit`/`--no-git-commit` REQUIRED in BOTH modes* (map-file too) — symmetric; map-file
  `--git-commit` commits the `.dx`/`.unr` after the binary swap. Resolves the long-open "should
  map-file commit?" question (answer: yes, and require the explicit choice). `--allow-outside-git`
  only composes with `--no-git-commit`.

**Also applied (clear safety fixes, no fork):** guard A's "target exists" keys on **state-tree
content** (`actors/`/`order`), not the `name` file, so a populated-but-`name`-less tree isn't
first-written over; a NEW `_install_tree_atomic` directory-swap helper (the file-only
`_install_atomic` cannot be reused — `os.replace` fails on a non-empty dir; the old tree is kept
recoverable until the new is in place); a named `_trunk_git` seam (working repo, not the store
repo) for offline mockability; `state_name()` accessor + `name` force-remove against seed-from-tip;
`session status` shows the name (not `dx_path`); error messages name the offending value;
validation/guard ordering pinned (flags → flock → guards → THEIRS); `rebind` token removed.

**Rejected:** accepting the target race / deferring the lock (the user's overriding concern is
never-irretrievably-clobber); a `backups/` copy for `--no-git-commit` (store snapshot + git
suffice); a single `--allow-name-mismatch` covering unrelated targets (foot-gun); map-file staying
swap-only (Andrzej chose symmetry).

**Refs:** `specs/2026-06-23-uedcli-new-level-authoring-design.md` (revised).

## 2026-06-23 13:39 UTC — Dev-doc system: add `direction.md`, UTC-stamp decisions, doc-upkeep rules

**Decision:**
- *Decision-log headings carry the date AND UTC time* (`YYYY-MM-DD HH:MM UTC`) so same-day
  entries order unambiguously and supersession is precise. Pre-existing date-only entries are
  left as-is (never reworded).
- *Add `dev/docs/direction.md`* — the **compiled target**: the coherent end-state uedcli is being
  built toward, stated present-tense even where the code differs, synthesized from `decisions.md`
  with newer decisions overriding older (superseded points dropped). It is the *balance*;
  `decisions.md` is the *ledger*; `architecture.md` is *what is*.
- *Upkeep rules (now in uedcli `CLAUDE.md`):* whenever a decision is added/superseded, reconcile
  `direction.md`; topic docs (`architecture.md`/`unrealed/*.md`) MUST be updated to match whenever
  the implementation changes; every doc is written for a reader with NO familiarity with the
  implementation — explicit, defines its terms, assumes no prior context.
- *`docs/README.md` carries an authoritative "which doc is for what" table* so the roles can't be
  confused.

**Context:** The conversation kept blurring "what is" vs "what we want" (a genericity note landed
in `architecture.md` as if current). Andrzej asked for a dedicated target-philosophy doc compiled
from decisions, UTC times on decisions, an ultra-clear doc map, and standing upkeep rules.

**Rejected:** *folding the target into `architecture.md`* (conflates is/want — the exact problem);
*`vision.md`/`target-architecture.md`/`philosophy.md`* names (chose `direction.md` — matches the
"Direction" callout vocabulary, action-oriented, not grandiose); *auto-compiling `direction.md`*
(no tooling — hand-reconciled under the upkeep rule, like `MEMORY.md`).

**Refs:** `dev/docs/direction.md`; `docs/README.md` ("Which doc is for what"); uedcli `CLAUDE.md`
("Documentation").

## 2026-06-23 13:51 UTC — New-level authoring: second-fleet hardening

Resolves the second reviewer fleet's findings on the new-level spec. Extends the prior 2026-06-23
new-level entries; no reversals, but refines the unrelated-target guard and the locking/commit/atomicity.

**Decisions / fixes:**
- *Unrelated-target guard is a HEURISTIC over authored, non-singleton actors* — the naive
  `base ∩ THEIRS` is defeated by the universal `LevelInfo` singleton and deterministic
  auto-allocated `Uedcli<Class><n>` names (so it's never empty → the "refuse unrelated" guard was
  inert). Exclude both from the overlap; a non-empty overlap of hand-named authored actors ⇒
  plausibly a rename (overridable), empty ⇒ unrelated (refused). The store has no THEIRS-provenance
  record, so this is honestly a strong heuristic, not a guarantee.
- *The target flock is held across the WHOLE op (read→merge→write→commit→store-event), then released*
  — releasing after the write left the commit outside the lock and reopened the last-writer race.
  Both locks are `LOCK_NB` (no deadlock); order target→editor; target outlives editor. `editor_lock`
  is refactored into a generic `_flock(path)`; the session lock relocates to `locks/session/`, the
  target lock to `locks/target/`.
- *The trunk commit (`_trunk_git`, both modes) uses an isolated `GIT_INDEX_FILE`* (the store's own
  discipline), never the shared working index N agents stage into — a bare `git add` on the shared
  index was unsafe.
- *`_install_tree_atomic` orphan-scan:* before first-writing an "absent" target, scan for a sibling
  `.uedcli-old-*` from a crashed prior swap and REFUSE (with a restore instruction) rather than
  silently clobber the orphaned prior tree; the staging-temp sweep runs under the target lock.
- *Outside-git `--no-git-commit` safety stated honestly:* with `--allow-outside-git` there's no git,
  no dirty-check, and no `_backup` for trees — the ONLY net is the store's `apply/<uuid>/result`
  snapshot. The dirty-check is "always **when in a repo**," not unconditionally.
- *Map-file `--git-commit` commit-failure is NOT "clean retry safe"* — the swapped, uncommitted map
  file trips its own dirty-check on retry (binary still recoverable via `_backup`). Aligned with the
  T3D path.
- *Spec made readable cold* — added a Vocabulary section (THEIRS/OURS/base, `plan_apply`, H3, FULL
  RE-IMPORT, `_backup`, `latest_open`, `NON_COMMAND_VERBS`, …) per the just-added "no-familiarity"
  doc rule. Minor: `state_name` `.rstrip()`s; `name` force-remove cites `commit_command`'s per-path
  `--force-remove`; full `rebind` caller audit (incl. `_session_status`).

**Rejected:** *raw actor-name intersection for "shared ancestor"* (inert — LevelInfo/Uedcli*); *auto-
restoring a `.uedcli-old-` orphan* (refuse-and-instruct is safer than guessing); *bare `git add` on
the shared index* (races N agents); *claiming the dirty-check is unconditional* (false outside a repo).

**Refs:** `specs/2026-06-23-uedcli-new-level-authoring-design.md` (revised).

## 2026-06-18 — Store-centric model (pivot from editor-centric)

**Decision:** The durable source of truth is the **session store's model-side T3D level**
(`main/`), not a live UnrealEd instance. Every read and mutation is pure model-side
compute against `main/`; no `docker exec`, no `MAP EXPORT`, no liveness check during a
content verb. UnrealEd is reached only at `level apply` (and `level preview`) to
build/render the merged result. The LLM issues semantic by-name commands; T3D is internal
plumbing.

**Context:** The earlier design had the live editor as the authoritative level holder:
every read was a `MAP EXPORT`, every write drove the editor via console verbs, and the
"model" was just parsed T3D in memory. This failed in three ways: (1) the editor
**crashes often, even idle** — a live-editor-centric model crashes mid-read; (2) **no
concurrent sessions** — one container serializes all work; (3) **a substrate blocker** —
reading the current level state requires a live editor container, so a container must
always be running, making sessions expensive to start.

**Rejected:** *Keep the editor-centric model* — every read as a `MAP EXPORT` and every
write as a console exec. The session store model doesn't have these costs; the editor's
job is narrowed to building/previewing, which is what it does well.

**Refs:** `specs/2026-06-18-uedcli-store-centric-model-design.md` (ephemeral, now
deleted); the implementation is in `architecture.md` "Premise (store-centric)" and the
`level apply` → materialize seam.

## 2026-06-18 — FULL RE-IMPORT as the materialize strategy (over suffix-rebuild)

**Decision:** `level apply` materializes the merged level by **FULL RE-IMPORT**: `MAP NEW`
(blank level) then re-import the entire merged result in order — `MAP IMPORTADD` for
point actors, `EDIT PASTE` for brushes, LevelInfo first. No attempt to surgically update a
running editor by deleting only changed actors.

**Context:** The sessions/prefabs spec originally proposed a **suffix-rebuild** approach:
keep the running editor's level as a starting point, identify changed actors by suffix
comparison, delete just those, and re-import the changed ones — apply a diff, not the
whole level. A pre-implementation spike was gated on whether by-name brush delete
would work against the live editor.

The spike proved it cannot: brushes added via `MAP IMPORTADD` lack a `Bound` field (only
`BRUSH ADD` / well-formed `EDIT PASTE` compute it), so they are **never `ACTOR SELECT
INSIDE`-selectable**. Without selectability, a brush cannot be deleted or replaced.
Suffix-rebuild can't reliably delete/replace brush actors.

**Rejected:** *Suffix-rebuild* (the incremental "diff and patch" path — code stubs as
`materialize.earliest_changed_actor`/`actor_suffix_plan`). FULL RE-IMPORT is cheaper to
reason about (no diffing), crash-recoverable (`MAP NEW` starts clean), and guaranteed
correct (no stale actors from a prior materialize).

**Refs:** `unrealed/quirks.md` "How brushes enter the level" for the brush selectability
proof; `architecture.md` "Materialize / apply" for the FULL RE-IMPORT seam;
`specs/2026-06-17-uedcli-sessions-prefabs-design.md` (suffix-rebuild origin, now
deleted).

## 2026-06-21 — Class qualification via `OBJ LIST` (not `OBJ DEPENDENCIES` positional match)

**Decision:** `qualify_level_classes` qualifies bare `Class=` names by running **`OBJ
LIST CLASS=Class`** — a dump of all loaded classes with their fully-qualified
`Package.ClassName` names — and building a bare-name → package map
(`parse_loaded_classes`). A bare class name with exactly one loaded candidate qualifies
directly; zero or 2+ raise rather than guess.

**Context:** Textures are qualified via `OBJ DEPENDENCIES PACKAGE=MyLevel`, which prints
one block per brush in brush order — matched positionally to poly index. Mirroring this
for classes would use `OBJ DEPENDENCIES` per-actor block order to resolve each actor's
class. This was disproven live by two contradicting examples: the per-actor block order in
`OBJ DEPENDENCIES` output **does NOT match `level.order`**, making positional matching
impossible. `spikes/2026-06-21-class-qualification-discovery-and-roundtrip.md`.

**Rejected:** *Mirror the texture approach: positional match from `OBJ DEPENDENCIES`.*
Block order ≠ level order. No other per-actor class read-back exists; raising on a genuine
two-package collision is the only safe contract.

**Refs:** `qualify.py` (`qualify_level_classes`, `parse_loaded_classes`,
`export_and_qualify`); `architecture.md` "Commands → `export_and_qualify`";
`spikes/2026-06-21-class-qualification-discovery-and-roundtrip.md`;
`specs/2026-06-21-uedcli-class-qualification-design.md` (ephemeral, now deleted).

## 2026-06-24 08:50 UTC — `level doctor` BSP-issue detector is static-only; live "deep" mode deferred

**Decision:** Add a `level doctor` command that detects BSP holes and geometry issues
**model-side / offline only** — it never starts the editor. It analyses the authored `Level`
and **predicts** what UnrealEd's CSG/BSP build will do, using the exact thresholds reverse-
engineered from the binaries (the two 2026-06-24 BSP spikes). A live tier (`--deep`) that
rebuilds in an ephemeral editor and reports *ground truth* — captured engine drop-warnings
(`FPoly::CalcNormal: Zero-area polygon`, `FPoly::Finalize: Not enough vertices`,
`BspValidateBrush linked X of Y polys`), an authored-vs-built `Surfs` diff, and active
collision-trace probing — is **deferred** to a separate future TODO. The static report must
state its own incompleteness (static can't enumerate holes that only emerge from CSG
*interactions* or the partition choice; only `--deep` is ground truth).

**Context:** The user asked to "detect ALL holes and other BSP issues." Offered three scopes
(static-only / two-tier static+`--deep` / live-only); Andrzej chose **static-only for now,
defer deep mode, add a TODO for deep mode**. Aligns with the store-centric model where content
verbs are model-side and the crash-prone editor is touched only to build/preview
(`architecture.md` Premise) — a default-offline linter fits that, and the live tier carries the
editor's crash risk plus a still-unverified collision-probe verb.

**Rejected:**
- *Two-tier with `--deep` available now* — Andrzej deferred the live tier entirely to keep the
  first cut offline and deterministic; `--deep` is real future work, not a flag to stub now.
- *Live-only* — no offline lint, full editor crash exposure on every run; rejected.
- *Claiming static completeness* ("detects ALL holes") — dishonest: holes from brush-to-brush
  CSG interaction and phantom collision nodes need the build. The static tier is a high-recall
  predictor of known hole-causing patterns; the report says so.

**Open (not ratified):** the command name (`level doctor` proposed vs `level lint`/`bsp check`);
`--grid` default; the "walkable" normal-angle for the fall-through heuristic. See the spec §8.

**Refs:** `specs/2026-06-24-uedcli-bsp-doctor-design.md` (ephemeral);
`spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` +
`spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md` (durable evidence + thresholds);
`board/to-spec.md` (`level doctor` implement + `--deep` deferred spike).

## 2026-06-24 09:07 UTC — Reimplement UnrealEd's BSP/CSG build OFFLINE in uedcli (faithful, editor-verified) — supersedes the live `--deep` tier

Supersedes the "deferred live `--deep` editor tier" in the 2026-06-24 08:50 entry (the static
first cut stands; what "ground truth" means changes — it is no longer the live editor).

**Decision:** Build a **pure-Python, fully-offline port of UnrealEd's CSG/BSP build (and the
collision leaf/zone build)** inside uedcli, faithful enough to **reproduce the engine's actual
dropped faces and collision decisions** — so `level doctor` can detect build-emergent holes
(slivers, T-junction cracks, phantom collision nodes, coplanar-merge collapses) with NO editor at
runtime. The accuracy gate is a **differential harness**: build a corpus of maps in the REAL
UnrealEd and diff every node/surf/vertex against the Python build; the editor is the **test/CI
oracle only**, never a runtime dependency. Arithmetic is **float32-faithful at the thresholds**
(same discipline as the GMath rotation table) because holes hinge on boundary cases (a vertex
within 0.25 uu of a plane, the 1e-8 area floor). **Bit-identical BSP tree is a stretch goal, NOT
the gate** — the gate is "0 face/collision diffs on the corpus."

**Sequencing:** **static `level doctor` first** (the cheap offline linter — watertightness,
degeneracy, solidity, CSG-order; days), **then** the offline BSP engine as the major follow-on
that upgrades doctor from *predict* to offline *ground truth* (weeks).

**Context:** The user wants hole detection **fully offline AND 100% accurate**. The reviewer
fleet on the static spec independently confirmed the decisive holes (T-junctions/slivers) are
**products of the build, not the authored model** — so static prediction structurally can't
enumerate them; only running the build can. The user chose to reimplement the build offline rather
than depend on the crash-prone editor at runtime. Offered three approaches; Andrzej chose **"faithful
port, editor-verified"** over a disassembly-only bit-identical port and over keeping the live
editor for ground truth.

**Rejected:**
- *Bit-identical, disassembly-only port (no editor oracle ever)* — more work AND less trustworthy:
  accuracy asserted-by-construction can't be *measured*. The differential harness makes "100%
  accurate" a provable claim; purity for its own sake doesn't.
- *Keep the live `--deep` editor tier as ground truth* — accurate by definition but NOT offline
  (Docker + crash-prone editor at runtime); contradicts the fully-offline goal. The editor is
  retained as the test-time oracle, not a runtime path.
- *Gate on a byte-identical BSP tree* — the partition-plane heuristic + pervasive float32 make this
  research-grade; the mapper cares about which faces/collision survive, which the corpus-diff gate
  captures directly.

**Biggest known risk / gating spike:** the `bspBuild` **partition-plane selection heuristic**
(`Balance`/`PortalBias` scoring + tie-breaking + iteration order) is the one core piece NOT yet
disassembled (the render spike flagged it out-of-scope). The whole tree — hence which faces
split/survive — hinges on it. Disassembling it is the gating spike for the engine port; do it
before committing to the port's feasibility.

**Refs:** `spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` (FPoly/CSG thresholds, the
partition-heuristic gap called out in §7) + `spikes/2026-06-24-bsp-collision-solidity-movers-from-binary.md`
(collision is structural — the engine port must build the leaf/zone structure, not just surfaces);
`specs/2026-06-24-uedcli-bsp-doctor-design.md` (Phase 2 section); `board/to-spec.md` (engine project +
partition-heuristic gating spike). Supersedes the live-`--deep` plan in the 08:50 entry.

## 2026-06-24 12:40 UTC — BSP-issue ground truth = D0+D1 (editor drop-warnings + saved-build reader); the fully-offline engine (D2) is an optional upgrade

Revises the 2026-06-24 09:07 UTC "fully offline" framing after a full design spec + **three rounds
of paired cold review**. The 09:07 entry committed to a fully-offline faithful CSG/BSP/collision
port as *the* path. Review found that path is the riskiest, least-bounded part — and that the
*capability* (catching build-emergent holes/HoM/collision bugs) is available far more cheaply.

**Decision (Andrzej):** Build a **two-part detector that is complete on the editor's real build**,
and keep the fully-offline engine as a deferred-but-fully-specced optional upgrade:
- **D0 — editor `MAP REBUILD` drop-warnings.** The editor confesses every face it drops
  (`FPoly::CalcNormal: Zero-area polygon`, `FPoly::Finalize: Not enough vertices`,
  `BspValidateBrush linked %i of %i polys`) + T-point/infinitesimal-node counts. These ARE the
  dropped (absent) faces, as ground truth, on real semisolid/portal maps, with no port.
- **D1 — parse the saved `.dx` built model and LOCATE the present/structural issues:** HoM /
  T-junction cracks (built-surf edge adjacency), invisible walls (near-zero-area blocking nodes),
  fall-through (collision probe under rendered floor surfs), leaf/zone structure.
- **D0 + D1 = the complete issue detector** on a build the editor already made (one editor run to
  produce the `.dx`). The only class they miss is *silent absence* (a face dropped with no warning
  and no built trace).
- **D2 — the fully-offline faithful engine** (the 09:07 port) is the **only** route to runtime-
  fully-offline + silent-absence holes. **Retained fully-specced; built only if D0-b's measurement
  (how common is silent-absence?) justifies it, behind the spec's budgeted Tier-S bar.**

**Context:** Andrzej's want was "fully offline, but 100% accurate," conditioned on actually finding
ALL BSP issues (holes, HoM, invisible walls, fall-through). Review established that reading the
built model gives **presence** (located HoM/walls/fall-through) but not **absence** (a dropped face
needs knowing what *should* exist); D0's warnings supply the absence side. So completeness = D0+D1,
cheaply, on the real build — and runtime-fully-offline (D2) is a separate, optional, expensive goal.

**Rejected:**
- *Build the fully-offline engine first (the literal 09:07 path)* — buries all real-map value behind
  the multi-week faithful port (risk #1) and a soundness caveat (unsound on semisolid/portal maps
  until its solidity slice); D0+D1 delivers the capability now.
- *D0 alone* — misses HoM/T-junctions and located collision bugs (those need D1's built-model
  analysis); Andrzej's condition ("find ALL issues") rules it out.
- *Drop D2* — kept fully specced: it remains the only fully-offline path and the only catcher of
  silent-absence holes, and it unlocks cheap offline textured rendering later.

**Also decided (spec detail, logged so it isn't re-litigated):** Tier-S (per-face identity) is D2's
ship gate (implements 09:07's "0 diffs" as a bounded frozen-corpus bar + `heuristic`-confidence
real-map findings, not an unbounded "classify every diff"); `BuildResult` is a sum type
(`BuiltOk`|`WouldCrashCsg`); the spike's `balance=15` default is a bug (the `MAP REBUILD` default is
50). The earlier draft that called D1 a "presence-only small prize" is corrected — D1 locates the
user's hardest items.

**Refs:** `specs/2026-06-24-uedcli-offline-bsp-engine-design.md` (the 3-round-reviewed design; D2
notes retained in full); the five `spikes/2026-06-24-*bsp*`/`*offline-bsp-engine*` spikes;
`board/to-spec.md`. Revises (does not delete) the 2026-06-24 09:07 entry.

## 2026-06-24 14:30 UTC — Generator pattern: `brush build`, `actor build`, `stash intersect`/`deintersect`

**Decision:** Three capability gaps resolved by the **generator pattern** — a session-free verb
that writes a single-actor T3D snippet to stdout and does not touch the session store:

1. **`brush build <shape>` replaces `brush <shape>`.** The six shape verbs (`cube`/`cylinder`/
   `cone`/`sheet`/`staircase`/`spiral`) are removed; `brush build <shape>` writes the same
   geometry to stdout as a single-actor T3D. Common flags (`--at`, `--csg`, `--solidity`,
   `--group`, `--name`) are baked into the T3D at generation. Session-free.
2. **`actor build <fully-qualified-class>`** is new: writes a point-actor T3D for the given
   class, with optional `--at`/`--prop KEY=VALUE`. Bare class name (no `.`) is rejected per
   to-resolve #9. Session-free; no substrate validation at generation time.
3. **`actor add -`** (hyphen = stdin) extends the existing verb with stdin support. **Name
   allocation lives here**: strip trailing digits from the template name the generator emitted,
   append the lowest non-negative integer N such that no actor in `main/` has that name. This
   is the natural seam — `actor add` has the session; generators are session-free and cannot
   query existing names.
4. **`stash intersect <id>` / `stash deintersect <id>`**: new live-editor verbs (session-required
   to read the stash); both write a single-actor T3D to stdout. `stash intersect` always
   prepends a synthetic `CSG_Subtract` covering the stash world bounding box + 32 uu margin,
   placed FIRST in CSG order, before the stash actors. `stash deintersect` does not. If the
   stash contains no additive brushes, `stash intersect` exits non-zero with a clear error.

**Context:** `brush <shape>` verbs added to the model directly, making composition with `stash`
or `actor add` impossible. No CLI verb generated a point-actor T3D (callers had to write T3D by
hand). No first-class CLI for `BRUSH FROM INTERSECTION`/`BRUSH FROM DEINTERSECTION` despite
driver verbs existing since 2026-06-17. Human-question #11: `brush cube`/etc. should output T3D
so it can be separated from adding to the level and composed with other commands. Specced
2026-06-24.

**Rejected:**
- *Keep `brush <shape>` names adding directly to the model* — makes piping and composition
  impossible; the brush is already placed, with no way to inspect, redirect, or compose.
- *Flags on `actor add`, not the generator* — the generator is session-free; to bake
  `--at`/`--csg` into the T3D (so stdout is ready for any disposition), flags must be on the
  generator. `actor add` handles only name uniqueness.
- *`brush build intersect` as a one-off command-line form* — stash is the natural reusable,
  named input; listing brush names on the CLI gets unwieldy for many actors and produces nothing
  reusable.
- *`--out-stash <id>` on `stash intersect`* — the pipe (`| actor add -`) handles all
  dispositions uniformly; a flag special-cases a pattern the pipe covers naturally.
- *No wrapping subtract for `stash intersect`* — without it, additive brushes in a pure-add
  stash fill already-solid space (Unreal's world is infinite solid after `MAP NEW`) and
  `BRUSH FROM INTERSECTION` returns the bounding box unchanged (useless). Always-wrapping gives
  a consistent semantic: "solid additive objects within this stash."
- *Conditional wrap (only for pure-add stashes)* — works but the always-wrap semantic is
  cleaner; the error on subtract-only stashes covers the remaining invalid case.
- *Wrapping subtract for `stash deintersect`* — inner subtracts define the carved void directly;
  prepending an outer subtract makes the inner ones operate on already-empty space and corrupts
  the result.
- *Offline CSG for `stash intersect`/`stash deintersect`* — would require D2 (the offline BSP
  engine, deferred per the 2026-06-24 12:40 entry). Live editor for now.

**Refs:** `specs/2026-06-24-uedcli-generator-pattern-stash-intersect-design.md` (ephemeral).

## 2026-06-25 10:36 UTC — `actor find`: separate verb, group-membership semantics, OR/AND combining, case-insensitive FName matching

**Decision:** Add a stateless, read-only `actor find` verb (filter flags → bare actor names,
one per line, exit 0) for piping into name-taking verbs. Five filter flags:
`--name GLOB`, `--class C`, `--group G`, `--prop KEY=VALUE`, `--kind point|brush`.
Repeating a flag within the same dimension is OR (broadens); combining different flags is AND
(narrows); repeating `--prop` is AND (each key-value pair must match). All matching
implemented in `query.list_actors`, so `actor list` and `actor cat` inherit the same behavior.

**Context:** Resolves `to-resolve.md` #13 (find-by-group/property) and #8 (case-insensitive
names). Specced 2026-06-22; five review rounds; reviewed plan 2026-06-24.

**Decisions made (choice → rejected):**
- *Separate `actor find` over overloading `actor list` or adding filter flags to mutating
  verbs.* Rejected: per-verb `--only-groups`/`--only-actors` (the "verbs compose" convention's
  anti-pattern); merging into `actor list` (conflates human-readable output with machine-
  readable name lists).
- *`--group` = group-membership* (split the comma-joined `Group=` value, strip, casefold,
  match any). Rejected exact-equality for `--group` (silently drops multi-group actors);
  exact matching is available via `--prop Group=…`.
- *Repeat `--class`/`--group`/`--name` = OR; repeat `--prop` = AND.* An actor has one class,
  so repeat `--class` can only OR. `--group` and `--name` follow the same convention for
  consistency ("in a OR b"). `--prop` is the exception: distinct key-value pairs are an
  intersection query ("in group cells AND with brightness 128"). Repeated flags chosen over
  comma-lists: uniform `action="append"`, no comma-in-value concern, natural aloud reading.
  Rejected: comma-lists (extra parser + edge case for prop values); repeat=AND for all
  (makes repeated `--class` always-empty — useless).
- *Output = bare names, one per `print`, in `level.order`; zero-match = byte-exact-empty
  stdout, exit 0.* Makes `actor find … | xargs <verb>` safe and deterministic.
- *Matching is case-insensitive for FNames (name/group/class/prop-key); `--prop` VALUE is
  exact.* Unreal FNames are case-insensitive (`SELECTNAME` already confirmed this live).
  Implemented in `list_actors`, so `actor list` and `actor cat` share the fix — a deliberate
  shared correctness improvement. Rejected: case-sensitive matching (contradicts engine
  semantics); folding prop values (heterogeneous; deferred).
- *`--class` accepts bare (last `.`-component) AND qualified (`Package.Name` exact); stored
  classes are always fully qualified.* Bare matches any package's class by that name; qualified
  disambiguates. No bare-stored leniency — bare-stored is a bug to fix at source. Rejected:
  matching qualified vs. bare (would mask the bug); bare-only (can't disambiguate).
- *`--kind point|brush` over `--geometry yes|no|any`.* `Actor.brush is None` is the split.
  `--geometry any` just restates "flag omitted"; "geometry" mislabels mesh decorations (point
  actors with visible mesh). `--kind` was kept over two `store_true` flags (breaks the value-
  filter pattern) and over `--type`/`--actor-type` (reads as synonym for `--class`).

**Refs:** `specs/2026-06-22-uedcli-actor-find-design.md` (ephemeral, now deletable);
`plans/2026-06-24-uedcli-actor-find-plan.md` (ephemeral, now deletable); `query.py`
(`list_actors`, `_class_matches`, `_group_matches`); `cli.py` (`_nonempty`, `_nonempty_class`,
`_parse_kv`); `dispatch.py` (`actor find` block).

## 2026-06-25 11:04 UTC — Case-insensitive actor-name resolution via resolver helpers, not dict key change

**Decision:**
- *Resolution is in two new `query.py` helpers* — `resolve_actor_name(level, name) -> str`
  (exact match first, then case-fold scan of `level.actors`; raises `KeyError` on miss) and
  `resolve_actor_names(level, names) -> list[str]` (all-or-nothing batch; collects ALL misses
  before raising `KeyError` naming the complete missing set). Every verb that takes an actor
  name at the CLI calls one of these before any other lookup; dispatch catches the `KeyError`
  and emits a clear "Actor not found: <name>" or "Actors not found: <n1>, <n2>" message to
  stderr + exit 2, never a bare traceback.
- *`e.args[0]` not `str(e)` for `KeyError` messages.* Python's `str(KeyError("foo"))` returns
  `"'foo'"` (with extra quotes) — only `e.args[0]` yields the bare message.
- *`poly set` recording exemption:* `rec_args["targets"]` stays as raw user-typed tokens
  (`"brush1:all"` etc.) because the `apply_surface_edit` return value (the canonical touched
  brush names) is already canonical; `cmd["hashes"]` keys are canonical. The targets field is
  intentionally raw so the command log reproduces the original user intent.
- *`actor delete` changed from silent-miss to error.* Previously a missing name was silently
  skipped; now `resolve_actor_names` is called first and a missing name is an error (exit 2).
  This is a behavior change, but the old silent-skip masked typos and made the command log
  unreliable (a log entry with a non-existent actor name could not be replayed).

**Context:** Unreal `FName` comparisons are case-insensitive (`SELECTNAME NAME=helperlight0`
selects `HelperLight0` — confirmed live 2026-06-23 in `commands.md`). uedcli's mutating
verbs used raw dict lookups, so a wrong-case actor name silently failed or raised a bare
`KeyError` traceback at the CLI. Specced 2026-06-24; plan reviewed 2 rounds.

**Rejected:**
- *Case-fold the `level.actors` dict key at parse time* — would change the canonical stored
  name (losing the original casing) and break every actor-name-keyed lookup site. The resolver
  pattern preserves canonical names end-to-end; only the lookup is case-insensitive.
- *Per-callsite try/except wrapping without helpers* — 12 callsites would each need their own
  scan loop; helpers centralize the logic and keep the contract (exact match first → fold scan →
  KeyError on miss) in one tested place.
- *Silently ignore a missing name in batch verbs* — produces an unreliable command log and
  masks typos. All-or-nothing (collect all misses, then raise) was chosen instead.

**Refs:** `specs/2026-06-24-uedcli-actor-name-resolution-design.md` (ephemeral);
`plans/2026-06-24-uedcli-actor-name-resolution-plan.md` (ephemeral); `query.py`
(`resolve_actor_name`, `resolve_actor_names`); `dispatch.py` (every affected verb);
`surface.py` (`apply_surface_edit`); `tests/test_actor_name_resolution.py`.

## 2026-06-25 12:17 UTC — Mover support: offline keyframe authoring

**Decision:** uedcli authors UnrealEngine-1 movers (animated brush actors: doors/lifts/gears)
entirely model-side — a session-free `brush build --mover-class` generator for the base mover plus
a session-aware `mover key add/move/rotate/remove/list` family for keyframes — built on a general
indexed-array (`Foo(N)=...`) round-trip fix. Folds the 2026-06-25 mover spec's eleven decisions
(choice → rejected):

1. **Mover stored at `KeyNum=0`, base pose in `Location`/`Rotation`, `KeyPos(i)`/`KeyRot(i)` as
   relative offsets; `BasePos`/`BaseRot` never emitted (computed-stripped).** *Rejected:*
   storing/emitting `BasePos`/`BaseRot` as authored (the editor overwrites them from
   `Location`/`Rotation` — spike test D); special-casing `actor move`/`rotate` to sync them
   (unnecessary once `KeyNum=0` is invariant). Grounded in the 2026-06-25 spike.
2. **CLI speaks absolute (`--at`/`--rot`/`--to`), store speaks relative.** Mirrors the editor's own
   keyframe authoring. *Rejected:* relative-offset CLI (`--pos +0,0,256`) — absolute is how a mapper
   thinks ("the open position is here").
3. **Keyframes live ONLY in the `mover key` family; the generator makes the base mover only.**
   *Rejected:* baking keyframes on `brush build --mover-key` — duplicated `NumKeys`/index bookkeeping
   and forced a full rebuild to edit one key.
4. **Index 0 reserved for `actor move`/`actor rotate`.** `mover key move/rotate/remove` reject index
   0. *Rejected:* a `mover key` path that edits the base (two ways to do one thing).
5. **No combined `mover key set`.** `move --to` + `rotate --to` cover absolute repositioning.
   *Rejected:* a `set` verb overlapping `move`/`rotate`.
6. **8-key hard cap (error past it); minimum 2 keys.** Engine arrays are `[8]`. *Rejected:* uncapped
   (a 9th key is silently dropped at engine load).
7. **Ingest canonicalizes THEIRS movers to `KeyNum=0`** (fold the selected-key offset back into
   `Location`/`Rotation`, drop `KeyNum`) at BOTH ingest funnels (`qualify.export_and_qualify`,
   `session.read_state_dir` — mover blobs only, non-movers byte-verbatim). Idempotent. *Rejected:*
   preserving `KeyNum`≠0 verbatim (round-trips wrong via `EDIT PASTE` — re-derives `BasePos` from
   the offset pose, drifting).
8. **Mover detection by ONE shared `is_mover` predicate (class bare-name equals/ends in `Mover`),
   replacing `doctor.py`'s narrower `_MOVER_CLASSES` exact-match.** *(The name-suffix half is
   SUPERSEDED by 2026-07-25 10:18 UTC — the predicate is now a descends-from-`Engine.Mover`
   hierarchy test. The "ONE shared predicate" half stands.)* Substrate-generic; doctor now
   recognizes subclass movers (`DeusEx.ElevatorMover`) as closed solids — a deliberate additive
   behavior change. *Rejected:* a subclass registry (deferred — needs a per-substrate class graph);
   leaving doctor's check separate (two definitions drift).
9. **`brush build --mover-class` required-FQCN, no default, `--csg` AND `--solidity` rejected with
   it.** A mover carries no `CsgOper` and its collision is the dynamic hash + actor flags, not CSG
   solidity, so both would be silent no-ops. *Rejected:* accepting `--solidity` as inert.
10. **`mover key` introduces absolute keyframe rotation (`--to`), which `actor rotate` lacks**
    (`actor rotate` is `--by`-only). A keyframe is an absolute target pose the author states
    directly. *Consequence:* the index-0 redirect for `mover key rotate 0` points at `actor rotate
    --by` (delta); absolute base rotation has no v1 verb (an `actor rotate --to` is a flagged
    follow-up). *Rejected:* forcing keyframe rotation delta-only for false parity.
11. **The mover name template is the mover-class bare-name** (`Engine.Mover` → `Mover0`,
    `DeusEx.ElevatorMover` → `ElevatorMover0`), not the shape name. *Rejected:* the shape template
    (`Cube0` — opaque) or a hardcoded `Mover` (loses the subclass).

**Two deliberate shared-behavior changes:** `model._PROP` widens to parse indexed props `Foo(N)=...`
(a general correctness fix — also stops `MultiSkins`/`Skins` loss on decorations/meshes); `doctor`
recognizes subclass movers as closed solids (Decision 8). `brush build`'s `--csg`/`--solidity`
argparse defaults move to `None` (runtime unchanged via the existing `or "add"`/`or "solid"`
fallbacks) so an explicitly-supplied flag can be detected and rejected alongside `--mover-class`.

**Deferred (flagged):** the `BaseRot≠0` + non-axis-`KeyPos` world-space-vs-rotated question (a
one-session spike — `mover key add/move` on a base-rotated translating mover warns-and-proceeds in
v1, exit 0); `actor rotate --to`; `mover key set`; subclass-registry detection; `OldRot`
confirmation (gated on the integration re-export — added to `COMPUTED_PROPS` only if observed). See
`board/to-spec.md` + `board/to-spike.md`.

**Refs:** `specs/2026-06-25-uedcli-mover-support-design.md` + `plans/2026-06-25-uedcli-mover-support-plan.md`
(ephemeral); `spikes/2026-06-25-mover-keyframe-basepos-semantics.md` (durable grounding); `uedcli/movers.py`
(new), `rotation.py` (struct helpers + `subtract_uu`), `model.py` (`_PROP`), `normalize.py`
(`COMPUTED_PROPS`), `builders.py`/`cli.py`/`dispatch.py`/`query.py`/`doctor.py`/`qualify.py`/`session.py`.

## 2026-06-26 10:53 UTC — `actor prop`: model-side property set/clear (replaces the `actor set` stub)

**Decision:** Replace the crude `actor set <name> <prop> <value>` stub with **`actor prop <name>
--set KEY=VALUE … --unset KEY …`** — symmetric, repeatable flags applied as ONE atomic recorded
mutation, model-side (no editor). The choices:

- **One neutral verb with symmetric `--set`/`--unset`**, not `set` + an `--unset` flag and not two
  sibling `set`/`unset` verbs. Andrzej's constraint: set-and-clear must be possible in a SINGLE
  command (one mutation). `set`-the-verb + `unset`-the-flag reads awkwardly; `actor prop` makes the
  two directions parallel and leaves room for a future `actor prop get`.
- **Minimal handling — set almost everything; the default is "no special handling."** `actor prop`
  is model-side and reversible, so there is no safety case for blocking authored props. Four buckets
  (narrowed across the 2026-06-26 design conversation, each over-block walked back in turn):
  - **Hard reject (exit 2) — not a freely-settable property:** `Name` (the actor's identity; changes
    are **never allowed on an existing actor** — Andrzej's directive; a props write doesn't rename and
    dups the line), `Brush` (the internal `Brush=Model'…'` geometry binding — an arbitrary value
    corrupts it), and `KeyPos(N)`/`KeyRot(N)` (mover keyframe arrays — they carry the `KeyNum=0`
    invariant + relative-offset bookkeeping only the `mover key` verbs maintain; matched by base name,
    any index — Andrzej's directive 2026-06-26). These are the ONLY hard rejects.
  - **Route to its typed field:** `Location` — dual-stored as the parsed `actor.location` (move/
    rotate/bounds math) + a `props` mirror, and `emit_actor` emits from `actor.location`, so a plain
    props write is silently ignored. `--set Location=` is parsed into `actor.location` (the one field
    needing wiring beyond a props write); `--unset Location` resets it to origin. Equivalent to
    `actor move --to` — accepted redundancy (Andrzej: "setting Location is fine").
  - **Warn + proceed (exit 0):** computed fields (`Region`/`bSelected`/`OldLocation`/`AIProfile(N)`/…
    — `normalize` strips them on save, so warn "won't persist", do NOT block — Andrzej's directive);
    `MainScale`/`PostScale` (round-trip, but model-side measurement ignores scale — `rotation.world_vertices`
    applies Location+Rotation+PrePivot but not scale, an unimplemented measurement feature, not
    corruption — so `bounds`/`preview`/stash-placement mis-measure the actor).
  - **Set silently — everything else:** `Rotation` (props-only, verbatim; does NOT orbit Location —
    that's `actor rotate`), `CsgOper`, `PrePivot` (honored by model-side measurement; D8 bans only
    *implicit* rewrites, an explicit set is fine — dropped the earlier warn), `PolyFlags`, `Tag`, and
    all scalar light/trigger/mover props.
- **Computed *detection* is case-insensitive.** `normalize._is_computed` is case-sensitive and could
  not be reused directly (it would have missed `--set region=…`), so add a case-folded helper used
  both here (to warn) and inside `normalize` (to strip).
- **Case-insensitive key handling throughout** (FName): replace/unset match existing `props` by
  case-fold (preserving stored casing on replace), collapse pre-existing duplicate keys, and reject
  intra-invocation collisions case-fold + index-aware.
- **Value stored verbatim minus surrounding quotes** (mirrors `model._parse_actor`'s `strip('"')`)
  so set → export → re-parse is idempotent. `Group`/`Name` re-quote on emit as today.
- **Validation fully precedes mutation** (pinned order: set-token grammar → key grammar → reject
  `Name`/`Brush` → intra-invocation conflict → actor resolve → `Location` value parse), so a failed
  multi-`--set` leaves `main/` untouched (`record_mutation` rewrites the whole tree from the model).
- **`set` verb dropped, no alias.** Undocumented/pre-release; parser + dispatch branch both removed.
  Replay is unbuilt (no production caller registers a handler map; `main/` is written directly, never
  replayed), so the rename has no replay consequence today — `prop` joins the handler list whenever
  `session verify --deep` / `merge --sessions` lands.

**Context:** The spike "is there an editor `ACTOR SET` console verb?" found none (Spike 9,
`spikes/2026-06-23-capability-gaps-round2.md`) — a red herring, since uedcli mutates the model
directly and only materializes at `level apply`. A crude `actor set` stub already existed but
silently no-op'd on `Location`, could clobber computed fields, was single-prop-only, and had no
`help=`. Specced 2026-06-26; two cold reviews then Andrzej's review progressively **narrowed the
block set** — the first cut rejected `Location`/`Name`/`Brush`/`PrePivot`/`MainScale`/`PostScale` +
the computed set; the final design rejects only `Name`/`Brush`, routes `Location`, and warns (not
blocks) on computed/scale/mover-key. The principle that emerged: model-side edits are reversible, so
block only what genuinely *can't* work (not a settable property), route what's typed, and warn where a
set works but has an invisible downstream effect.

**Rejected:** keeping a single `set` verb with a sentinel empty-value clear (`K=` ambiguous vs a
real empty string); two sibling `set`/`unset` verbs (can't combine in one mutation);
**reject-and-redirect for `Location`** (superseded — route it into `actor.location` so it works,
accepting the `actor move` overlap, per Andrzej); **rejecting/​warn-blocking computed and `PrePivot`/
scale** (superseded — computed and scale warn, `PrePivot` is silent); schema-validating property
names (no offline class catalog — unknown keys pass opaque); reusing `normalize._is_computed` as-is
(case-sensitive bug).

**Refs:** `specs/2026-06-26-uedcli-actor-prop-set-design.md` (ephemeral); folds into `dispatch.py`
(`actor prop` handler), `cli.py` (parser), `normalize.py` (new case-folded computed helper),
`architecture.md` (the `actor` verb list) on implementation.

## 2026-06-26 — `uedcli deusex con`: high-level conversation source ↔ `.con`

**Decision:** Build a session-free `uedcli deusex con` tool (under the DeusEx substrate namespace)
that compiles a git-trackable text **source** to the binary `.con` and decompiles back. Folds the
2026-06-26 design's decisions (choice → rejected):

1. **Session-free, under `deusex con`** (verbs `new`/`compile`/`decompile`/`validate`/`search`/
   `voices`). *Rejected:* level-scoped/session-bound — a `.con` spans missions and references
   mission-wide tables, so it is not level design (texture-catalog precedent).
2. **Source = a high-level dialogue tree (YAML).** *Rejected:* a flat event-list mirror (byte-exact-
   trivial but assembly-like to author); a hybrid with a raw-bytes escape (unneeded once the equality
   bar is semantic, not byte-exact-adoption).
3. **Equality bar = deterministic + semantic** (same source ⇒ byte-identical `.con`; output loads/
   plays; the Layer-1 codec is independently byte-exact-tested on the corpus). *Rejected:* byte-exact
   *adoption* round-trip (`decompile(X)` then `compile == X` byte-for-byte) — a high-level tree can't
   reproduce an external file's event-index/ordering/bool-encoding bookkeeping, and the originals are
   DEED-reconstructed anyway; also rejected the captured-ballast and faithful-lowering routes to it.
4. **Two-layer architecture:** `con_codec.py` (byte-exact `.con`↔event-list, ported from the format
   spike's `con_roundtrip.py`) under `con_source.py` (semantic tree↔event-list), sharing
   `con_model.py` dataclasses.
5. **A `.con` maps to a directory, one conversation per file + a `con.yaml` manifest** (manifest
   holds the `.con`-level record + the deterministic conversation order; `id` author-overridable).
   *Rejected:* one source file holding N conversations (worse diffs / locality).
6. **Every statement is a uniform single-key `{verb: payload}`; `speech` is an explicit verb**
   (`if`/`choice` keep `then`/`else`/`options` *inside* the value). *Rejected:* an actor-as-key
   screenplay shorthand (`- paul: "…"`) — needs an alias table and forbids actor names colliding
   with verbs; uniform parsing + agent-generation won. Actor/flag names appear only as values, so
   verb/name collision is impossible by construction.
7. **Reuse = conversation-scoped `fragments` + `use:`, which REPLACES raw `label`/`goto`** (the
   author never writes a label/goto; the compiler owns them). Recursion is decided over the fragment
   **call-graph SCCs** (catches mutual recursion); a **tail** `use:` lowers to a `Jump` (covers
   loops, convergence, DRY-binary), a **non-tail** `use:` of a non-cyclic fall-through fragment
   **inlines** (composes/chains). **Non-tail recursion is a hard compile error.** *Rejected:* raw
   label/goto in the source; inline-only (no loops); jump-only (no chaining); a cross-file fragment
   library (deferred); a flag-encoded stack to fake bounded non-tail recursion (pollutes
   savegame-visible flag state; real dialogue doesn't need it — deferred, revisitable).
8. **Cross-conversation `jump:` is a one-way goto (no call/return)** — spike-proven: the conversation
   VM is stackless (`ConPlayBase` holds only `con`+`startCon`, the `EEventAction` enum has no return
   verb, `End` terminates the whole playback). See the jump-return spike.
9. **`voice` metadata (IPA/style) is source-only, dropped at compile** (the `.con` has no slot);
   `mp3` is optional, hand-writable, → the binary `mp3` field verbatim. **TTS audio generation is a
   separate future tool**; this tool only exports the `voices` sidecar for it. *Rejected:* compiler-
   generated mp3 names as the default (the user wants manual mp3 + a future metadata-driven TTS tool).
10. **Trade(8) unsupported** (undecoded, no corpus sample) — errors both directions. **`MoveCamera(6)`
    is under-decoded** (the decompiled `ConEventMoveCamera` has 10 fields vs the format spike's 3
    ints) → v1 authors only the predefined-position form; the full payload needs a follow-up decode
    spike and round-trips as opaque until then.

**Context:** The `.con` format was fully decoded + byte-exact round-tripped in the 2026-06-25 format
spike; this is the design of the tool that consumes it. The reuse model and cross-conversation
semantics were settled with Andrzej over a brainstorm; the jump-return question was resolved by a
dedicated decompile spike (run at his request); a two-reviewer cold pass on the spec drove field-
semantics corrections grounded in a fresh `ConSys.u` decompile (`Flag.expiration`/`bGoalCompleted`/
`MoveCamera`/`Random` confirmations).

**Refs:** `specs/2026-06-26-uedcli-deusex-con-tool-design.md` (ephemeral);
`spikes/2026-06-25-deusex-con-conversation-format.md` (format, byte grammar) +
`spikes/2026-06-26-deusex-con-jump-no-return.md` (stackless VM / one-way jump). Implements as
`con_codec.py`/`con_model.py`/`con_source.py` + `cli.py`/`dispatch.py` under `deusex con`.

## 2026-06-26 12:41 UTC — Property validation: sole `.u` parse, error-not-fallback, normalize key casing to `.u`

**Decision:** Property-name validation for `actor prop` / `actor build --prop` is built on a single,
reliable mechanism with **no fallbacks**:

- *Source = parse the compiled `.u` **export table** directly* (pure Python, a `dxpkg` extension —
  `spikes/2026-06-26-class-property-extraction.md`). A class's properties = export records whose
  `Outer` is the class and whose type is a `*Property`; the full set is the union up the `Super`
  chain (cross-package via the import table). **The UCC `batchexport` decompile is NOT a runtime
  source or fallback** — it stays a dev/test cross-check oracle only. Reliability is verified, not
  assumed: **49/49** substrate+install `.u` files parse with the cursor landing **exactly at EOF**
  on both v68 and v69, and the complete UProperty type set is a finite **11** classes
  (`Array/Bool/Byte/Class/Float/Int/Name/Object/Pointer/Str/Struct` `Property`).
- *An unknown property is a hard ERROR* (exit 2, naming the prop) — **no opaque-accept, no silent
  pass-through to apply**. If the schema itself can't be built (a class or ancestor package can't be
  resolved/parsed), that is **also an error** — fix extraction/packages, never degrade silently.
- *No bypass.* There is no escape hatch — an unknown prop or unbuildable schema simply errors. (A
  `--force` override was considered and **dropped for now**: pure error is simpler and the extraction
  is reliable enough not to need one; revisit only if a real need appears.)
- *Property key CASING is normalized to the canonical `.u` spelling* (e.g. `lightbrightness` →
  `LightBrightness`). The engine is case-insensitive on property names (spike Q8), so this is
  canonicalization for stable diffs and authoritative output, not correctness. It **supersedes**
  `actor prop`'s earlier "preserve stored casing on replace" — the validator returns the canonical
  spelling and that is what's stored. Applies to property keys stored in T3D.
- *Two CONFIRMED extensions (Andrzej, 2026-06-26):* (a) the mover-keyframe-bookkeeping reject family
  extends `KeyPos`/`KeyRot` to **`NumKeys`/`KeyNum`** (same family — a raw set desyncs the mover the
  same way; `mover key` owns them); (b) `normalize`'s computed-strip becomes **case-insensitive**
  (`is_computed_key`, folding the `AIProfile` prefix family too) so the "won't persist" warning is
  truthful — a deliberate **global, hash-affecting** change (it runs in `canonical_actor_t3d` for
  every actor), guarded by its own non-`actor prop` regression test and an explicit check that no
  `COMPUTED_PROPS` member case-collides with a plausibly-authored prop. It is FName-consistent, so it
  strips strictly-more-correctly.

**Context:** Andrzej's directives on the resolved extraction spike (2026-06-26): "No fallbacks. Focus
on making `.u` extraction reliable. Error if property is not found, no opaque-accept." + "Normalize
property names stored in T3D to how they're defined in `.u`." (A floated `--force` was then dropped:
"Maybe drop --force for now.")

**Sequencing (flagged for the plan):** because "no opaque-accept" contradicts shipping `actor prop`
with unknown keys passing through, `actor prop` should **integrate** validation+normalization (taking
a dependency on the `.u`-extraction work) rather than ship an opaque-accept v1 then tighten later.

**Rejected:**
- *Opaque-accept of unknown props* (the extraction spike's first cut) — the silent no-op-at-apply is
  the exact bug this exists to kill.
- *Graceful degradation to opaque-accept when the schema can't be built* — superseded by the
  no-fallback rule; an unresolvable schema errors.
- *A `--force` escape hatch* — floated, then dropped for now (pure error is simpler; revisit if
  needed).
- *UCC decompile as a runtime source/fallback* — `.u` parse is sole and proven; decompile is a
  cross-check oracle only (and is fiddlier text-parsing + needs wine).
- *Preserve-stored-casing on replace* (`actor prop`'s earlier rule) — superseded by
  normalize-to-`.u`-spelling.

**Refs:** `spikes/2026-06-26-class-property-extraction.md`;
`specs/2026-06-26-uedcli-actor-prop-set-design.md`; `board/to-spec.md` (the validation item, to be
triaged from `to-spike.md`).

## 2026-06-26 — `deusex con`: remaining `.con` field semantics resolved (supersedes "MoveCamera under-decoded")

Supersedes point 10 of the `deusex con` entry above ("MoveCamera(6) is under-decoded … needs a
follow-up decode spike … round-trips as opaque"). That follow-up spike ran
(`spikes/2026-06-26-deusex-con-remaining-field-semantics.md`) and resolved the last unknowns:

- **MoveCamera is NOT under-decoded for any real data.** The 3-int wire form (`cameraType`,
  `cameraPosition`, `cameraTransition`) is complete for 100% of the corpus (1592 events, all
  `cameraType` ∈ {Predefined(0), Random(3)}, all 12 bytes). The 10-field class form only serializes
  for `CT_Speakers`/`CT_Actor`, which no conversation uses — so authoring those is the only
  (no-real-impact) deferred gap, NOT a blocking decode. `cameraTransition` round-trips as a raw int
  (its `TR_*` meaning is unresolved — corpus shows `-1`/`0`).
- **Check-event jump polarity is NON-uniform** (load-bearing): CheckFlag jumps on ALL-flags-MATCH,
  CheckObject on FAIL (`failLabel`), CheckPersona on TRUE. The `if {cond} then/else` lowering carries
  a per-event-type polarity constant + a test.
- **Opaque fields named:** Speech spare bool = `bBold` (`bold?`), trailing int = `speechFont`
  (`font?`); Animation int1/int3 = `mode`/`bFinishAnim`. Only `Choice.unrecognized1`,
  `MissionFile.unrecognized1`, Animation `int2` stay round-trip-opaque.

Also folded in (two cold spec-review rounds): the `choice` `skill` gate is a `-1` conditional gate
(parallel to `goal done`); `Jump.conversationId` = `-1` for same-conversation; `give`/`take` compile
defaults (`amount`=1, omitted `from`/`to` = empty `-1` ref); conversation `id` is persisted-once and
never renumbered by reorder (it is externally referenced); bare-scalar payload forms are sugar over
the single-key-map invariant.

**Refs:** `spikes/2026-06-26-deusex-con-remaining-field-semantics.md`;
`specs/2026-06-26-uedcli-deusex-con-tool-design.md` (revised).

## 2026-06-26 14:10 UTC — Class-property schema parses the game's REAL `.u`, never the stub cache

**Decision:** The class-property schema extraction (the `actor prop` validator's source) reads a
class's properties by parsing the **game's own `.u` packages directly**, and **MUST NOT consult the
v69 stub cache** (`.uedcli/cache/stubs/`).

**Why stubs are the wrong source.** Stubs exist for exactly ONE reason: to let the **non-DeusEx,
UT-lineage UED22 editor** load DeusEx packages. UED22's `Engine.u`/`Core.u` differ from DeusEx's, so
the real DeusEx `.u` won't load into that editor — the stub pipeline converts v68→v69 (stripped,
recompiled against UT's Engine/Core) purely so the editor can open them at materialize. The schema
extraction parses `.u` **bytes ourselves** (the `dxpkg` export-table reader — pure Python, no editor,
proven on v68 AND v69), so it has **no use for the conversion**: it should read the ORIGINAL package,
not an editor-oriented stand-in. Reading a stub would also be subtly wrong — a stub is recompiled
against UT's Engine/Core, so its inherited base-class properties are UT's, not the game's.

**Consequence — schema source is the substrate's real game packages, parsed directly:**
- For the **DeusEx substrate**: the v68 install code (`repo_paths.install_system_root()` —
  `Engine.u`/`Core.u`/`DeusEx.u`/`DeusExItems.u`/…) plus repo-authored code (`System/`, `LUM/`, e.g.
  `LUM_Core.u`). This is a **different search path from `packages.substrate_search_dirs`** (which is
  editor-load-oriented: it leads with the UT-lineage `uned/UED22/` and the stub cache). The schema
  path drops the stub cache and the UT-lineage substrate where it would mis-answer the game's classes.
- Generic-UE1: schema = the packages of the GAME the level targets, never the editor's stand-ins.
- **Honest cost:** for DeusEx this makes schema-buildability depend on the gitignored v68 install
  being present. Per the no-fallback directive, an absent package errors (`Cannot validate <Class>`)
  — no silent degradation. (This supersedes the round-2 framing that "the committed UED22 substrate
  covers the common classes" — that substrate is the editor's, not the schema authority.)

**Open (for the extraction spec to pin):** the exact schema search path and whether the committed
UT-lineage `Engine.u`/`Core.u` is ever an acceptable base-class source (a DeusEx class's OWN `var`s
are identical between v68 original and any v69 recompile, so the divergence risk is confined to
DeusEx-modified ENGINE/CORE base properties — the spec decides whether to require the v68 install
engine/core or tolerate UT's).

**Context:** Andrzej, reviewing where uedcli looks for `.u`: "This mechanism really shouldn't need to
look at stubs, because it's being parsed by us. The only reason stubs exist is to be able to start
non-DeusEx UnrealEd (which has Engine.u/Core.u differences, so the DeusEx .u packages won't work)."

**Rejected:** *reuse `packages.substrate_search_dirs` as-is for schema* (it leads with the
UT-lineage substrate + stub cache — wrong authority for the game's classes); *parse a v69 stub for
schema* (recompiled against UT Engine/Core, so inherited base props would be UT's).

**Refs:** `spikes/2026-06-26-class-property-extraction.md`;
`specs/2026-06-26-uedcli-actor-prop-set-design.md` ("Dependency & sequencing"); supersedes the
schema-source note in the 2026-06-26 12:41 UTC entry.

## 2026-06-26 — `deusex con`: conversation `id` is internal-only — DROP the persisted/stable-id rule

Supersedes the "conversation `id` is persisted-once and never renumbered by reorder (it is
**externally referenced**)" point in the two earlier 2026-06-26 `deusex con` entries. A spike
disproved the external-reference premise.

**Decision:** The conversation `id` (`conversationID`) is **not stored and not author-controlled** —
`compile` **derives it from manifest order** and re-resolves every cross-conversation `jump:` by
name, so reordering is free. `con.yaml`'s `conversations` reverts to a **plain ordered name list**
(no per-entry `id`). `new`/add no longer read-modify-write an id (`max+1` machinery removed) — they
just add a name to the order list, which keeps those commands purely additive.

**Context:** Andrzej's hypothesis ("levels don't bind by id — spike it"). The binding spike
(`spikes/2026-06-26-deusex-con-binding-by-name-not-id.md`) found, across all 1201 decompiled
DeusEx/ConSys classes: `conID`/`conversationID` has **zero readers** (only two `var` decls — one
commented "Internal Conversation ID" — and two `=0` inits); the only conversation finder is
`ConListItem.FindConversationByName(Name)` (no `…ById`); `ConversationTrigger.conversationTag` is a
`name`; every conversation-owning actor carries `var(Conversation) String BindName`. So levels bind
by name/`BindName`, and the numeric id is internal linkage only (the cross-conversation `Jump.conID`,
which compile re-resolves by name).

**Rejected:** *persist + never-renumber* (the prior rule) — unnecessary once nothing external reads
the id; derive-from-order is simpler and keeps internal jumps consistent because they resolve by
name. *Author-controllable `id:`* — no consumer needs it.

**Residual caveat / revisit trigger:** the runtime selector bodies (`ConPlay*.SetConversation`/
`StartConversation`) are retail-stripped, so "id is dead data" is structural, not body-proven
(HIGH on binding-by-name, MEDIUM-HIGH on the corollary). If a hidden id reader ever surfaces,
reintroduce an OPTIONAL `id:` pin — derive-from-order stays safe regardless.

**Refs:** `spikes/2026-06-26-deusex-con-binding-by-name-not-id.md`;
`specs/2026-06-26-uedcli-deusex-con-tool-design.md` (manifest + equality-bar sections, revised).

## 2026-06-27 — De-containerization investigation: native-first is feasible; stub rationale corrected; D2 scope is the open decision

**Decision (the part that IS decided):** Andrzej directed an investigation into removing
uedcli's entire Docker/wine/`.exe` stack by going native, and specifically to
reverse-engineer texture + mesh extraction to minimize `.exe` dependency. The
investigation (spike series `spikes/2026-06-27-decontainerize-uedcli/`, roadmap
`specs/2026-06-27-uedcli-decontainerization-roadmap-design.md`) establishes native-first
as **feasible**, with the work decomposed and the long pole isolated. The
texture/qualify/package-write/stub-deletion pieces are PROVEN or low-risk and are the
direction for new work. **What is NOT yet decided is the geometry strategy and end-state
scope** — see the spec's open questions (esp. Q0); those belong in `to-resolve.md`.

**Findings that are durable facts (correct/extend the 2026-06-21/22 stubbing entries):**
- **The stub rationale is mesh-format + `Engine.u`/`Core.u` divergence, NOT package
  version v68-vs-v69.** UED22's UCC reads v68 fine (already noted 2026-06-22). Confirmed
  concretely: DeusEx `FMeshVert` = 8-byte int16 (X,Y,Z,pad) vs stock Unreal's 4-byte
  packed dword (178/178 `DeusExDeco.u` meshes). Stubs exist only to make the UT-lineage
  UED22 editor load DeusEx code; **native read+write obviates stubbing entirely** (the
  whole `stub.py`/`uscript_rewrite`/cache pipeline + UCC `make`/decompile + umodel die).
- **Native texture decode is pixel-EXACT vs `UCC batchexport`** across the whole install
  (v61/68/69, 100% P8); reproducible harness committed. Replaces the texture container seam.
- **Native package-CONTAINER write is byte-exact** on real `.dx` maps (incl. a 4.7 MB
  full-file round-trip). The container writer (header/name/import/export tables, layout,
  offsets) is proven; new-body synthesis (actor/`ULevel`/`Model`), GUID/generation minting
  are mechanical-but-untested.
- **Native qualification** replaces `OBJ DEPENDENCIES`/`OBJ LIST CLASS`: a `.dx` import
  table already carries fully-qualified refs; authored content resolves via a manifest
  name→package index (1.8% global collisions).
- **The dominant remaining work is the offline BSP/CSG `Model` build (already specced as
  "D2", `specs/2026-06-24-uedcli-offline-bsp-engine-design.md`) PLUS completing+inverting
  the incomplete `Model` serial-read format** (`spikes/2026-06-25-umodel-serialize-format.md`,
  Nodes/Verts/Leaves still TBD). The game loads pre-built BSP and never CSG-rebuilds, so
  geometry must be built offline (premise needs a game-side load probe).

**Important reframing of D2 (a real decision for Andrzej, NOT taken here):** `decisions.md`
2026-06-24 12:40 DEMOTED D2 to an optional, measurement-gated upgrade, with D0 (editor
drop-warnings) + D1 (saved-build reader) as the planned BSP ground-truth path. But D0/D1
are editor-dependent, so they do NOT serve an editor-free pipeline — **de-containerization
is precisely the justification that would PROMOTE D2 from optional to required.** Whether
to make that commitment (vs an editor-`MAP REBUILD`-only-geometry intermediate that keeps
the rest native) is the pivotal open question.

**Rejected (within the investigation):** treating native mesh decode as on the critical
path (umodel only feeds stubbing, which dies — so it's optional, for a future mesh
catalog/preview); claiming `Model` (de)serialization is a free inverse (the read format is
incomplete); deleting the editor/Docker image wholesale (it must survive as a build-time
differential-verify ORACLE for D2 — distinct from the runtime authoring loop being removed).

**Refs:** `specs/2026-06-27-uedcli-decontainerization-roadmap-design.md`;
`spikes/2026-06-27-decontainerize-uedcli/` (README + 01–06 + harness); extends/corrects the
2026-06-21 and 2026-06-22 package-stubbing entries; references the D2 design spec +
`decisions.md` 2026-06-24 12:40 / 2026-06-26 (partition gate cleared).

## 2026-06-28 18:52 UTC — `Location` is canonical in the typed field only; drop the `props` mirror

**Decision:** An actor's `Location` lives in **one** place — the typed `Actor.location` field
(exact `Decimal`, what `move`/`rotate`/`translate`/bounds mutate). `model._parse_actor` no
longer ALSO appends a `('Location', …)` entry to `actor.props` (it now branches
`Location`/`Name`/else, so both `Location` and `Name` are kept out of `props`). `emit_actor`
**skips any `Location` props entry** and emits the line solely from `actor.location` (at the
trailing slot, before the `Brush=` ref / `Name`). This makes the parser consistent with how
every model-side constructor already builds an actor (`location=` field, no props copy).

**Context:** Investigating a from-scratch `level apply --to-map-file` H3 post-verify failure,
the materialized-vs-authored diff reduced to origin actors (`LevelInfo0`, a carved brush)
carrying an explicit `Location=(0,0,0)` that survived canonicalization while the editor's
re-export omits it. Root cause: `Location` was **dual-stored** — parsed into `actor.location`
AND mirrored into `props`. `normalize_actor` nulled the field for an origin actor, but
`emit_actor`'s `Location` branch (`elif key == "Location" and a.location is not None`) then
fell through to the generic `{key}={val}` else and re-emitted the **stale props string**,
defeating the strip. A first commit (`bdd33a52d`) patched the symptom (also delete the props
entry in `normalize_actor`); Andrzej then asked why `Location` is denormalized at all and
directed removing the dual-storage. (The "6 editor `Camera` extras" that earlier looked like a
second cause were a **red herring** — a live `MAP EXPORT` artifact that never persists into the
saved `.dx`; H3 verify re-exports the saved `.dx`, where they are absent.)

**Rejected:**
- *Props-canonical, `actor.location` a derived property over `props`* (Andrzej's literal first
  phrasing) — a `location` setter must format `Decimal`→`(X=…)` with `emit`'s formatter, but
  `emit` imports `model`, so `model` can't import it (circular); it would text-quantize
  `location` to 6 dp on every assignment; and it wouldn't even preserve the source line position
  without extra in-place-replace logic. The field-canonical direction kills the drift more
  simply and changes no call site.
- *Keep the dual-store, fix only `normalize_actor`* (the `bdd33a52d` approach) — treats the one
  symptom while leaving the field/`props` drift footgun live for every other write path
  (`move`/`rotate`/`translate` already update only the field, so the props copy is perpetually
  stale and merely ignored). Removing the denormalization removes the whole class.

**Consequence:** A *parsed* actor's `Location=` line now emits at the fixed trailing slot rather
than its original source position — invisible to `canonical_actor_t3d` (props are sorted there
and `Location` is positioned identically on both sides of every compare) and to correctness;
parse→emit is idempotent. `emit_actor` also defends against a stray `('Location', …)` props
entry (the legacy `actor set` stub can still append one) by skipping it, so it can never
double-emit. Supersedes the "`Location` — dual-stored … + a `props` mirror" description in the
2026-06-26 10:53 UTC `actor prop` entry.

**Refs:** `model._parse_actor`, `emit.emit_actor`, `normalize.normalize_actor`;
`tests/test_normalize.py` (origin-canonicalization regressions added in `bdd33a52d`, still
valid under the field-canonical model).

## 2026-06-29 — Class-property schema source is the configured `paths`, not a hardcoded schema search list

Extends the 2026-06-26 14:10 UTC schema-source decision (schema = the game's real `.u`, never the
stub cache). That entry pinned *what* to read (real `.u`) but left the *search path* as a bespoke
hardcoded list (`repo_paths.install_system_root()` + repo `System/`/`LUM/`). This refines *how* the
set is resolved; it does not reverse the no-stub-cache rule.

**Decision (Andrzej, 2026-06-29):** for `actor prop`'s class-property validation, **which properties
are available is pulled from the configured `paths`** — the layered package-path scheme introduced by
`specs/2026-06-29-uedcli-global-cli-projects-design.md` (the project `uedcli.toml` overlay globs ++
the target substrate's `config.toml` base globs, composed project-shadowing-base, §3.4 there). The
`.u`-class-property extraction is just another **`.u` consumer of the composed `paths`** (that spec
§7, alongside closure/missing/qualify/`package load`), filtered to the `.u` subset. It must take its
search path from the resolved-`paths` machinery, NOT re-implement `install_system_root()`.

**Context:** the global-CLI-projects spec replaces the hardcoded `packages.substrate_search_dirs`
with declared per-layer globs; the `actor prop` schema source is exactly such a consumer, and a
hardcoded second search path would drift from the project/substrate the rest of uedcli resolves
against (and would miss a project's custom/override classes). Surfaced reviewing the `actor prop`
spec against the new global-CLI design.

**Consistency with no-stub-cache (no tension):** a substrate's `paths` point at the **real** game
`.u` (the authoritative source); the stub cache is a derived, editor-load-only artifact computed from
those and is **never on the authored `paths`** — so a `paths`-driven schema read reads the originals
by construction. The `actor prop` spec's `install_system_root()` + repo-`System/`/`LUM/` text is the
pre-global-CLI form of this composed `paths`.

**Rejected:** *a bespoke hardcoded schema search list* (`install_system_root()` + repo dirs) — drifts
from the resolved package paths, doesn't see project overlays/overrides, and re-entrenches a
DeusEx-specific path against the generic-UE1 direction.

**Sequencing note:** the global-CLI `paths` mechanism is itself **pending ratification** (its §10
decisions fold to this ledger on sign-off); whichever of {global-CLI `paths`, the `.u`-extraction
subsystem, `actor prop`} lands first adapts to the other, but the constraint stands: schema reads the
configured `paths`.

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§3.4, §7, §12);
`specs/2026-06-26-uedcli-actor-prop-set-design.md` ("Schema source" / "Dependency & sequencing");
extends `decisions.md` 2026-06-26 12:41 UTC and 14:10 UTC (class-property schema extraction).

## 2026-06-29 05:18 UTC — Global-CLI: drop migration; container overlay = dynamic mount + dynamic ini Paths

Resolves the two open decisions in `specs/2026-06-29-uedcli-global-cli-projects-design.md` §10.

**Decision (Andrzej):**
- **No migration tooling.** Existing in-repo `.uedcli/` sessions + the tracked `texture-catalog/`
  are NOT carried over; there is no `uedcli migrate` verb. The **legacy fallback stays** (no
  `uedcli.toml`/`config.toml` => exact current behavior) so nothing breaks on upgrade; a user opts
  into the new layout by creating the configs, starting fresh. Plan slice **G is dropped**.
- **Container overlay = option (a): a programmatic per-project `docker run -v` mount AND dynamic
  `[Core.System] Paths` ini editing.** The mount makes a project's assets *visible* in the
  container; the editor only *searches* its ini `Paths` list, so the per-project apply/preview must
  ALSO prepend the project's `Paths=` entries **before** the base substrate's (project-first =>
  shadowing matches the host-side resolver, spec section 3.4). Reuses the existing live ini-edit
  machinery (`packages.write_paths_and_reload` / `ensure_load`), extended to add the project mount
  root + project-precedence ordering. (Plan slice **H**.)

**Rejected:**
- *A `uedcli migrate` that carries old sessions* -- Andrzej: ignore migrations. The durable record
  is the committed maps/T3D trees; un-applied sessions are transient and not worth the carry code.
- *Option (b): lean on de-containerization first* -- deferred in favor of building the overlay now;
  the two efforts still converge.
- *Mount-only (no ini edit)* -- insufficient: a qualified `Texture=`/package isn't found just by
  being on disk; it must be on `Paths` (and OBJ-LOADed), confirmed live 2026-06-20
  (`unrealed/quirks.md`). Hence the dynamic-ini half is load-bearing.

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` section 8/10;
`plans/2026-06-29-uedcli-global-cli-projects-plan.md` (slice G dropped, H = a); `packages.py`
(`write_paths_and_reload`, `ensure_load`, `_remap_to_container`).

## 2026-06-29 05:18 UTC — `actor prop`: fold typed + enum-value + array-bounds validation into v1

**Decision (Andrzej):** `actor prop`'s property validation is **not name-only** -- it folds in
**type + enum-value + array-bounds** checking from the start, using the offline `.u` typed decode
the 2026-06-26 `uproperty-typed-decode` spike proved feasible (0 failures across 49 packages, v68 &
v69). So `--set CsgOper=CSG_Subtrct` (bad enum value), `--set KeyPos(9)=...` (past the `[8]` bound),
and a wrong-typed value all error at validation, before any mutation -- alongside the unknown-name
error (decision 2026-06-26 12:41, no fallbacks).

**Context:** the class-property extraction (P1) was specced name-only-first with typed as a flagged
fast-follow. Andrzej chose to fold it in now: the decode is reliable, marginal cost is low, and it
catches real authoring bugs.

**Rejected:** *name-only v1 + typed fast-follow* -- superseded; no reason to ship the weaker check
when the typed decode is ready.

**Refs:** `plans/2026-06-29-uedcli-actor-prop-plan.md` (P1 `Prop{kind,type_ref_name,array_dim}` +
enum value names now ENFORCED in P2); `spikes/2026-06-26-uproperty-typed-decode.md`;
`specs/2026-06-26-uedcli-actor-prop-set-design.md`.

## 2026-06-29 06:02 UTC — Ditch the in-repo ignored `.uedcli/`; a project gets a TRACKED `.uedcli/` config dir

**Decision (general direction, Andrzej):**
- **The in-repo gitignored `.uedcli/` runtime state goes away.** Sessions/caches/locks/tmp no longer
  live in the content tree; they move to the per-user global home (global-CLI design). Consistent
  with the no-migration decision (2026-06-29 05:18 UTC): existing in-repo state is **dropped, not
  carried**, and the `.gitignore` `.uedcli/` line is removed.
- **That frees the `.uedcli/` name inside a project tree, so the project's TRACKED uedcli config
  lives under one `<project>/.uedcli/` dir** instead of scattering files at the root. Shape:
  ```
  <project>/.uedcli/
    config.toml         # the project marker + config (substrate, paths, catalog, id, ...)
    texture-catalog/    # project classification (tracked)
    prefabs/            # project prefab library (tracked)
  ```
  Tracked, travels with a clone, self-describing. Supersedes the earlier "project marker = a bare
  root `uedcli.toml`" + tracked `texture-catalog/`/`Prefabs/` at the repo root.

**Why it's now clean:** the only thing that made a tracked `.uedcli/` a footgun was the existing
"`.uedcli/` = gitignored runtime state" meaning (the repo `.gitignore` + the global home). Removing
the in-repo ignored state leaves `.uedcli/` with a single meaning *inside a project tree*: tracked
project config.

**Open sub-point (to settle) — the GLOBAL home name.** Keeping the global home at `~/.uedcli/`
leaves a same-basename / opposite-tracked-ness twin: `~/.uedcli/` (machine-local STATE) vs
`<project>/.uedcli/` (tracked CONFIG) — mild, but a standing "why is one tracked and one not" snag.
Cleaner end-state: move the global home to **XDG** — `~/.config/uedcli/` (config) +
`~/.local/state/uedcli/` (sessions/caches) — so `.uedcli` means "project dir" exclusively and `$HOME`
follows platform convention. **Lean: XDG; pending Andrzej** (flagged).

**Rejected:**
- *Keep the in-repo ignored `.uedcli/` AND track config elsewhere* — the source of the original
  collision; ditching the ignored state is what makes the name reusable.
- *Track config under a non-dot `<project>/uedcli/`* — viable (avoids the dotdir-is-ignored
  surprise) but loses the tidy single-dotdir grouping; superseded by ditching the ignored meaning.
- *A mixed tracked+ignored `.uedcli/` with gitignore negation* — fragile pattern; moot now that the
  project holds no ignored state.

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§3 marker/schema, §5 layout — to
reconcile on ratification); extends the 2026-06-29 05:18 UTC no-migration decision; `board/flagged.md`
(the global-home XDG sub-point).

## 2026-06-29 06:48 UTC — Prefab naming (slashes/subdirs) + texture model: classification in-project, images in home cache, clone-classification across projects

Refines the texture storage in `specs/2026-06-29-uedcli-global-cli-projects-design.md` §6 and pins
prefab naming. Builds on the 2026-06-29 06:02 UTC decision (tracked `<project>/.uedcli/` config dir).

**Prefabs (Andrzej):**
- Stored under **`<project>/.uedcli/prefabs/`** (the project's tracked config dir).
- **Subdirectories are allowed and become part of the prefab NAME** — so a prefab name can contain
  slashes: `<project>/.uedcli/prefabs/furniture/chairs/office-chair.<ext>` ⇒ name
  `furniture/chairs/office-chair`. Namespacing is NOT required (a flat `prefabs/foo` ⇒ name `foo`),
  but the dir tree is the organizing/naming mechanism. (Supersedes the repo-root `Prefabs/` library.)

**Texture model (Andrzej) — three clean rules:**
1. **Classification (the catalog: tags/colors/description) lives ONLY in the project**, tracked at
   `<project>/.uedcli/texture-catalog/`. **There is NO home/per-user catalog and NO per-substrate
   "base" catalog** (drops the spec's base+project two-catalog merge and the
   `[substrates.*].catalog` config key). Keyed by **pixel-hash** (the durable identity).
2. **Texture IMAGE files are NEVER stored in the project** — they are derived (decoded from the
   package files) and live in a **content-addressed cache in the home dir** (`~/.uedcli/` or the XDG
   cache, per the pending global-home decision): `…/textures/data/<pixel-hash>.png` +
   `…/textures/packages/<pkg-hash>.<schema>/index.json`. Regenerable any time via `texture sync`; a
   wipe costs only a re-decode, never classification.
3. **Share classification across projects by CLONING, not a shared catalog.** A verb (e.g.
   `texture classify clone --from <other-project>`) copies classification entries from another
   project's catalog into this one, **matched by pixel-hash** — so common Deus Ex assets (identical
   pixels ⇒ identical hash) inherit their tags/colors/description **without re-running
   classification**. This replaces the earlier "configurable shared base-catalog path" idea: no
   shared mutable catalog, just an explicit copy keyed on content.

**Why:** classification is expensive human/LLM work → belongs with the project, tracked and
committed; images are cheap to regenerate → belong in a derivable cache, not the tracked tree;
re-classifying the same vanilla assets per project is the waste, solved by a content-keyed clone
rather than a shared catalog with its sharing/staleness problems.

**Rejected:**
- *A per-substrate base catalog (shared, configured path)* — the prior spec model; superseded.
  Cloning by pixel-hash gives the same "classify common assets once" benefit without a shared
  mutable store or a base/project merge.
- *Storing decoded images in the project* — they're regenerable; tracking them bloats the tree.
- *Namespaced-but-flat prefab names* — subdir-as-name is simpler and gives free organization.

**Refs:** reconciles `specs/2026-06-29-uedcli-global-cli-projects-design.md` §3.5/§5/§6.2 (to update);
extends the 2026-06-29 06:02 UTC tracked-`.uedcli`/global-home decision; `decisions.md` 2026-06-22
(texture catalog — pixel-hash identity, classification-is-expensive).

## 2026-06-29 08:09 UTC — The `.con` conversation tool is a STANDALONE `dxconcli` prod tool, not `uedcli deusex con`

**Decision (Andrzej):** the Deus Ex conversation tool (source ↔ `.con`) is its **own production
CLI, `dxconcli`** — a separate tool, NOT a subcommand under `uedcli` (was `uedcli deusex con`). Its
verbs become `dxconcli <verb>` (`new`/`compile`/`decompile`/`validate`/`search`/`voices`/…).

**Why it stands alone:** the tool was already specced **session-free** and **substrate-specific** — a
`.con` spans missions and references mission-wide tables, so it is not level-design and needs none of
uedcli's session/project/editor/store machinery. Splitting it keeps uedcli focused (a generic
UnrealEngine-1 *level* tool) and lets the conversation tool ship and version as an independent prod
tool. The proven two-layer codec is unchanged — only the packaging/entry point moves out of uedcli.

**What carries over unchanged:** the format (the 2026-06-25/26 spikes + `deusex-con-format.md`), the
two-layer architecture (`con_codec.py` byte-exact ↔ `con_source.py` high-level tree, `con_model.py`),
and every `deusex con` design decision (2026-06-26 entries). Those decisions still hold; only the
tool's NAME and home change — `dxconcli` (likely its own `Tools/dxconcli/` package + entry point,
sibling to `Tools/uedcli/`), reusing the committed format-spike harness.

**Rejected:** *keep it as `uedcli deusex con`* — bundling a Deus-Ex-conversation prod tool inside the
generic level tool muddies uedcli's scope; the tool is self-contained and benefits from shipping
separately.

**Refs:** `specs/2026-06-26-uedcli-deusex-con-tool-design.md` (reframe to `dxconcli`);
`deusex-con-format.md` (consumer); `board/to-plan.md`; supersedes the "session-free, under `deusex`"
packaging note in the 2026-06-26 `deusex con` decision (the format/source decisions there are intact).

## 2026-06-30 06:18 UTC — Project layout: the project dir IS the (conventionally-named) `uedcli/` dir; project root = its parent

Supersedes the dotdir naming of the 2026-06-29 06:02 UTC entry ("a project gets a TRACKED
`.uedcli/` config dir") and refines the catalog/prefab locations of the 2026-06-29 06:48 UTC entry.
The tracked-not-ignored direction, the no-base-catalog texture model, and the pixel-hash clone all
stand; only WHERE the tracked config/trunk lives and how a project resolves change.

**Decision (Andrzej):** a uedcli project is organized around a single **project dir** that holds
everything uedcli manages, sitting INSIDE the user's own content tree:

```
my_cool_project/              # the PROJECT ROOT — the user's tree (docs, their own stuff, ...)
  Maps/*.dx Textures/*.utx LUM/*.u   # the project's package overlay (the `paths` globs)
  uedcli/                     # the PROJECT DIR — uedcli's home; conventionally named `uedcli`
    config.toml               #   the project config + marker (substrate, paths, id, name)
    texture-catalog/          #   classification (tracked; NO images — they are derivable)
    maps/<map>/               #   the T3D-tree TRUNK per map (maps/20_AireGardens/{actors/,order,packages,name})
    prefabs/                  #   the prefab library (subdirs become prefab names)
    # ...whatever else uedcli needs...
```

- **The project dir is the handle uedcli is pointed at** (`--project my_cool_project/uedcli`); it is
  identified by containing a `config.toml`. The **dir name is conventionally `uedcli` but
  configurable** — any name works when pointed at explicitly; the convention is what auto-discovery
  keys on.
- **The project root is the PARENT of the project dir** (`my_cool_project/`), `.git`-style — the
  project dir is to the root what `.git/` is to a repo. **`config.toml`'s `paths` globs resolve
  against the project root**, so `Maps/*.dx:Textures/*.utx:LUM/*.u` reach the user's root-level
  content unchanged (matches dx_lum's current layout). The container overlay (decision 2026-06-29
  05:18 UTC, option (a)) **mounts the project root**.
- **The project config file is `config.toml`** (inside the project dir), REPLACING the bare-root
  `uedcli.toml`. This is uniform: *every* uedcli home dir holds a `config.toml` — the per-user
  global home `~/.uedcli/config.toml` (substrate/base config) and a project's
  `<project>/uedcli/config.toml` (project overlay) are the same filename, differing only by schema
  (detectable by content: `[substrates.*]` vs the project keys).
- **T3D-tree trunks live under `<project-dir>/maps/<map>/`** — the authored source of truth for each
  level, tracked and committed. `level apply --to-t3d-tree` defaults its destination there (by level
  name), overridable with an explicit `--out`. Built `.dx` artifacts are NOT uedcli-managed source —
  they go to the content area like any other package (e.g. `Maps/*.dx` at the root, via
  `--to-map-file`).
- **Catalog and prefabs default under the project dir** (`texture-catalog/`, `prefabs/`), overridable
  via `config.toml` keys; both resolve relative to the project dir (not the root).

**Resolution (§4 ladder, refined):** `--project`/`UEDCLI_PROJECT` accept a path to the project dir
(or its `config.toml`). **Walk-up auto-discovery looks for a conventionally-named `uedcli/config.toml`
under an ancestor of cwd** — project dir = `<ancestor>/uedcli`, root = `<ancestor>`. A
non-conventionally-named project dir is NOT auto-discoverable (the name is unknown) and needs explicit
`--project`/env or a session's recorded `id` (tier 3, unchanged).

**Why:** the user wants one self-describing, tracked dir for everything uedcli owns (config,
classification, map trunks, prefabs) that travels with a clone, kept cleanly apart from their own
files — while the engine-facing package content (the `paths` overlay) stays at the natural project
root so it loads exactly as the engine sees it. Naming it `uedcli` (not a dotdir) makes it visible
and obvious; the `.git`-style parent-as-root keeps `paths` and the container mount natural.

**Rejected:**
- *The `.uedcli/` dotdir at the project root* (2026-06-29 06:02 UTC) — superseded: a visible,
  conventionally-named `uedcli/` is clearer and removes the dot-dir-is-hidden surprise. The thing
  that made a dotdir attractive (disambiguating from the gitignored in-repo state) is moot — that
  state is gone (06:02).
- *Project dir as the `paths` anchor* — rejected (Andrzej): real projects keep their package content
  at the tree root alongside the project dir, so anchoring `paths` at the parent root makes
  `Maps/*.dx` work unchanged; anchoring at the project dir would force `../` globs.
- *Keeping `uedcli.toml` as the project config name* — superseded by `config.toml` for uniformity
  across uedcli home dirs.
- *T3D trunks scattered via `apply --out` only* — the `maps/<map>/` convention gives each level a
  stable tracked home and a sensible default apply target.

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§2/§3.3/§3.5/§4/§5/§6.2/§6.4
reconciled); supersedes the dotdir of `decisions.md` 2026-06-29 06:02 UTC, refines 06:48 UTC;
`board/flagged.md` (global-home name + the derived calls). `config.py`'s `uedcli.toml` /
`Project.root`-is-the-content-dir assumptions are now stale — flagged for the slice-B/E rebuild.

## 2026-06-30 18:47 UTC — Global-CLI rulings: home stays `~/.uedcli/`; substrate = game (one install, many games); drop the package manifest; derived calls confirmed

A batch of rulings (Andrzej) closing the open global-CLI questions surfaced after the 2026-06-30
06:18 UTC project-layout decision.

**Decisions:**

1. **The global home stays `~/.uedcli/`.** The XDG split (`~/.config/uedcli` +
   `~/.local/state/uedcli`) is rejected — one obvious home dir for per-user config + machine-local
   state. The same-basename concern that motivated XDG is moot now that the project dir is the
   non-dot `uedcli/` (2026-06-30 06:18 UTC). *Rejected:* the XDG split (more dirs + platform
   machinery for no real gain here).

2. **A substrate IS a game; one uedcli install serves many games.** The per-user
   `~/.uedcli/config.toml` declares each game's asset files once (`[substrates.<game>].paths` +
   `image`); each project's `config.toml` picks its game via `substrate = "<game>"`. So a single
   install works across Deus Ex, Unreal, etc. — affirming and locking the multi-substrate model the
   spec already carried (§3.2/§3.3). **Terminology unchanged:** the schema key/term stays
   `substrate` (deliberate, generic-UE1 — 2026-06-23), documented as "one substrate per game"; NOT
   renamed to `game`. *Rejected:* a single-game tool (the substrate split already made the core
   game-agnostic); renaming `substrate`→`game` (churns the established term for no capability gain —
   flagged for objection).

3. **No stored package manifest.** The session state tree's `packages` file (the loadable-package
   manifest) and the `package load` verb are dropped. The set of packages to load/resolve is
   **derived on demand** from the level's fully-qualified `Texture=`/`Class=`/object refs
   (qualification already stamps the owning package onto every ref — `qualify.export_and_qualify`)
   and resolved to files via the composed `paths` (§3.4). *Rejected:* keeping the stored manifest
   (redundant with the qualified refs the T3D already carries; an extra artifact to keep in sync).
   - **Open sub-point (flagged, not decided):** transitive content deps a level never names directly
     (e.g. `CoreTexMetal`→`CoreTexDetail`) are NOT in the level's refs, and a qualified `Texture=`
     does **not** auto-demand-load its package (`unrealed/quirks.md`). So the derivation likely must
     still walk the import-table transitive closure on demand (computed, not stored) rather than rely
     on engine demand-load. Whether to keep closure-walking or change the load contract is the one
     thing the manifest drop leaves to pin at build time.

4. **The three derived calls of the 2026-06-30 06:18 UTC decision are CONFIRMED** (were flagged
   assumptions): project config filename `config.toml`; `level apply --to-t3d-tree` defaults its
   `--out` to `<project-dir>/maps/<level>/` by level name; walk-up auto-discovery keys on the
   conventional `uedcli/config.toml` (a non-conventional name needs explicit `--project`/env).

Also: **`board/to-resolve.md` #1 (workflow / source of truth) is partially resolved** by the layout —
the git-tracked T3D trunk lives at `<project-dir>/maps/<level>/`, sessions merge into it, the `.dx`
is a build artifact (matches `direction.md`). The "test a changeset before merging" step is
**deferred** (Andrzej).

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§3.2/§5/§6.2/§7/§9 reconciled);
`direction.md` (new "Projects, substrates, and the global CLI" section); resolves the
`board/flagged.md` global-home + derived-calls flags; supersedes the "lean XDG" of 2026-06-29 06:02
UTC. The manifest drop's transitive-dep sub-point + the `substrate`-vs-`game` naming are flagged for
the build (`board/flagged.md`).

## 2026-06-30 21:07 UTC — Config key is `game`/`[games.*]` (user-facing), not `substrate`

Refines the 2026-06-30 18:47 UTC point 2 ("terminology kept as `substrate`"): that stands for the
**internal concept/code term** (`substrate` = a game's editor + base packages, generic-UE1,
2026-06-23), but the **user-facing TOML key is renamed `game`** (Andrzej, on seeing the config
example).

**Decision:** in `~/.uedcli/config.toml` the per-game blocks are `[games.<name>]` (was
`[substrates.*]`); `[defaults].game` (was `.substrate`); the project `config.toml` selects its game
with `game = "<name>"` (was `substrate =`); `project init --game` (was `--substrate`); `project ls`
shows a `game` column; the generated back-pointer records `game`. The internal concept and code
symbols (the `substrate` abstraction, `packages.substrate_search_dirs`, the `Substrate` value
object) **keep the `substrate` name** — a substrate maps 1:1 to a game for every game we support, so
the key is `game` while the internals stay `substrate`.

**Rejected:** keeping `substrate` as the user-facing key (the 18:47 lean) — Andrzej reads/says
"game"; the TOML should match. Renaming the internal `substrate` concept/symbols too — out of scope,
churns established code for no user benefit (the term is correct as the generic-UE1 abstraction).

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§3.2/§3.3/§3.5/§4.1/§5 keys
renamed; concept prose keeps "substrate"); `direction.md`; supersedes the user-facing-key half of
`decisions.md` 2026-06-30 18:47 UTC point 2. `config.py` key constants (`substrates`→`games`,
`[defaults].substrate`→`game`, project `substrate`→`game`) folded into the slice-B/E reconcile flag.

## 2026-07-01 04:26 UTC — No per-game editor image: one shared UED22, game paths wired into the ini at launch

Drops the `image` key floated in the global-CLI config (spec §3.2/§3.5).

**Decision (Andrzej):** there is **no per-game editor image** in `config.toml`. A **single shared
UED22 image** is the editor for every game. Per-game/project differences are handled the way the
container overlay already works (decisions.md 2026-06-29 05:18 UTC, option (a)): the game's + the
project's package `paths` are wired into the editor's `[Core.System] Paths` ini **before launch**
(plus the read-only mounts), and each uedcli session gets its **own container instance** of that one
image (the per-session editor `uned-<uuid7>`, already the model). So a `[games.*]` block carries
**assets only** (`paths`) — the `image` key is removed.

**Why one UED22 works for all games:** UED22 is a generic UT-lineage UnrealEd; a game's content
loads via its `paths`, and a game's code the editor can't load directly (Deus Ex v68) is converted
to loadable stubs (decisions.md 2026-06-21/22). The editor is a build/preview tool reached only at
`level apply`/`preview`; nothing about it is game-specific beyond what the ini `Paths=` + stubs
supply.

**Rejected:**
- *A per-game `image` key* (the earlier spec draft) — implies each game needs its own editor build;
  it doesn't. One UED22 + per-launch ini paths covers every game, so the key is dead weight (and it
  vanishes entirely under de-containerization anyway).
- *A built-in default image per game* — same redundancy; there is exactly one image.

**Residual note:** if some future game genuinely needed a different editor build, the internal
`substrate` concept can carry that (it is the abstraction) — but no game we target does, so it stays
out of config. The image name itself is a code/compose constant, not user config.

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§2/§3.2/§3.5/§8, `image` removed);
`direction.md`; builds on decisions.md 2026-06-29 05:18 UTC (container overlay = mount + ini
`Paths=`) and 2026-06-21/22 (stubbing). `config.py`'s `Substrate.image` field + `image` key constant
folded into the slice-B/E reconcile flag.

## 2026-07-01 04:33 UTC — Ditch the `container` config key/knob: container instances are ephemeral and derived

Extends the 2026-07-01 04:26 UTC one-image decision.

**Decision (Andrzej):** there is **no configured container** — the `[defaults].container` config key
is dropped, and container selection is not a user knob. Container instances are **ephemeral and
derived per session/op** (the per-session editor `uned-<uuid7>`; an ephemeral `docker compose run`
for offline UCC/stub work — already the parallel-editors pattern), spun from the single shared UED22
image (2026-07-01 04:26 UTC) and torn down after. Nothing to name in config; `[defaults]` now carries
only `game`.

**Context:** with one shared image and per-session instances, a user-declared container NAME has
nothing to select — every container is a fresh instance of the one image, named deterministically
from the session (or minted for a one-off op). The old `--container` / `[defaults].container` existed
to point at a *standing* substrate/UCC container; the ephemeral-per-op model retires that. Aligns
with de-containerization (containers are transient and shrinking to just the apply/preview path).

**Rejected:**
- *Keep `[defaults].container` for the offline UCC/stub container* — that phase runs an ephemeral
  `docker compose run` from the one image (`parallel-editors.md`), so it needs no configured name.
- *Keep `--container` as a power-user override* — no use case survives the one-image + ephemeral
  model; a container name is an internal derived detail, not user config.

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§3.2/§3.5, `container` removed;
`[defaults]` = `game` only); extends decisions.md 2026-07-01 04:26 UTC (one shared UED22 image).
`architecture.md` "The editor is a per-session, lock-guarded resource" / "Substrate" describe
today's `--container` (current code); its removal is flagged for the slice-B/E build
(`board/flagged.md`).

## 2026-07-01 04:36 UTC — No default game: every project declares `game` explicitly

Extends the 2026-07-01 04:33 UTC config-minimization.

**Decision (Andrzej):** drop `[defaults].game`. A project's `game` key is **required** — there is no
global default and no "sole substrate" fallback; a project `config.toml` omitting `game` is an
error. With `container` and `image` already gone (07-01), `[defaults]` is now empty and **removed
entirely** — the per-user `~/.uedcli/config.toml` is just `[games.*]` blocks.

**Context:** matches uedcli's standing no-silent-default discipline (§4 project resolution,
`--session` selection): a consequential binding — which game's assets + editor a project builds
against — must be explicit, not inherited from an ambient default that could silently bind the wrong
game.

**Rejected:**
- *Keep `[defaults].game` as a convenience* — a silent default game is exactly the ambient foot-gun
  the no-default discipline exists to prevent.
- *Fall back to the sole `[games.*]` when there's only one* — still an implicit bind; a one-game
  world just repeats `game = "deusex"` once per project, which is cheap and honest.

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§3.2/§3.5, `[defaults]` removed,
project `game` REQUIRED); extends decisions.md 2026-07-01 04:33 UTC (ditch container) + 04:26 UTC
(one image). `config.py`: `load_project` must require `game`, and drop `default_substrate` +
`select_substrate`'s sole-substrate fallback — folded into the slice-B/E reconcile flag.

## 2026-07-01 06:16 UTC — Editor loads stubs via an override `Paths=` entry; raw `paths` are analysis-only

Resolves the "composed `paths` vs what the editor actually loads" gap under the new game-`paths`
model.

**Decision (Andrzej):** a game's composed `paths` (the real install `.u`/`.utx`/…) are the
**analysis/authority set** — consumed model-side by closure / missing-check / qualify /
class-property schema. The **editor never loads the raw v68 code** on those paths (UED22 can't).
Instead:
- code deps are **built and cached as v69 stubs on demand** (the existing lazy stub pipeline,
  decisions.md 2026-06-21/22), and the **stub cache is wired into the container as a high-priority
  override `[Core.System] Paths=` entry** — so the editor resolves each code package to its stub;
- content (`.utx`/`.uax`/`.umx`) is wired from the read-only content mounts as today;
- the raw v68 `System/*.u` globs on `paths` are **never** placed on the editor's ini (unchanged from
  today's substrate split, which keeps `install_system_root()` out of the editor load path).

So there are two derived views of a game's `paths`: the **analysis view** (real `.u`, model-side)
and the **editor-load view** (stubs override for code + content mounts). The overlay wiring
(decisions.md 2026-06-29 05:18 UTC, option (a)) prepends the stub cache + project paths ahead of the
baked substrate.

**Rejected:** putting the raw v68 code globs on the editor's `Paths=` (UED22 fails to load them —
the whole reason stubs exist); a separate editor-only `paths` key in config (the stub set is derived
from the analysis `paths`, not separately authored).

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` (§7 analysis consumers, §8 editor
overlay); builds on decisions.md 2026-06-21/22 (stubbing), 2026-06-26 14:10 UTC (schema reads real
`.u`, never stubs), 2026-06-29 05:18 UTC (overlay = mount + ini `Paths=`). Stub-cache home moves
under `~/.uedcli/` (was `<repo>/.uedcli/cache/stubs/`) — flagged for the build.

## 2026-07-01 06:16 UTC — DEFER replacing sessions with git branches; spike its viability first

**Decision (Andrzej):** do **not** replace the store-centric session model with plain git branches
now — it is **deferred**, not adopted and not rejected. The bespoke event-sourced session store
(`session.py`/`replay.py`/`merge.py`/`audit.py`/`integrity.py`) stays the model for the current
design. Its potential replacement — "the T3D tree is real git; a session is a branch; merge is
`git merge`; materialize (`.dx`) is a separate build step" — is captured as a **deferred pivot** in
the global-CLI spec (§9) and **must be spiked before any commitment**.

**Why it's attractive (recorded so it isn't re-derived):** `direction.md` already targets a
git-committed T3D trunk with map files as build artifacts; the trunk is per-actor text
(`maps/<level>/actors/*.t3d` + `order`), which git merges natively; emit is canonical (the
precondition for clean diffs/merges); the manifest is gone. Git branches would parallelize work for
free, and git's per-file (per-actor) 3-way merge ≈ uedcli's hand-rolled per-actor merge — collapsing
the store/replay/merge machinery.

**Why deferred, not taken:** it supersedes the 2026-06-18 store-centric model and a lot of built
code (a real migration); the single-file `order` is a merge hotspot; git merge is textual, not
semantic (intra-actor property conflicts). These need a **spike** (git-merge two divergent T3D-tree
branches: disjoint-actor auto-merge, same-actor conflict, `order` contention) before a spec commits.

**Coupled, therefore also deferred:** *project id = its path* (Andrzej proposed) — clean **iff**
sessions go git-native (nothing machine-local keyed by a move-unstable id; then also drop the
`config.toml` `id`, `project init` uuid minting, and the name→id registry). While sessions stay under
`~/.uedcli/projects/<id>/`, id stays a **uuid** (moving a project would otherwise orphan its
sessions). Also `session start <level>` (resolve a bare level name against `<project-dir>/maps/`) is
adopted as the primary entry point regardless of model.

**Rejected (for now):** adopting the git-branch model immediately (unspiked, high blast radius);
switching id to path immediately (would orphan sessions under the current store).

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` §9 (deferred pivot + spike plan);
`direction.md` "The trunk we want" / "The store is the source of truth"; supersedes nothing —
extends the 2026-06-18 store-centric decision by scoping its possible future replacement.

## 2026-07-01 07:05 UTC — Git-merge-on-T3D-tree spike: viable; the shared `order` file is the one blocker

Result of the spike gated by the 2026-07-01 06:16 UTC deferral (evidence:
`spikes/2026-07-01-git-merge-t3d-tree/`). Does NOT lift the deferral — it de-risks the eventual
decision.

**Finding:** plain `git merge` (default `ort`) on the per-actor T3D tree is a viable replacement for
uedcli's custom 3-way merge. Disjoint per-actor edits/adds auto-merge with **zero** conflict (each
actor is its own file); a same-actor edit conflicts cleanly, scoped to the changed property line
(human/LLM-resolvable); **canonical emit is confirmed load-bearing** — reordering two adjacent
property lines (a semantic no-op a sloppy emitter could produce) caused a *spurious* conflict, so the
sorted/normalized emit invariant must be enforced, not assumed (we already emit that way).

**The one required change: eliminate the shared `order` file.** It conflicts on every concurrent add
(two branches append to the same last line — proven to be pure textual tail-adjacency, not inherent
to ordering). Replace CSG precedence with a **per-actor sortable order key** (fractional / LexoRank,
to avoid renumbering); the spike proved two concurrent adds then merge with zero conflict. Reordering
existing actors genuinely conflicts (correct — it IS a real conflict).

**Bearing:** strengthens the deferred pivot's viability. The residual gate for a future spec is the
migration cost + the worktree-vs-plumbing edit model, NOT merge correctness.

**Refs:** `spikes/2026-07-01-git-merge-t3d-tree/` (findings + harness); informs `decisions.md`
2026-07-01 06:16 UTC (deferral); folded into spec §9.1.

## 2026-07-01 07:20 UTC — Paths-precedence spike: shadowing is enforced HOST-SIDE at apply; editor `Paths` order only governs the by-name path

Result of the live paths-precedence spike (evidence: `spikes/2026-07-01-paths-precedence/`). Confirms
the global-CLI overlay-shadowing design AND refines the mechanism in spec §8.

**Confirmed live:** `[Core.System] Paths` is **first-match-wins** (both orderings; an override dir
ahead of the baked substrate shadows it — H1/H2 with controls). So project-shadows-base is real.

**Refinement (load-bearing):** the editor's `Paths` precedence governs only the **indirect / by-name**
linker path (what `UCC.exe` exercises — and UCC, reading the ini fresh per invocation, is the reliable
probe). uedcli's shipped `apply` loads each package with an explicit `OBJ LOAD FILE=<resolved path>`
(no live console verb does a by-name `Paths` search — `OBJ LOAD PACKAGE=` is a no-op). Therefore **at
apply, shadowing is decided HOST-SIDE** by the composed-`paths` resolver picking the file (§3.4,
first-wins), NOT by the editor at load time. The host resolver must impose project-shadows-base when
selecting files to `OBJ LOAD FILE=` (it already does); the ini `Paths=` (for the by-name/demand-load
path) must still be written project-first, stubs ahead of substrate, so the two agree.

**Two durable UnrealEd facts (→ `unrealed/quirks.md`):** (1) the running GUI editor rewrites
`unrealtournament.ini` from boot config and clobbers a post-launch `Paths=` edit → the ini edit + its
consuming op must be **one atomic `docker exec`**; (2) only **directory-glob** `Paths=` entries are
searched (a full-file-path entry is ignored).

**Rejected framing (corrected):** "the editor shadows a base package via `Paths` order at load time"
— false for the apply path (explicit `OBJ LOAD FILE=` bypasses `Paths`); shadowing there is host-side.

**Refs:** `spikes/2026-07-01-paths-precedence/` (findings + `run_precedence.sh`/`run_shadow.sh`);
folded into spec §8 + `unrealed/quirks.md`; confirms `decisions.md` 2026-06-29 05:18 UTC (overlay =
mount + ini `Paths=`) with the host-side-selection clarification.

## 2026-07-01 07:45 UTC — Walk-up project discovery is by SCHEMA (any dir name), not conventional-`uedcli/`-only

Supersedes the "walk-up auto-discovery looks for a conventionally-named `uedcli/config.toml`; a
non-conventionally-named project dir is NOT auto-discoverable" sub-point of the 2026-06-30 06:18 UTC
decision. Surfaced by a cold code review flagging the spec-vs-decisions conflict.

**Decision:** §4 tier-4 walk-up scans each ancestor's **immediate child dirs** for a `config.toml`
that classifies as a *project* config (§3.5 schema), returning that dir — **regardless of its name**
(conventionally `uedcli/`, but any name works). Two matching child dirs under one ancestor → an
ambiguity error (pass `--project`). The `~/.uedcli` home never matches (its schema is *user*).

**Why the change:** the 06:18 conventional-only rule made a non-`uedcli`-named project dir invisible
to walk-up — contradicting the standing "the dir name does NOT have to be `uedcli`, it's convention"
intent (Andrzej, 2026-06-30). A cold review of the consolidated spec flagged conventional-only as a
foot-gun (name it `editor/`, and the tool mysteriously can't find it from inside the tree).
Schema-scan makes "any name works" true for walk-up too, reusing the project-vs-user schema
classification the two same-named `config.toml`s already require.

**Cost, accepted:** walk-up reads each child `config.toml` up to the filesystem root (bounded; tiny
files; a read/parse error is swallowed — `_is_project_config_file` catches `ConfigError` + `OSError`,
the latter added after the same review flagged an uncaught permission error). An explicit
`--project`/`UEDCLI_PROJECT` short-circuits the scan.

**Rejected:** conventional-`uedcli/`-only (cheaper, but reintroduces the foot-gun and breaks "any
name"); bounding the climb at `$HOME` (breaks out-of-home trees like `/tmp`).

**Refs:** `specs/2026-06-29-uedcli-global-cli-projects-design.md` §4; `uedcli/config.py`
(`walk_up_project_dir`, `_is_project_config_file`); `tests/test_config.py` (non-conventional walk-up,
ambiguity, user-schema-ignored tests); supersedes the walk-up sub-point of `decisions.md`
2026-06-30 06:18 UTC.

## 2026-07-05 14:58 UTC — Project state goes fully in-tree; git feature branches replace the session store; `~/.uedcli/` holds only per-user config + derivable caches

Supersedes the central per-project state model (`decisions.md` 2026-06-29 06:02, 2026-06-30
06:18/18:47; spec §5), the store-centric session model (2026-06-18), and the `project init`/id/
registry + `config`-verb surface (spec §4.1). **Un-defers** the git-branch pivot (2026-07-01
06:16), building on the git-merge viability spike (2026-07-01 07:05).

**Decision (Andrzej):**

1. **All per-project state lives IN-TREE under `<project>/uedcli/`; nothing per-project is
   central.** The project dir holds:
   - **Tracked** (committed, travels with the clone): `config.toml`; `maps/<level>/` (the T3D
     trunks); `texture-catalog/` (classification — tags/colors/description keyed by **pixel-hash**,
     the expensive human/LLM work); `prefabs/` (the durable prefab library).
   - **Gitignored `tmp/`** (machine-local, throwaway): host↔container docker-cp scratch,
     apply/materialize staging temps, preview shots, **stash** (captured actor sets), and the
     editor/target **`flock`s**. (Exact sub-names are a build detail.)
2. **Ditch the bespoke session store; a level is edited on a git FEATURE BRANCH and merged into
   trunk with `git merge`.** There is no event-sourced session store, no session `id`, no
   `~/.uedcli/projects/<id>/`. The T3D trunk at `uedcli/maps/<level>/` is the source of truth;
   work-in-progress is an uncommitted/feature branch in the project's own git repo; the `.dx`/
   `.unr` produced by `level apply --to-map-file` is a build artifact committed like any package.
   - **This commits to the order-key change:** the shared `order` file — which conflicts on every
     concurrent add (the git-merge spike's sole blocker, 2026-07-01 07:05) — is replaced by a
     **per-actor sortable order key** (fractional / LexoRank) so disjoint edits merge cleanly.
     Reordering existing actors stays a genuine conflict (correct).
3. **`~/.uedcli/` holds ONLY per-user, non-project state:** `config.toml` (the `[games.*]` config)
   + **`cache/{textures,stubs}`** — the content-addressed texture-image cache and the v69 stub
   cache, **shared cross-project, derivable, never committed**. (Regroups spec §5's
   `~/.uedcli/{textures,stubs}` under `cache/`.)
4. **Drop `id` / `project init` / the name→id registry / the `config` verb.** With no central
   state bucket there is no key to mint, nothing central to register or GC, and config is
   hand-edited. The **`project` verb shrinks to `project show`** — print the resolved project +
   the composed `paths` with shadow provenance (the old `--explain-paths`). (`project init/ls/rm`
   + `config get/set` of spec §4.1 are dropped; the id/registry machinery flagged "at risk" since
   2026-06-30 is deleted, not built.)

**Context:** walking the layout with Andrzej surfaced that the central `~/.uedcli/projects/<id>/`
bucket was the *sole* reason `id`/registry/`project init` existed, and bought little over in-tree
state (one wipe location). He chose in-tree, then to ditch the session store outright for git
feature branches — the git-merge spike had already proven per-actor T3D merges viable. Image + stub
caches stay central because they are content-addressed and useful across projects.

**Rejected:**
- *Central per-project state (`~/.uedcli/projects/<id>/`)* — forces a stable project key (uuid +
  registry + `project init`) for marginal gain over in-tree gitignored state (found by location).
- *Keep the bespoke session store (2026-06-18) / squash sessions into trunk commits (direction.md)*
  — git branches + `git merge` give the same merge semantics for free (per-actor T3D files merge
  natively) and collapse `session.py`/`replay.py`/`merge.py`/the store; sessions-as-a-concept are
  dropped, not squashed.
- *Put classification / prefabs in gitignored cache* — both are non-regenerable (classification is
  expensive human/LLM work; prefabs are authored) → tracked (2026-06-22, 2026-06-29 06:48).
- *Keep the `config` verb / `project init`* — hand-editing `config.toml` + no central id to mint
  make them dead surface.

**Open (build-time, not blocking):** the order-key encoding (fractional vs LexoRank); the exact
gitignored sub-names under `uedcli/tmp/`; how `apply`'s target `flock` keys without a session id
(by resolved `--out` abspath, as today — likely unchanged). The largest remaining build is the
git-branch edit/merge model itself (replacing the store) + the order-key format; a fresh spike/spec
should precede it.

**Refs:** supersedes `decisions.md` 2026-06-18, 2026-06-29 06:02, 2026-06-30 06:18/18:47, and the
`project init`/registry/`config`-verb parts of the global-CLI arc; un-defers 2026-07-01 06:16;
builds on 2026-07-01 07:05. Reconciles `direction.md` ("The store is the source of truth", "The
trunk we want", "Sessions have no bound target", "Projects, substrates, and the global CLI") and
`specs/2026-06-29-uedcli-global-cli-projects-design.md` §4/§5/§9.

## 2026-07-05 15:11 UTC — Order-key scheme: `(order_value, random-id)` tiebreak; random-suffix actor names; duplicate-value `doctor` warn

Resolves the order-key + naming items left "open (build-time)" in the 2026-07-05 14:58 UTC entry.

**Decision (Andrzej):**

1. **Per-actor ordering, sorted by a PAIR.** Each actor carries its own `order_value` (a field in
   its `.t3d`, or a sidecar — a build detail), so disjoint edits touch disjoint files and merge
   natively. The effective CSG order sorts by **`(order_value, actor_id)`** — value first, the
   actor's unique id as tiebreak. Equal `order_value`s are therefore **harmless**: the tiebreak
   yields a total, deterministic order identical on every clone. No scheme tries to *prevent* equal
   values — impossible without coordination across offline branches — they are made irrelevant.
2. **Actor identity = a random unique SUFFIX on the name.** Replace D6's sequential
   `Uedcli<Class><n>` (allocated against the current level → collides across branches) with a
   **random-suffix name**: a legible stem + a ~6–8-char base32 random suffix (e.g. `Cube_k7f2qd`),
   minted at creation, immutable. This one token is simultaneously the actor's identity, its
   **filename** (so two concurrent adds never collide add/add), and the **order tiebreak**. Entropy
   sized so birthday-collision across realistic branch counts is negligible.
3. **Duplicate `order_value`s are DETECTED and WARNED — never blocked, never auto-fixed.** A
   `level doctor` finding flags "actors X, Y share order value V — relative CSG order is arbitrary
   (resolved by the id tiebreak)." With the tiebreak, a duplicate does NOT break determinism, so it
   is a warning, not an error. It is worth surfacing because (a) it means the precedence between
   those actors was decided by the random id, not by intent — reorder if precedence matters there;
   and (b) it is a **canary** — duplicates are the one place a bug that sorts by `order_value` alone
   would leak nondeterminism.

**Context:** refining the git-branch order-key + naming left open in the 2026-07-05 14:58 entry.
Andrzej: random unique suffix for names; detect same-value; "just warn."

**Rejected:**
- *Guaranteeing distinct `order_value`s across branches* — needs a central allocator offline
  branches don't have; unnecessary once the id tiebreak makes equal values harmless.
- *Sequential `Uedcli<Class><n>` (D6) under git branches* — two branches off one base both mint
  `UedcliBrush5` → add/add filename conflict + a non-unique tiebreak. Random suffix is
  coordination-free (fixes both at once).
- *Hard-error / block apply on a duplicate value* — nothing is actually broken (determinism holds
  via the tiebreak); a blocker is false urgency.
- *Silent auto-respread on apply, or an explicit `--fix`/reorder verb* — auto is surprising; an
  explicit fix verb is more surface than a plain warn needs. Warn-only; reorder by hand if it
  matters.
- *LexoRank/fractional as the load-bearing mechanism* — the value encoding (fractional midpoint,
  optional random jitter to make accidental equal values rare) is a build detail; correctness rides
  on the tiebreak, not the encoding.

**Refs:** refines `decisions.md` 2026-07-05 14:58 UTC (its order-key open item); supersedes D6's
sequential name allocation (`architecture.md` Invariants "D6") **for the git-branch model** (the
current code / `architecture.md` still describe sequential allocation until the model is built);
new consumer = a `level doctor` duplicate-`order_value` check.

## 2026-07-05 15:54 UTC — Git-branch model: `level apply`→a pure `level materialize`; uedcli reads/writes only (git is the user's); per-actor directory layout

Resolves the three model opens raised on the 2026-07-05 14:58/15:11 entries.

**Decision (Andrzej):**

1. **`level apply` becomes a pure BUILD step, renamed `level materialize`.** With git doing the merge,
   apply's 3-way reconcile (THEIRS/OURS/base) has nothing left to do — the verb just
   **materializes the current T3D trunk into the `.dx`/`.unr` build artifact**. It is **map-file
   output only**: there is no `--to-t3d-tree` mode — the trunk *is* the git-tracked T3D tree,
   reached by committing/merging on the branch, not by "applying" to it. Drops `merge.py`/
   `replay.py` and apply's reconcile path. (Verb name confirmed: **`level materialize`**.)
2. **uedcli only reads/writes the T3D files; git is driven by the USER.** No branch/merge verbs, no
   git wrapping — the human/agent runs `git branch`/`git merge`/commit directly. uedcli operates on
   the `actors/…` files; its surface does not grow a VCS layer.
3. **Per-actor DIRECTORY layout:** a level is
   `maps/<level>/actors/<name>/{actor.t3d, order_value}` + `name` — **one directory per actor**
   holding a constant-named `actor.t3d` (geometry/props) and a **separate `order_value` sidecar
   file**. (See the 2026-07-05 16:48 entry: the name lives only in the dir; `actor.t3d`, not
   `<name>.t3d`.) The order
   value is NOT stored inside the `.t3d`, so a reorder touches only `order_value` and never dirties
   the geometry diff (and leaves room for future per-actor sidecars). Resolves the 15:11 "field vs
   sidecar" open → **sidecar**. The old `{actors/, order, packages, name}` tree collapses: `order`
   moves into each actor's `order_value` sidecar, `packages` is already dropped (no stored manifest,
   2026-06-30 18:47), leaving per-actor `actors/<name>/` dirs + `name`.

**Context:** Andrzej resolving the three model opens after the git-branch decision.

**Rejected:**
- *Keep apply's 3-way reconcile + the dual `--to-map-file`/`--to-t3d-tree` modes* — git is the merge
  engine now, and the trunk is the T3D tree, so "apply to a tree" is just a commit. Build is
  map-file-only.
- *uedcli wrapping git (branch/merge verbs)* — the cleanest surface is files-only; git stays git,
  driven by the user.
- *Storing `order_value` inside the `.t3d`* — would dirty the geometry diff on every reorder and
  couple ordering to geometry; a per-actor sidecar isolates it.

**Refs:** extends `decisions.md` 2026-07-05 14:58 + 15:11; renames the `level apply` verb
(`architecture.md` `level apply` bullet — current code until built); reconciles `direction.md`
(apply→materialize, T3D-tree shape) + the global-CLI spec.

## 2026-07-05 16:06 UTC — `level materialize` refuses to overwrite; guards A/B + backup dropped; H3 kept

**Decision (Andrzej):** `level materialize` (the renamed build step, `decisions.md` 2026-07-05 15:54)
**refuses to overwrite an existing `--out` file** — if the target map file already exists it errors
(exit 2, naming the file); it only ever writes a NEW file. This replaces the old `level apply` name
guards (A/B) and the pre-write binary backup: the thing worth protecting — the authored work — is now
the git-tracked T3D trunk (git protects it), and the `.dx`/`.unr` is a regenerable build artifact, so
the only safety still needed is "never clobber an existing file." The **H3 post-verify is KEPT**
(re-export the freshly built map offline and confirm it matches the intended trunk — a build-
correctness check that catches a silent `MAP SAVE` failure, independent of clobber safety).

**Context:** Andrzej, resolving the guards/backups open on the apply→materialize rename: "Do not
overwrite existing file, keep h3."

**Rejected:**
- *Keep guards A/B (nameless-can't-overwrite / rename-mismatch) + the binary backup* — that machinery
  guarded a clobbered `.dx`; with the trunk safe in git and the map file regenerable, a blunt
  no-overwrite rule covers the real risk (accidental clobber of a hand-placed file) with far less
  surface.
- *Overwrite freely (drop all clobber protection)* — the map file is regenerable, but an accidental
  overwrite of an existing file the user cares about is still worth preventing; refuse instead.
- *Drop H3* — it is a build-correctness check, independent of clobber safety; kept.

**Note (ergonomics):** a routine rebuild to the same path now requires removing the prior file first
(no silent overwrite). An explicit `--force`/`--overwrite` opt-in was NOT requested and is not added;
revisit if the rebuild loop proves annoying.

**Refs:** extends `decisions.md` 2026-07-05 15:54 UTC; supersedes the `level apply` anti-clobber
guards A/B + `_backup` for build output (`architecture.md` `level apply` — current code until built);
keeps H3 post-verify.

## 2026-07-05 16:48 UTC — Layout/ordering clarifications: `actor.t3d` (name lives only in the dir); tiebreak sorts by the unique name

Two refinements Andrzej raised on the 2026-07-05 15:11/15:54 entries.

**Decision (Andrzej):**

1. **The actor name lives ONLY in the directory name — not repeated in the `.t3d`.** The per-actor
   file is a constant **`actor.t3d`** (not `<name>.t3d`, which is redundant with the dir). The
   **`Name=` field is stripped from the stored `actor.t3d` body** and re-injected from the directory
   name at `materialize`, so the directory name is the **single source of truth** for identity — a
   dir-name and a body `Name=` can never drift. Layout: `maps/<level>/actors/<name>/{actor.t3d,
   order_value}`.
2. **The order tiebreak sorts by the actor's unique NAME**, not a separate random-id field — the
   random-suffix name IS the coordination-free unique key (2026-07-05 15:11). So the sort is
   **`(order_value, name)`**. This is correct because the tiebreak fires ONLY on **equal
   `order_value`** — a genuinely ambiguous case (concurrent same-gap inserts, no intended relative
   order). What is required there is **determinism across clones**, not meaningfulness, and an
   immutable unique key is the only thing that is both deterministic *and* stable under edits
   (insertion order varies by git merge order; a content hash would shift when geometry changes).
   Sorting by the full name breaks ties **stem-then-suffix**, so same-stem actors still group — the
   arbitrary order is at least legible.

**Context:** Andrzej: "`<name>` in t3d redundant" + "sort by random-id?".

**Rejected:**
- *Repeat the name as the `.t3d` filename and/or a body `Name=`* — redundant with the dir; two more
  places to drift. Dir name is authoritative; `materialize` injects `Name=`.
- *Tiebreak by insertion order* — nondeterministic (varies by merge order). *By content hash* —
  shifts when the actor is edited. Both fail the determinism/stability the tiebreak needs.

**Refs:** refines `decisions.md` 2026-07-05 15:11 (tiebreak key) + 15:54 (per-actor layout).

## 2026-07-05 17:11 UTC — Git-native spec review resolutions: materialize dup-order warn, `level materialize --overwrite`, cancel deep-verify/merge-sessions

Resolves three points the two cold reviewers of `specs/2026-07-05-uedcli-git-native-model-design.md`
raised that touched prior decisions (the rest of their findings are spec-text fixes, folded into the
spec's "Review resolutions" section).

**Decision (Andrzej):**

1. **The duplicate-`order_value` warning is ALSO emitted at `level materialize`, not only `level
   doctor`.** Reviewers flagged that two brushes concurrently placed at the same `order_value` git-
   auto-merge with no conflict, so their CSG precedence is silently decided by the random name suffix
   — and a `doctor` warn may never be run. Emitting the same warn on the build that ships the map
   makes it unmissable. Still **warn-only** (no block, no auto-fix). **No mandatory jitter** — Andrzej
   selected the materialize-warn only; jitter stays the "optional" of the 15:11 entry. Extends
   `decisions.md` 2026-07-05 15:11.
2. **`level materialize` gains an opt-in `--overwrite`.** The default still **refuses** to overwrite
   an existing `--out` (2026-07-05 16:06), but `--overwrite` allows it — because rebuilding a map to
   the same path is the inner loop (edit trunk → rebuild → commit), and forcing a manual `rm` every
   rebuild is friction on the most-run command. The regenerable `.dx` is the common overwrite case; a
   hand-placed file is still protected by the default. Revises `decisions.md` 2026-07-05 16:06 (which
   had deferred a `--force`).
3. **`session verify --deep` and `merge --sessions` are CANCELLED — git subsumes both, not lossily.**
   `merge --sessions` is exactly what `git merge` now does. `session verify --deep` verified the
   bespoke store's per-command integrity; that store is gone, and `git fsck` + git's content-
   addressing give corruption/tamper detection for the tracked trunk. The one genuinely-new need — a
   lightweight **"is the T3D trunk well-formed?"** lint (each actor dir has `actor.t3d` + a valid
   `order_value`, files parse, refs resolve) — folds into **`level doctor`** as follow-on work, NOT a
   resurrected deep-verify. `replay.py`/`merge.py`/`audit.py`/`ownership.py` are deleted with the
   store.

**Context:** two cold reviewers on the git-native spec; Andrzej's calls on the three findings that
touched decisions ("Warn at materialize too"; "--overwrite"; "do they still have value?" → my
assessment: no, git subsumes them + a new trunk lint in `doctor`).

**Rejected:**
- *Mandatory jitter on `order_value`* — Andrzej chose the materialize-warn instead; jitter remains
  optional (a duplicate is deterministic-and-now-loudly-surfaced, not silently arbitrary).
- *Strict no-overwrite with no escape* — the rebuild-to-same-path loop makes a `--overwrite` opt-in
  worth the small surface; the default-refuse still guards a hand-placed file.
- *Reimplementing deep-verify / merge-sessions on git* — no residual value; git fsck + `git merge`
  cover them, and a trunk-well-formedness lint (a different thing) covers the only new need.

**Refs:** extends `decisions.md` 2026-07-05 15:11 (dup warn) + 16:06 (overwrite) + 14:58/15:54
(store deletion); folds into `specs/2026-07-05-uedcli-git-native-model-design.md` (§5/§7/§9 + the
Review-resolutions section).

## 2026-07-05 19:07 UTC — Level targeting: a machine-local "selected level" via `level select`

**Superseded by 2026-07-20 21:30 UTC (level is `$UEDCLI_LEVEL`, no pointer, `level select` dropped).**
The `level select` pointer proved a live cross-session race (probe 2026-07-19); the env-as-primary
mechanism this entry *rejected* ("an env knob can come later if scripting/parallel needs it") is now
the primary. See that entry.

With the session store gone (2026-07-05 14:58), a content verb (`actor …`, `brush …`, `poly …`,
`mover …`, stash/prefab) no longer has a session to bind the level it edits — but a project holds many
levels (`maps/<level>/`). Surfaced planning slice 2 (re-point content verbs onto the trunk).

**Decision (Andrzej):** a **machine-local "currently-selected level" pointer**, set by **`level select
<name>`**, with a way to **check** the current selection. Concretely:
- **`level select <name>`** sets the current level (validated against `maps/<name>/`), stored as a
  gitignored, per-checkout machine-local pointer under `uedcli/tmp/` (git-branch-`HEAD`-like — a
  working-copy state, not tracked).
- **`level select`** (no argument) **prints** the currently-selected level (or "none selected"). The
  selection also surfaces in `project show` / a status read.
- **Content verbs operate on the selected level**; **`--level <name>` overrides** per-command. With
  neither a selection nor `--level`, a verb errors ("no level selected: run `level select <name>` or
  pass `--level <name>`") — no silent default, on-brand with uedcli's selection discipline.

**Context:** offered `--level`/`UEDCLI_LEVEL` (mirror the old `--session`/`UEDCLI_SESSION`) vs a
git-branch-like current-level pointer vs cwd-inference. Andrzej chose the **pointer** (`level select`)
+ an explicit check — ergonomic for an editing session (set once, run many verbs) while still a
deliberate, inspectable choice.

**Rejected:**
- *`--level`/`UEDCLI_LEVEL` on every verb, no pointer* — cleanest 1:1 replacement of the session-
  selection code, but forces the level on every command; the pointer is nicer for interactive editing.
  (`--level` survives as the per-command override.)
- *Infer the level from cwd (inside `maps/<level>/`)* — content verbs run from the project root in
  practice, so you'd pass `--level` most of the time anyway.
- *An ambient `UEDCLI_LEVEL` env as the primary mechanism* — not added now (the pointer is the primary,
  `--level` the override); an env knob can come later if scripting/parallel needs it.

**Refs:** feeds slice 2 (`specs/2026-07-05-uedcli-git-native-model-design.md` §6/§8 — add `level select`
to the verb surface; the pointer lives in the in-tree gitignored `uedcli/tmp/`, decisions 2026-07-05
14:58). Replaces the old `session_select.resolve_session` contract with a level-selection resolver.

## 2026-07-05 19:28 UTC — Drop the `--level` per-command override; `level select` is the sole level source

**Superseded by 2026-07-20 21:30 UTC.** `level select` no longer exists; the sole *default* source is
now `$UEDCLI_LEVEL`, and `--tree KIND/NAME` (the renamed `--target`) is the per-command override.

Refines the 2026-07-05 19:07 UTC level-targeting decision.

**Decision (Andrzej):** there is **no `--level` flag** on content verbs. The `level select` pointer is
the **sole** source of the level a verb edits — set it with `level select <name>`, check it with bare
`level select`. A verb with nothing selected errors ("no level selected: run `level select <name>`").
The selection is an explicit, inspectable mode (git-branch-like); it does not need a per-command escape
hatch, and dropping it keeps one flag off every content verb.

**Rejected:** *keeping `--level` as a per-command override* (the 19:07 form) — an extra flag threaded
through every content verb for a rarely-needed escape; the pointer + `level select` is enough.

**Refs:** supersedes the `--level` override point of `decisions.md` 2026-07-05 19:07;
`level_select.resolve_level` drops its `flag` param (`level_select` was still unwired, so no verb had
`--level` yet — a clean removal); spec §8 + the slice-2a plan reconciled.

## 2026-07-05 19:50 UTC — Add `level status`: a thin read-only per-level dashboard

The git-native model deletes `session status`; nothing answers "what level am I on and is anything
obviously off?" in one shot. `project show` is project-level (game/paths), bare `level select` just
echoes the pointer, `level doctor` is a full lint, `git status` is git — none orient you on the
selected level.

**Decision (Andrzej):** add **`level status`** — a **thin, read-only** dashboard for the *selected*
level. Shows: the selected level name (or the no-selection hint); actor counts (total / brushes /
point actors); the **duplicate-`order_value` count** (the silent footgun — a count + "run `level
doctor`", not the findings); the referenced packages (the derived load set); and **at most a one-line
git hint** ("on branch `x`; N uncommitted changes — see `git status`").

**Explicitly NOT:** it does not duplicate `git status` (uedcli never wraps git — a hint, then defer),
`level doctor` (a count, not the lint), or `project show` (the project/paths layer). Its whole value
is staying thin; if it grows into those, it's noise. Three read verbs with distinct jobs:
`project show` (project) · bare `level select` (the pointer) · `level status` (the selected level's
content health).

**Rejected:**
- *Fold it into bare `level select` or `project show`* — different scope (a level's content vs the
  pointer vs the project); a dedicated verb is clearer and mirrors the old `session status`.
- *A rich status that reprints git state + doctor findings* — becomes a worse `git status` +
  `level doctor`; kept deliberately thin.

**Refs:** rides the slice-2b trunk-read plumbing (`trunk.read_level` → counts + `duplicate_ranks`);
add to the slice-2b plan + spec §8 verb surface. Read-only, no editor, no git ops.

## 2026-07-05 22:52 UTC — `dxconcli` object transfer: one explicit `transfer` verb + a `give`-spawn sugar (drop `give`/`take` default-direction)

**Decision (Andrzej):** the `dxconcli` source surface for a `TransferObject` event is **one explicit
verb `transfer: {item, from, to, amount?, on_fail?}`** with both actor sides named, **plus a thin
`give: {item, to, amount?, on_fail?}` sugar** for the single runtime-sanctioned default (omit `from`
→ the `-1` "spawn from thin air" case). There is **no `take`** and **no implicit-side default
direction**.

**Why (grounded by the spike `spikes/2026-07-05-deusex-con-transfer-give-take/`):** the earlier
`give`/`take` design (2026-06-26 spec §TransferObject) was self-contradictory — it said the two verbs
"differ only in the default direction of omitted `from`/`to`" *and* that "an omitted side compiles to
the empty `index=-1` ref", which cannot both hold (the `TransferObject` wire form has no direction
bit, so two both-sides-omitted forms would be byte-identical). The spike resolved the facts: (1) the
`.con` carries no give/take concept, only `fromName`/`toName` actor refs; (2) the retail-stripped
`ConPlayBase.SetupEventTransferObject` comment documents only **absent-`from` = spawn from thin air**
(absent-`to` is undocumented); (3) **empirically all 147 corpus `TransferObject` events name BOTH
sides explicitly — zero omitted sides**. So the default-direction feature was never exercised in
shipped data. An explicit `transfer` matches 100% of the corpus and removes the ambiguity; `give`
(omit `from`) is kept only because the runtime explicitly sanctions the spawn case (InfoLink
DataVaultImages).

**Rejected:**
- *Keep `give`/`take` with default-direction* — the source of the contradiction; unused by any
  shipped conversation; two source forms collapsing toward identical bytes is a decompile hazard.
- *`transfer`-only (no `give`)* — loses the one genuinely-useful, runtime-supported default
  (spawn-from-thin-air) for no gain.
- *Implicit-side `take`* — absent-`to` is undocumented in the runtime and unused; unsafe to author.

**Refs:** `plans/2026-07-05-dxconcli-implementation-plan.md` Tasks 2.2/2.3;
`spikes/2026-07-05-deusex-con-transfer-give-take/`; supersedes the give/take framing in the
2026-06-26 `deusex con` spec §TransferObject; `board/flagged.md` 2026-07-05 (resolved).

## 2026-07-05 23:00 UTC — `level materialize` load contract: load the whole composed search path (no per-level derivation)

Resolves the one build-time open sub-point of the manifest-drop decision (`decisions.md` 2026-06-30
18:47 UTC point 3), surfaced while planning git-native slice 3 (`level materialize`).

**Decision (Andrzej):** with no stored `packages` manifest, `level materialize` does **NOT** derive a
per-level package set. It **loads the whole composed search path** — the project overlay globs first,
then the selected game's base globs (deduped project-shadows-base, per the `paths` composition in
`direction.md`) are wired into the editor's `[Core.System] Paths` ini at launch, and `MAP
IMPORT`/`REBUILD` resolve every `Texture=`/`Class=`/object ref against that search path. There is no
transitive-closure walk and no `referenced_packages`-style per-level derivation on the build path.

**Why:** the composed `paths` are what the project already declares as "the assets this project can
use"; loading them all is the engine's own search-path model and needs no closure-walker, no reliance
on qualified `Class=` refs (which T3D writes unqualified — see `stashlib.referenced_packages`), and no
per-level manifest to keep in sync. The manifest drop's flagged worry — transitive deps a level never
names, and qualified textures not auto-demand-loading — dissolves when the whole search path is
loadable up front rather than demand-loaded from a derived subset.

**Rejected:**
- *Derive per-level + walk the import-table transitive closure on demand* — the flagged
  "likely must still walk the closure" option. Correct but heavy: needs a header-closure walker AND
  needs the trunk's stored refs fully qualified (class refs aren't). The whole-search-path load makes
  the derivation moot.
- *Hybrid: load direct refs + rely on search-path demand-load for the rest* — still leans on
  demand-load firing for indirect deps, which `unrealed/quirks.md` says it may not for a qualified
  `Texture=`. Loading the whole path up front removes that dependency.

**Cost accepted:** the editor loads more packages than a given level strictly needs (slower boot,
more memory). Acceptable — materialize is a build step, not an inner-loop read, and the packages are
already the project's declared set.

**Refs:** resolves `decisions.md` 2026-06-30 18:47 UTC point 3's open sub-point (transitive-closure /
load-contract); reconciles `direction.md` "Layered packages" (the loadable set is the composed paths,
not derived from the level's refs); clears the `board/flagged.md` manifest-drop transitive-dep flag.
Feeds the slice-3 `level materialize` plan.

## 2026-07-06 05:12 UTC — Git-native editor identity: a per-COMMAND ephemeral container; materialize hard-errors without a games config

Resolves the two blocking forks the slice-3 `level materialize` plan draft surfaced (the editor
lifecycle lost its `session/<id>` key when sessions were dropped; and the load set needs the games
config).

**Decision (Andrzej):**

1. **The git-native editor is a per-COMMAND ephemeral container.** Every editor-driving invocation —
   `level materialize`, `level preview`, and the slice-2c-deferred `stash intersect`/`deintersect` —
   spins up its **own** editor container, drives it, and tears it down when the command ends. The
   identity is the single command run (a fresh unique id minted per invocation), NOT a session, NOT a
   shared machine-wide container, NOT per-level or per-project. Parallelism is free by construction
   (each command owns its own container, so two materializes never contend) and no cross-command
   editor lock is needed — the only serialization is a command holding its own container for its own
   lifetime. This replaces the old `session/<id>`-keyed `editor_lock`/`ensure_editor`/`stop_editor`.
2. **`level materialize` hard-errors when no per-user `~/.uedcli/config.toml` games config exists.**
   The load set is the composed search path, whose base globs come from `[games.<name>].paths` in that
   file. With no games config there is no base package set to load, so materialize refuses with a clear
   message ("create `~/.uedcli/config.toml` with a `[games.<name>] paths` glob") rather than guessing.
   No implicit baked-image fallback.

**Context:** Andrzej, on the two BLOCKING open questions in the slice-3 plan draft
(`plans/2026-07-05-uedcli-slice3-level-materialize-plan.md`).

**Rejected:**
- *One shared editor container + a global lock* — simplest, but serializes every build machine-wide
  (materializing level A blocks level B). The per-command container gets isolation AND parallelism.
- *Per-level or per-project container* — still a shared, keyed, longer-lived container needing a lock
  and lifecycle bookkeeping; the per-command ephemeral container is simpler and needs neither.
- *Baked-image fallback when the games config is absent* — an implicit, image-defined load set is
  surprising and can't express a project's overlay; a hard error keeps the load set explicit.

**Implications for the build:** `run_materialize`/`_level_preview` no longer take a `store.branch`
lock key; they mint a per-invocation container id (uuid), `ensure_editor` it, drive, and
`stop_editor` in a `finally`. The `stash intersect`/`deintersect` git-native deferral
(`board/flagged.md` slice-2c entry) is now unblocked by this identity — its ephemeral editor keys off
the command, not a session. The slice-3 plan's two blocking Open-Questions are closed by this entry.

**Refs:** closes the slice-3 plan draft's blocking Open-Qs #1/#2; unblocks the `board/flagged.md`
slice-2c `stash intersect` deferral (editor identity resolved); reconciles `direction.md` (the editor
is per-command ephemeral, superseding "one container instance per session"); feeds `parallel-editors.md`
(per-command containers are the concurrency unit).

## 2026-07-06 12:01 UTC — `level preview` is a batch SHADED-SNAPSHOT renderer, not a live VNC handoff

Surfaced while re-pointing `level preview` onto the trunk in git-native slice 3: the old preview left
the editor UP for interactive VNC (a session-era design), which has no clean teardown under the
per-command ephemeral editor model (2026-07-06 05:12).

**Decision (Andrzej):** `level preview` is **redefined as a batch snapshot renderer**, not an
interactive VNC session. It spins up a **per-command ephemeral editor** (2026-07-06 05:12), materializes
the selected trunk level into it, renders a shaded/textured image **from each of a caller-supplied list
of vantage points** (position + orientation) in that ONE editor spin-up (one image file per shot — the
boot amortized across all shots), then tears the editor down. **View mode is selectable per the render
(default: shaded)** — e.g. shaded/textured vs wireframe, mapping to the editor's `RMODE`. Camera posing
uses the verified console-only mechanism (pose a helper `Light` + `SELECTNAME` + `CAMERA ALIGN`, adopts
the full FRotator; `RMODE 6` for a non-black shaded first paint — see `unrealed/rendering.md` /
`unrealed/commands.md`). **VNC is retained ONLY as a dev-debug affordance, not the `preview` product
behavior.**

**Why:** a snapshot renderer needs no persistent container and no teardown verb — the ephemeral editor
model fits it exactly (render → tear down), dissolving the "preview leaks a container per run" problem.
Snapshots are also the composable, scriptable, LLM-consumable output (image files an agent can inspect),
where an interactive VNC URL is not.

**Rejected:**
- *Keep the interactive VNC handoff as `preview`'s behavior* (per-level container + a `level stop`
  verb, or a shared preview container) — VNC is dev-debug, not the product; and every persistent-editor
  option needs a teardown/identity model the snapshot renderer avoids entirely.
- *One shot per invocation (`--at`/`--rotate`), composed N times* — rejected for the batch form: a
  caller-supplied list renders all vantage points in a SINGLE editor boot (the boot is the expensive
  part), so batching amortizes it.
- *A fixed default view set only* — the caller supplies the list; a default set can layer on top but the
  vantage points are caller-selected.

**Refs:** redefines `level preview` (supersedes the interactive-VNC `level preview` in `architecture.md`
— current code until rebuilt); builds on the per-command ephemeral editor (2026-07-06 05:12) + the
materialize build seam (slice 3); cites `unrealed/rendering.md` (RMODE, non-black shaded shots) +
`unrealed/commands.md` (`CAMERA ALIGN`). Its own small spec/plan follows (git-native slice 3 preview
re-point → a preview REDESIGN).

## 2026-07-06 12:05 UTC — `dxconcli`: labels are first-class (ConEdit parity); fragments are a DRY convenience, not a replacement for label/goto

Amends the 2026-06-26 `deusex con` decision "conversation-scoped `fragments` + `use:` **replace** raw
label/goto". Surfaced closing the one open `dxconcli` v1 item: 39 corpus cross-conversation `Jump`s
target a **mid-conversation label** in another conversation (e.g. `M02Briefing` → `MeetManderley` at
`Chastise`), and v1 had no way to name a *position* in a conversation, so it silently retargeted them
to the entry.

**Decision (Andrzej):** re-introduce **raw labels as a first-class source construct, mirroring
ConEdit** (whose model is labels + gotos underneath). Concretely: a `label: Name` **marker statement**
names a position in a conversation body, and `jump:` targets a label — `jump: {label: L}`
(same-conversation goto), `jump: {label: L, conversation: X}` (cross-conversation goto to a label in
`X`), `jump: {conversation: X}` (enter `X` at its start). **Author labels may be any name (no reserved
prefix, no collision error); the compiler makes its own generated internal labels dodge the author
labels by construction** (seed the label generator with the author-label set, bump on collision) —
chosen over a `_`-prefix ban because it imposes nothing on authors and produces no confusing
"clashes-with-an-invented-name" error. **Fragments/`use:` are unchanged but re-framed as a pure
in-conversation DRY convenience layered on top of labels — NOT the replacement for label/goto the
2026-06-26 entry called them.** Both coexist: `use: frag` = run a reusable block; `jump: {label}` =
raw goto to a named point. (Labels and fragments are separate namespaces — `use:` vs `jump: {label}` —
so a shared name is unambiguous, not an error.)

**Why:** a fragment is a conversation-*internal reuse* block, not a named externally-addressable
*position*; it structurally cannot express "jump into another conversation at point P" (nor the
related future need of a level trigger entering a conversation partway). Labels are exactly the
addressable-position concept, and they are what the format/ConEdit already use, so first-class labels
give both faithful round-trip (the 39 cases) and honest parity. Same-conversation control flow still
**decompiles** to structured `if:`/`choice:`/`random:`/fragments (readable) — labels are emitted only
where cross-conversation addressability requires them, so the decompiler output is not flattened back
to raw gotos.

**Rejected:**
- *`jump: {conversation, fragment: F}`* (address a fragment in another conversation) — a fragment is
  conversation-private reuse plumbing, not a public entry position; overloading it is incoherent and
  still can't serve external (level-trigger) entry.
- *`jump: {conversation, entry: Name}` with a new "entry point" abstraction* — a cleaner name, but
  inventing a bespoke concept over what is literally a label diverges from ConEdit for no gain; the
  honest, format-matching primitive is the label.
- *Keep it deferred / decompile lossless-but-inert* — leaves 39 real corpus jumps mis-targeting on
  recompile; the fix is small and makes the tool actually faithful.
- *Reserve the `_` prefix (ban author labels starting with `_`), or error when an author label
  collides with a generated one* — both push a restriction/confusing error onto the author; having the
  compiler dodge author names instead imposes nothing and cannot collide.

**Refs:** `specs/2026-07-06-dxconcli-cross-conversation-labels-design.md`; amends the 2026-06-26
`deusex con` fragments-replace-label/goto point (fragments + the two grounding spikes otherwise
intact); closes `board/flagged.md` 2026-07-05 cross-conv-mid-label item; builds on
`spikes/2026-07-05-deusex-con-jump-conid-live/` (`Jump.conversationID` = own id).
## 2026-07-06 12:59 UTC — `level preview` snapshot-renderer: CLI grammar, no auto-frame, full RMODE set, roll omitted

Concretizes the 2026-07-06 12:01 `level preview`-is-a-snapshot-renderer decision into the built design
(Andrzej confirmed each point).

**Decision (Andrzej):**

1. **Shots are POSITIONAL args, not `--shot` flags:** `level preview <shot>… --out-dir DIR [--mode
   MODE] [--size WxH]`. Each `<shot>` token is **`POS@ROT[:MODE]`**:
   - **`POS`** = `x,y,z` (raw world coords) **or an actor NAME** → the camera sits **at that actor's
     Location** (a coords shorthand, "camera AT the actor", NOT look-at).
   - **`ROT`** = `pitch,yaw` (degrees) **or a named preset** — `iso-ne`/`iso-nw`/`iso-se`/`iso-sw`/
     `top`/`bottom`/`front`/`back`/`left`/`right` (a canned pitch,yaw). Orientation ONLY.
   - **`:MODE`** = optional per-shot view mode (else the global `--mode`, default `shaded`).
   - Optional **`=NAME`** suffix overrides the auto output filename.
2. **Position is ALWAYS explicit — NO auto-framing.** Every shot carries a position (raw coords or an
   actor name); a named preset is orientation-only and must pair with a position. The tool never
   computes a framing distance/position from the level bounds. (Supersedes, for this verb, the
   auto-frame option floated in the 12:01 discussion — Andrzej chose raw-camera control.)
3. **Full `RMODE` view-mode set, per-shot with a global `--mode` default:** `shaded` (PlainTex, RMODE
   6 — DEFAULT), `lit` (DynLight 5 + `LIGHT APPLY`), `wire` (1), `zones` (2 — colors zones / shows the
   skyzone), `polys` (3).
4. **Roll is OMITTED** (camera orientation is pitch,yaw only; roll fixed 0). The editor camera FRotator
   HAS a roll field and `CAMERA ALIGN` can set it, but level snapshots want a level horizon; add roll
   later only on a real need (and verify SoftDrv actually renders it first).
5. **Output: `--out-dir DIR` + auto per-shot filenames** — `<pos>-<rot>[-<mode>].png` (preset/actor
   names sanitized), `shot-<i>.png` for a raw-coords pose, `=NAME` overrides. PNG default.

**Engine (implementation, not a choice):** per-command ephemeral editor (2026-07-06 05:12) →
materialize the trunk (slice 3 seam) → per shot: pose a helper `Light` carrying the shot's
Location+Rotation, `SELECTNAME` + `CAMERA ALIGN` (adopts the full FRotator — memory
`uned-camera-rotate-via-align`), set `RMODE`, `LIGHT APPLY` for `lit`, `driver.screenshot` (`wine_ctl
shot`) → `cp_out` to `<out-dir>/<name>`. Must handle the `rendering.md` live traps (stale framebuffer,
`RMODE` can't target the perspective pane headless without a mouse, black-window overlays) — a spike
gates any that aren't already solved by the existing shaded-shot path (memory `uned-shaded-rendering`).

**Rejected:** `--shot` flags (positional reads better); auto-framed named views (raw-camera control);
per-shot `=out` paths / an `--out` template (—`--out-dir`+auto names chosen); roll in v1 (YAGNI).

**Refs:** implements the 2026-07-06 12:01 preview-redesign decision; builds on per-command ephemeral
editor (05:12) + the `run_materialize` seam (slice 3); the spec is
`specs/2026-07-06-uedcli-level-preview-snapshots-design.md`.

## 2026-07-06 14:30 UTC — `level preview` renders NATIVELY (offline rasterizer), not by driving the editor's display

The 2026-07-06 12:01/12:59 preview design assumed the editor would render the shots. A 7-round live
spike (`spikes/2026-07-06-level-preview-headless-shots/`) proved that path is a dead end for a clean
posed, multi-mode preview.

**Decision (Andrzej — "figure out a clean way without restarting the editor"):** `level preview`
renders its snapshots **NATIVELY in pure Python (offline), not via the editor's display.** It reuses
the RESOLVED native-textured-preview renderer (`spikes/2026-06-27-decontainerize-uedcli/09-native-
textured-preview.md`, `harness/native_render.py`): parse the level's built `Model`, decode each surface
texture natively, rasterize with affine UV + a z-buffer. Arbitrary **pose** = a view+perspective
transform at the projection (the renderer is top-down ortho today — a standard swap, not a feasibility
gap); per-shot **mode** = a renderer option (textured/wire/lit). The editor's *display* role is removed
from preview (the de-containerize direction — memory `decontainerize-uedcli`).

**Why (the spike evidence, folded into `unrealed/rendering.md`):** the editor headless path can't do
posed multi-mode cleanly — `CAMERA OPEN` renders only from a FIXED default pose (can't be aimed, even
after making the pane current; 3 poses → diff 0.0); runtime `RMODE` can't target the perspective pane
headless (the command-box click steals "current"); and the only editor way to set the mode is
`[U2Viewport2] RendMap` in the launch ini, which forces an **editor restart per mode** — which Andrzej
explicitly rejected. The native renderer sidesteps all of it.

**Requires:** a built `Model` (a CSG-built `.dx`), which `level materialize` produces — so `level
preview` materializes the trunk (the one editor touch = the CSG build) then native-renders offline.
(A future native CSG build (D2) would remove even that; out of scope here.)

**Rejected:** the editor `CAMERA OPEN`-with-`REN=`/`FLAGS=` mode path — it does per-shot MODE without a
restart (correct — `rendering.md`), but CANNOT be posed, so it can't produce arbitrary vantages;
main-pane `ALIGN`+crop with a per-mode ini restart — Andrzej rejected the restart.

**Refs:** supersedes the editor-render mechanism in `specs/2026-07-06-uedcli-level-preview-snapshots-
design.md` (§Architecture/§Feasibility — pending native rewrite); builds on the native renderer
(spike 09) + `level materialize` (slice 3, the Model source); durable editor-render facts in
`unrealed/rendering.md`.

## 2026-07-06 15:58 UTC — REVERSE: `level preview` is the EDITOR-screenshot version (per-boot mode; radii/show-flag views); native renderer shelved

Reverses the 2026-07-06 14:30 native-render decision. On reflection Andrzej wants the editor
screenshot version for now: **"I'm fine restarting the editor per mode... but we also need radii view,
etc. I want the UnrealEd-screenshot version for now."**

**Decision (Andrzej):** `level preview` captures the **UnrealEd editor's own render** (screenshot), NOT
a native rasterizer. Rationale: radii view (actor collision cylinders + light radii) and the other
editor overlays (zones, paths, coords) are **editor-only** — a geometry+texture native renderer
fundamentally cannot produce them, and Andrzej needs those views. **Restarting the editor per render
mode is ACCEPTED** (so per-shot mode is supported via boot-per-mode-group). The native offline renderer
(spike 09) is **shelved as a future option**, not built now.

**Mechanism (proven in `spikes/2026-07-06-level-preview-headless-shots/`):** per shot — pose the main
perspective pane with a helper `Light` + `CAMERA ALIGN`, a `wine_ctl click` inside the pane to make it
current + force the repaint, `driver.screenshot` the frame, **crop the bottom-left perspective pane**
(≈`(122,636,800,1072)` at the fixed 1600×1158). The **render MODE + show-flags are set at editor LAUNCH
via `[U2Viewport2]` in `UnrealEd.ini`** (`RendMap` for the mode: 1 wire/2 zones/3 polys/5 lit/6 shaded;
the `Show*` keys for overlays incl. **radii**) — one editor boot per distinct mode/view-config, restart
between. `shaded` (RendMap=6) posed shots are live-proven (mean 142.5).

**One thing to VERIFY at build (small):** posed **radii** view. Runtime `SHOWACTORRADII` blanks the
main pane black (a re-render under SoftDrv, `unrealed/commands.md`); the fix is to boot the pane with
`SHOW_ActorRadii` already ON via the ini's viewport ShowFlags (the `[U2Viewport2]` section has per-flag
keys) — plausible like `RendMap=6` worked, but untested. If the ini-ShowFlag-at-boot path fails, radii
view falls back to the un-posed `CAMERA OPEN NAME=X FLAGS=127` (proven, but default pose only).

**Rejected (this reversal):** the native offline renderer (14:30) — clean and feasible, but can't
render editor-only overlays (radii/zones/paths) Andrzej needs; shelved for a possible future
`preview --native`. Per-command single-mode (no restart) — Andrzej accepts the per-mode restart to get
per-shot mode across all view modes.

**Refs:** SUPERSEDES `decisions.md` 2026-07-06 14:30 (native render); re-selects the editor mechanism
proven in the 7-round spike (folded into `unrealed/rendering.md`); reconcile
`specs/2026-07-06-uedcli-level-preview-snapshots-design.md` back to the editor architecture + add
radii/show-flag modes.

## 2026-07-07 07:39 UTC — `stash intersect`/`deintersect` re-point onto a per-command ephemeral editor (slice 4)

**Decision:** When slice 4 removes the `--session` flag (git-native teardown), `stash intersect` and
`stash deintersect` — the two CSG generators that were left `--session`-only because their git-native
path "was never built" (flagged 2026-07-05, `dispatch.py:201` comment) — are **re-pointed onto a
per-command ephemeral editor**, the same lifecycle `level materialize`/`level preview` already use
(fresh `uuid7` → `ensure_editor` → drive → `stop_editor`). They read the stash from the
`FileStashRegister` (the trunk-side register slice 2c added) instead of the session store, and stay
**stdout generators** (they already `print(result)` a T3D snippet — the store was only ever used to
read the stash and to reach a live editor, never written back). No `--session` survives after slice 4.

**Rejected:**
- *Drop them now, re-add later on their own slice* — cleanest teardown, but leaves a real functional
  gap in the shipped tool (two verbs that error unconditionally) for an unbounded window. Andrzej
  chose continuity.
- *Keep a minimal `--session` escape-hatch just for these two* — contradicts the whole point of
  removing sessions and would keep `session.py`/the store core alive past slice 6 (the "delete store
  core" slice), defeating the teardown.

**Context:** Every other content/stash verb got a trunk path in slices 2a–2c; these two were the sole
holdout because they drive the live editor (`BRUSH FROM INTERSECTION`/`FROM DEINTERSECTION`) and the
git-native model reaches the editor only via an ephemeral spin-up. Slice 4 now closes that gap rather
than deferring it.

**Refs:** implements the git-native migration (git-branches-replace-sessions 2026-07-05); resolves the
`stash intersect/deintersect` deferral flagged in `board/flagged.md` + `dispatch.py:201`; part of
slice 4 (`project show` + un-wire session).

## 2026-07-07 12:11 UTC — Mover keyframe offsets are world-additive under `BaseRot≠0`; the caution is dropped

**Decision:** A mover keyframe's stored `KeyPos[i]` is added to the base pose in **world axes**
(`Location = BasePos + KeyPos[i]`), **not** rotated by `BaseRot` first — confirmed even when the base
is rotated. Rotation composes the same trivial way (`Rotation = BaseRot + KeyRot[i]`, FRotator
componentwise addition). So `mover key add`/`move`/`rotate` on a base-rotated mover need **no**
special-casing, and the interim stderr caution they printed is removed.

This **supersedes** the "Deferred (flagged)" note in the 2026-06-25 12:17 UTC mover entry (the
`BaseRot≠0` + non-axis-`KeyPos` world-space-vs-rotated question, warn-and-proceed in v1). uedcli's v1
assumption was correct; the warning was pure noise.

**Evidence (two independent confirmations, folded into
`spikes/2026-06-25-mover-keyframe-basepos-semantics.md`):** (1) a live measurement — a 90°-yaw base
mover with `KeyPos(1)=(X=256)` moved along **world +X**, not +Y; (2) the editor's own disassembled
mover transform adds `KeyPos[i]` to `BasePos` with no rotation. The rotation half was already live in
that spike's test E (`Yaw=8192 + Yaw=16384 = Yaw=24576`).

**Refs:** `dispatch.py` (removed `_warn_base_rot` + its three call sites); regression test
`test_it_does_not_warn_on_a_base_rotated_mover_key_op`; `architecture.md` "Mover support" (now states
world-additive as a confirmed fact, previously an extrapolation).

## 2026-07-11 23:19 UTC — Drop `actor list`; `actor find` is the sole name-query verb

**Decision (Andrzej):** Remove the `actor list` verb entirely. `actor find` already prints actor
names one-per-line, its filters (`--class`/`--group`/`--name`/`--prop`/`--kind`, each repeatable)
are a **strict superset** of `list`'s (`--name`/`--class`, single), and both emitted identical
output. With no filters, `actor find` now prints every actor — fully covering `list`'s bare form.

**Context:** A CLI consistency sweep surfaced the overlap. Two name-query verbs with the same
output shape violates the tool's "verbs compose; prefer one stateless query verb over sprinkled
filter flags" convention (`CLAUDE.md`; direction.md "Explicit, discoverable, model-side"). Keeping
both bought nothing.

**This supersedes** the "*Separate `actor find` over overloading `actor list`*" choice in the
2026-06-24 (actor-find) entry **to the extent it kept `actor list` as a distinct human-readable
verb** — the two were never actually differentiated in output, so the redundancy is removed rather
than preserved. The library function `query.list_actors` is unchanged and keeps its name (it backs
`actor find` and `actor cat`).

**Rejected:**
- *Make `actor list` a human-readable table (name + class + group)* — a real second verb, but no
  one asked for a table surface and it re-splits query output into two shapes; if a table is wanted
  later it can be a formatting flag on `find`, not a separate verb.
- *Leave both* — perpetuates the redundancy the sweep set out to remove.

**Refs:** `cli.py` (removed the `list` subparser); `dispatch.py` (removed the `actor list`
handler); tests `test_parser_actor_list_is_removed`, `test_actor_find_reads_the_trunk`;
docs `README.md`, `usage.md`, `docs/README.md`, `dev-runtime.md`, `architecture.md`.

## 2026-07-12 03:06 UTC — `--target KIND/NAME`: generic content-verb targeting (level/stash/prefab), driven by prefab template editing

**Flag renamed `--target` → `--tree` on 2026-07-20 21:30 UTC** (same KIND/NAME grammar and routing;
the three boxes are one T3D-tree format, and "target" wrongly connoted a destination — see that
entry). The July-12 rejection of `--t3d-tree` ("names the FORMAT, not the box") is answered there: the
2026-07-18 23:01 unify-T3D-trees invariant made the three genuinely one tree, so `--tree` is now
accurate.

**Decision (Andrzej):** Add a single `--target <kind>/<name>` flag (kind ∈ `{level, stash, prefab}`)
to every shared content verb, so `actor`/`brush`/`poly`/`vertex`/`mover key` can edit a stash or a
prefab in place, not just the selected level. Default (omitted) is `level/<current selected level>`
— exactly today's behavior. Mechanism: two new `LevelSource` classes (`StashLevelSource`,
`PrefabLevelSource`) beside the existing `TrunkLevelSource`, selected by a parse branch in
`_resolve_level_source`; verbs stay source-agnostic (they only touch `src.load()`/`src.save()`), so
there is no per-verb logic change. Specced in
`specs/2026-07-12-uedcli-target-flag-design.md` (ephemeral).

**Motivation — prefab _template_ editing.** Fixing a library component today is a 4-step roundtrip
(apply → edit in level → capture → promote --force). Editing a prefab in place is a real recurring
need AND safe: a prefab is durable/git-tracked, so the "edited scratch thinking it was the level"
footgun does not apply. Explicit `--target` also dissolves that footgun for stashes (you must *name*
the scratch box; the default is the durable level), so stash/level targeting come along for free at
~no extra cost.

**Grammar:** split the value on the FIRST `/` — the prefix must be one of the three fixed kinds
(unambiguous), the remainder is the (possibly nested) name (`stash/hangar/archway`). Malformed value
/ unknown kind / non-existent target all resolve to a clean exit 2 (reusing the stash/prefab
"not found" guards). Save recomputes the stored `packages` from the edited actors
(`referenced_packages`) so a `--texture` edit updates the dep set; `meta`/anchor preserved.

**Scope:** content verbs only. Generators (`actor build`/`brush build` → stdout) and level-lifecycle
(`materialize`/`preview`/`select`/`status`/`doctor`) stay level-scoped. Container-lifecycle
(`stash capture/apply/promote/…`, `prefab apply/drop`) is kind-specific and unchanged. Fully
additive — no grammar migration; lifecycle verbs stay verb-first.

**Flag-name deliberation (rejected alternatives):**
- *`prefab <name> <content-verb>` (container-first, name-first grammar)* — rejected: verb-first
  lifecycle (`prefab show door`) doesn't compose with content verbs that carry their own name
  (`prefab poly set door Panel:2` has two positionals doing different jobs), and it would force a
  migration of every prefab verb. A flag keeps content verbs verb-first and needs no migration.
- *Full `{level,stash,prefab} {actor …, brush …}` container-first overhaul* — rejected as
  over-engineering: the common (level) case gains nothing under "level implicit", content verbs
  proliferate across four mount points (bigger tree, not smaller), and the per-container lifecycle
  verbs stay distinct anyway. The flag captures the whole benefit (targeting) without the grammar
  churn.
- *Per-kind flags `--prefab NAME` / `--stash ID`* — rejected: two flags where one uniform
  `--target KIND/NAME` generalizes and extends to a new kind for free.
- *Name `--in`/`--on`* — prepositions, not a noun for "the box"; and the "consistent with existing
  prepositional flags" claim was an overreach (no `--in` exists to be consistent with).
- *Name `--container`* — rejected: collides with the just-removed docker `--container` flag (still a
  live concept in the tool). *`--source`* — implies read-only (this is read+write).
- *Name `--t3d-tree`* — rejected: names the on-disk FORMAT not the logical box, and is inaccurate —
  "T3D tree" is defined (`architecture.md`) as the LEVEL trunk's per-actor-dir layout specifically;
  a stash is the flat `read_state_dir` form and a prefab is a `.t3d` blob + `.json` sidecar, neither
  a per-actor tree. *`--store`/`--t3d-store`* — rejected: "store" is the exact term the session-store
  removal deleted (`session_store_root`→`state_root`; docs now say "the store was removed"), so a
  `--store` flag would contradict the docs; and "store" connotes the repository-that-holds-many (the
  `FileStashRegister` IS a store) not one box.
- *`--target` chosen* — the category is genuinely heterogeneous (durable map / scratch clipboard /
  library part sharing only "holds editable actors"), so every umbrella noun is somewhat abstract;
  `--target` (Andrzej's first instinct) is widely understood as "the entity a command acts on"
  (`docker build --target`), and the mild destination connotation is acceptable.

**Non-goals:** NO instance/placement refresh — editing a prefab changes the template for future
`apply`s, never the copies already placed in levels (apply = copy, no back-link); "update every
placed door" is a separate, much larger feature. No new lifecycle verbs. Concurrent same-box edits
are last-writer-wins via the atomic swap (no corruption, no merge) — acceptable for v1.

**Refs (on build):** `dispatch.py` (`StashLevelSource`/`PrefabLevelSource`, `_resolve_level_source`
branch, `_target_flag` helper), `cli.py` (flag on content verbs), `architecture.md` (fold in the
source-selection + the three sources), `specs/2026-07-12-uedcli-target-flag-design.md`.

## 2026-07-12 07:37 UTC — `level preview` posing is unrenderable headless; replace POS@ROT with brush auto-frame

**Decision.** `level preview`'s per-shot vantage is no longer a camera pose (`POS@ROT[:MODE][=NAME]`)
but an **auto-frame target** (`TARGET[:MODE][=NAME]`): `TARGET` is a brush actor name (the editor
`CAMERA ALIGN NAME=<brush>` repositions + aims the camera to frame it) or the reserved word `all`
(alias `level`, and the default when omitted) = the **level overview**, resolved to the largest
`CSG_Subtract` brush (the enclosing room). Framing is size-locked (distance ∝ the target brush's own
size) and single-angle; no arbitrary pitch/yaw.

**Why.** Live calibration (spike `2026-07-12-preview-pose-calibration/`) proved the old posing never
worked: `CAMERA ALIGN` on the helper **point** actor sets camera *position* only — its `Rotation`
FRotator never reaches the headless render. All nine calibration poses (yaw {0,90,180,270} × pitch
{−89…+89}) rendered the **identical** view; every past "distinct posed image" differed by *position*,
not aim (the 2026-06-20 "adopts the full FRotator" result verified the *stored* rotation via a `MAP
SAVE` readback, never the pixels). Aligning to a **brush** instead DOES re-aim the render (verified on
the castle: distinct, correctly-framed shots of the keep, a tower, and the room). So the only
console-reachable aiming primitive headless is brush-frame; the pose interface was a fiction.

**Rejected alternatives.**
- *Keep chasing arbitrary pose* (find a repaint/console path that makes the stored rotation render):
  deferred, not abandoned — logged as a "steerable framing angle" spike carrying the specific untested
  lead (point-align to set position, then brush-align to fit). May be a headless SoftDrv dead end.
- *Correct the `PRESETS` pitch/yaw signs* (the original build-TODO): moot — no angle is ever honored,
  so the table was deleted, not fixed.
- *A synthetic bbox marker for the overview*: unnecessary — an invisible (`PolyFlags=1`) vs visible
  marker rendered byte-identical (backface-culled from inside the sealed room), so `all` frames the
  real enclosing subtract directly, no synthetic actor / no new flag.
- *Union-of-all-AABBs overview target*: you can't `CAMERA ALIGN` to an abstract AABB, only to a real
  brush; the largest subtract is the concrete stand-in.

**Consequence / known limits.** v1 is a real capability reduction vs the *promise* of POS@ROT: one
canonical angle per brush, size-locked framing (small brushes → tight close-ups, no in-context
padding), interior-only (the camera can't leave the enclosing subtract → no exterior bird's-eye; a
level-geometry property). The reliably-useful shot is the `all` overview; specific-actor framing is a
size-dependent convenience.

## 2026-07-12 12:15 UTC — Ingest of user-concatenated T3D must uniquify per-actor, not Name-key-collapse

**Decision.** Every path that ingests **user-supplied, concatenated T3D** — `actor add <file|->` and
`stash capture --from-t3d/--from-stdin` — parses via a new `model.parse_t3d_actors(text)` (an
ordered list that PRESERVES duplicate `Name`s), NOT `parse_t3d` (whose `dict[Name]→Actor` silently
keeps only the last of each duplicate group). `parse_t3d` is refactored to build its dict from
`parse_t3d_actors`, so the collapse is now a deliberate property of the *stored-level* dict, not of
parsing. `actor add` then mints a distinct `<stem>_<rand>` per incoming actor (all N survive);
`stash capture` **filters by the requested names first (raw), then uniquifies the chosen set**
(first keeps its bare Name, later collisions get an `alloc_name` suffix). `actor add` also prints
`added N actor(s)` so a collapse is visible, not silent.

**Why.** Dogfooding a castle (inbox 2026-07-12, CRITICAL) concatenated 14 `brush build --base-name
Merlon` outputs into one `actor add` and silently got 1 — `parse_t3d`'s Name-keyed dict overwrote 13
*before* the existing uniquify loop ran. Same collapse on `stash capture`. Silent data loss on a
normal batch.

**Rejected alternatives.** *Change `Level.actors` to a list* — the dict-by-Name is correct and
relied on everywhere for stored levels (lookup, `in`); the bug is only at the raw-ingest boundary, so
a parse variant is the surgical fix. *Uniquify-then-filter in capture* — reintroduces the silent drop
(an explicit `capture Merlon` over two `Merlon`s would suffix the 2nd, so the bare-Name filter
matches only the 1st); filter-then-uniquify keeps both. *Error on duplicate incoming Names* — a batch
of same-named merlons is a legitimate, wanted input; uniquify (as `actor add` already did per-actor)
is the right behavior, not a rejection.

## 2026-07-12 12:15 UTC — `brush build`/`actor build` name flag is `--base-name` (a stem), not `--name`

**Decision.** The brush/point generator name flag is **`--base-name`** (dest `base_name`);
`brush build --name` is **renamed** (hard break, no alias) and `actor build` **gains** the same
`--base-name` (it previously had no name flag, so every `actor build Engine.Light` was named `Light`).

**Why.** `alloc_name` always appends `_<rand>` at `actor add`, so the passed value is only ever a
**stem/prefix** — the stored Name is always `<value>_<rand>`; calling it `--name` implied a literal
final Name it never was. `actor build`'s missing flag also forced point actors to be added one at a
time (all named `Light` → collapsed by the parse bug above).

**Rejected alternatives.** *Keep `--name`* — misleading about the suffix. *`--name-prefix`* — the
`_<rand>` is a suffix, not a prefix chain, so "prefix" is also slightly wrong; "base name" reads
cleanest. *Hidden `--name` alias for back-compat* — deliberately NOT added (Andrzej chose the clean
break to force the correct name into LLM prompts); captured as an inbox flag to revisit if
LLM-prompt breakage bites.

## 2026-07-13 19:01 UTC — `level preview` renders IN-GAME via a uplayctl-style TCP link (game replaces the editor as preview driver)

**Decision.** `level preview` is reworked to render from the **actual headless game engine**, not
UnrealEd. It boots an ephemeral **game** container and drives it over a **uedcli-owned, uplayctl-
*similar* TCP link** purpose-built for previewing: **freeze** the world (`slomo 0`), put the player in
**ghost** (no-collision) mode, **pose the pawn to an arbitrary world Location + Rotation**, and capture
the engine's own frame. Four sub-decisions:

1. **uedcli verb; the game replaces the editor as the preview driver.** Previewing stays a `uedcli`
   verb, but the *driving mechanism* switches from booting UnrealEd to booting the game + a
   preview-specific TCP link (uplayctl-*similar*, not a call-out to `uplayctl`; uedcli owns its link).
2. **Supersedes the editor auto-frame preview** (the `TARGET[:MODE][=NAME]` grammar + per-mode editor
   boot). Supersedes `2026-07-06 15:58` (preview = editor-screenshot) and `2026-07-12 07:37` (replace
   POS@ROT with brush auto-frame).
3. **Pose inputs:** absolute `--at`/`--rot`, plus **look-at** (a point or `@actor`) and **orbit**
   conveniences; **batched** (many poses → many images in one boot+freeze).
4. **Auto-materialize the trunk, but reuse a materialized `.dx` that is *current* for the trunk** —
   keyed on `canonical_level_hash` (the same oracle `verify` uses); a `--map PATH.dx` overrides.

**Why.** Two limits of the editor previewer, both hit dogfooding the castle: (a) the headless editor
render **cannot be freely posed** — `CAMERA ALIGN NAME=<brush>` only auto-frames a brush from one
canonical angle; free `POS@ROT` rotation never reaches the pixels (spike
`2026-07-12-preview-pose-calibration`), so there is no hero/arbitrary-angle shot; (b) **editor-lit ≠
in-game baked lighting** (the castle's `LE_NonIncidence` fills looked moody in `--mode lit` but washed
out in-game). The game engine is the *only* faithful, freely-posable preview surface, and uplayctl
already proves a headless game can be driven over TCP and screenshotted. Freezing (`slomo 0`) + ghost +
an exact-pose link function give arbitrary vantage points with true lighting/sky/textures.

**Rejected alternatives.**
- *Keep driving the editor (status quo).* Cannot pose freely (the fatal 2026-07-12 limitation) and is
  an unfaithful lighting preview — the two problems this exists to solve.
- *Revive the offline native rasterizer* (shelved `2026-07-06 15:58`). It would render posed angles
  but reproduces neither real BSP lighting nor sky/decorations; it was already shelved for being a
  poor likeness. The game IS the renderer we want.
- *Put previewing in `uplayctl` (it owns game-driving).* Rejected: previewing is a uedcli authoring
  concern (it owns the trunk, materialize, level hash, and the `preview` verb); routing through
  uplayctl's session lifecycle couples two tools. uedcli mirrors the *mechanism* (a small TCP link
  actor) rather than depending on uplayctl's CLI — chosen as "own link."
- *Reuse uplayctl's session/link as-is via shell-out.* Rejected for the same coupling reason; the link
  actor/protocol may be shared at the UnrealScript level, but orchestration is uedcli's.
- *Always re-materialize before preview.* Rejected: materialize is the expensive step; a level-hash
  freshness check reuses an up-to-date build. (Not a blanket cache — the hash guarantees "current for
  the trunk," so a stale build is never silently rendered.)
- *Free camera via a detached spectator/Camera actor instead of the pawn.* Deferred: "player as ghost"
  (pose the real pawn) is simpler and matches uplayctl's existing pawn-centric link; a detached camera
  can be revisited if pawn-posing proves limiting.

**Spike gate.** Live unknowns before build (spike `2026-07-13-ingame-preview`): `slomo 0` freezes yet
still renders + screenshots; an exact-pose link function moves the render camera (pitch AND roll, the
editor's failure); the BaseEyeHeight offset so `--at` = the eye; whether the game `.u` link actor can
gain a `pose` function + be recompiled into the image; whether `ghost`/`slomo` ride an existing console
passthrough. Findings fold back into `specs/2026-07-13-ingame-preview-design.md`.

## 2026-07-13 19:11 UTC — In-game preview: no uplayctl dependency (port minimal); single `Screenshot <LOC> <ROT>` verb; HUD+weapon hidden

**Decision (refines the 2026-07-13 19:01 entry, made during speccing).**
1. **No uplayctl dependency.** uedcli does NOT import, shell out to, or share a package/image with
   `uplayctl`. It **ports the minimal subset** it needs into its own tree (its own preview
   UnrealScript package + a game image built on the `dx-lum-uned` base uedcli already owns + its own
   in-container client + orchestration). uplayctl's implementation is the reference/template only.
   *(Supersedes the 19:01 aside that the link actor/protocol "may be shared at the UnrealScript
   level" — it is copied, not shared.)*
2. **One high-level TCP verb: `Screenshot <x> <y> <z> <pitch> <yaw> <roll>`.** It internally does
   everything — freeze + noclip + hide HUD + hide weapon + pose. No granular
   `FreezeTime`/`SetNoclip`/`PoseCamera`/`HideHUD` verbs on the wire. The host X-grabs the clean posed
   frame after the verb replies OK (capture stays uedcli's step, not a TCP command).
3. **HUD + first-person weapon are hidden in every preview frame** — clean architectural stills. DeusEx:
   `ShowHud(False)` (DeusExPlayer.uc:6525) + `PutInHand(None)`. Substrate-specific step in the verb.
4. **Freeze = `Level.bPlayersOnly=True`, not `slomo 0`** (spike finding). `GameInfo.SetGameSpeed` clamps
   `GameSpeed=FMax(T,0.1)` (GameInfo.uc:402-406) so `slomo 0`→0.1 (still ticking). "slomo 0" was the
   *intent to freeze*; `bPlayersOnly` is the mechanism.

**Why.** (1) Andrzej: keep the tools fully decoupled — uedcli's previewer must be self-contained, not
chained to uplayctl's lifecycle/build. (2) Andrzej: a single verb is a smaller, cleaner API surface
than exposing every engine-side concern; the caller says "screenshot from here" and the verb does the
rest. (3) A preview is an architectural still — the HUD/weapon are player-UI noise. (4) Discovered
from the DeusEx/Engine source while speccing.

**Rejected alternatives.** *Granular TCP verbs (FreezeTime/SetNoclip/PoseCamera/HideHUD)* — rejected by
Andrzej for a bloated wire surface; folded into the one `Screenshot` verb. *Share uplayctl's UPlayCtl
package/image* — rejected (see #1). *`slomo 0` freeze* — doesn't reach 0 (#4). *Leave HUD/weapon in* —
noise in an architectural preview.

## 2026-07-13 20:38 UTC — In-game preview: spec-gate resolutions (grammar, freeze/noclip, capture, spawn, cache)

**Decision (resolving the two-reviewer spec gate + Andrzej's answers; folds into the 2026-07-13
in-game-preview entries).**
- **Positional SHOT tokens, not flags** (`at:X,Y,Z;rot:P,Y` / `look:@actor` / `orbit:…`) — flags can't
  batch, and batching (N poses, one freeze) is the point. Look-at/orbit `@brush` aims at the actor's
  **AABB centre** (a brush's `Location` is its pivot, wrong target). **Roll not accepted** — `rot` is
  `pitch,yaw`; the verb forces `ViewRotation.Roll=0` (roll *does* reach pixels — `ViewShake` — so it's
  explicitly zeroed). Pitch is engine-clamped to ~±98.9° (`UpdateRotation`).
- **Noclip = `PlayerPawn.Ghost()` with cheats enabled** (Andrzej), not hand-rolled field writes —
  `Ghost` does `GotoState('CheatFlying')`, the load-bearing part (`SetPhysics(PHYS_Flying)` alone drops
  the pawn because `PlayerWalking` re-derives physics), and `CheatFlying` sets `EyeHeight=BaseEyeHeight`
  so the eye offset is exact + instant.
- **Freeze = `Level.bPlayersOnly`** (primary), **`Level.TimeDilation`~0 as fallback** if it doesn't
  render-while-frozen (Andrzej). NOT pause (the player must keep ticking to redraw re-poses).
- **Freeze/noclip/clean applied at POSSESSION, not lazily** — so intro scripts/conversations never run
  live between travel and the first shot (a conversation hijacks the camera via `ConCamera`).
- **Capture = X-framebuffer grab of the game window off `:99`** — how `uplayctl shot` works, and
  **already proven this session**. (The reviewer's "uplayctl never screenshots" premise was wrong.)
- **HUD/weapon hide via a BY-NAME-loaded substrate driver** (`DynamicLoadObject`), so the generic link
  `.uc` has **zero DeusEx compile dependency** — mirrors uplayctl's base/substrate-driver split, and
  serves the game-agnostic goal. **Weapon hidden by hiding the weapon actor directly** (synchronous),
  not async `PutInHand(None)` (Andrzej). Plus damage-flash zero + conversation guard.
- **Cache key = `canonical_level_hash(trunk)` alone** (Andrzej) — the `.dx` is a pure function of the
  trunk; packages load dynamically at runtime, so they're NOT in the key; `--rebuild` covers the rare
  materialize-logic change. **No lock** — ephemeral container per preview + atomic `.dx` swap.
- **v1 requires a valid PlayerStart** (Andrzej); a spawn failure is a clean exit-2. Auto-injecting a
  safe PlayerStart is **deferred post-v1**.
- **Render modes dropped** — one faithful lit reality; wireframe stays on `brush preview`, lint on
  `level doctor`. `brush`/`stash`/`prefab preview` (offline PGM) are unaffected.

**Why.** The gate's two cold source-verified reviewers caught: the flags/tokens contradiction, the
`SetPhysics`-drops-the-pawn bug (→ `Ghost()`), the `DeusExPlayer` cast re-coupling the "generic" link
(→ by-name driver), the buffered-log readiness trap (→ link probe authoritative), and the
stale-lighting cache over-reach. Andrzej corrected several toward simplicity (trunk-hash-only key, no
lock, require PlayerStart for v1, direct weapon hide, no roll).

**Rejected alternatives.** *Flag-based poses* — can't batch. *Cache key incl. package set + build
stamp* — packages are runtime-dynamic, not baked into the `.dx`; over-engineered (Andrzej). *Per-level
flock* — unnecessary given ephemeral containers + atomic swap (Andrzej). *Auto-inject PlayerStart in
v1* — deferred (Andrzej). *Replicate `Ghost`'s body ungated* — just enable cheats + call `Ghost()`
(Andrzej). *Engine screenshot-to-file* — X-grab is already proven; no need. *Accept roll* — level
horizon wanted; roll dropped (Andrzej).

## 2026-07-14 00:55 UTC — `qualify_level_textures` correlates blocks to brushes by CONTENT, not position; "semisolid breaks materialize" was a transient wedge, not a bug

**Context.** `level materialize` was failing on textured levels. Two separate things were
reported as one "semisolid breaks materialize" bug; investigation
(`dev/docs/spikes/2026-07-13-semisolid-save/`) split them:

**Decision 1 — texture qualify is position-independent (content matching).** The editor's
`OBJ DEPENDENCIES PACKAGE=MyLevel` dump emits one `Engine.Polys` block per authored brush
PLUS one extra non-empty block: the level's own world BSP `Model`, an AGGREGATE of every
brush's surviving surfaces (non-empty once any brush is textured; an older 2026-06-20 build
had seen it empty). `qualify_level_textures` used to demand `#textured-brushes ==
#non-empty-blocks` and correlate them positionally — so it raised `N vs N+1` on EVERY
textured level, aborting materialize with nothing written. The aggregate block's POSITION is
NOT stable (live-probed 2026-07-14: last for a 2-brush level, FIRST for the 95-brush castle,
middle for a World-shell level), so "drop the first/last block" is unsafe. **Each brush is
now bound to the first not-yet-claimed non-empty block whose ordered per-poly object-names
(`_bare`, the segment after the last `.`) equal the brush's own textured polys' object-names;
the world aggregate is left unclaimed and dropped.** This makes the correlation robust to the
aggregate floating anywhere in the walk, and raises loudly if a brush finds no matching block.
One load-bearing limit (cold review, 2026-07-14): matching is by object-NAME, so two brushes
sharing the same object-name from DIFFERENT packages (`PkgA.Wall` vs `PkgB.Wall`) can't be told
apart by content — that tie falls back to block ORDER, correct only because dump block order ==
authored order (`spikes/2026-06-19-read-surface-texture-package.md`). A reorder of two real brush
blocks would swap packages silently (H3 can't catch it, as it re-qualifies both sides the same
way); never observed, but it's why the empty/aggregate filter must preserve relative order.

**Why content, not position + a count guard.** A cold review established that the H3
post-verify canNOT catch a *deterministic* texture mis-bind: `verify_dx_matches` re-qualifies
the re-exported `got` with this SAME function and hash-compares against `expected`, whose
textures came from the trunk (qualified earlier by this same function) — a mis-bind made
identically on both sides matches itself. So verify only catches non-deterministic drift; the
qualifier itself must be correct-by-construction. A position-based scheme with a per-brush
poly-COUNT check is silently wrong for a single-brush level whose aggregate (same poly count)
precedes the brush's own block. Content matching removes that class of bug entirely.

**Decision 2 — "semisolid breaks MAP SAVE" is NOT a code bug (no fix).** The original one-shot
failure (castle + 1 semisolid, `--no-verify`) did not reproduce. `probe_bug2.py` ran the exact
suspect conjunction — full castle + 16 semisolids + `LIGHT APPLY` + `MAP SAVE`, **3 times**,
with solid+light and semi+no-light controls — and all 5 cells saved. The one-off was a
transient silent editor wedge (quirks.md "Stability"), not a semisolid/LIGHT-APPLY defect.
Semisolid emission is byte-correct (actor-level `PolyFlags=32`); `builders.py` is unchanged.

**Rejected alternatives.** *Drop the trailing (or first) aggregate block* — its position is
not stable (proven: castle put it first, a 6-vs-853 raise). *Keep positional zip + a `<` count
guard* — fails loud on multi-brush drift but SILENTLY mis-binds the single-brush
aggregate-precedes case; and leans on H3 verify, which can't catch a deterministic mis-bind.
*Identify the aggregate by its duplicate textured `Engine.Model` block* — works for multi-brush
but drops BOTH blocks for a single-brush level (brush Polys == Model too) → under-count; content
matching handles single-brush correctly. *Treat semisolid as a materialize bug and rework
`builders.py`* — emission is correct; the failure was transient.

## 2026-07-14 01:40 UTC — Materialize post-verify: LevelInfo-name + float32-coords + poly-Normal are round-trip noise (canonicalized); editor default-prop omission is an open gap

**Context.** With the qualify blocker fixed (entry above), a real 161-actor castle materialize
was driven end-to-end and its H3 post-verify peeled back four more round-trip fidelity
mismatches, each a case of the on-disk build faithfully matching authored INTENT while differing
in an editor-managed representation detail. Three are now canonicalized away; the fourth is
recorded as an open gap.

**Decisions (canonicalize — not authored content, so excluded from `canonical_level_hash`):**
- **LevelInfo singleton actor NAME.** The engine assigns it (`LevelInfo0`); uedcli auto-names it
  on capture (`LevelInfo_4dosan`). Canonicalized to a fixed sentinel on both sides
  (`normalize._levelinfo_rename`). Confirmed live: a trunk `LevelInfo_4dosan` re-exported as
  `LevelInfo0`.
- **Geometry coordinates → float32.** UnrealEd stores ALL geometry as IEEE single precision, so a
  full-precision authored fraction (`43.552099`) re-exports as `float32 = 43.552097`. Every
  emitted coordinate (Location, poly Origin/TextureU/V, vertices) is quantized to float32 for
  hashing (`normalize._to_f32`); integer/grid coords are unaffected.
- **Polygon `Normal` dropped.** The importer recomputes the normal from vertex winding and
  ignores the authored one (unrealed/t3d.md), so authored vs re-exported differ STRUCTURALLY (a
  roof brush's `(0.707,0.707,0)` → the true slope `(0.541,0.541,0.643)`). Winding (the vertices,
  kept) is the authoritative face direction, so the derived Normal carries no authored info.

**Open gap (NOT decided — flagged to Andrzej, `board/inbox.md`):** the editor OMITS actor props
whose value equals the class default (`LightPhase=0` on a Light is dropped on export). A trunk
carrying an explicit default then fails post-verify. A correct general fix needs class-default
awareness (a baked default table, or reading a freshly-spawned actor's defaults from the editor);
neither exists yet. The castle was demonstrated end-to-end on a copy with the redundant
`LightPhase=0` stripped — the machinery is proven; default-omission is the remaining materialize
gap.

**Why canonicalize rather than "fix the trunk".** These are editor-owned representation choices
(engine-assigned names, single-precision storage, winding-derived normals) that NO authoring
discipline can avoid — a level and its own faithful rebuild legitimately differ in them. The hash
oracle must therefore ignore them, exactly as it already ignores the builder brush, Link indices,
and computed props. Default-prop omission is the one case that is arguably authoring discipline
(don't store redundant defaults), which is why it is flagged rather than silently canonicalized —
stripping a prop that merely LOOKS default risks erasing a meaningful explicit value.

## 2026-07-14 02:20 UTC — Asset wiring: config lists bare DIRS (not globs); full cutover to config-driven /resources mounts; UED22 is the editor image, not content

**Context.** The two-file config schema (`~/.uedcli` `[games.*]` + per-project) already PARSES, but
nothing wires it to the container: the editor boots via a static `docker-compose.yml` with hardcoded
asset mounts (`/content/Textures`, `/deusex`, …) and `packages.substrate_search_dirs` is a hardcoded
host list. This lands the wiring so the composed config `paths` actually drive the mounts + the
`[Core.System] Paths` ini.

**Decisions (Andrzej, 2026-07-14):**
- **Config `paths` are bare DIRECTORIES, not globs.** You write `paths = "/…/Textures:/…/System"`,
  never `.../Textures/*.utx`. uedcli owns the five package extensions (`.u .dx .utx .uax .umx`) and
  uses that knowledge for BOTH jobs: crafting the `Paths` ini and scanning dirs for file-resolution.
  Simpler config surface; extensions live in one place (uedcli), not smeared across every config.
  *(Supersedes the glob-based `paths` semantics for the games/project configs — existing config files
  migrate from `.../X/*.ext` to `.../X`.)*
- **Full cutover.** Config-derived mounts replace BOTH the hardcoded `substrate_search_dirs` content
  list AND the static `docker-compose.yml` asset mounts (and the `/deusex`-specific entrypoint Paths
  block). Each composed dir → its own read-only BIND mount at `/resources/<n>`; the editor/materialize
  path uses them immediately. Bind mounts (not volumes — they're existing host dirs), read-only.
- **UED22 is the EDITOR, not content.** The baked v69 editor binary + its substrate `.u` stay in the
  image and are NEVER config-driven; likewise the v69 stub cache (`~/.uedcli/cache/stubs`). Config
  drives only game CONTENT (Textures/System/Music/Sounds/Maps).
- **Paths ini = per-dir-per-ext (proven), wildcard is an optional follow-on.** The entrypoint already
  ships `Paths=<dir>/*.<ext>` per dir/ext (for `/deusex/*`), so that mechanism is known-good and the
  cutover builds on it — one `Paths=/resources/<n>/*.<ext>` per (mounted dir × extension). The shorter
  `Paths=/resources/*/*.*` (middle-dir `*` + `*.*`) you floated is a nice-to-have optimization to
  spike SEPARATELY (risk: `*.*` may try non-package files); it is NOT a blocker.

**Rejected alternatives.** *Glob-based `paths`* — pushes extension knowledge into every config and is
noisier; dirs are cleaner (Andrzej). *Mechanism-first, editor stays on compose* — chose the full
cutover now (Andrzej). *Gate the whole thing on the wildcard spike* — unnecessary; per-ext is proven,
wildcard is optional. *Config-drive UED22/stub-cache too* — they're editor code, baked, not content.

## 2026-07-14 02:55 UTC — Paths generation is ONE mechanism for ALL editor search dirs, UED22 included

Refines the 02:20 entry (not a reversal). UED22 stays baked in the editor image and is NOT
user-configurable — but the editor finds its OWN substrate `.u` via `[Core.System] Paths`, so its
`Paths` line must come from the SAME generator that emits the content Paths, not a hand-preserved
baked entry (Andrzej, 2026-07-14: "UED22 must use the config paths too — it uses Paths from the INI,
so it should be the same paths generation mechanism"). Net: the crafted ini's `[Core.System] Paths`
is **fully regenerated** over the ordered container-dir list `[/opt/UED22, /stubs, /resources/<n>…]`
by one `paths_ini_lines` call — a wholesale replace, no "strip content but preserve substrate" split.
This also cleanly resolves the spec-review finding that a naive strip would delete the editor's own
substrate Paths: they're regenerated, not kept.

## 2026-07-14 03:30 UTC — Asset wiring, finalized: editor+game share the mounts; code-vs-content split; schema folded into config (kill schema_search_dirs); stubs-first; bare `*` Paths; no legacy config

Extends/settles the 02:20 + 02:55 entries with Andrzej's 2026-07-14 answers.

- **The mounts serve BOTH the editor (materialize/qualify) AND the game (preview) containers** — not
  editor-only. `container_assets` is shared by both images. (Corrects a mis-statement that "only the
  editor sees /resources".)
- **uedcli classifies each config dir by content:** a dir of **code** (`.u`, the game's v68 `System`)
  vs a dir of **content** (`.utx/.dx/.uax/.umx`).
  - **Content dirs** → read-only bind mount at `/resources/<n>`, Paths generated, visible to editor+game.
  - **Code dirs** → HOST-SIDE ONLY: the single source for (a) v69 **stub-building** and (b) `actor prop`
    **schema** reading. Never mounted/loaded directly (UED22 v69 can't load v68 `.u`); the editor loads
    the derived v69 stubs, not the v68 source.
- **`schema_search_dirs` (the bespoke hardcoded `DeusExAssets/System` path) is REMOVED** (Andrzej "a)
  Yes"): schema now reads the config code dirs — same source stubs come from. The v68-schema /
  v69-editor DISTINCTION remains (it's inherent to building maps in a foreign editor for a
  different-version game — UED22's UT-lineage `Engine`/`Core` mis-answer Deus Ex's inherited
  properties), but the divergent PATHS collapse into the one config layer.
- **Stubs are first in the Paths order** (Andrzej "b) Proceed"): `[/stubs, /opt/UED22, /resources/<n>…]`.
  Practically moot (stubs are game code, UED22 is engine/editor — no shared names), but hardcoded as
  chosen. Stubs stay host-stored (`~/.uedcli/cache/stubs`) + bind-mounted.
- **Paths line form = `Paths=/resources/<n>/*`** (bare `*`, per-dir, NO extension) — drops the per-game
  extension list AND avoids the unverifiable middle-dir `*`. Verified END-TO-END (a real materialize),
  since the standalone `OBJ LOAD PACKAGE` probe can't test Paths; fall back to explicit extensions only
  if bare `*` misbehaves (e.g. chokes on a stray non-package file).
- **No legacy config handling** (Andrzej: uedcli is WIP) — the globs→dirs change just updates the few
  existing config files; no migration path, no graceful glob-error.

**Rejected/superseded:** the "mount every config dir uniformly" simplification (a code dir can't be
mounted-and-loaded — it must go through stubbing); the separate `schema_search_dirs`; per-dir-per-ext
Paths (bare `*` is simpler and game-agnostic); substrate-before-stubs ordering.

## 2026-07-14 12:00 UTC — Bare `*` Paths DOESN'T WORK (UE1 needs `*.<ext>`); use per-dir-per-ext — SUPERSEDES the bare-`*` bullet of 03:30

The 03:30 "Paths line form = `Paths=/resources/<n>/*`" is WRONG and is superseded. The live castle
materialize through the config-driven wiring caught it: `Paths=/opt/UED22/*` (bare `*`) STALLS the
editor at boot (log dies right after "Timer Frequency"). Mechanism: UE1's `Paths` format is
`<dir>/*.<ext>` where `*` is the package NAME and the extension is REQUIRED — a bare `<dir>/*` looks
for extension-LESS files, finds no packages, and boot wedges. (This vindicates Andrzej's own earlier
worry that `*` "breaks with non-unreal files without explicit `*.utx`,`*.u`".) `container_assets.
paths_ini_lines` now emits **one line per (dir × extension)**: the code roots `/stubs` + `/opt/UED22`
→ `*.u`; each content mount → the content extensions actually present in it (host-scan). The castle
then materialized + H3-verified clean (448 KB) through the config-driven `/resources` mounts — the
end-to-end verification the standalone `OBJ LOAD PACKAGE` probe could never give. So the config stays
game-agnostic (bare dirs; uedcli owns the 5 exts), but the emitted Paths carry extensions.

## 2026-07-14 13:30 UTC — Asset wiring Part C: retire the static compose mounts + entrypoint sed; build container self-wires its mounts; its dirs come from `substrate_code_dirs` (NOT yet the project config)

Completes the cutover (Parts A+B config-drove the GUI editor; this removes the last static
plumbing and config-mount-drives the last two containers). Landed:

- **`docker-compose.yml`**: the static asset mounts (`./DeusExAssets:/deusex`, `../../../{Textures,
  Maps,System}:/content/*`, the `_scratch` Sounds/Music stub mounts) are DELETED. Only the
  baked-adjacent v69 stub cache (`${HOME}/.uedcli/cache/stubs:/stubs`) + the wine prefix remain.
- **`entrypoint.sh`**: the `$DEUSEX_ASSETS_DIR` `[Core.System] Paths` `sed -i` block is DELETED
  entirely — Paths are composed host-side and bind-mounted pre-launch for every container, so
  nothing edits the ini in-container. This makes the `UED_DEUSEX_ASSETS_DIR=/nonexistent` stopgap
  in `ensure_editor` (Part B, to skip that sed) unnecessary; it too is REMOVED. Editor still boots
  (castle materialized clean, 448822 B).
- **Build container self-wires (`stub.ephemeral_build_container`)**: it now mounts its OWN assets the
  same way the GUI editor does — the v68 `.u` decompile SOURCE (`install_system_root`) read-only at
  **`/install-system`** (was the static `/deusex/System`; `build_stub`'s `install_system_dir` default
  changed to match), the config CONTENT dirs at `/resources/<n>`, and a crafted `unrealtournament.ini`
  (Paths regenerated over `/stubs`+`/opt/UED22`+content) bind-mounted pre-launch via the shared
  `editor.engine_ini_mount`. Verified live on the host daemon: `texture sync`'s
  `batchexport CoreTexBrick` resolved by bare name through `/resources` → 21 PCX; a `DeusExItems` stub
  built v69 through `/install-system`.

**Decision — the build container's dirs come from the host `substrate_code_dirs`/`install_system_root`
lists, NOT (yet) a project's `composed_search_dirs(project)`** (provisional call, flagged to Andrzej).
The Part-C prompt floated sourcing them from `config.composed_search_dirs(project)`, but: (a) `texture
sync` / `substrate stub` / the lazy `stub_missing_packages` trigger carry NO project in scope; and (b)
the live LUM config's `[games.deusex].paths` points at the mod's own small `LUM/{System,Textures,Maps}`,
NOT the 45-package DeusEx v68 install under `DeusExAssets/` — so config-driving discovery from the
project would resolve against the wrong (mod-only) set and BREAK DeusEx stubbing/texture-sync. So Part
C only swaps the MECHANISM (static compose mounts → self-wired `container_assets` mounts + crafted
Paths) while keeping the SAME host source lists, preserving discovery semantics and staying verifiable.
Folding the v68 CODE/stub-source path onto the config `paths` layer, and re-basing `texture sync`
discovery + catalog dir onto the composed PROJECT path (Andrzej's 2026-07-11 directive), remain the
separate deferred items on `board/inbox.md` (p3 chore + p2 `[spec]`).

**Rejected/deferred:** *source the build-container dirs from `composed_search_dirs(project)` now* —
breaks DeusEx stubbing under the current config + needs project threading into the stub-cache-key
machinery (orthogonal, risks the green stub pipeline). *Keep the `/deusex` compose mount as a
fallback* — unnecessary: the self-wired mount was live-verified, so nothing unverifiable ships.

## 2026-07-14 14:30 UTC — uedcli runs HOST-NATIVE in a dev venv (retire the uedcli-dev container); asset paths need no bind-mounting into a container

The `bin/uedcli` dev wrapper ran uedcli INSIDE a `uedcli-dev` Python-3.12 container (identity
path-mapping + docker-out-of-docker). That was a convenience ("host needs no Python 3.12"), but it
forced a bad choice for reaching game asset dirs that live OUTSIDE the repo (e.g. the Deus Ex install
at `/home/…/DX`, parent of the LUM repo): to let uedcli `os.listdir`/hash them it would have to
bind-mount arbitrary host roots into the dev container at identity paths — which can shadow/clobber the
container's own dirs (`/usr`, `/opt`, …). Andrzej: "I don't want to allow bind mounts at arbitrary
paths in the container … not clean."

**Decision: run uedcli on the HOST in a Python-3.12 venv** (`bin/_venv.sh` → `.venv-uedcli/`, deps
`Pillow>=11`+`pytest`), the same runtime `bin/test` now uses. This is exactly the eventual Nuitka
release model — a host-native binary. Consequences, all clean:
- uedcli has NATIVE access to asset dirs wherever they live; no bind-mount-of-arbitrary-roots, no
  clobber risk, no `config mounts` machinery.
- uedcli is **host-path-native everywhere** — dev path-handling == prod. It never branches on
  "am I in a container?"; the ONLY container paths it emits are the ephemeral editor/build
  containers' `/resources|/stubs|/opt/UED22` (via `container_assets`, host→container remap), identical
  in dev and prod.
- The `uedcli-dev` image + `bin/_dev-run.sh` are retired. The editor/build containers uedcli DRIVES
  still run under Docker (the baked UED22 image) — only uedcli itself went native.

**Rejected:** identity-mount external roots with a `$HOME` allowlist (still mounts user paths into a
container — a stopgap, not the end-state); mount at a sandboxed prefix + translate (reintroduces the
host-vs-self path branch host-native avoids). Requires `python3.12` on PATH (pyenv) instead of pure
Docker — the accepted cost.

## 2026-07-14 17:35 UTC — Materialize OBJ-LOADs only the LEVEL's referenced packages, not the whole composed install — SUPERSEDES the 2026-07-05 whole-search-path load

The 2026-07-05 23:00 "wire the whole composed search path" load contract does NOT scale to a real
game install. Surfaced live 2026-07-14 pointing the games-config at the real 45-code/57-texture/
100-map/35-music Deus Ex install: `ensure_load` explicitly `OBJ LOAD`ed **214 packages** for a castle
that references exactly **one** (`LUM_CoreTex`), and materialize failed with an EMPTY-detail
`OBJ LOAD … failed` (empty because `driver.exec` runs `capture=False`, so the real error is only on
the editor's screen / the passthrough stderr). Diagnosed NOT as a bad package (every package,
incl. the one it failed on, loads fine in isolation and all 214 loaded cleanly on a lucky repeat) but
as the crash-prone editor **wedging silently** — and 214 `OBJ LOAD` commands are 214 chances to wedge.
NOT a config problem (Andrzej: "don't you dare blame that").

**Decision:** materialize `OBJ LOAD`s only the packages the level's own actors REFERENCE
(`apply._level_referenced_packages` — qualified `Class=` + poly `Texture=` package prefixes). The
whole composed set still populates `[Core.System] Paths` (via the mounts), so any INDIRECT
demand-load still resolves; only the explicit preload shrinks — O(level), not O(install). Plus
`ensure_load` now dismisses the "Cleaning up…" GC dialog before each `OBJ LOAD` (belt-and-suspenders
for the crash-prone editor). The full-install castle then materialized + H3-verified clean (448 KB).

**Rejected:** keep the whole-set load + make it resilient-skip only (still O(install), still hundreds
of wedge chances); trim the games-config to fewer categories (blaming the config, not the bug).

## 2026-07-14 17:40 UTC — Stub-build + texture-sync discovery config-driven; ONE uniform `resource_mounts` for code AND content; retire `substrate_code_dirs`/`enumerate_substrate_packages` — SUPERSEDES the "dirs from the host lists" call of 13:30

Un-defers the two follow-ups the 13:30 Part-C entry parked. Its blocker — "the live LUM config's
`[games.deusex].paths` points at the mod's own small dirs, NOT the DeusEx install, so config-driving
discovery would resolve the wrong set" — is GONE: the games-config now points `[games.deusex].paths`
at the real install (`DX/System:DX/Textures:DX/Sounds:DX/Music:DX/Maps`), so the composed config's
CODE split (`DX/System` + the LUM `System` overlay) IS the v68 stub source and its CONTENT split IS
the texture-sync source. So both discovery paths now source from the project's composed config, not a
hardcoded host list.

**Landed:**
- **Texture sync (`dispatch._dispatch_texture`)** is project-scoped: it resolves a project + games
  config, discovers packages from the CONTENT half of `config.composed_search_files(project,
  user_config)` (project overlay shadows game base, stem-deduped), and writes the catalog to the
  PROJECT's `catalog` dir (`config.project_catalog_dir`, default `<project>/texture-catalog/`) — not
  the retired repo-root `texture_catalog_root()`. Verified live: `texture sync --package Airfield` →
  108 textures → `uedcli/texture-catalog/Airfield.json`.
- **Stub-build source** is the composed CODE dirs (`container_assets.split_dirs(
  config.composed_search_dirs(project, user_config))[1]`), threaded through
  `stub_missing_packages`/`ensure_stub`/`compute_cache_key`/`_dep_shas`/`_code_deps` and
  `stub_closure.resolve` (`install_system: str` → `install_system_dirs: list[str]`). MULTIPLE code
  dirs are supported (LUM `System` overlay before `DX/System` base); a package resolves first-dir-wins
  (config shadowing) via `stub_closure._find_code`. `substrate stub` + the lazy trigger in
  `qualify.export_and_qualify` thread the same dirs.
- **ONE mount way (Andrzej's directive, verbatim: "single way to mount resources").** The v68 `.u`
  SOURCE dirs are NOT a separate mount scheme: the stub-build container mounts the FULL composed set
  (content + code) through the SAME `container_assets.resource_mounts` → `/resources/<n>` the editor
  uses, `batchexport`/`umodel` read the `.u` by its remapped `/resources/<n>` path
  (`container_assets.remap`), and `paths_ini_lines` now emits a line per package ext present in a
  mount (a code dir → `*.u`). A v68 `.u` reaching `[Core.System] Paths` is HARMLESS and deliberately
  not avoided (Andrzej: "Who gives a fuck if they are under INI Paths for make? … we didn't need em
  for make"): `/stubs` (v69) is FIRST in Paths, so `UCC make` always binds the v69 stub over any
  same-named v68 code mount, and the source is read by explicit path, never via Paths. The EDITOR
  (materialize/preview) still mounts the CONTENT split only, so it never gets a `.u` on Paths.
- **Retired:** `packages.substrate_code_dirs` and `packages.enumerate_substrate_packages` (no
  production caller left); `repo_paths.install_system_root`/`install_content_dirs` survive only as
  install POINTERS for schema/closure integration tests (docstrings updated to say so), no longer a
  discovery path. `build_stub`'s single `/install-system` mount is gone (was the 13:30 mechanism).

**Verified live** (host daemon, real DeusEx install): editor path unaffected (`foobar` materialized,
magic `c1 83 2a 9e`); config-driven stub SOURCE resolution reaches `batchexport` at the right
remapped `/resources/<n>` path (`DXOgg` → `/resources/r006/DXOgg.u`); texture sync end-to-end as
above. A full end-to-end stub BUILD stays blocked by the environment, NOT by this change: `Effects.u`
is absent from the install (so `DeusExItems` can't build) and the UED22-vs-DeusEx `Engine` divergence
fails decompile of packages referencing `Engine.Actor.PostPostBeginPlay` (e.g. `DXOgg`) — both
pre-existing gaps, identical before this change (the source read the same `DX/System` via the
`DeusExAssets` symlink).

**Rejected:** *a separate `/install-system/<n>` mount scheme + keep v68 off Paths* (my first cut) —
Andrzej rejected it as non-elegant ("single way to mount resources"); the collision/shadowing worries
it guarded against are moot because `/stubs` is first in Paths. *Keep `substrate_code_dirs` as the
build-container source* — that was the 13:30 stopgap, now removed since the config code split is the
correct source.

## 2026-07-14 19:21 UTC — ONE uniform mount set for ALL containers (editor/preview/texture/stub); retire the code-vs-content dir split; stubs-first Paths shadows v68 — SUPERSEDES the content-vs-code split of 03:30 + the "editor mounts content-only" of 17:40

Andrzej: *"why the fuck would you do container_assets.split_dirs? what other than complexity does it
get us? always mount ALL resources (for simplicity), but then stubs shadow game .u"* + *"I want as
uniform a mounting setup for all these places as possible"* + *".u and .utx (and others) are the same
format. .u can have textures too."*

**Decision — there is no code-vs-content DIRECTORY split.** `.u`/`.utx`/`.uax`/`.umx`/`.dx` are the
same Unreal package format; the extension is convention, not role (a `.u` can hold textures — DeusEx
skins live in `DeusExItems.u`; a `.dx` can embed them). So `container_assets.split_dirs`/`classify_dir`
are DELETED, and the WHOLE composed config dir set (`config.composed_search_dirs`) is mounted the SAME
way — `container_assets.resource_mounts` → `/resources/<n>` — for **every** container: the GUI editor
(materialize/preview), `texture sync`, and stub-build. `dispatch._composed_content_dirs` →
`_composed_dirs` (returns all); `run_materialize`/`render_shots`/`export_and_qualify` take one
`search_dirs`; `stub_closure.resolve` and the whole stub pipeline take one `search_dirs`;
`packages.schema_search_dirs` returns the whole composed set (the resolver picks `.u` by EXTENSION).

**Safety rests on Paths ORDER, not on a dir split.** `paths_ini_lines` emits `/stubs/*.u` (v69 stub
cache) then `/opt/UED22/*.u` FIRST, before any `/resources` mount. So a v69 stub SHADOWS the same-named
v68 `.u` a composed code dir puts on Paths — the editor never loads a v68 package it has stubbed. The
v68 `.u` SOURCE for stub-build is still read by EXPLICIT `/resources/<n>` path (`batchexport`/`umodel`),
never via Paths. `texture sync` now discovers EVERY package (incl `.u`) and batchexports each; one with
no textures just yields nothing and is skipped (per-package `try/except`, never fatal).

**Residual + its guard:** a v68 `.u` referenced by a materialized level that has NO stub would
otherwise demand-load the v68 via Paths and GPF/wedge the editor (vs the old content-only mounts,
where it was a clean resolve-miss). Two review passes flagged this (one HIGH). GUARDED by a gate in
the shared editor-load chokepoint: `packages.unloadable_v68_packages` flags any package whose resolved
file is a v68 `.u` under a config-mount (a game v68 code package with no shadowing stub), and
`ensure_load` REFUSES with a clean named error (`unstubbed_v68_message`, "build the stub first") BEFORE
any `OBJ LOAD` — so the failure mode is a clean rc-2, never a silent v69-loads-v68 wedge. This covers
materialize, preview, and qualify (all route through `ensure_load`). The **capability** follow-up —
AUTO-stubbing the referenced packages in `level materialize` (like `qualify` does) so such a level
actually builds instead of erroring — remains on board/inbox.md. Andrzej accepted the uniform mount
explicitly ("stubs shadow game .u"); the gate makes the unstubbed case fail safely.

**Live-verified** (real DeusEx install, host daemon): editor path unaffected — `foobar` materialized
with all 45 `DX/System` v68 `.u` now mounted + on the editor's Paths (demand-load + stubs-first keep
them inert), magic `c1 83 2a 9e`; stub SOURCE remaps correctly under the new uniform ordering (`DXOgg`
→ `/resources/r002`, DX/System being 3rd in composed order); `texture sync --package Airfield` → 108
textures → project catalog. (Full stub BUILD still env-blocked — `Effects.u` absent + `PostPostBeginPlay`
decompile divergence — not by this change.)

**Rejected:** *keep split_dirs so the editor never mounts v68 code* (the 03:30/17:40 model) — Andrzej
rejected the complexity; stubs-first makes it unnecessary for the stubbed case. *A separate
`/install-system/<n>` mount root for code* (an earlier cut) — same rejection ("single way to mount
resources"). *Filter texture-sync discovery to content extensions* — wrong, a `.u` can hold textures.

## 2026-07-16 03:03 UTC — Native `level materialize` ships MINIMUM-VIABLE paths (nav actors + empty `ReachSpecs`); the full reachspec AI-graph build (N-5) is a scoped, deferred follow-on

**Decision (Andrzej, this session).** For the native-materialize line, "paths" as a materialize
deliverable is **satisfied by the minimum-viable form already implemented**: NavigationPoint-family
actors (`PlayerStart`, `PathNode`, `PatrolPoint`, …) serialize as ordinary point actors, and the
`ULevel` body emits an **empty `ReachSpecs` array** (`Count = 0`). This is a **complete, loadable,
human-playable** result — the engine does no path validation at load and reachspecs are consumed
lazily only by monster/NPC AI (`findPathToward`/`Reachable`), so a human plays normally with zero
reachspecs (ground truth: retail `DXOnly.dx`/`Entry.dx`/`Test_Castle.dx` all ship `ReachSpecs.Count=0`
and load/play; spike section 30 §4). The pawn spawning on `NativeCSG.dx` already exercises the
`PlayerStart` nav actor live.

**The full AI reachspec graph (spike section 30 §4 "N-5") is deferred as its own slice**, NOT
attempted this session. It is a large pawn-physics port — the scout cylinder-trace reachability
(`walkReachable` `MAXTESTMOVESIZE=128`, plus fly/swim/jump), the `findBestReachable` size sweep
(18/39→70), the 1.2× `Prune` pass, and the per-node `Paths[]`/`upstreamPaths[]`/`prunedPaths[]`
static-array property tags — that cannot be responsibly verified without extensive live AI-routing
testing. The spec explicitly frames it as "an AI enhancement, not a load requirement" (§4.5).

**Rejected:** *port the full N-5 reachspec build now* — too large to complete AND verify to a trusted
state in one session alongside closing the lighting lit-render slice; shipping an unverified physics
sim would violate the "run a spike to completion / never leave a check open" rule. The minimum-viable
form is correct and complete for its scope; the full build lands later as a dedicated slice with its
own live-verification gate.

## 2026-07-16 12:13 UTC — `level preview` becomes two-backend: `--native` (offline Rust rasterizer, DEFAULT) + `--game` (the in-game faithful tier); editor-screenshot backend retired

> **Superseded in part by 2026-07-17 18:46 UTC:** point 2's "`--native` is the DEFAULT" is reversed —
> `--game` is now the default, `--native` is opt-in. Everything else in this entry (two backends on one
> verb, editor-screenshot retirement, shared pose grammar, native geometry source, `--lit` follow-up)
> still stands.

**Decision (Andrzej, speccing the native textured offline preview — spec
`specs/2026-07-16-native-preview-design.md`).** Seven choices:

1. **The native offline renderer COMPLEMENTS the in-game preview — it does not replace it.** Native
   is the instant, docker-free, freely-posable **draft tier** for the edit loop; the in-game preview
   (decision 2026-07-13 19:01, specced not built) remains the planned **faithful tier** (true baked
   lighting, sky, decorations). *This partially revises 2026-07-13 19:01's rejection of "revive the
   offline native rasterizer": it stays rejected as THE preview, and is now accepted as a draft
   tier.* (Rejected: *native replaces the in-game preview entirely* — loses the faithful lit/sky/mesh
   ground truth; *native as interim-only, demoted when `--game` lands* — the draft tier is valuable
   permanently, not a stopgap.)
2. **CLI surface: backend flags on the ONE `level preview` verb** — `level preview {--native|--game}`,
   **`--native` is the DEFAULT**, and the current editor-screenshot backend
   (`preview_render.py` + the `TARGET[:MODE][=NAME]` auto-frame grammar) is **retired/deleted when
   `--native` lands**. `--game` selects the in-game tier once built (until then: a clean exit-2
   "not built yet"). (Rejected: *keep all three backends* (`--editor`) — three codepaths incl. the
   wmctrl/crop hacks for the one backend both newer tiers exist to replace; *editor stays default
   until `--game` lands* — keeps the crash-prone editor in the hot loop longest; *a separate verb*
   (`level render`/`level draft`) — two overlapping pose surfaces; *updating `brush preview` with
   texturing instead* — considered mid-speccing, then reverted: the wanted artifact is a posed
   preview of the LEVEL, and `brush preview` stays the wireframe inspection tool [texturing it was
   explicitly DROPPED, not deferred].)
3. **`--native` geometry = the Rust CSG build (`build_geometry`) run in-process on the trunk** —
   zero docker, zero editor; the preview renders the CARVED world (BSP surfs), not raw brushes.
   The two known N-2 residuals are accepted for a draft tier: un-merged coplanar fragments
   rasterize identically, and missing zone splits have no visual effect. (Rejected: *render the
   materialized `.dx`* — exact editor geometry but keeps docker + editor boots in the draft loop;
   *native with a `--from-dx` escape hatch* — not needed in v1, can be added later if debugging
   materialize output wants it.)
4. **Pose grammar = the in-game spec's SHOT tokens, shared verbatim across both backends**
   (`at:X,Y,Z;rot:P,Y`, `look:@actor`, `orbit:…` — spec 2026-07-13 §3/D3). The same pose tokens
   render on `--native` and later on `--game`, so switching draft→faithful is a flag. The old
   `TARGET[:MODE][=NAME]` grammar retires with the editor backend (`look:@actor` covers its
   auto-frame use-case). (Rejected: *keep the TARGET grammar + bolt pose flags on* — two grammars
   diverging between tiers.)
5. **Lighting: flat-textured v1; `--lit` is an explicitly-scoped fast-follow** consuming the N-4
   native bake (the 1-bit lightmap visibility masks × light brightness/hue). v1 ships textures with
   simple geometric shading so shapes read. (Rejected: *lit from day one* — more work before anything
   ships, and lit output is approximate regardless; *flat only, never lit* — the bake exists, the
   fast-follow is cheap and useful.)
6. **Rasterizer lives in Rust (`uedcli-native`)** — a z-buffered perspective texture-mapper is a hot
   loop; consistent with the 2026-07-14 hot-loops-in-Rust decision. Python orchestrates; Pillow
   writes the PNG. (Rejected: *pure Python/Pillow* — the perf probe already showed pure CPython
   missing targets badly on hot loops; *Python prototype then port* — slower to a usable v1.)
7. **Texture decode: promote the proven spike decoder to a shipped module** (`uedcli/utexture.py`
   from `spikes/2026-06-27-decontainerize-uedcli/harness/utexture_decode.py` — pixel-exact vs UCC
   across the corpus, spike 01). Consequence of 3/5/6 rather than a separate ask.

**Why.** The edit loop needs a preview that costs seconds, not an editor/game boot: today's editor
backend cannot pose freely and lights unfaithfully (the two 2026-07-13 findings), and the in-game
tier — while faithful — will always cost a container boot + materialize. The native pieces matured
past the 2026-07-13 "poor likeness" judgment: the N-1 CSG build carves real geometry offline, the
texture decoder is pixel-exact, and a working textured-rasterizer harness already exists
(`spikes/2026-06-27-decontainerize-uedcli/harness/native_render.py`). A draft tier that renders the
carved, textured world from any angle in-process covers the 90% "did my edit look right" case;
`--game` stays the ground truth for lighting/mood.

## 2026-07-16 15:20 UTC — Native `level materialize` builds COLLISION HULLS (`bspBuildBounds`); this — not zones — is the playability blocker

**Decision.** The native build MUST emit per-node collision hulls (`Model.LeafHulls` +
`FBspNode.iCollisionBound`), ported from the editor's `bspBuildBounds`. This is required native
build output, not optional. Render bounds (`Model.Bounds` + `iRenderBound`) stay EMPTY/`-1` (a
separate concern — the box sweep reads neither, and a `>=0` render bound re-arms the OccludeBsp
NULL-FBox crash). `zones.rs`/`TestVisibility` portalization is NOT needed for collision and remains
a separate parity slice.

**Why.** Live diagnosis (2026-07-16) disproved the handoff's assumption that missing multi-zone
portalization made the native castle unplayable. The real blocker: the player pawn fell through the
floor ("fell out of the world"), reproducing with a SINGLE subtract. Root cause (offline decode of
the game `Engine.dll` + the `harness/line_check.py` box-sweep oracle,
`spikes/2026-07-15-native-materialize/re-raw-zones/linecheck-oracle.md`): **`UModel::LineCheck`
forks on `Extent`.** `Extent==0` (a plain line trace) uses the node-plane walk `0xf3560` — what
`sections/60` decoded — and needs no hulls. But **every actor/pawn sweep is `Extent!=0`** and takes
a SEPARATE function `FBoxLineCheckInfo::BoxLineCheck` `0xf42f0`, whose only hit is produced by
clipping the swept box against `LeafHulls[node.iCollisionBound]`; `iCollisionBound==-1` → immediate
"NO HIT" (`0xf4602`). **There is no node-plane fallback for box traces**, so our `iColl=-1`/empty
`LeafHulls` build was totally non-solid to any pawn. Fix verified: box-oracle HITs at `floor+extent`
on rebuilt native maps (matching the editor), and a live boot of `NativeCastle` shows `phys=1`,
pawn resting at `(0,-250,47)`, level stays, `uplayctl shot` renders the castle first-person.

This **supersedes** `sections/60`'s closing "`iCollisionBound=-1` is fine / no collision hull
required" — true only for the zero-extent line trace. (Rejected alternatives: *fix zones first* —
zones are playability-neutral for collision, D-review + oracle confirmed; *fix the finalize
front/back swap / node flags* — the reviewers' initial hypothesis, refuted by the oracle: topology
and flags are correct, the box path simply never consults them.)

**Hull format** (`re-raw-zones/linecheck-oracle.md`): per solid terminal BSP cell, one `LeafHulls`
run `[bounding plane-node ref (| 0x40000000 = FLIP so the normal points OUT of solid), …, -1, 6×
raw-i32-bitcast f32 bbox]`; the owning node (whose child on the solid side is `-1`) gets
`iCollisionBound` = the run start. A ±32768 world bbox is emitted (the bounding planes fully define
the convex cell). Coplanar `iPlane`-chain nodes are not traversed (matches the editor `FilterBound`).

## 2026-07-16 17:30 UTC — Native `TestVisibility` zones ported (leaves/flood/ZoneActor); CSG-geometry parity is the remaining gap to identical rendering

**Decision.** The native build now ports `TestVisibility` (`uedcli-native/src/zones.rs`): real
per-cell leaves (Pass A), a leaf-adjacency portal graph + union-find zone flood (a `PF_Portal` surf
separates zones), per-node `iZone`/`ZoneMask`, `Connectivity`, and per-surf `iZone`; ZoneActor refs
(ZoneInfo/SkyZoneInfo) are wired at assembly (`_patch_zone_refs`). Per-poly `PolyFlags` are now
carried into the build (`_build_brush_input` → `BrushTuple.poly_flags_flat` → Rust FPoly), so
Portal/FakeBackdrop/Translucent surfaces exist. This supersedes the single-zone stub +
`_multizone_warning` (removed). Zone MEMBERSHIP is approximate vs the editor (the flood is a
centroid/poly-filter simplification of the exact `sub_aa370` passes), acceptable for now: the pawn's
zone is valid and disconnected regions (SkyBox) separate.

**The remaining gap to rendering IDENTICALLY to UnrealEd is CSG geometry, not zones.** Live A/B at
the same spawn (0,-250,47) shows the native `NativeCastle` and the editor `Test_Castle` render
DIFFERENTLY: ~11% of a solidity grid diverges, traced to ~8 of 95 brushes (battlement merlons, some
walls/steps, an arrow-slit) building a different solid/void than the editor — the player sees through
missing walls. This is in the CSG/BSP core (`csg.rs`/`build.rs`), untouched by the collision/zones
work, and is the same family as the b/f xfail residuals: the surf-SET differential passes but
SOLIDITY parity on complex abutting/edge geometry is unported. Closing it is the full-parity effort
(user directive 2026-07-16: land playable+zones, then pursue CSG parity). (Rejected: *treat playable
as done* — the user wants pixel-identical rendering; *fix the sky/FakeBackdrop separately* — the
sky/rainbow is largely a SYMPTOM of the missing walls, since the editor view is fully enclosed.)

## 2026-07-16 15:49 UTC — the `--game` preview container wires its packages/ini from the uedcli config (composed search path), not an uplayctl-style asset root

**Decision (Andrzej, mid-build directive).** The in-game preview tier resolves the game's base
packages AND the project overlay through the SAME config machinery every other container-driving
uedcli verb uses: the per-user `~/.uedcli/config.toml` `[games.<game>].paths` plus the project
`uedcli/config.toml` `paths`, composed project-shadows-base (`config.composed_search_dirs` /
`composed_search_files`). The game container's mounts come from `container_assets.resource_mounts`
over that composed set, and the game ini's package search path (`[Core.System] Paths` in
`DeusEx.ini`) is GENERATED from the same set — the crafted-ini pattern the editor already uses
(`editor.engine_ini_mount`), adapted to the game ini's extra boot keys (`LocalMap`, `Console=`,
render device, resolution).

**Rejected:** porting uplayctl's asset wiring verbatim — its `~/.uplayctl/config.toml` asset root
mounted whole at `/deusex` plus a single `DX_OVERLAY` dir at `/overlay`, with the entrypoint
assembling a symlink-farm game root. uedcli already standardized on ONE uniform config-driven
mount + crafted-ini scheme (asset-wiring decisions 2026-07-14); a second bespoke asset-resolution
scheme inside the same tool would fork package resolution and ignore the project/base layering the
config already encodes. uplayctl remains the reference for the boot/link/travel MECHANICS only.

## 2026-07-16 — native CSG classifier is POINT-IN-SOLID, not rebuilt-BSP propagation

**Decision.** The native CSG leaf-filter (`csg::bsp_brush_csg`) classifies each face fragment
keep/discard by REPLAYING CSG against the accumulated convex brushes — a `point_in_solid` test —
instead of trusting the `outside` flag propagated through a classify BSP rebuilt from the
accumulated world SURFACE list at each brush step.

**Why.** The rebuilt-classify-BSP approach was surface-based: it rebuilt `build::build_bsp(&world_
polys)` per brush and filtered faces through it. For complex non-axis-aligned geometry (an
octagonal tower's diagonal planes) the intermediate surface set is not perfectly watertight, so the
rebuilt tree misclassifies some empty regions as solid; the next brush's faces in that region are
then over-discarded (an Add's faces read "inside" → dropped), so its solid never forms — the
"missing walls" bug (a box wall added AFTER an octagonal tower built no solid; reversing brush
order built it correctly). ~8 of 95 castle brushes diverged (~11% grid-solidity) from the editor.

**Mechanism.** The classify BSP is kept ONLY to SPLIT faces at boundaries so surviving fragments
align with existing geometry. Each terminal fragment's keep/discard is decided by sampling FULL
solidity (`point_in_solid` over the world-space `WorldBrush` list threaded from `build`,
convex-hull membership within `EPS_CONVEX=0.1`) just in front of (+normal) and behind (−normal) the
fragment centroid (`EPS_NUDGE=0.5`, along the TRUE winding normal): void-front/solid-back → Outside
(as-authored), solid-front/void-back → Inside (reversed), solid-both → CospatialFacingIn,
void-both → CospatialFacingOut. These feed the UNCHANGED per-CsgOper leaf funcs, so the winding
conventions (Add as-authored, Subtract reversed) and the §6.5 buried-face annihilation are
preserved — the fix only changes WHICH fragments survive.

**Two build-side corrections for sheared brushes** (`build.rs`): (a) before the final BSP partition,
re-derive each surviving face's plane normal from its winding — a diagonal-wall brush stores a stale
PRE-shear AXIS normal that is geometrically wrong for the slanted face, which otherwise gives an
axis-aligned FINAL node plane and misroutes the point-region descent; (b) after `bsp_build_bounds`,
re-check each terminal leaf's solidity against `point_in_solid` and clear a spurious empty-leaf ref
where `zones::assign_leaves`'s `outside` propagation (the same propagation weakness, now in the
FINAL tree) mis-marked a solid cell empty (solid corrections only; collision hulls untouched).

**Result (gate).** Castle centroid divergence 8 → 0; dense-grid solidity agreement ~89% → 99.76%;
the editor-golden CSG differential (a/c/d/e) and the full offline suite stay green; b/f stay xfail.

**Rejected:** UE1-faithful incremental BSP CSG (`bspBrushCSG` adds/removes nodes rather than
rebuilding a classifier) — heavier; the point-in-solid classifier sufficed. Recomputing winding
normals DURING CSG (not just for the oracle + final partition) was tried and rejected: it perturbs
the split/coplanar-merge path and made divergence worse.

**Residual (not a regression):** ~0.24% of dense-grid cells still read native-solid where the editor
is empty — thin shells along slant planes from the un-ported `bspOptGeom`/Balance=50 BSP-quality
trim (already tracked as the b/f xfail). The point-in-solid leaf correction only clears spurious
SOLID cells (never invents empty leaves), so these remain; see board/inbox.md.

## 2026-07-17 04:36 UTC — Native byte-identity ⇒ port UnrealEd's INCREMENTAL `bspBrushCSG` (supersedes the scope of the point-in-solid classifier for the byte-identical goal)

**Decision.** To make native `level materialize` produce a `.dx` `UModel` **byte-for-byte identical**
to UnrealEd's build of the same trunk, replace the native CSG core — per-brush point-in-solid
classifier → surface poly list → ONE from-scratch partition — with a faithful port of the editor's
`csgRebuild` pipeline: **incremental `bspBrushCSG`** over structural brushes (each brush's polys
filtered through the GROWING world node tree via `FilterFPoly`, fragments added as nodes bounded by
the brush's temp-BSP bevel planes) → **`bspRepartition`** (`bspBuildFPolys` → `bspMergeCoplanars` →
from-scratch `bspBuild`) → `TestVisibility` → a **semisolid second incremental layer** (not
repartitioned) → **`bspOptGeom`** → `bspBuildBounds`. Design: `specs/bspbrushcsg-port.md`.

**Why.** The 2026-07-16 "point-in-solid classifier" decision established that a point-in-solid
classifier is sufficient for CSG *correctness* (which faces survive, watertight solidity) and
explicitly REJECTED the UE1-faithful incremental BSP CSG as "heavier; the classifier sufficed." That
holds for correctness — but it is structurally INCAPABLE of byte-identity: the editor's node count
(castle 1156 vs our 909), FVert pool (16163 vs 3604), surf count (485 vs 438) and render `Bounds`
(484 vs 0) come *precisely* from the fat CSG-fragmented, coplanar-fused faces the incremental build
retains and the semisolid/zone-split fragments it adds. Instruction-level decode proved
`SplitPolyList` is a PURE partition with no hidden leaf-bounding pass
(`re-raw-zones/bspbuild-splitpolylist-decode.md`), so the extra structure can ONLY be reproduced by
the incremental construction. This decision therefore does not overturn the earlier one — it narrows
its applicability: the classifier stays valid for the "playable + close" build and is **demoted to a
differential VALIDATION oracle**; the faithful incremental path is what the byte-identity goal
requires.

**Rejected alternatives.** (a) Keep the classifier and post-process the tree to inflate fragments to
match — impossible; the fragment set is an emergent property of incremental filtering, not
recoverable from a collapsed surface list. (b) Canonicalize both sides and compare topology only —
that is the *fallback* (Q2), not the target. (c) Continue with the synthetic leaf-bounding scaffold —
it makes collision behave but never approaches byte-identity and is deleted by this port.

## 2026-07-17 04:36 UTC — Delete the synthetic leaf-bounding scaffold once the faithful CSG lands

**Decision.** The synthetic collision-repair scaffold (`build.rs::bound_leaked_solid_leaves` +
`collect_leaks`/`insert_solid_bound`/`region_interior_point`, the `NF_SOLID_BOUND` 0x40 transient
marker and its handling in `finalize`/`zones`, the post-build point-in-solid leaf-correction loop,
and `passes.rs::cull_parallel_planes` + the ±WORLD_MAX bbox shortcut) is **removed** as the faithful
incremental `bspBrushCSG` bounds every solid leaf with REAL faces (watertight by construction) and
`bspBuildBounds` builds real hulls. Deletion is **gated per phase**: each piece is removed only in
the phase whose byte-diff gate proves the faithful path subsumes it, and the collision box-drop test
(`test_native_collision.py`) must stay green in the SAME commit that deletes it (a red box-drop
blocks the deletion — no collision hole may open).

**Why.** The scaffold (spike `sections/80`) is explicitly "not a reproduction of any real editor
pass — a synthetic topology repair"; it grafts fake `NF_SOLID_BOUND` nodes and slack hull planes
that the editor never emits, so it is incompatible with byte-identity. The faithful build makes it
redundant.

**Rejected.** Keeping the scaffold behind a flag "just in case" — it would diverge the tree from the
editor's and defeat the goal; git history is the recovery route.

## 2026-07-17 04:36 UTC — Byte-identity scope + FP-feasibility stance + the same-trunk editor oracle

**Decision (scope).** The byte-identity target is the **`UModel` export body + the Name/Import/Export
tables**, with the per-save random package **GUID and timestamps EXCLUDED** (the header can never
match an independent editor save; a whole-file diff copies the golden GUID). Confirmed open as Q1 in
the spec.

**Decision (oracle).** Parity is judged by **materializing the SAME trunk both ways** — native
`build_geometry` vs the editor (`MAP IMPORT` + `MAP REBUILD` pinned to the byte-verified
`Balance=50, PortalBias=70, OPTIMAL`) — and byte-diffing. `Maps/Test_Castle.dx` is the castle golden
(the editor build of `_scratch/castle/uedcli/maps/foobar`), `DXOnly.dx` a trivial golden, the CSG
differential fixtures the micro-goldens. The oracle must be **regeneratable on demand** (a committed
regen script rebuilds the golden from the trunk), and an **editor-determinism precondition**
(build the same trunk twice in the editor, diff == 0) is checked before any port work — if the
editor's own build is not reproducible, byte-identity is impossible and the goal reframes.

**Decision (FP feasibility — provisional, ACHIEVABLE).** Bit-exact f32 in Rust is provisionally
achievable and is the target. Rationale: the already-decoded routines quote **SSE-scalar**
instructions (`minss/maxss/mulss/movss/xorps` in `bspBuildBounds`/`BuildInfiniteFPoly`/
`BuildZoneMasks`), i.e. true 32-bit floats with NO x87 80-bit intermediates — which Rust `f32`
matches exactly, contingent only on operation order (already fixed left-to-right in `fpoly.rs`/
`Vec3::dot`). A blocking **Phase-0 per-site FP characterization** converts this to a verdict at every
hot site (`SplitWithPlane`, `FindBestSplit`, `bspAddPoint`, `CalcNormal`/normalize/`appSqrt`).
Fallback ladder if a site uses `rsqrt`/x87: emulate that exact op locally; failing that, relax to
**structurally-identical + byte-identical after a canonicalization/snap pass** (Q2 — Andrzej's call).

**Why.** Byte-identity of a BSP is cliff-edged in FP: a single f32 dot-product landing on the other
side of `SplitWithPlane`'s 0.25 band picks a different splitter and diverges the whole subtree; split
vertices are serialized as raw 4-byte f32 so a last-ULP difference changes the bytes and can flip a
`bspAddPoint` dedup. Whether this is reachable hinges entirely on x87-vs-SSE, hence characterizing it
first.

**Rejected.** Assuming x87 and building an emulator up front (premature — the SSE evidence says
likely unnecessary); assuming SSE and skipping characterization (too risky — one x87/`rsqrt` site
silently defeats the whole effort).

## 2026-07-17 18:00 UTC — Phase-0 feasibility resolved: FP is SSE-scalar, byte-identity is GO (supersedes the "provisional, ACHIEVABLE" FP stance of 2026-07-17 04:36)

**Decision.** The blocking Phase-0 feasibility spike is COMPLETE and the verdict is **GO** — literal
`UModel`-body + name/import/export-table byte-identity (GUID/timestamps excluded) is **reachable** for
the castle-class trunk. This supersedes the *provisional* FP stance in the 2026-07-17 04:36 "Byte-
identity scope + FP-feasibility" entry with an evidence-backed one. Evidence:
`spikes/2026-07-15-native-materialize/81-phase0-feasibility.md` +
`re-raw-zones/fp-classification-sites.md` (per-site disassembly).

**Load-bearing finding — build provenance.** The UED22 DLLs (`Editor/Engine/core.dll`) are a **2022
MSVC/VS2022 rebuild** (linker version 14.32, TimeDateStamp 2022-10-29), NOT the 1999 retail MSVC6
binaries, and the `dx-lum-uned` container that materializes the golden ships the **MD5-identical**
binaries. 32-bit MSVC defaults to `/arch:SSE2` ⇒ scalar float is true-32-bit SSE, no x87 80-bit
intermediates. This **retires the "1999/x87 → needs extended-precision emulation" risk branch** and
also answers the cold-reviewer caution ("observed `minss/mulss` might be localized FVector intrinsics,
not proof the scalar CSG hot path is SSE") — the scalar hot path itself (the split-param `divss`, the
±0.25 `comiss` classify band) was disassembled and **is** SSE-scalar.

**The four gates (all PASS).** (1) FP: every classification/pool/normalize site is SSE-scalar or
f64-`sqrtsd`+f32-`divss`; no x87, no `rsqrt` on the surf path. (2) Input identity: all 95 castle
brushes are identity-scale/zero-rotation/zero-sheer/zero-prepivot ⇒ world transform is a bit-trivial
`v+Location` translation. (3) Editor determinism: deterministic tree-walk + array-append emission, only
GUID+timestamp vary (excluded) — static PASS. (4) The four decodes: dedup = `UModel::FindNearestVertex`
(BSP nearest search, thresh 0.002, deterministic order); `bspRefresh` = reachability-GC compaction;
`NumSharedSides` = `bspOptGeom` T-junction tally; **normal provenance = PRESERVE the authored T3D
normal** (`FPoly::Finalize` recomputes only a zero normal — the diagonal `0.707107` is kept verbatim,
NOT recomputed to `0.70710677`).

**Honest fallback framing (narrows the earlier "relax to canonicalize/snap").** Canonicalization is
NARROW: a snap pass only rescues sub-ULP value noise on an ALREADY topology-identical tree. A 1-ULP
split vertex can flip a `bspAddPoint` dedup or reclassify a poly across the ±0.25 band → a topology
cliff snap cannot fix. So if a CLASSIFICATION-affecting site were ever x87/`rsqrt`-bound and
unemulatable, the honest fallback is **"abandon literal byte-identity, keep structural + functional
parity"**, NOT "byte-identical after snap." Phase 0 found no such site on the castle surf path, so the
fallback is not triggered; it re-arms only if the lightmap bake (Phase E) or rotated content surfaces
one (Q2).

**Residual (does not block GO; tracked in `board/inbox.md`).** Rotated-brush input identity — the
editor's `BuildCoords` FRotator→matrix uses the `GMath` sine LOOKUP TABLE, not libm `sinf`, so
rotated content (UNATCO-class) needs that table ported before its input is bit-identical;
`materialize.py` already rejects non-identity rotation with a `BuildError`. Also: xref
`FVector::Normalize` (`0x24940`, the one x87 `fdivrp` reciprocal) against the CSG-build call graph;
and run the empirical GUID-masked editor double-build as determinism corroboration.

**Rejected.** Starting the from-scratch CSG port before Phase 0 (the reviewers gated it); assuming
x87 and building an emulator (the binary is SSE); treating snap as the FP fallback for a
classification-affecting divergence (dishonest — snap can't cross a topology cliff).

## 2026-07-17 21:30 UTC — First byte-identity increment: the incremental `bspBrushCSG` core lands as a SEPARATE, FLAGGED path (default untouched)

**Decision.** The port of UnrealEd's incremental `bspBrushCSG` (the GO'd byte-identity plan of the
2026-07-17 04:36/18:00 entries) is implemented as a **new, opt-in Rust module `bspcsg.rs`** exporting
`uedcli_native.build_geometry_bspcsg`, strictly PARALLEL to the existing default
`build_geometry`/`build.rs`. The default point-in-solid-classifier path and its byte outputs stay
UNCHANGED and the offline suite stays green — the new core is additive, selected only by the new entry
point. `point_in_solid` is retained as the **differential validation oracle** (the new core's descent
solidity is gated against it), not replaced.

**What the increment reaches (castle, 95 brushes).** End-to-end incremental build → serializable
UModel. Section counts move toward the editor: nodes 909→1235 (ed 1156), surfs 438→506 (ed 485),
points 1563→2509 (ed 2035), verts 3604→4914 (ed 16163). Descent-solidity vs the oracle: 99.35%
(repartition on) / 99.52% (repartition off), vs the default 99.79% — NOT yet at the correctness floor.

**Residual to node-for-node parity, by stage** (full detail in `board/inbox.md`): the dominant
false-solid + a chunk of the vert gap trace to the **FILTER stage** — `FilterWorldThroughBrush` is a
face-level cut that deletes fully-interior faces and annihilates shared walls but clips (does not
node-SPLIT) straddling world faces; the **MERGE/REPARTITION** from-scratch `bspBuild` leaks on the
non-watertight soup and does not yet reproduce the editor's retained-T-junction ~14-FVert/node
fatness; `num_shared_sides` (bspOptGeom side-linking) and `bounds` (render bounds, deliberately empty
on native) are unbuilt. The two decode items still needing a LIVE differential trace to finalize are
the coplanar-cascade micro-order and the exact `SubtractBrushFromWorldFunc` mirror (both flagged
PARTIAL in `82-bspbrushcsg-port-decode.md §6`).

**Rejected.** Modifying `build.rs`/`csg.rs` in place (the guardrail keeps the validated default path
byte-stable; the new core duplicates the pooling/`bspAddNode` helpers rather than change their
visibility). Using the point-in-solid oracle to *classify surviving faces* in the new core (that is
the default path's method — the new core must earn solidity from topology, so the oracle stays a
GATE, not an input). Reverting to the `SPLIT_WEIGHT` `FindBestSplit` deviation (the new core uses the
byte-exact engine score for the repartition).

## 2026-07-17 06:57 UTC — `--game` preview: one warm reusable container + bind-mounted, hash-named map delivery

**Decision (Andrzej, 2026-07-17).** The `level preview --game` tier moves from a per-command
ephemeral container to **ONE machine-global reusable game container**, `flock`-serialized (one
preview at a time — no registry of many), that **self-terminates after 10 min idle** from inside
(last-use marker + internal watchdog). This amortizes the ~90 s boot across an edit→preview loop.
Map delivery becomes: materialize/copy the level to a **hash-named** file in the existing
`<project>/uedcli/tmp/preview/` freshness dir, which is **bind-mounted** into the container; the
host then **symlinks that one map into the LOCAL Maps farm** so it resolves via the existing
boot-safe RELATIVE Paths — deliberately NOT via a raw `Paths=/resources/preview/*.dx` glob, which
would reintroduce the esync boot wedge (globbing raw bind mounts at startup — the 2026-07-16 fix).
Trunk maps are `<level>.<hash12>.dx` (`canonical_level_hash`); `--map` copies are
`imported-<contenthash12>.<ext>`, provably non-clashing with trunk names. Unique names force a
guaranteed-fresh reload of a changed level from the engine's package-name-keyed object pool —
GATED on a live spike (SP-R) that decides whether the engine keys by FILENAME (rename-only
suffices) or INTERNAL name (trunk materialize must also rename the internal level-package). `--map`
accepts `.dx` AND `.unr`; the farm/Paths glob both; trunk materialize stays substrate-native
(`.dx`). Spec: `specs/2026-07-17-game-preview-warm-container.md` (3 review rounds requested).

**Supersedes for `--game` preview only:** the per-command-ephemeral / no-shared-session invariant
(D5/D7 of the 2026-07-06 per-command editor identity + the 2026-07-13 in-game spec) — the warm
container is shared and lock-serialized instead of ephemeral-and-parallel-safe. Editor/build/stash
containers remain per-command ephemeral.

**Rejected:** (a) a per-project POOL / session registry of warm containers — one global container
is enough for an interactive loop and far simpler (Andrzej). (b) Delivering the map via a raw
`Paths=/resources/preview/*.dx` bind-mount glob — even though that dir is empty at boot (so the
esync risk is probably low), the local-farm-symlink path is provably boot-safe and was chosen to
not re-litigate the 2026-07-16 boot fix. (c) `.unr` OUTPUT from materialize — no Unreal substrate
exists to target; input+globs only.

## 2026-07-17 07:30 UTC — (supersedes the 2026-07-17 06:57 warm-container entry, in part) per-user identity + `materialized__`/`copied__` naming + foreground-watchdog teardown

**Supersession (spec review rounds 1–2, folded).** Two points of the 2026-07-17 06:57 warm-container
decision are revised:
1. **Container identity is PER-USER, not machine-global** — name `uedcli-game-preview-<uid>` + a
   per-user `flock(2)`, so concurrent Unix users on one host never contend for the same container.
   (The 06:57 entry said "ONE machine-global reusable container".)
2. **Map naming is `materialized__<level>__<hash12>.dx` / `copied__<contenthash12>.<ext>`** — prefix
   by kind (Andrzej), dot-free in the stem (UE1 treats `.` as the `Package.Group.Object` separator;
   retail map stems never use interior dots), provably disjoint by the leading token, length-bounded
   vs the UE1 FName ceiling. (The 06:57 entry said `imported-<contenthash12>`.)

**Also folded (mechanism corrections from review, not decision reversals):** idle self-death is a
FOREGROUND watchdog (tini's child) whose `exit` stops the container — NOT `kill 1` (which is a no-op
or signal-forwarding-dependent). A SINGLE heartbeated `/work/.last_use` marker is the liveness signal
(no static in-use sentinel — that strands a container immortal on a SIGKILLed holder). `--rebuild`
appends a `uuid7`/ns-timestamp nonce (guaranteed non-resident). The reuse fingerprint includes the
image id + realpath-normalized mount `source:dest` pairs. `--keep-alive` is a container-side `.pinned`
sentinel. Overlay-package staleness uses cheap `(path,size,mtime)` stat over PROJECT-overlay packages
only. Reload keying is offline-first (UE1 package identity is likely filename-derived → the internal-
rename worry is likely moot) then spike-gated (SP-R). Full design + review provenance:
`specs/2026-07-17-game-preview-warm-container.md` (Andrzej: 4 review rounds).

### 2026-07-17 08:31 UTC — Warm-container reload keying + delivery: SP-R spike settles the gate (build unblocked)

The 4-round-reviewed warm `--game` spec (`specs/2026-07-17-game-preview-warm-container.md`) gated the
build on **SP-R**, a live spike of the one real exposure: does an already-booted game resolve a map
**symlinked** into its Maps dir **after boot**, on a **2nd..Nth `open`** in one long-lived container?
Ran it (`spikes/2026-07-17-game-preview-reload-keying/`, results.md). **All green:**

- **Gate ✅** — 5 post-boot symlinked travels to unique dot-free stems in one reused container all
  resolved (`GetURLMap`==stem), incl. Nth-open and a same-bytes-new-name case. **Symlink delivery
  form and Nth-open both work; Plan B (docker-cp real file / reboot-per-map-change) documented but
  UNNEEDED.**
- Unique filename ⇒ fresh content every time (running engine keys by FName, no resident reuse) — the
  D6 internal-rename alternative is confirmed moot.

Three review-flagged risks **deflated by data**, updating the spec:
1. **Memory leak → cheap insurance, not load-bearing.** RSS flat over 11 travels (386→414 MiB);
   levels GC'd on travel. Reboot bound kept as a backstop; travel-count N raised 40→**200**.
2. **FName-63 "silent truncation collision" → NOT reproduced at any length.** Map names resolve
   correctly to ≥180 chars and an over-long name (~250) fails **loudly** (open never resolves), never
   silently serving stale content. Production stems ≤~46 chars; §5.1 length cap set to **120** as
   belt-and-suspenders, no silent truncation possible.
3. **Conversation/datalink taint → confirmed unneeded.** A real mission map (`08_NYC_Bar`) rendered a
   clean posed frame through the no-abort driver (matches the 10 UNATCO shots). The DX-driver
   conversation abort is **dropped as a build item** (Andrzej: "it's just screenshotting"); kept only
   as a look-if-it-ever-appears watch note.

New UE1/DeusEx facts (evidence: the spike): a headless game re-resolves `open <stem>` against the
Maps dir **per-open** (not a boot snapshot), through a **symlink**, for the container's whole life;
levels are unloaded/GC'd on travel (flat RSS); map-URL resolution tolerates ≥180-char stems and fails
loudly (not silently) past that. Folded into `unrealed/` + memory.

### 2026-07-17 12:00 UTC — Native materialize: functional rotation ENABLED; default CSG oracle doesn't scale, bspcsg is the viable functional path too

Driving a real UNATCO level (`03_NYC_UNATCOHQ` trunk, 762 CSG brushes, 283 rotated) through the
native builder produced three calls (FUNCTIONAL-first — byte-identity is a separate track):

- **Rotation is now applied, not rejected.** `materialize._build_brush_input` builds the world
  rotation matrix `R` from the URU Pitch/Yaw/Roll via `rotation.actor_matrix` → `euler_to_matrix_uu`
  and passes it to the Rust `FPoly::transform` (`world = Location + R·(v − PrePivot)`), exactly as
  `preview_native` already did. `euler_to_matrix_uu` reads the **ported `GMath` sine table**
  (`rotation.gmath_sin/cos`), so the earlier "must port `BuildCoords`/`SinTab` first" precondition
  (Phase-0 residual; `81-phase0-feasibility.md`) was already met by `rotation.py`. The convention is
  the editor-verified `2026-06-19-frotator-convention` one. Verified on a controlled single box
  (`harness/verify_rotated_brush.py`: native CSG world verts == `rotation.world_vertices` for
  pure/combined/arbitrary Yaw/Pitch/Roll; −90° Yaw sends `+X(256,0,0)→(0,−256,0)`).
  *Rejected:* keeping the hard `BuildError` until the byte-identity port lands — it blocked ALL real
  DX content for a bit-exactness goal that functional rendering doesn't need.
- **Scale is still dropped (identity), knowingly.** `_build_brush_input` can't parse the nested
  `MainScale=(Scale=(…))` / `PostScale` form and the Rust rejects a non-identity `scale`, so ~90
  UNATCO brushes with a non-1.0 `PostScale` build at unit size. Accepted as a first-pass gap
  (boarded); real scale/sheer support is a later spec.
- **The default `build_geometry` (point-in-solid oracle) does not scale to real levels.** 762
  brushes never finished under a 45-min timeout (each fragment replays `point_in_solid` over every
  accumulated `WorldBrush` ⇒ ~O(brushes²·fragments)); the opt-in `build_geometry_bspcsg`
  (BSP-growing) builds the same 762 in **38 s** and the full unlit materialize in **44 s**. So the
  byte-identity `bspcsg` core is ALSO the only viable FUNCTIONAL CSG path for DX-scale content — the
  oracle path is a castle-only stand-in. Functional native materialize/preview should route through
  `bspcsg` once trusted (boarded). *Rejected:* optimizing the oracle for now (spatial index) — the
  BSP core supersedes it.

Also observed (boarded, not decided): the Rust `LIGHT APPLY` bake is too slow/heavy for a full DX
level (an unbounded LIT build was OOM-SIGTERM'd at ~7 min; unlit completes); and a `bspcsg`-built
UNATCO `.dx` does not yet become PLAYABLE in-game (pawn never possesses — the known native
multi-brush collision-hull leak at scale), though the geometry itself is complete and self-checks.

### 2026-07-17 14:42 UTC — `--game` drive: ONE `docker exec` batch (daemon rejected), settle in-batch, PrepareCamera

The warm `--game` container (built 06:57–08:31) drove its container with ~8-10 `docker exec`/
`inspect`/`docker stats`/`docker cp` round-trips per batch → a same-map 1-shot preview took ~9s,
almost all docker-CLI latency (Andrzej: "why is same map 9s? I'd expect ≤1s… only ONE docker exec").

**Chosen: a single in-container batch script (`preview_batch.py`), run via ONE `docker exec`.** The
host is now just ONE `docker inspect` (reuse gate on the fingerprint label) + ONE `docker exec` (the
batch: deliver symlink → 3-phase travel/skip-if-on-stem → per-shot pose+settle+X-grab → length-framed
PNGs on stdout) + a bounded reboot-retry. `docker stats`, the per-op execs, the per-shot `docker cp`,
and the host heartbeat thread are all deleted; the batch refreshes `/work/.last_use` itself.

**Rejected: a persistent published-port daemon** (host talks TCP, zero hot-path docker). Two design
reviewers: it buys only ~one exec-spawn (~0.4s) over one-exec-per-batch, at the cost of a long-lived
server, a collision-prone fixed published port (Linux ephemeral range), a hand-rolled wire protocol,
relocated idle/pin lifecycle, and a testability regression — and Andrzej's condition ("*if* it needs
a daemon") wasn't met. The one-exec batch is a low-risk consolidation that preserves the live-verified
boot/entrypoint/flock surface and stays offline-mockable.

**Link verb `Screenshot` → `PrepareCamera`** (it never captured — it poses; the X-grab is the shot).
It replies SYNCHRONOUSLY. The settle (wait for the posed frame to render before grabbing) CANNOT live
in the verb: **the `bPlayersOnly` freeze we apply for a static frame also freezes the link actor's
`Tick`/`Timer`, so a deferred in-verb reply never fires** (the socket poll that dispatches
ReceivedLine runs in the engine's unfrozen network layer, so synchronous replies still work). The
settle (~0.2s, `UED_SETTLE_S`-tunable) therefore lives in `preview_batch.py`, between the OK and the
grab. New UE1 fact → memory + `unrealed/`.

**Measured (live, real map — DX.dx is the intro cinematic where a director camera overrides the pawn,
so it was a bad test map):** cold ~60s → **warm reuse ~2.2s** (skip-travel) → **10-shot batch 8.37s,
all frames distinct**. The docker-exec explosion (the 9s cause) is eliminated; the residual ~2.2s is
~0.56s Python CLI startup + 2 docker round-trips + ~0.6s render (settle+grab). **≤1s is not reachable
from the dev CLI** (startup alone floors it) — it needs the Nuitka release binary + folding the 2nd
docker call + settle tuning; boarded as a follow-up. Spec `specs/2026-07-17-game-preview-container-
daemon.md`; the daemon design is retained there as the rejected alternative.

### 2026-07-17 16:24 UTC — Actor-relative poses with `--game --map` (game-resolved) + `--list-actors` query

`--game --map` (retail maps) previously REJECTED `@actor` poses (they resolved only against a trunk),
so non-PlayerStart shots weren't possible through the CLI — you had to hand-drive the link. Now:

- **`at:`/`look:`/`orbit:@Actor` resolve against the RUNNING game** for `--map` (the game knows every
  actor's position). Two read-only link verbs: `ListActors <Package.Class>` (all actors of a class →
  `Name x y z`) and `GetActorLocation <name>` (one actor, any class). `preview_shots.py` gains an
  `at:@Name` form and is BAKED into the image so `preview_batch.py` resolves `@refs` (via
  `GetActorLocation`) + poses with the shared `resolve_pose`, keeping the ONE-`docker exec` contract.
  Trunk resolution is unchanged (host-side). Also fixes the `at:@PlayerStart` gap.
- **`--list-actors CLASS [--sample N]`** is a QUERY mode (Andrzej: sampling is fine for *querying*,
  never baked into preview) — prints a map's actors (or N evenly-indexed) as `Name x y z`, no
  screenshots; you COMPOSE those `@Name` refs into preview shots. A rejected `--sample`-and-shoot
  convenience would have put sampling in the shooting path.

An unresolved `@actor` fails loudly (no reboot-retry — a bad name won't fix on reboot). Live-verified:
`--list-actors Engine.PathNode --sample 8` + `at:@PathNodeN;rot:...` → distinct in-bounds frames;
delivered 40 non-PlayerStart shots across 5 OG maps entirely via the CLI. Spec
`specs/2026-07-17-game-actor-relative-poses.md`.

### 2026-07-17 19:37 UTC — Offline class discovery + qualify-and-validate on ingest (classes + textures)

Closes the audit's `[implement] p1 No offline actor-CLASS DISCOVERY` gap (+ its texture-ref twin).
Spec `specs/2026-07-17-class-discovery-and-author-validation.md`. Refined after the review gate (two
cold reviewers) + two rounds of Andrzej decisions. Reuses the existing class-property extractor
(`uprops.resolve_class_properties`), the LIVE class qualifier (`qualify.qualify_level_classes`), and
the texture package reader (`utexture`).

**One OFFLINE class index** built by scanning `.u` on the composed search path
(`config.composed_search_files`) powers everything: `bare→{FQCN}` (the OFFLINE analogue of the live
`OBJ LIST CLASS=Class` map `qualify.parse_loaded_classes` builds, so `qualify_level_classes` consumes
it unchanged), per-package class lists, and lazy abstract/Super. Built once per invocation; no cache
(schema is cheap+exact — the no-catalog decision).

**A new top-level `class` namespace** (`class list` / `class show`), NOT under `actor` or `substrate`.
*Rejected:* `actor classes`/`actor schema` (reads oddly beside the generator verbs); `substrate
classes` (that namespace is build utilities/stubbing). `class` mirrors `texture list`/`search`,
generic-UE1 framed.

**`class list` is a rooted, depth-limited BROWSE, not a flat dump** (Andrzej 2026-07-17: a flat
~1200-class placeable list is unusable). **Default** = the ~40 direct `Engine.Actor` children (the
browsable CATEGORIES, abstract branch-points included — they're what you drill into). **`--subclass-of X`**
drills to the PLACEABLE classes that are/descend from X (the leaves). **`--depth N`** = a structural
browse N levels below the root (Actor or `--subclass-of`), unfiltered. **`--package P`** = all placeable in P.
**`--all`** = every class flat (composes with `--subclass-of`; the old "all placeable flat" is `--subclass-of
Engine.Actor`). *Rejected (Andrzej's fork):* a tree-by-default view; keeping the flat dump default.
**Placeable is a PROXY** — UE1 has no `CLASS_Placeable` (UE2+), so non-abstract-Actor over-lists
weapons/ammo/projectiles/AI-pawns; documented as "technically instantiable," curated placeability
deferred to the annotated catalog. *(Original design was "flat placeable default"; superseded by this
browse model after the first live use showed the flat dump was unusable.)* **Partly superseded
2026-07-18 10:56 UTC** — the DEFAULT rendering is now an indented inheritance TREE (the flat forms
here moved behind `--flat`), and `--depth` counts from the shown/rerooted root; see that entry.

**Abstract detection = ONE offline path: parse the shipped ScriptText source** for the `abstract`
class modifier (every DX class ships a TextBuffer). *Rejected (review fix):* the earlier dual
`ClassFlags`-for-script-free path — the UStruct/UState prefix before ClassFlags is variable-length
compact fields (a constant offset is only coincidentally right for low-index classes), and script-
bearing classes' on-disk bytecode length ≠ the stored `ScriptSize` so ClassFlags isn't front-seekable
at all; a `SerializeExpr` token walker (~60 opcodes for one bit) is far too heavy. TextBuffer body
layout pinned live: `[UObject `None` prop-list terminator: 1 compact] + Pos:u32 + Top:u32 +
Text:FString` (miss the `None` and you land 1 byte short; the FString length ends exactly at
`soff+ssize`). Comment-strip then `\bclass\b(.*?);` DOTALL + `\babstract\b` word-boundary (multi-line
decls; no `*Abstract*`-name false-match). `None` (source-stripped substrate) ⇒ fail-OPEN (list it,
`abstract=unknown`). Abstract is per-class-declared, NOT inherited — no "abstract-via-abstract-Super"
mode. New UnrealEd fact → `unrealed/`.

**Class validation = qualify-and-validate on ingest; stored T3D FQCN going forward** (Andrzej:
validate at generators AND write boundaries, all T3D input+output/stash/prefab, DRYly; stored is
`Package.Name`). External T3D uses BARE class names (`Class=Light`) and `resolve_class_properties`
requires an FQCN, so ingest must QUALIFY, not just check. **Premise corrected (review fix):** `actor
add` does NOT qualify today (bare point actors are stored bare — `verify.py` documents this), so this
is a going-forward invariant; existing trunks are NOT migrated (they still materialize — `verify.py`
live-qualifies legacy bare at H3). A shared helper **MIRRORS** (does not literally reuse)
`qualify_level_classes`'s zero/2+ logic against the offline index — it takes an actor list, adds a
qualified-existence branch, and raises `_SelectionExit` NOT the function's bare `ValueError` (which
`dispatch()` doesn't catch → would traceback; review fix). Qualified → existence via
`uprops.class_export_index` (NOT the full ancestry union — review fix: it false-reports a real class
with a missing *ancestor* as "unknown"). **Ambiguity policy (review fix — offline is STRICTER than
live):** the offline index sees ALL on-disk classes, the live `OBJ LIST` only LOADED ones, so a bare
name in 2 on-disk packages is offline-ambiguous though materialize would bind one cleanly — so DON'T
hard-reject: prefer a single Engine/Core candidate, else (a game-package-only collision) leave it BARE
for live qualification. NO composed-path-order tiebreak (`bare_to_fqcn` is a set, and an offline
order-pick could store a package the editor never binds — leaving bare is strictly safer); NO "qualify
explicitly" error for an ambiguity. **Ordering (review fix):** the
helper runs strictly AFTER `is_builder_brush` filtering (which keys on the exact bare `"Brush"` — else
the red builder brush escapes the filter). **Cost/H3 (review fixes):** ingest uses a header-only table
scan (not `load_package`'s property decode), built once per invocation, deduped; and H3 must be fixed
in `verify.py` to reconcile a now-FQCN `expected` against the live loaded set (my earlier "H3 stays
FQCN-vs-FQCN via qualify_live_level" was mechanically WRONG — `qualify_level_classes` skips dotted
classes, so a stored FQCN would carry the offline pick unreconciled with the live pick). Runs at
`actor add`, `stash capture --from-t3d`, `stash/prefab apply`, `stash promote`, and the generators.
*Rejected:* warn-only; write-boundary-only (Andrzej wanted generators too); folding into
`LevelSource.save` (fires on no-op mutations that introduce no class). Consequence owned: generators
become project-dependent (were "session-free / no validation") and their check is redundant with the
`actor add` boundary — existing project-free generator tests must migrate; no project/search-path ⇒
exit-2 up-front with a pinned message (review fix — `schema_resolver(None)` vs `composed_search_files
(None)` diverge). Suggested build phasing: (A) index + discovery verbs, (B) abstract+placeable,
(C) the invasive ingest-qualify + H3 fix.

**Texture validation = EXISTENCE, not decodability; mirror the class sites; no offline qualification**
(Andrzej: mirror the class decision). Validated at `brush poly set --texture` + `brush build
--texture` + any brush ingested via `actor add`/stash/prefab (scan poly `Texture=`). *Rejected (review
fix):* `utexture.TextureResolver.resolve()` as the predicate — it's a pixel decoder that returns None
on a REAL non-P8 / imported-palette / missing-mip texture, so hard-failing None would block a
legitimate materializable ref (violates the codebase's own "no false reject"). Instead: a
`Texture`-classed export of that name exists in the package (`utexture.textures`), bare ⇒ "exists in
any package". Texture bare→FQCN QUALIFICATION stays LIVE at materialize (`qualify_level_textures`
content-matches an editor dump; no offline analogue) — deliberate asymmetry with classes.

**`dispatch()` does NOT catch `SchemaError`** (review fix) — user-facing misses raise `_SelectionExit`
(already caught); a `SchemaError` clause is added to `dispatch()` as the corrupt-`.u` backstop (no
traceback). A single unparseable `.u` SKIPS-with-note in the index build, never aborts `class list`/
validation (review fix).

**NO class catalog** (unlike textures). Schema is cheap/exact/deterministic from the `.u`, so a
tracked cache is pure staleness — verbs read raw `.u` each call. *Deferred (boarded follow-up):* a
tracked ANNOTATED class catalog (curated description/category/scale/CURATED placeability — knowledge
NOT in the `.u`, overlapping the `[docs] p2` "no class catalog" item), on TOP of these derived verbs.
Also boarded: the backward-compat behavior change (previously-green no-config runs now exit-2).

**Non-goals:** class-default (CDO) VALUES (`uprops` carries types only; a CDO reader enriches `class
show` later); prop-value validation on `actor build` (existence only — `actor prop` validates values);
offline texture qualification; a ranked `class search` verb.

## 2026-07-17 18:46 UTC — `level preview` default backend flips to `--game`; `--native` becomes opt-in

**Decision (Andrzej): "Switch `level preview` to use `--game` by default."** The faithful in-game
tier is now the DEFAULT; the offline native rasterizer renders only when `--native` is passed
explicitly. **Supersedes point 2 of the 2026-07-16 12:13 decision** (which made `--native` the
default). Rationale: a subagent capability audit (2026-07-17, boarded in `board/inbox.md`) showed the
native draft tier silently MISLEADS on exactly the things a level-builder must judge — it mis-renders
overlapping-subtract doorways (magenta/wedge, with `doctor` clean), and by design shows no lighting,
no meshes/decoration, and no sky. As the *default* feedback loop that made an agent trust broken
output. The faithful tier shows what the player sees, so it is the safer default; `--native` stays a
first-class opt-in for the fast, docker-free draft loop (seconds/batch) when geometry-only iteration
is what's wanted.

**Mechanics.** `dispatch._level_preview` resolves `use_game = not args.native` (the two flags stay a
mutually-exclusive group; neither given ⇒ game). All four backend guards key off `use_game`: the
`--fov` reject (fov is native-only), the `--map`/`--rebuild`/`--keep-alive` "requires --game" reject
(now only fires when `--native` is opted into), the `--list-actors` gate, and the render-branch
selector. So a bare `level preview "at:…;rot:…"` now materializes the trunk and previews it in the
warm game container (first batch ~1-3 min: ~90s boot + travel; later batches reuse the warm
container); `--native` is the escape hatch to the instant offline draft.

**Trade-off accepted.** The default now needs Docker + a one-time ~90s container boot (then reused
across previews, self-terminating after 10 min idle), where the old default was instant and
offline. Andrzej chose the faithful default anyway — correctness of the feedback loop outweighs
draft speed, and `--native` remains one flag away. (Rejected: *keep `--native` default, just document
its blind spots* — an agent doesn't read caveats mid-loop; the misleading render is the problem.
*A separate `level render` verb for the game tier* — two overlapping pose surfaces, already rejected
in the 2026-07-16 entry.)

## 2026-07-17 21:10 UTC — Native lit build ships through the `bspcsg` CSG core (cleaner BSP → clearer light LOS)

**Decision:** `run_materialize_native` / `_build_level_model` now default to the incremental
`bspBrushCSG` core (`uedcli_native.build_geometry_bspcsg`) for the shipping build, via a new
`core="bspcsg"` selector on both functions. The original coarse core (`build_geometry`) is kept,
selectable with `core="coarse"`, only for the byte-identity pinning tests that compare
`_build_level_model` against a direct `build_geometry` serialize round-trip.

**Context:** ~58 interior floor/ledge surfaces rendered PURE BLACK in-game where UnrealEd shows
lit grey. The coarse core's merge-then-single-rebuild partition LEAKS solid cells: the space just
~4uu above some interior ledges was wrongly classified SOLID, so the lightmap bake's per-lumel
self-shadow-biased LOS origin (`+Normal*4`) landed inside solid → `linecheck::line_clear` returned
occluded for every light → an all-dark lightmap → the surface renders the texture × 0 = black. The
`bspcsg` core reproduces the editor's cleaner BSP (485 surfs / ~99.97% solidity vs the coarse
core's 438 surfs), so the space above most such ledges is correctly EMPTY and the bake lights them.
Both cores emit the same UModel shape and both run `passes::bsp_build_bounds` (LeafHulls +
iCollisionBound), so the downstream assemble + N-4 bake + zone/collision passes are unchanged and
collision still works (verified live: pawn walks, phys=1).

**Measured (castle, Test_Castle geometry):** fully-dark surfs coarse=63 → bspcsg=59 (editor=55);
surf count 438 → 485 (== editor). Most previously-black interior floors now render lit (s34 floor,
much of s76). A residual handful of cells are still wrongly solid (bspcsg is ~99.97%, not 100%
solid) and still over-occlude a few visible surfaces (s76 left wall/floor) — tracked as the
byte-identity solidity residual; closing it fixes the last render parity AND advances byte-identity.

**Rejected:** *fix the coarse core's leaked-solid over-occlusion directly* (PATH B — refine
`build.rs::bound_leaked_solid_leaves` / the coplanar consolidation). bspcsg already produces the
editor-matching BSP and moves toward byte-identity, so routing the shipping build through it is the
higher-leverage fix; PATH B would harden a core we are migrating away from.

**Refs:** `uedcli/native/materialize.py` (`_build_level_model` core selector, `run_materialize_native`
`core` arg); spike `dev/docs/spikes/2026-07-15-native-materialize/` section 20 §16;
`uedcli/tests/test_native_materialize.py::test_gate5_populated_hulls_rust_matches_python` pins the
coarse core explicitly.

## 2026-07-17 20:58 UTC — Project layout reorg: a free `uedcli.toml` at the repo root; in-repo gitignored `.uedcli/` for machine-local state

Supersedes the project-*layout* part of the global-CLI arc (project = a `<child>/config.toml` dir,
conventionally `uedcli/`, root = its parent — 2026-06-29/30, 2026-07-01 07:45 walk-up-by-schema)
and the `<project>/uedcli/tmp/` placement of machine-local scratch (2026-07-05 14:58 §1, its
gitignored-`tmp/` bullet). The in-tree/no-id/no-registry substance of 2026-07-05 14:58 is
UNCHANGED — this moves files, not the model.

**Decision (Andrzej, via spec Q&A):**

1. **A project is a repo with a free-standing `uedcli.toml` at its root** (à la
   `pyproject.toml`/`.git`). The dir containing `uedcli.toml` IS the project root — no `<project>/`
   subdir, no root-is-parent indirection. The root path is the project identity (keeps "no project
   id"). Discovery = walk up from cwd to the first ancestor containing `uedcli.toml`; nearest wins;
   `~/.uedcli/` can never match (different filename, and its schema stays rejected). The
   walk-up-by-schema child-dir scan and its two-matching-children ambiguity error are retired
   (filename beats schema-sniffing).
2. **`uedcli.toml` declares each managed dir as a RELATIVE path** (absolute allowed), so uedcli can
   point at a repo's EXISTING dirs (`Maps/`, `Prefabs/`) instead of forcing a parallel tree. Keys:
   `game` (required), `paths` (overlay dirs, resolved against the root), `maps`, `prefabs`,
   `catalog`. **Omitted dir keys default root-relative: `maps/`, `prefabs/`, `texture-catalog/`** —
   a minimal project file is one line (`game = "deusex"`). *(Rejected: all-keys-required — more
   typing for no safety, defaults are conventional; LUM-style capitalized defaults — bakes one
   repo's convention into the tool.)* `id`/`name` keys are DROPPED (registry dead since 2026-07-05).
3. **Machine-local, never-tracked state lives in one in-repo `.uedcli/` beside `uedcli.toml`** —
   stash, delivered-preview maps, locks, staging/scratch. It is **self-ignoring**: uedcli writes
   `.uedcli/.gitignore` containing `*` when it first creates the dir (cargo/direnv pattern), so it
   can never be committed by accident and needs no repo-.gitignore edit. *(Rejected: user-managed
   .gitignore — a documented requirement someone will miss.)* This FOLDS IN the standing "relocate
   locks + tmp from `<repo>/.uedcli/` (repo_paths.state_root) to the project" item: the legacy
   location and the new one coincide by construction; what changes is that it is project-derived
   (from `uedcli.toml` discovery), not CLAUDE.md-marker-derived. `~/.uedcli/` (per-user) is
   untouched: `config.toml` ([games.*]) + `cache/{textures,stubs}` only.
4. **Hard cutover, no dual-layout support.** Only `uedcli.toml` is recognized; the old
   `<child>/config.toml` layout errors clearly (message names the migration). The LUM project
   migrates in the same change. *(Rejected: transitional dual support — two documented layouts and
   more code for exactly one existing project.)*
5. **No scaffold verb.** `project` stays `project show` only (2026-07-05 14:58 §4 stands);
   `uedcli.toml` is hand-written (1–4 lines, docs show the template); `.uedcli/` self-creates on
   first use. *(Rejected: reintroducing `project init` — dead surface for a one-line file.)*
6. **Tool-install assets resolve PACKAGE-RELATIVE, not from any repo/project root** *(review-gate
   resolution — both cold reviewers flagged that `host_repo_root` also anchored the tool's OWN
   assets, which are not project state)*: the docker-compose dir + UED22 substrate
   (`Tools/uedcli/uned/`) and `Tools/umodel_win32` resolve from the installed `uedcli` package's
   own location (`__file__`-relative into the source tree). Zero config for the dev checkout; how
   assets ship under pipx/Nuitka is decided by the (stale, to-be-respecced) global-CLI packaging
   item, not here. *(Rejected: a per-user config key — a required setup step before any
   editor-driving verb works; keeping a marker-based `tool_root()` — keeps the CLAUDE.md walk-up
   alive for no gain.)*
7. **LUM migration keeps the trunks in place: `maps = "uedcli/maps"`** — zero file moves; the old
   `uedcli/` dir stops being a project dir and lives on as a plain content dir holding the trunks
   (its `config.toml` moves to the root as `uedcli.toml`, dropping the retired `name` key; `tmp/`
   is deleted). *(Rejected: `<repo>/maps/` — case-collision with the existing binary-artifact
   `Maps/` on the case-insensitive Wine prefix; `git mv` to `uedcli-maps/`/`Trunks/` — churn on
   every trunk file for a cosmetic rename.)*

**Consequences:** `repo_paths.host_repo_root` (CLAUDE.md-marker walk-up), `state_root`,
`prefab_library_root`, `texture_catalog_root`, and the `UEDCLI_REPO_ROOT`/`UEDCLI_PREFAB_DIR`/
`UEDCLI_TEXTURE_CATALOG` env overrides retire — project state resolves from the project, tool
assets package-relative (§6), per-user state from `$UEDCLI_HOME`/`~/.uedcli`.
`--project`/`UEDCLI_PROJECT` point at the project ROOT (or the `uedcli.toml` itself). Relative CLI
file paths (`--out`, `--map`, `--from-t3d`, …) resolve against **cwd** (standard CLI semantics),
no longer against a repo root. Details + module-level consequences: spec
`specs/2026-07-17-project-layout-uedcli-toml.md` (ephemeral; this entry is the durable record).

**Refs:** board `inbox.md` "Reorganize the project layout" (Andrzej, 2026-07-13); folds the
`to-spec.md` "Relocate locks + tmp" item; supersedes the layout parts of 2026-06-29 06:02 /
2026-06-30 06:18 / 2026-07-01 07:45; amends 2026-07-05 14:58 §1 (state moves from
`<project>/uedcli/tmp/` to `<root>/.uedcli/`).

## 2026-07-18 07:53 UTC — Texture per-package flock is CATALOG-adjacent (`<catalog>/.locks/`), not project-derived

Resolves the layout-reorg slice-2 deviation flag ("`texture classify set` now resolves the project
even with `--catalog-dir`", board inbox 2026-07-18).

**Decision (Andrzej): option 2 — derive the texture lock home from the CATALOG DIR it guards.**
`texture sync` and `texture classify set` take their per-package flock in a **self-ignoring
`<catalog>/.locks/`** (created with a `*` `.gitignore` via the shared `config.self_ignoring_dir`
mechanic, so lock litter can never be committed from a tracked catalog dir). The lock is NOT in the
project's `.uedcli/locks/`.

**Why:** the lock's scope now matches the resource it guards. (1) An explicit `--catalog-dir`
needs no project for ANY texture verb — spec §6's "override given ⇒ no project needed" contract is
restored for the one verb (`classify set`) the reorg had broken it for. (2) Two projects/checkouts
pointing at the SAME shared catalog dir serialize each other — a project-derived lock would give
each writer its own lock domain and silently lose concurrent classifications (the same mis-scoping
pattern as the shared texture-image-cache race fixed in review round 2).

**Rejected:**
- *Accept the project requirement for `classify set` (amend spec §6)* — cheapest, but leaves the
  shared-catalog lock mis-scoping and breaks the standalone-catalog classification pipeline.
- *Per-user `~/.uedcli/locks/` fallback when no project* — restores the contract but the lock
  domain is per-user-machine, still wrong for a shared catalog across users, and splits the lock
  location by context.

**Refs:** `uedcli/dispatch.py` (`_dispatch_texture.lock_dir`), `uedcli/config.py`
(`self_ignoring_dir`, extracted from `state_dir`); regression
`test_dispatch.py::test_dispatch_texture_classify_set_with_explicit_catalog_dir_needs_no_project`;
resolves the inbox flag (deleted); amends the 2026-07-17 20:58 reorg's slice-2 lock placement for
the texture locks only (editor/target locks stay in `.uedcli/locks/`).

## 2026-07-18 08:08 UTC — Trunk saves are DELTA writes under a per-level flock; concurrent disjoint edits compose

Resolves the round-3 review's p2 board item ("Concurrent `actor add`s to one level: silent lost
updates + tracebacks — no trunk write lock", inbox 2026-07-18; reproduced: 8 parallel adds → +1
actor, several acknowledged adds silently destroyed, 2 raw `FileNotFoundError` tracebacks).

**Root cause:** the per-actor trunk layout makes disjoint edits mergeable, but `trunk.write_level`
was a make-disk-match-memory FULL rewrite — it pruned every on-disk actor dir absent from the
caller's in-memory model. A process that loaded before a concurrent add therefore deleted the
other's new actor on save; the prune also raced other writers mid-write (the tracebacks).

**Decision (Andrzej: "fix it"; mechanism follows from the layout):**
1. **`write_level` becomes a DELTA write:** every model actor is (re)written; only dirs named in a
   new explicit `deleted` set — the caller's OWN deletions (`TrunkLevelSource` records its loaded
   name-set; deleted = loaded − current) — are pruned. A dir the process never loaded belongs to a
   concurrent writer and is left alone. Same-actor concurrent edits stay last-writer-wins (like
   git); delete-vs-edit resolves by save order.
2. **Each save runs under a short per-level flock** — `<maps-dir>/.locks/level-<name>.lock`,
   resource-adjacent and self-ignoring exactly like the catalog locks (2026-07-18 07:53) — so one
   saver's prune/write can never interleave with another's (kills the FileNotFoundError window).
   Loads take no lock (readers see benign transients at worst; CLI saves are ms-scale).
3. **Rank minting needs no coordination:** two concurrent adds may mint equal `order_value`s —
   already harmless by the (order_value, name) tiebreak (2026-07-05 15:11); `doctor` warns.

Live re-verified: the original repro now yields 8/8 "added", 0 tracebacks, all 9 actors on disk.
This also makes `direction.md`'s "a per-target flock serializes concurrent writes" claim true for
trunk writes (it previously held only for the materialize `--out` swap).

**Rejected:** *a flock spanning load→save* — a long-running load-only verb (materialize reads the
trunk, then builds for minutes) would block every writer on the level, and read-only verbs don't
need serializing; *staged-swap whole-tree writes* — atomicity without delta semantics still loses
concurrent adds (the destroy happens at the model level, not the file level).

**Refs:** `uedcli/trunk.py` (`write_level(deleted=…)`), `uedcli/dispatch.py`
(`TrunkLevelSource.load/save`); tests `test_level_source.py` (interleaved-saves compose /
own-deletions-only / lock location) + `test_trunk.py::test_write_level_prunes_only_explicit_deletions`;
deletes the inbox p2 item.

## 2026-07-18 08:26 UTC — Trunk delta writes, completed: content-diff writes + atomic per-actor files + dotted-level guards (review-gate resolutions on the 08:08 entry)

The 08:08 entry's build passed its gate for add‖add, but two cold reviewers proved the "disjoint
edits compose" claim did NOT yet hold beyond adds, and found two crash/wedge classes. Resolutions
(same session, Andrzej's standing "fix it" directive):

1. **Saves write a CONTENT-DIFF, not the whole model.** `TrunkLevelSource.load` keeps each actor's
   raw stored body (`trunk.read_level_with_bodies`); `save` writes only actors whose body or rank
   differs from that snapshot (`write_level(only=…)`). Without this, an add-only saver re-wrote
   every actor from its stale model — resurrecting a concurrently-deleted actor and reverting a
   concurrently-edited one (both reproduced live: 5 of 6 acknowledged parallel deletes silently
   undone). The diff is content-based, NOT the `touched` hint — robust to any verb under-reporting;
   a non-canonical (hand-edited) stored body just gets one canonicalizing rewrite.
2. **Per-actor writes are atomic and ordered:** `order_value` first, then `actor.t3d` via tmp +
   `os.replace`. Un-flocked readers (loads take no lock) previously hit a raw `StopIteration`
   traceback on the truncate-then-write window (~4% of reads under load), and a SIGKILLed writer
   left a 0-byte `actor.t3d` that made EVERY later command on the level fail until hand-repair.
   `read_level` also now skips an empty `actor.t3d` (a crashed pre-atomic leftover), so an
   already-wedged trunk self-heals on the next write.
3. **Dotted/nested level names rejected everywhere** (`level create`, `level select`,
   `--target level/NAME` — which also now enforces single-segment names): `.locks` is the maps-dir
   lock home, so `level create .locks` would have nested a level inside the self-ignored dir —
   silently invisible to git.
4. **Scope note:** the flock is `fcntl.flock` — advisory, POSIX, local-filesystem semantics (NFS
   not warranted). Matches the tool's Linux-host stance.

Live re-verified after the fixes: mixed parallel workload (adds + deletes + moves + hammering
readers) with zero tracebacks and zero lost/resurrected actors; SIGKILL mid-save leaves a readable,
writable level. direction.md's "Atomic writes" bullet corrected (the old "staging dir and swap"
T3D claim was false and is superseded by per-actor atomicity).

**Refs:** amends 2026-07-18 08:08 (its rejected-alternatives list stands); `uedcli/trunk.py`
(`write_level(only=…)`, `read_level_with_bodies`, atomic replace), `uedcli/dispatch.py`
(`TrunkLevelSource`, `_resolve_level_source` level branch), `uedcli/level_select.py`
(`_check_safe_level`); tests in `test_level_source.py`/`test_trunk.py`/`test_level_verbs.py`.

## 2026-07-18 08:33 UTC — `actor show`: exact-name miss is a named error; glob miss stays empty rc-0

Resolves the round-3 p3 chore ("`actor show <no-match>` prints empty and exits 0").

**Decision:** `actor show <name>` with a NO-glob token (no `*?[`) that names no actor now errors
`Actor not found: <name>` + exit 2 (the house bad-actor-name rule). A **glob** with zero matches
stays grep-like — empty output, exit 0 — because an empty match set is legitimate pipeline data
(mirrors how `actor find` output composes). Andrzej accepted the recommended minimal scope
("fix the 2 chores"). *(Rejected: erroring on glob misses too — would make composed pipelines
treat a legitimately-empty selection as a failure.)*

Sibling chore fixed in the same pass (mechanical, no decision): the compose `/stubs` volume source
is now `${UEDCLI_STUB_CACHE:-${HOME}/.uedcli/cache/stubs}`, with `editor.ensure_editor` passing
the resolved `config.stub_cache_root()` (honors `$UEDCLI_HOME`) in the compose env — the mount can
no longer silently diverge from the host stub cache under a non-default home.

**Refs:** `uedcli/query.py` (`show_actor`), `uedcli/dispatch.py` (actor-show KeyError guard),
`uedcli/editor.py` (`ensure_editor` env), `uned/docker-compose.yml`; tests in
`test_query.py`/`test_dispatch.py`/`test_editor.py`; deletes both inbox chores.

### 2026-07-18 10:03 UTC — `class show --category` filter to specific editor categories

Spec `specs/2026-07-18-class-show-category-filter.md`. Narrows `class show` to named editor categories
(`Movement`/`Lighting`/…) so "what X props does this class have?" is a direct query.

**`--category NAME` is repeatable, exact, case-insensitive, OR-combined** (`--category Movement
--category Lighting`). *Rejected:* a comma-list `--category A,B`; substring/fuzzy match. The genuine
repeatable-append precedents are `actor find --class/--group/--name` and `texture search --tag` (NOT
`class list --subclass-of`, which is single-valued — review correction). **Divergence noted:** `level doctor`
already has a `--category` that is comma-split + case-sensitive; this one deliberately differs (the
better shape), and a follow-up (inbox) reconciles `level doctor --category` to match rather than
copying its shape. **Degrade path:** when `class show`'s missing-ancestor fallback (own-props-only)
fires, `--category` is REJECTED (exit 2 "inherited schema unavailable") — else "available = all depths"
would be a lie; a class with no editable categories → exit 2 "has no editable categories".

**A `--category` filters AND expands the matched categories** (own + inherited props, inherited
FQCN-tagged — the `--all` rendering), NOT the collapsed `(+N inherited …)` count. If you asked for a
category you want to SEE its props, and for a derived class most of a category is inherited (e.g.
`ScriptedPawn --category Movement` is entirely inherited from `Engine.Actor`, so a count would show
nothing useful). So `--category X` is the selective form of `--all`. `--depth N` still limits
superclass hops, but the **default depth when filtered is UNLIMITED** (a single category is narrow —
the ~60-line auto-depth budget of the unfiltered `--all` does not apply). No `--category` → unchanged.

**Unknown category → exit 2, listing the class's actual categories** (sorted), naming the offender —
consistent with the tool's no-silent-miss stance (`no category 'Movment' on Engine.Actor; available:
…`). *Rejected:* empty output + a stderr hint (a typo would silently yield nothing on stdout). Any one
bad value among several fails all-or-nothing (like multi-`--set` in `actor prop`).

**Non-goals:** category-filtering `class list`; filtering by prop KIND or name/regex (`grep` covers
ad-hoc text); a show-hidden-internals escape (plain `var` props carry no category, so unreachable).

## 2026-07-18 10:02 UTC — `actor prop set|unset|get` subcommands, dot-paths, default-value fallback (spec `specs/2026-07-18-actor-prop-subcommands.md`)

Andrzej's design decisions for the trunk prop-verb rework (each choice his, from the speccing Q&A;
the spec compiles them into one surface):

1. **Subcommand grammar, name-first: `actor prop set|unset|get <actor> TOKEN…`.** Replaces the
   `--set`/`--unset` flags **outright** (no deprecation aliases — pre-release tool). *Rejected:*
   name-before-verb (`prop <actor> set …`); keeping the flags as aliases. Accepted consequence: a
   mixed set+unset is no longer a single atomic invocation.
2. **Comma sugar is Vector/Rotator struct sugar.** `KEY=4,5,-17` on a schema-known Vector/Rotator
   prop canonicalizes to the T3D struct form at store; wrong arity / non-struct prop → exit 2.
   *Rejected:* verbatim-only (no sugar); comma-list as static-array fill.
3. **`get` output: bare values, ONE line per requested key**, in argument order; `--kv` switches to
   round-trip `KEY=VALUE` lines; zero keys = dump-all of the actor's stored props (plus the typed
   `Location` field — see 8) as round-trippable KEY=VALUE lines. Arrays render as a one-line
   `(0=v0,1=v1,…)` tuple, full dim — never one element per line (line count must equal key count;
   Andrzej's own format proposal). *Rejected:* per-element lines for arrays; index-required error on
   a bare array key; stored-elements-only sparse print; no-dump-all variants.
4. **Unset-everywhere reads synthesize the type's ZERO value** (engine semantics: an unspecified
   default is zeroed) — `get` always prints exactly one line per key. *Rejected:* empty line
   (ambiguous with empty string); hard error (would make get unusable for zero-defaulted props).
5. **Default values come from the BINARY route — a `SerializeExpr` bytecode walker to the UClass
   tail defaults block — built on a UNIFIED low-level package core** (`upackage.py`): one parser
   for the shared `.u/.dx/.utx/.uax/.umx/.unr` format, no per-use-case/per-extension
   reimplementations. *Rejected:* parsing the shipped `.uc` ScriptText `defaultproperties` text
   (unverified for v68, second grammar); spike-first route choice (Andrzej picked the walker
   directly); leaving the three existing private parser copies as-is for the new code.
6. **All three subcommands hard-require the class schema** — the no-fallback contract (2026-06-26
   14:10) now covers reads too; no degraded stored-only read when the install is absent.
   *Rejected:* graceful stored-key reads without the schema (two-tier semantics).
7. **Unified-core scope: extract the core + migrate `uprops` now; `utexture`/`dxpkg` migrate as a
   follow-up chore.** *Rejected:* migrating everything in this change (regression risk on two
   byte-validated decoders for no feature gain); new-code-only with no uprops migration.
8. **Retire `actor get`** (deleted, not aliased) — `actor prop get` is the one reader; closes the
   p3 silent-rc-0 item. Typed-field routing (`Location`) becomes a small reusable REGISTRY (get/
   set/unset per field) so future typed fields are one entry, and `get <actor> Location` must work.
   *Rejected:* keeping `actor get` as sugar or unchanged.
9. **Dot-path grammar ONLY: `KEY.N` (array index), `KEY.Member` (struct member), recursive
   (`VectArray.0.X`).** The T3D `KEY(N)` spelling is rejected on the CLI with a hint (stored T3D
   keeps its native spelling). `KEY=VALUE` is whole-value REPLACE (array tuple `KEY=(0=V,3=W)`
   clears unmentioned elements); `KEY.PATH=VALUE` is a targeted edit; `unset` takes paths too;
   member names schema-validated against the struct's own member list from the `.u`; `get` paths
   print the single element/member bare. (All four targeted-edit semantics confirmed as a package.)
   *Rejected:* accepting both spellings; tuple-as-sparse-merge (Andrzej: tuple = replace, dot =
   targeted); path-less unset.
10. **Writes store EXPLICIT member values — no canonicalize-to-editor-form (zero-member omission)
    on write.** "The CLI user can use unset if they want to clear; more power to a power user."
    So the p2 "explicit zero FRotator fields fail H3" item stays open and separate. *Rejected:*
    canonical zero-omitted emit (would have folded that p2 fix in); Rotation-only special case.
11. **H3 "trunk prop equal to class default" stays a SEPARATE item** consuming the new defaults
    capability. *Rejected:* folding the verify fix into this change; shipping a defaults-lookup
    API shaped for it now.
12. **`actor build --prop` and `actor find --prop` adopt the new grammar IN THIS CHANGE, and
    `find --prop` matches the EFFECTIVE value** (defaults fall through; type-canonicalized
    compare — bool/numeric/enum equivalence) rather than the stored-line string. *Rejected:*
    follow-up-item deferral; stored-only matching with new grammar; a `--stored` flag pair.

Open (build-gating) probe recorded in spec §9: whether stored-partial struct/array values leave
unmentioned members/elements at ZERO or at the CLASS DEFAULT at load — decides get/unset fine
semantics; probe live, fold into `unrealed/t3d.md` with evidence.

**Refs:** spec `specs/2026-07-18-actor-prop-subcommands.md`; supersedes the inbox `[spec]`
"`actor prop --get`" proposal (2026-07-18) and absorbs the p3 `actor get` silent-rc-0 debug item.

## 2026-07-18 10:30 UTC — `actor prop` subcommands: spec review-gate rulings (amends 10:02)

Two cold reviewers of `specs/2026-07-18-actor-prop-subcommands.md` surfaced 2 HIGH conflicts +
a batch of ambiguities. Mechanical ambiguities were resolved in-spec under the 10:02 decisions;
four points needed Andrzej's ruling:

1. **Comma sugar is SCOPED: interpreted only when the schema says Vector/Rotator** (then bad
   arity/component → exit 2); on every other prop a comma value is plain verbatim text — so the
   documented comma-joined `Group=a,b` membership pattern and comma-containing strings keep
   working. Narrows 10:02 §2's wording, which read as rejecting any comma form on a non-V/R prop
   (both reviewers: would break a live workflow). *Rejected:* the strict reject + migration note.
2. **Partial whole-value on the typed `Location` field ZERO-FILLS unmentioned axes**
   (`set Location=(X=1)` → `(1,0,0)`), superseding `_parse_location_value`'s deliberate
   all-three-axes reject. Andrzej: "Location is NOT the only prop that can use a vector (think
   velocity/acceleration, where you only care about one axis)" — assignment semantics stay
   uniform across all Vector-typed values. *Rejected:* keeping the strict reject (the
   anti-teleport guard) with `Location.X` as the only partial-edit route. The bare positional
   comma form still requires all three components.
3. **`find --prop` mixed-level rule confirmed as effective-value**: the `.u` schema decides
   whether a class declares the key; declared-but-unset falls back to the class default; a key
   on NO present class → exit 2; an unbuildable class schema → exit 2 (no-fallback); plain
   `find` without `--prop` stays schema-free. (Andrzej re-confirmed effective-value matching in
   his own words.)
4. **Dump-all hitting a stored prop the schema doesn't know → HARD ERROR, exit 2** ("let's see
   if this is ever a problem in real life"). *Rejected:* warn+print-verbatim; silent skip.

Also folded from review (no new decision, derived from 10:02): hard-rejects apply to all three
subcommands; whole-key `unset` clears every static-array element; dump-all is the verbatim
STORED view vs keyed get's EFFECTIVE view; dynamic `ArrayProperty` out of scope; imported-enum
cross-package resolution wired in; §5.2's UClass-tail layout + in-struct value encodings marked
to-be-RE'd with value oracles (pinned Light defaults + ScriptText cross-check); the
store-explicit ⇒ H3-post-verify interaction cross-referenced (raises the open H3 items'
practical priority).

**Refs:** spec `specs/2026-07-18-actor-prop-subcommands.md` (rulings R1–R4 inline).

### 2026-07-18 10:56 UTC — `class list` UX: default inheritance TREE + rename `--isa`→`--subclass-of`

Two refinements to the `class list` browse (Andrzej):

**Default output is now an indented inheritance TREE** (`_class_tree` in dispatch, over
`ClassIndex.children_map()`), rooted at `Engine.Actor`: abstract classes marked `*`, a frontier
node's hidden direct subclasses shown inline as `(N)`, depth AUTO-grows to fit a ~60-line budget
(min 1 level, never renders empty — a thin class whose members are all on a huge deep superclass
still shows that level), `--depth N` overrides, `--subclass-of X` reroots, `--all` reroots at
`Core.Object` (every class incl. non-Actor), `--package P` prunes to P + the branches reaching it.
*Rejected (earlier `class list` UX Q, now superseded):* flat-list default; tree-only with no flat
escape. **`--flat`** restores the pipeable one-`Package.Class`-per-line list (the prior default +
`--subclass-of` placeable-leaf drill), for grep / piping into `actor build`. Contents = ALL classes
(abstract branch-points needed to keep the tree connected), not the placeable-only flat set —
*rejected:* pruning to placeable-only (would break the tree structure).

**Renamed `class list --isa` → `--subclass-of`** (`--isa` was programmer shorthand). Single-valued,
same semantics (the class + its descendants). *Rejected:* `--descends-from`, `--under`. Pre-release,
so a hard rename (no alias); the internal `list_classes(subclass_of=…)` param + the "unknown
--subclass-of class" error match.

## 2026-07-18 11:47 UTC — `actor prop` subcommands BUILT; the §9 probe + two engine facts (closes the 10:02/10:30 spec's open points)

The 10:02/10:30 spec is built, tested (1392 offline + 4 integration green), live-E2E'd against the
real v68 install, and folded into `architecture.md`/`unrealed/*`. Three findings made during the
build resolve the spec's open points (facts, recorded here because they finalize spec semantics):

1. **§9 probe RESULT: partial property values import MEMBER-WISE ONTO THE CLASS DEFAULT** — members
   unmentioned in a stored-partial struct value, and elements unmentioned in a sparse static array,
   resolve to the class default, NOT zero (decisive live case: `DeusEx.Rat
   RotationRate=(Pitch=4096)`, a partial equal to the default member, exports NO line at all).
   `get`'s full-form fill and `unset KEY.Member` follow it (`propedit.STRUCT_FILL="default"`).
   Bonus: `MAP EXPORT` is member-precise default-diffing — the exact H3-omission mechanism.
   Evidence: `spikes/2026-07-18-partial-value-import-semantics/`; durable fact `unrealed/t3d.md`.
2. **v68 ScriptText carries NO defaultproperties block** (class source ends at the `#exec`
   directives; live-verified). The 10:02 §5 rejected textual route was impossible, not merely
   second-best — the bytecode-walker choice is vindicated; pinned as a regression test.
3. **The UClass-tail layout + in-struct value encodings** (10:30 "to-be-RE'd") are now
   corpus-verified byte-exact — 1914/1914 DX classes land the defaults block exactly at EOF; bools
   inside structs are ONE byte. Recorded in `unrealed/class-schema.md` "UClass body".

Scope note (no new decision, executing 10:02 §12): `actor find --prop`'s key-on-no-class typo
guard evaluates over the classes of the actors the OTHER filters admit (the considered set), not
the whole level — the level-wide reading would force schema builds for classes the query excluded.

**Refs:** `uedcli/{upackage,propedit}.py`, `uedcli/uprops.py` (walker + defaults),
`uedcli/{cli,dispatch,query}.py`; tests `test_{propedit,actor_prop,uprops_defaults}.py` + reworked
`test_{cli,dispatch,query,generators,actor_name_resolution,target_flag}.py`; docs
`architecture.md`, `unrealed/class-schema.md`, `unrealed/t3d.md`, `usage.md`; board `done.md`.

## 2026-07-18 12:14 UTC — Actor "folders": hierarchical, per-actor-sidecar, uedcli-only (the groups overhaul) (spec `specs/2026-07-18-actor-folders-hierarchical.md`)

Andrzej's design decisions for the "groups overhaul" (each choice his, from the speccing Q&A). The
overhaul introduces a **folder**: a hierarchical, uedcli-side organizational path for actors,
distinct from the T3D `Group=` property. Supersedes the inbox item "Hierarchical (nested) groups +
group-path queries" (2026-07-12).

1. **Rename the concept `group` → `folder`.** Avoids the three existing "group" collisions (T3D
   `Group=` actor prop, texture `Package.Group.Name`, property-browser `var(Group)` category); no
   clash with UnrealEd's `Group=` since a folder is never emitted to the editor. *Rejected:* keeping
   the name `group`.
2. **A folder is a per-actor SIDECAR file, not a T3D prop** — `maps/<level>/actors/<name>/folder`
   beside `order_value`; a typed `Actor.folder` field. Reason (Andrzej): "non-T3D, next to the order
   value file. T3D Group can't handle long values" (deep dotted paths overflow UnrealEd's FName
   length limit on `Group=`). Merges per-actor under `git merge` like the rest of the trunk.
   *Rejected:* storing the folder in the T3D `Group=` prop.
3. **The folder is INDEPENDENT of the T3D `Group` prop, which is retained UNCHANGED.** "Group not
   used for folder, but retained as a T3D prop unchanged." No absorb/derive either way; an actor may
   carry both. *Rejected:* absorbing an ingested `Group=` into the folder on `actor add`/import.
4. **Bare pattern = whole subtree.** `--folder castle` matches `castle` and every descendant.
   *Rejected:* bare = exact match only.
5. **Globstar wildcards:** `*` = exactly one segment; `**` = any depth (zero or more); **no
   triple-star**. A **wildcard-free** pattern is a subtree prefix; **any** wildcard makes the pattern
   a pure glob segment-match (no implicit subtree). So `castle.*` = direct children only, `castle.**`
   = whole subtree (== bare `castle`), `**.roof` = a `roof` at any depth, `*.roof` = a `roof` one
   level down. *Rejected:* a single any-depth wildcard (can't express "direct children only"); a
   `***` "one-or-more" token.
6. **Single path per actor** — no multi-membership. Cross-cutting selection uses `--class`/`--prop`,
   not folders. *Rejected:* keeping today's comma-list multi-membership.
7. **Folder is NOT emitted to the built map.** `level materialize` writes no folder to the `.dx`
   (gameplay-irrelevant editor-organization metadata; the sidecar is the source of truth; fully
   sidesteps the FName limit). Folder is excluded from the canonical level hash (naturally — not in
   the body or order). *Rejected:* emitting the leaf segment; emitting the full path when it fits.
8. **`--folder` lives on `actor add`, not the generators.** A folder is trunk state, and the
   generator pattern forbids generators (`brush build`/`actor build`) from writing trunk/stash state
   — so `brush build … | actor add - --folder X`. *Rejected:* `--folder` on the generators (the
   pre-sidecar item text) — would bend the generator pattern.
9. **Management verb mirrors `actor prop`: `actor folder set|unset|get`; folder shown in `actor
   show` with a `--t3d-only` suppressor.** v1 is assign-only. *Rejected:* a v1 whole-subtree
   `folder rename`/move (deferred to inbox).

Deferred to inbox (not in v1): `folder rename <old> <new>` (subtree re-parent); an exact-single-node
matcher (no form exists now that bare = subtree and `--prop Group=` no longer reaches the folder).

Open review points (in spec §8, unresolved at spec time): whether to retire `actor find --group`
(T3D-prop membership) in favor of `--prop Group=`; the stored-path character set; `apply`'s default
folder (id/basename vs ungrouped); `actor folder get` ungrouped-output convention.

**Refs:** spec `specs/2026-07-18-actor-folders-hierarchical.md`; touches
`uedcli/{model,trunk,query,cli,dispatch,stashlib,normalize}.py` + a new folder path-algebra module.

## 2026-07-18 12:32 UTC — Actor folders: spec review-gate resolutions (amends 12:14)

Two cold reviews of the folders spec (both verified against the code) resolved several points; folded
into the spec. The rulings that carry a design commitment beyond the 12:14 decisions:

1. **`apply` gains `--folder`/`--no-folder` ALONGSIDE `--group`/`--no-group` — NOT a rename.** A
   rename would silently drop the ability to stamp a T3D `Group` prop at placement and change a
   scripted `apply --group X`'s meaning. `--group` = the T3D prop (unchanged); `--folder` = the
   sidecar (new). *Rejected:* renaming `--group`→`--folder` on apply (the spec's first draft).
2. **`actor find --group` is KEPT — single-path-per-actor forces it.** Folders can't express
   arbitrary cross-cutting tags (`wip`/`act2`/`reviewed`) the way `Group`'s comma-list can, and
   `--class`/`--prop` are fixed dimensions, so `--group` is the multi-tag safety valve. Closes the
   12:14 "retire `--group`?" open point as DECIDED-KEEP. *Rejected:* retiring `--group`.
3. **`actor folder set` takes the path on `--to`, names variadic (`set --to <path> <names…>`)** — not
   two greedy positionals (`set <names…> <path>`, ambiguous + breaks the stdin-`-` compose). Corrects
   the "mirrors `actor prop set`" wording (prop set is single-name + `KEY=VALUE` tokens).
4. **All folder surfaces reject `--target stash|prefab`** (exit 2): the stash/prefab boxes serialize
   T3D-only with no per-actor sidecar slot, so a folder there can't persist / is always `None`.
5. **`actor find --no-folder` selects the ungrouped set**; `folder=None` matches no `--folder`
   pattern. **`actor folder get` prints `(none)` for ungrouped** (closes 12:14 R4 as DECIDED).
6. **Sidecar writes are atomic (`tmp + os.replace`)** and the delta-write changed-set diff fires on
   any folder change **including `"x"`→`None`** (the unset trap, symmetric to the set trap).
7. **Globstar matching is specified by a normative ALGORITHM** (regex translation with the
   `**`-separator-absorption boundary rule), not by example; `*` is the only wildcard, `?`/`[`/`]`
   rejected. The subtree-vs-glob asymmetry (bare = subtree; `**.roof` is non-compositional — the roof
   nodes only) is Andrzej's explicit choice, documented loudly in help, not reopened.

Left open for Andrzej (spec §8): stored-path char set (R2); `apply` default folder id/basename-vs-
ungrouped (R5); **NEW R6** — `actor show` folder-shown-by-default (his choice) breaks
`actor show | actor add -` unless `--t3d-only`; reviewers propose the inverse (pure-T3D default,
`--with-folder` opt-in) — kept as his default pending ruling.

**Refs:** spec §7b/§8 (resolutions + migration recipe); the two review findings folded 2026-07-18.

## 2026-07-18 12:45 UTC — Actor folders: the `// uedcli-folder:` interchange carrier + R2/R5/R6 rulings (closes the folders spec's open points)

The T3D-comment spike (`spikes/2026-07-18-t3d-comment-tolerance/`, static RE + live `MAP IMPORTADD`,
both agreeing) settled how a folder rides `actor show` output, and Andrzej ruled the last open points:

1. **Folder interchange encoding = a bare `// uedcli-folder: <path>` T3D comment line.** UnrealEd's
   T3D importer **silently strips `//` line-comments** (`Core.dll ParseLine`, gated `Exact==0` +
   not-in-quotes), so the comment makes `actor show` output **both** folder-round-tripping (uedcli's
   parser reads it into the sidecar) **and** UnrealEd-importable (the editor drops it, no warning).
   *Rejected:* the unknown-property carrier `UedcliFolder="…"` (works, but spams a per-actor
   `Unknown property in defaults` warning); `/* */` and `;` (NOT comment syntax on import — survive
   only as incidental no-`=` skipped lines). Storage is unchanged: the folder is the sidecar; the
   comment is interchange-only, never in the trunk body or the built map. Pinned:
   `test_engine_facts.py::test_t3d_import_strips_double_slash_comments` (byte pattern in the committed
   `core.dll`); durable fact in `unrealed/t3d.md` "Comments & unknown properties on import".
2. **R6 — `actor show` folder output → the carrier above, on by DEFAULT.** Default output is pure
   importable T3D that also carries the folder; `--t3d-only` suppresses the comment for a byte-exact
   editor export. Supersedes the 12:14 `folder:`-header + mandatory-`--t3d-only` sketch — the spike
   removed the round-trip-vs-compatibility tension entirely. `actor add`/ingest parses the carrier
   into the sidecar (explicit `--folder` overrides). *Rejected:* pure-T3D-default + `--with-folder`
   opt-in (the reviewers' fallback — now unnecessary).
3. **R2 — stored-path char set → KEEP `[A-Za-z0-9_+-]` per segment** ("fine for now").
4. **R5 — `apply` folder default → UNGROUPED unless `--folder`** ("unfoldered unless --folder"):
   apply's `--folder` is optional with **no default**; `--group` keeps its id/basename default,
   independent. *Rejected:* defaulting the folder from the stash id / prefab basename.

**Refs:** spike `spikes/2026-07-18-t3d-comment-tolerance/{findings,RE-findings}.md` + `harness/`;
`uedcli/tests/test_engine_facts.py`; `unrealed/t3d.md`; spec §4/§6/§8.

## 2026-07-18 12:36 UTC — `actor prop` build: 3-reviewer gate findings resolved (amends 11:47)

Andrzej asked this build for a THREE-reviewer gate (correctness / adversarial-live / docs+quality).
All confirmed findings were fixed same-session and pinned with regression tests; the fixes are
semantics-preserving hardening, no design change:

- **Exception safety (HIGH):** corrupt-but-loadable `.u` bodies could escape as bare
  IndexError/struct.error/RecursionError (fuzz-proven). `upackage`'s ref helpers are now
  bounds-safe (None, never IndexError), tagged-list bounds validate, `struct_members` gained a
  super-chain cycle guard, and `uprops._schema_guard` wraps every body decoder → `SchemaError`.
- **Non-finite/absurd numerics (HIGH):** `nan`/`inf` passed `Decimal()` and tracebacked in
  emit/normalize; `1e999` wrote a ~1000-digit trunk line. All numeric inputs now require finite,
  float32-range (±3.4e38) values — named exit-2.
- **Nested-struct semantics (MED):** stored-partial NESTED members now merge RECURSIVELY over the
  class default (the §9 probe semantics at every depth); struct members that are THEMSELVES static
  arrays (`Nest.Marks.1` ↔ `Marks(1)=` in the text — real DX: `Scale`, `NearbyProjectileList`)
  are fully pathable; whole-struct `get` renders the genuinely FULL member form (default merged
  over zero — supersedes the sparse-default rendering two earlier tests pinned).
- **`find --prop` completions (MED):** the Vector/Rotator comma sugar applies to query values;
  whole-static-array tuple queries expand and compare element-wise; a value that can NEVER match
  (non-numeric on a numeric, bad enum name, bad bool) is a typo → exit 2, LOOSER than set's
  validation on numerics (`128.0` matches a byte 128 — the §7 promise); the undeclared-key guard
  now fires even when the other filters admit zero actors (falls back to all level classes).
- **Stored-line hygiene (MED/LOW):** T3D last-wins duplicate lines — set edits the winner and
  drops shadowed dups, unset removes all; an unindexed `Key=` line on a static array is element 0
  everywhere (edit/unset/dump-all); a silent-success member unset no longer rewrites the line.
- **Misc (LOW):** genuine-wrapping-pair-only quote stripping; the `(N)`→dot hint fires on pathed
  spellings too; an unresolvable imported enum degrades to ordinals instead of erroring; stale
  `usage.md`/`architecture.md` claims about the old surface corrected; dead imports/helpers swept.

*Dismissed with reason:* `format_float` (float) vs `_fmt_dec` (Decimal) duplication — different
numeric domains, merging would couple `uprops` to `propedit`; `STRUCT_FILL` constant's dead "zero"
branch — kept as the greppable probe-result anchor; historical inbox captures quoting the removed
`--set` syntax — they are dated records of past proposals, not live docs.

**Refs:** regression tests in `test_actor_prop.py` ("review-gate regressions"),
`test_dispatch.py` (`test_actor_find_prop_{comma_sugar,malformed,typo_flagged}*`),
`test_uprops.py::test_corrupt_class_body_raises_schema_error_not_traceback`,
`test_propedit.py`; suite 1429 offline + 4 integration green; live re-smoke against the real
v68 install.

## 2026-07-18 14:03 UTC — Unattended build batch: compose-pipe, CSG-order, scale (3 specs)

Speccing the "build while away" batch (Andrzej curated it). `actor bbox` was in the shortlist but
Andrzej **dropped it** from this queue; scale was **added**. Decisions per item (Andrzej's, from the
speccing Q&A):

**Compose pipe** (spec `specs/2026-07-18-actor-name-compose-pipe.md` — closes two inbox items):
1. **`actor add` prints allocated Names to stdout (one/line, allocation order); the `added N` count
   moves to stderr.** *Rejected:* dropping the count; opt-in `--names` flag keeping the count default.
2. **Name-taking verbs read `-` = a newline name list from stdin**, on `actor delete/rotate/prop` **and
   the read verbs `get`/`show`** (prop/get/show thereby become multi-actor); **NOT `move`** (multi
   `move --to` collapses targets) and NOT `actor add` (its `-` already means a T3D snippet).
3. **`-` is the SOLE names source** — mutually exclusive with CLI name args (both → exit 2). *Rejected:*
   mixing CLI names + stdin names.
4. **Empty stdin → no-op, exit 0** (Unix-filter semantics; an empty upstream `find` never fails the
   pipe). *Rejected:* error on empty.

**CSG-order** (spec `specs/2026-07-18-csg-order-control.md` — closes the "can't place a brush FIRST"
item):
5. **Both a reorder verb AND a place-at-add flag:** `actor order <names|-> --first|--last|--before
   NAME|--after NAME` (mint new LexoRanks) + `actor add --order first|last|before=NAME|after=NAME`
   (default `last`, unchanged). *Rejected:* verb-only; flag-only.
6. **Multi-actor = block move preserving relative order** (consecutive ranks in the target gap; the set
   keeps its internal CSG order). `--before/--after` reference an existing actor's rank; self-reference
   → exit 2.

**Scale** (spec `specs/2026-07-18-scale-support.md` — FORMALIZES the fully-resolved 2026-06-25 design;
no NEW decisions). The 2026-06-25 scale-verb decisions (recorded here for the durable ledger, made
during the original spiking, gating spike CLOSED — `spikes/2026-06-25-scale-transform-mechanics.md`):
`actor scale`/`actor apply-transform`/`actor rotate --to`; `--to`/`--by` symmetric + mutually
exclusive; `--to` is in-place and excludes `--pivot`; `--pivot` optional (default computed center),
never `PrePivot` (D8); `mirror` = `scale --by -1,1,1` (no sugar verb); v1 authors MainScale only but
the math handles the full `PostScale·R·MainScale` chain; geometry edits work directly on a scaled
brush (no bake-first); apply-transform bakes all three + reverses winding on `det<0`; disallow-zero
scale; scale-a-mover warns, apply-transform-a-mover deferred. See the spec §4–§7 for the full set +
rejected alternatives.

**Refs:** the three specs above; touches `cli.py`/`dispatch.py`/`trunk.py`/`model.py`/`rotation.py`/
`emit.py` (+ a scale-algebra module). **Review-gate PASSED** — two cold reviews folded into each spec's
"Review-gate resolutions" section: the blocking ones were the real `actor prop set`/`prop get` grammar
(compose-pipe), a required `TrunkLevelSource.save(ranks=…)` override seam (csg-order — a reorder never
persisted otherwise), and hidden `propedit.TYPED_FIELDS`/nested-struct-parse + emit-de-dup work
(scale). Build order: compose-pipe first (the `-` grammar the others cite), then csg-order, then scale.

## 2026-07-18 21:30 UTC — Persistent package-schema cache (v1 discovery; phased) (spec `specs/2026-07-18-package-schema-cache.md`)

Every `uedcli` command is a cold host-native process, so all `.u` schema decoding restarts from zero
each invocation. Measurement (spec §9) showed the dominant cost is `load_package`'s name/import/export
**table parse** (38–211 ms/big package; whole `class list` path ~2.3 s), NOT the DEFAULTS bytecode
walk (a few ms) — refuting the draft's hypothesis. A warm on-disk cache of decoded primitives makes
repeat cold runs 2.4×–6× faster (`class list` 3.6 s→~0.5 s, `class show` 484→~200 ms). New module
`schema_cache.py` + `cache/schema/` (sibling to `cache/{textures,stubs}`) + `config.schema_cache_root()`
+ a `uedcli cache clear` verb. **v1 BUILT** (this entry). Three decisions:

1. **Key = a `(SCHEMA_CACHE_VERSION, realpath, size, st_mtime_ns)` STAT TUPLE, not a content hash.**
   *Rejected:* a sha256-of-bytes content-hash key (correct-by-construction, no invalidation logic) —
   the measurement killed it: hashing the bytes must run on EVERY cold run and costs ≈ the parse it
   saves (21 ms DeusEx.u, ~1.4 s the whole path), reintroducing half the cost removed. For ship-once
   game packages an `os.stat` (~5 µs) is a safe change detector. Accepted narrow caveat: a content
   change preserving BOTH size and nanosecond-mtime (spoof / timestamp-restoring copy over a same-size
   file) serves a stale entry — covered by `UEDCLI_SCHEMA_CACHE=off` + `cache clear`. `realpath`
   (symlinks resolved) keys, trading cross-path dedup of distinct byte-identical copies (not a real
   workflow) for the hashing cost that dedup would need.

2. **Cache PER-PACKAGE primitives; recompute cross-package COMPOSITIONS in-process.** *Rejected:*
   caching the resolved cross-package union / effective per-class defaults, keyed by a hash-TUPLE over
   every contributing package — poor reuse (a distinct entry per class; the shared upper chain
   `…→Engine.Actor→Core.Object` re-decoded and re-stored per leaf), whole-composition invalidation on
   any one package's change, and a complex multi-package key. Per-package primitives give perfect reuse
   (`Engine.u` decoded once, reused by every command) and free per-package invalidation; composition
   (ancestry/tree/prop-union) is a µs dict-merge, not worth persisting. Also *rejected:* a SQLite index
   (write-lock contention for parallel-by-construction commands; a dependency + migration burden for no
   gain over immutable per-key files) and in-memory-only memoization (dies with the cold process — the
   exact failure this fixes).

3. **PHASED: v1 = discovery primitives; v2 = defaults values (deferred).** v1 caches only what
   `class list`/`class show` need — class list, casefold→index map, per-class super-ref FQCN strings,
   abstract flags, own-property schema (with local enum names) — the two biggest measured wins, and by
   rendering NO default *values* it needs neither `buf`, the tables, nor per-Struct layouts, so it
   sidesteps the review's HIGH-1 (the value-render path reaching into live `Package.buf`). v2 (a
   follow-up, specced not built) adds the raw DEFAULTS blocks, enum tables, per-Struct member schemas,
   and compact tables to render `actor prop get`/`find` default values buf-lessly — HIGH-1's full fix.

**Serialization = marshal, not JSON** (§9 spike `spikes/2026-07-18-schema-cache-serializer/`): the
draft defaulted to JSON for portability/safety, gated on a timing spike. JSON measured 16.69 ms decode
on DeusEx.u — ABOVE the ~13 ms pickle baseline the spec's trigger names (the "small fast JSON"
assumption refuted) — so the trigger fired ⇒ marshal (5.71 ms, half the size). marshal has no pickle
RCE (only reconstructs basic containers), and a format drift degrades to a cache MISS, so JSON's
safety objection to pickle doesn't apply and its version-fragility is contained (SCHEMA_CACHE_VERSION +
corrupt=miss; Python pinned to 3.12). **`SCHEMA_CACHE_VERSION`** (int) is folded into BOTH the hashed
key AND the `v<N>/` path, hand-bumped on any decoder/shape/format change — guarded by a committed
**frozen-golden-bundle** test (replacing the illusory decode→serialize→deserialize round-trip, which
runs the current decoder on both sides and can never catch a forgotten bump). Storage mirrors
`stub_cache`: immutable per-key files, atomic-rename writes, corrupt/version-mismatch = miss.

**Deferred (v1 scope-cut, board follow-ups):** v2 defaults cache; automatic LRU/size-capped GC (v1
ships only the manual `cache clear` — immutability means no correctness pressure to evict);
compact-binary swap iff a later spike shows marshal is a bottleneck (moot — marshal chosen). Two
CONCURRENCY deferrals: `ClassIndex.ancestry`/`_package` and `class show`'s Package-seeded union still
decode live (rewiring them collides with another session's uncommitted `class show --category` /
diagnostic-print hunks); fold onto the cache once that work lands — the DEFAULT `class list` tree is
already fully cached (the 6× win).

## 2026-07-18 22:10 UTC — Schema cache v1: split discovery/props on-disk blobs (amends 21:30, build refinement)

Build-time finding on the 21:30 schema cache: eagerly decoding `own_props` for EVERY class into the
single bundle made a `class list` cold-MISS **~4× slower than the pre-cache path** (measured 16 s vs
3.6 s on the full DX install), because `class list` never renders properties yet paid the ~8 s
whole-path own-property decode. Fix (keeps the 21:30 bundle contents, changes only the on-disk
layout): the per-package bundle is written as **TWO blobs** — a cheap **discovery** blob
(`<key>.disc`: class list, cmap, super refs, abstract) that `ClassIndex`/`class list` reads, and a
**props** blob (`<key>.prop`: own-property schema) decoded/loaded LAZILY only for
`load_package_schema(need_props=True)` callers (`resolve_class_properties`). Result: `class list`
cold-miss 16 s → ~7 s (discovery only), warm ~0.35 s; the own-property decode is deferred to its
actual consumer. Both blobs share the same stat-tuple key + `v<N>/` dir; the frozen golden freezes
the concatenation of both so either decoder's change still trips it. No change to the three 21:30
decisions. Also hardened during the build: the `resolve_class_properties` cache path preserves the
no-fallback contract (a corrupt super ref re-raises via a `""` sentinel + `super_ref_for`), and with
the cache OFF it keeps the old live per-class decode rather than a whole-package one.

## 2026-07-18 19:41 UTC — `class list`/`show` follow-ups: O(n²) abstract decode; cache-write errors SURFACE; `--all` == unlimited depth

Three fixes from investigating a "`class list` still takes 5–7 s on every run" report (Andrzej).
(Clock note: the container's `date -u` reads 19:41 while the 21:30/22:10 entries above used another
session's faster clock; this entry is genuinely LATER than those despite the smaller time.)

1. **The discovery cold-miss was O(n²), not the ~7 s the 22:10 entry claims.** `_decode_discovery`
   already builds the `cmap` (casefold→export-index) but then called `class_is_abstract(pkg, c)`,
   which re-ran the O(n) `class_export_index` linear scan for EVERY class → 13.4 M `casefold()` calls
   on the DX path. Fix: thread the already-known `ci` into `class_is_abstract`→`_class_script_source`
   (optional param; other callers unchanged). Cold miss **7 s → 2.8 s**; warm hit ~0.3 s. Output is
   byte-identical (two cold reviewers confirmed; the only delta is a corrupt out-of-range export name
   no longer turns the abstract decode into an uncaught `IndexError` — safe). Pinned by the existing
   discovery decode tests.

2. **An unwritable schema cache now ERRORS, it is no longer silently swallowed** (Andrzej: "if cache
   is owned by root, the command should error. No silent error swallowing"). Root cause of the field
   report: `~/.uedcli/cache` was **root-owned** (left by a container run), so every cache write hit
   `PermissionError`, which `_try_write`'s `except OSError: pass` swallowed — the cache stayed dead and
   every run re-decoded cold, invisibly. `_try_write`→`_write_blob` now raises a clean, actionable
   **`CacheWriteError`** (names the dir; suggests `chown` OR `UEDCLI_SCHEMA_CACHE=off`), rendered at
   dispatch exit 2. *Supersedes* the 21:30/22:10 "a cache write failure must never fail the command"
   swallow — a silently-dead cache is worse than a loud, fixable error. The read-miss path (corrupt/
   absent blob → re-decode) is unchanged. Regression-tested (`test_schema_cache`).

3. **`class show --all` now means the WHOLE super chain (unlimited depth, == `--depth ∞`)** (Andrzej:
   "TBH I thought --all means --depth <INF>"). It was budget-limited to ~60 lines exactly like the
   no-flag auto view, so `--all` showed FEWER levels than `--depth 3` on a deep class — surprising.
   Now `--all` and `--category` both expand the full chain; `--depth N` clips. *Supersedes* the
   "~60-line auto-depth budget of the unfiltered `--all`" point in the 10:03 `--category` entry (that
   budget no longer exists — the only remaining `_SHOW_LINE_BUDGET` use is the DEFAULT collapsed
   own-props view). *Still open (asked, not yet decided):* the no-flag default on a class with ZERO
   own editable props (e.g. `TNM.tnmAugCloak`) shows only the `(+N inherited …)` tail — reads as
   "nothing"; whether to auto-expand that case is unresolved → `inbox.md`.

## 2026-07-18 20:09 UTC — `brush build staircase` redo: box-per-step, watertight, floor-anchored

**Context:** the old `builders.staircase` emitted ONE non-convex brush replicating UED's
`LinearStairBuilder` face-for-face (Base/back/Step/Rise/tiled-Side). It (a) tripped `level doctor`
with 60+ `watertight` "open edge" errors (the stepped profile is T-junction-riddled; the static
validator is T-junction-naive by design), (b) sat one `rise` **below** the floor (local
`Z∈[-rise,(steps-1)*rise]`), and (c) was a single brush, unlike `spiral` (one slab per step).
Spec: `specs/2026-07-18-staircase-redo.md`. Board: `to-build.md` Geometry #8.

**Decision:** `staircase` now returns a **`list[Brush]` — one axis-aligned convex box per step**
(like `spiral_staircase`). Box `k` = `X∈[k*depth,(k+1)*depth]`, `Y∈[0,breadth]`,
`Z∈[0,(k+1)*rise]` — a **filled solid column from the floor up to that step's tread top**. The set
occupies `Z∈[0, steps*rise]`, **at/above the floor**, front-bottom corner at local origin so `--at`
places that corner. Each box passes every per-actor `doctor` check (clean convex cube) and all boxes
are `CSG_Add` (no `csg_order` finding). Per-face ItemNames (`Step`/`Rise`/`back`/`Side`/`Base`) are
retained via a local labeled-box helper `_step_box` (not `cube()`, which hard-codes `OUTSIDE`),
built through the same live-blessed `_face` winding logic.

**Rejected / accepted trade-offs:**
- *Keep UED's single non-convex brush (face-for-face parity)* — **rejected**: it is the source of
  the `doctor` failure and can't be a clean per-step editable set. Byte-identity is trunk-relative
  (native build must match UED's build of *whatever is in the trunk*), so the builder's decomposition
  is free. The UED reference fact ("LinearStairBuilder emits one non-convex brush with this face
  taxonomy") is preserved as a standalone engine-fact test over the `Brush5` fixture rather than
  deleted.
- *Keep UED's tiled per-step side strips* — **rejected**: they existed only to keep a **single**
  brush intra-manifold; across separate `CSG_Add` boxes the strips buy nothing and defeat the clean-
  convex-box goal. The resulting cross-brush **side-face T-junctions** (box `k` shorter than `k+1`)
  are **accepted** — ubiquitous and tolerated in UE1 CSG (like `spiral`'s adjacent slabs); `doctor`
  is T-junction-naive by design; a `level preview` is the deferred visual check (flagged, no live
  editor this session).
- *First tread at floor level (`z=0`)* — **rejected** in favour of first tread at `z=rise` (you
  climb one riser onto step 0), the natural masonry-stair placement with the whole solid at/above the
  floor. This re-anchors the same profile up by one `rise` vs the old geometry — a deliberate
  behavioural change for identical inputs (documented in `usage.md`).
- *Re-bless the frozen `stair_*` parity goldens live* — **deferred**: no live editor this session.
  Regenerated **offline** from the same `builder_world_verts`/`builder_poly_count` machinery (no
  hand-typed coords), touching only the four `stair_*` entries. Legitimate because axis-aligned
  integer-coordinate boxes reconstruct **identically** in the editor (same basis as the exact
  `cube_*` goldens); winding safety rests on reusing live-blessed `_face`. Until a live
  `python -m uedcli.tests.builder_parity_cases` runs, these four goldens are a change-detector, not
  an editor oracle (flagged in `inbox.md`).

## 2026-07-18 20:54 UTC — `event graph`: unset-Tag not matchable; lint is advisory (exit 0)

**Context:** `event graph` (build item 10, Analysis) is a pure, offline, model-side verb that
scans the selected level's T3D actors and prints the **Tag↔Event trigger wiring** (an edge
`A → B` when `A.Event == B.Tag`) plus a wiring lint (dangling wires / unreachable movers /
cycles). Two modelling questions were load-bearing.

**Decision 1 — an unset `Tag` is NOT a matchable receiver.** UnrealEngine defaults an unset `Tag`
to the actor's class name at runtime. We treat ONLY an explicitly-set, non-empty `Tag` as an edge
target; a default/class-name Tag creates no edge.
- *Rejected — honour the class-name default* (so `Event=Trigger` would wire every Trigger with no
  explicit Tag): it would flood the graph with spurious edges whenever an event name happens to
  equal a class name, which is essentially never the author's intent. Cost: a mapper who
  intentionally leaves Tag unset and fires the class name sees no edge — a rare pattern; the
  explicit-Tag form is the norm. The assumption is documented and flagged in `inbox.md`.

**Decision 2 — the verb exits 0 on any successful scan, even with lint findings.** `event graph`
is a query/producer verb (its stdout is the wiring, one edge per line, pipeable); lint is advisory
and goes to stderr (text/dot) or into the `--json` object. Real errors (no project/level, bad
flags) still exit 2 via the standard dispatch guards.
- *Rejected — non-zero exit on lint findings (à la `level doctor`'s ERROR gate)*: `doctor` is a
  dedicated lint gate; `event graph` is primarily a wiring **producer** whose output feeds other
  tooling, and a non-zero exit would break a `event graph | …` pipe on a level that merely has an
  unfinished wire. A future opt-in `--strict` exit is noted in `inbox.md`.

**Scope (not a decision, a limitation):** the edge model reads the single `Event` prop only —
multi-event ARRAY props (Dispatcher `OutEvents(n)`, Counter) fire events that produce no edges yet
(inbox follow-up). Unreachable-mover lint is deliberately conservative: it flags a Mover with an
explicit Tag that nothing targets AND no self-moving `InitialState` (self/bump/loop); a tagless
mover is not flagged (its trigger mechanism isn't reliably knowable offline).

## 2026-07-18 21:40 UTC — `poly align` v1 scope + face-selection grammar (Andrzej-decided)

Load-bearing choices for `poly align` (board item 11), decided by Andrzej from the spec
`specs/2026-07-18-poly-align.md` (which frames the options + rejected alternatives in full). This
verb makes a texture flow continuously across faces instead of restarting the pattern at every
brush edge; offline texture-vector math reproducing UnrealEd `TEXTURE ALIGN`, model-side (no
editor). UV convention (verified from `render.rs`/`preview_native.py`, not memory):
`U = (Vertex − Origin)·TextureU + PanU`, texel scale carried in `|TextureU|`.

1. **v1 modes = `--wall` + `--floor` (coplanar planar continuity) + `--ring` (cylinder facet-ring
   wrap).** Both board headline cases ship. *Rejected/deferred:* `--face` (fit-one-texture-to-a-
   surface), turning (non-coplanar) wall runs, and sphere wrap — v2, as follow-up queue items.

2. **Frame source = BOTH synthesize-from-normal AND adopt-an-existing-seed-face's frame, default
   adopt-seed.** Continuity by default continues the seed/first face's already-dialled-in
   `TextureU/V`+`Pan` (UnrealEd "align to surface"); `--fresh-frame` opts into a canonical frame
   synthesized from the face normal. *Rejected:* synthesize-only (discards a tuned mapping);
   adopt-only (no way to reset).

3. **Face selection = build a `brush poly find` PRODUCER verb; `poly align` takes positional
   `(brush,poly)` targets AND stdin `-`.** A new `brush poly find <brush> [--item …] [--facing …] …`
   stdout producer emits the exact face set (so `brush poly find Tower --item Side | brush poly
   align --ring -` skips a cylinder's 2 caps cleanly); `poly align` consumes `-` OR explicit
   positional `(brush,poly)` targets — both supported. *Chosen over* a per-command `--item` filter
   flag on `poly align` (option 1): Andrzej chose the cleaner producer-feeds-consumer grammar (the
   `CLAUDE.md` core "prefer a query verb feeding another over per-command filter flags" philosophy),
   accepting the larger scope (two verbs this item) over one small filter flag now. *Rejected:*
   positionals-only (no `-`, breaks the stdin-compose convention). Positional targets on BOTH verbs
   were explicitly required ("also positional").

**Lower-stakes model choices carried from the spec (may be revisited):** continuity defined in
WORLD space and written back per-brush via each brush's inverse transform (not identical stored
fields); the continuity offset lives in float32 `Origin` so `Pan` stays integer (no widening
`Polygon.pan` to float); `--ring` advances U by true chord length `2r·sin(π/N)` (flat facets →
uniform density); seam = first face in input order (`--seam` deferred), non-dividing perimeter
leaves the seam by default with an opt-in `--fit-perimeter` (ring-only) to snap scale for an exact
meet. Verb lives at `brush poly align` (peer of `list`/`set`/`find`).

## 2026-07-18 21:52 UTC — Warm per-user EDITOR container for `level materialize` (ephemeral becomes the fallback) — amends the 2026-07-06 05:12 per-command editor identity

`level materialize` (and `preview --game`'s internal `run_materialize`) stops paying a full
editor boot per invocation: it reuses ONE warm per-user editor container, gated exactly like the
warm game-preview container. Spec: `specs/2026-07-18-warm-editor-materialize.md` (blocking spike
SP-E — reused-editor cleanliness + timing split — `board/to-spike.md`). Andrzej directed the
feature ("I want as much setup reused as possible, as is reasonable") and made four choices:

1. **Warm the CURRENT editor path; no new flag now.** Materialize today IS the editor build; the
   warm reuse is default behavior with zero CLI surface change. The `--editor` flag name arrives
   with the later native-default cutover; the warm machinery carries over. *Rejected:* adding
   `--editor`/`--native` on materialize now (native isn't wired into the verb and isn't playable
   at DX scale yet); adding the flags with editor-default now (same cutover scope, premature).
2. **Contention → per-command ephemeral fallback, never a queue.** Acquisition is a NONBLOCKING
   per-user `flock(~/.uedcli/editor.lock)`; lock held, or the container pinned with a different
   fingerprint → THIS invocation runs today's ephemeral `ensure_editor`/`stop_editor` path.
   Parallel materializes still compose — this AMENDS (does not supersede) the 2026-07-06 05:12
   per-command identity: the ephemeral container remains the concurrency story, the warm
   container is a fast path in front of it. *Rejected:* blocking on the flock (serializes ~1-2
   min builds machine-wide — the exact cost the 2026-07-06 decision rejected); per-project warm
   containers (more idle ~0.5 GB editors + lifecycle bookkeeping; same-project builds still
   contend).
3. **Preview-style fingerprint gates reuse; ANY input staleness reboots.** ONE `docker inspect`
   on a fingerprint LABEL: image id + realpath-normalized mount pairs + `(path,size,mtime)`
   tuples of the MUTABLE package inputs (project-overlay packages + v69 stubs; base-game dirs
   treated immutable, the preview stance). Required because `MAP NEW`/`MAP LOAD` never purge the
   prior level's object pool (spike `2026-06-19-read-surface-texture-package`; load-bearing in
   `qualify.export_and_qualify`) and the running GUI editor rewrites its ini from boot-time
   config (quirks.md 🔬 2026-07-01) — whether `OBJ LOAD FILE=` on a resident package reloads it
   is UNPINNED (spike SP-E.3). In-place reuse = the existing `MAP NEW` + full re-import per
   build; H3 post-verify stays the CONTENT backstop (it cannot see package staleness — that is
   the fingerprint's job). *Rejected:* config-only
   fingerprint (a regenerated stub / re-synced overlay package silently builds stale);
   always-reboot-the-editor-process (forfeits the boot saving — the whole point).
4. **Callers = `level materialize` + `preview --game`'s internal materialize only** (both sit on
   the `apply.run_materialize` seam). `stash intersect`/`deintersect` and the no-GUI UCC build
   containers (stub build, texture batchexport) are explicit follow-ups, not in scope.

Lifecycle mirrors the warm game container (2026-07-17 06:57/07:30 decisions): per-user name
`uedcli-editor-<uid>`, own prefix volume, inline tini-child idle watchdog (10 min, `/work/
.last_use`), fail-closed boot, pin marker honored but no pin flag in v1. Any warm-mode drive
error or H3 failure tears the container down before the lock releases (an untrusted editor is
never left warm). The gate machinery is factored to be SHARED with `preview_game.
acquire_warm_container` where reasonable (behavior mandated, refactor not forced).

## 2026-07-18 21:59 UTC — `class list`/`show`: kill overloaded `--all`; `--depth all` + `--include-non-actor`/`--include-abstract` (Andrzej-decided; spec `specs/2026-07-18-class-flag-orthogonalization.md`)

`--all` was three unrelated switches under one name, and the name misled: users read `--all` as
"unlimited depth" but it delivered (E1) reroot `Engine.Actor`→`Core.Object`, (E2) drop the placeable
filter, and NOT reliable depth — the tree `--all` stayed `(N)`-collapsed. Andrzej: split the scope
effects out and let *depth* be depth, the same spelling on both verbs.

**`--depth N | all`** (both `class list` and `class show`). `--depth` gains the keyword value `all`
(case-insensitive, → `math.inf`) = the whole thing (full tree, no `(N)`-collapse / no ~60-line budget;
or the entire inherited-prop super chain). It is the SOLE depth control; `--depth 0` = root/own-only,
negatives rejected with a value-naming error. *Rejected:* a boolean `--full`/`--recursive` (reintroduces
the flag-proliferation the split removes) and `--depth -1` (magic number; argparse dash-parsing hazard).
`all`-as-a-value is already CLI vocabulary (`brush poly set Wall1:all`). `--depth` is *analogous* across
the verbs (list = descend tree levels; show = ascend superclass hops + flip to the expanded view), not
identical.

**`class list` scope split** (replaces `--all`): **`--include-non-actor`** reroots the default from
`Engine.Actor` to `Core.Object` (the only switch to non-Actor classes; no-op with `--subclass-of`).
**`--include-abstract`** drops the placeable filter in the `--flat --subclass-of` drill and `--package`
flat list (a no-op in the tree/default-category views, which already show abstract branch-points — a
one-line stderr note fires when it can do nothing, so it never reads as broken). `class show` loses
`--all`; unlimited = `--depth all`.

**Hard removal, but LEGIBLE:** `--all` is kept hidden on both verbs and errors with a targeted pointer
(`class list: --all was split — use --include-non-actor / --include-abstract / --depth all`; show:
`--all was renamed — use --depth all`), not an opaque argparse "unrecognized argument" — because a
3-way split leaves the user unable to guess which replacement they meant. No zombie alias.

**Migration:** old `class list --all` (tree) → `--include-non-actor`; old `--all --flat` (every class,
2034) → `--subclass-of Core.Object --include-abstract --flat` (verified byte-for-count identical:
`--include-non-actor` alone drops the `Core.Object` root via the `d==0` root-skip, so the faithful full
dump names the root explicitly); old `class show C --all` → `class show C --depth all` (verified
identical, 151 lines). Two cold spec reviews caught + fixed: **F1** — the placeable filter must stay
per-branch (globalizing it would break the default view + `--depth` structural browse and their tests);
**F2/F4** — the every-class migration and a false-equivalence row. Full suite green (1777).

**Supersedes** the `--all` points in: the 2026-07-17 19:37 `class` namespace entry, the 2026-07-18 10:56
`class list` tree entry, the 2026-07-18 10:03 `--category` entry ("the ~60-line auto-depth budget of the
unfiltered `--all`" — that budget is gone), and the 2026-07-18 19:41 `class show --all` entry (`--all`
→ `--depth all`).

## 2026-07-18 22:18 UTC — Warm editor: spec review-gate rulings (amends 21:52)

Two cold reviewers on `specs/2026-07-18-warm-editor-materialize.md`; every finding resolved into
the spec. The load-bearing rulings:

1. **Warm-mode build failure = FAIL with a hint, no automatic ephemeral retry** (Andrzej). The
   warm container (container + per-boot volume + ini temp) is torn down before the flock
   releases, and the invocation exits 2 with a message naming warm mode + "a retry boots fresh".
   *Rejected:* one automatic ephemeral retry (both reviewers' recommendation — masks whether warm
   reuse is flaky and doubles the cost of a genuinely-bad build); retry-on-drive-errors-only
   (same masking for the wedge class).
2. **The idle watchdog cannot kill a live build:** `wine_ctl.py` touches `/work/.last_use` on
   EVERY invocation (each host-side Driver exec), the entrypoint touches it at container START
   (a never-READY GPF'd boot still self-dies), and acquire touches it host-side immediately
   after the reuse `inspect`, BEFORE the health probe (the preview R3 MED-5 ordering). Watchdog
   is env-gated (`UED_IDLE_S`, default 0=off) in the SHARED `uned/entrypoint.sh`, so ephemeral
   editors and the standing `dx-lum-uned` are untouched; image rebuild sequenced (stale-image
   trap).
3. **H3 verify's live qualification dump is SCOPED to the current build's package set** — the
   object pool survives `MAP NEW` (the 2026-06-19 pinned fact), so a reused editor's
   `OBJ DEPENDENCIES` dump can carry a prior build's packages and a colliding bare name could
   mis-qualify (false FAIL or consistent false PASS). Spike SP-E.7 exercises the collision live.
4. **WINEPREFIX volume is unique per BOOT** (`uedcli-editor-wp-<uid>-<nonce>`), removed on every
   explicit teardown; acquire runs an orphan-volume sweep (idle self-death can't remove its own
   volume). A wedge-recovery reboot never reuses a possibly-corrupted prefix.
5. **No double `MAP NEW`:** the existing `materialize()` sequence (`ensure_load` → `MAP NEW` →
   re-add → rebuild) IS the per-build reset; the change is a `dismiss_blocking_dialog()` at
   `driver.map_new()` + a defensive dismissal before a reused build's first command (a SIGKILLed
   predecessor can leave a modal the health probe can't see).
6. **Warm ini + lock live under the per-user home** (`$UEDCLI_HOME`-honoring), not a project
   state dir — the container is per-user and outlives projects; ini unlinked only at container
   teardown.
7. **Fingerprint stub scope pinned:** only stubs for stems in THIS project's composed load set —
   not the whole shared stub cache (another project's stub regeneration must not reboot this
   editor).
8. **Boot-retry budget = ONE** (deliberately tighter than preview's `REBOOT_BUDGET=3`): a second
   same-image boot failure predicts the ephemeral path fails identically, so fail fast, capture
   the `docker logs` tail, remove container+volume (nothing leaks).
9. **Pinned+mismatch → silent ephemeral fallback** — a deliberate DIVERGENCE from the preview
   gate (which errors loudly): materialize never refuses to build while an ephemeral path
   exists; cost (a stale pinned editor degrades every build to ephemeral speed) accepted,
   surfaced by the stderr mode line. Stopped containers reboot regardless of pin (nothing
   running to preserve).
10. **Decision-1 clarification:** keeping an `--editor` path post-cutover AMENDS the 2026-07-14
    "editor ditched entirely (no fallback editor path)" stance (recorded in the native-
    materialize spec §4): the editor build path survives the native-default cutover behind
    `--editor`, carrying this warm machinery.

## 2026-07-18 22:25 UTC — Surface a texture's decoded image to the LLM for classification (Andrzej-decided; spec `specs/2026-07-19-texture-show-for-llm.md`)

Texture **classification is blind**: the write path (`texture classify set`) works and `sync` already
auto-derives dominant named colors, but nothing in the `texture` verb surface lets the classifier
*see* the texture it is naming — and the decoded PNGs are unlocatable by hand from a ref (the cache
filename is the manifest **stem** `<group>.<name>`, using the texture's internal Group, not the ref's
package: `CoreTexWater.bluewater` → `.../CoreTexWater/water.bluewater.png`). The **main consumer is an
LLM**, which cannot open a viewer but *can* read an image file the harness hands it a path to. So the
tool gains a ref→image-path capability. Four load-bearing calls:

1. **No composite montage; batched *distinct-file* reads are the blessed path.** The efficient loop is
   a query returning many refs+paths at once, whose images the harness reads as **separate files** in
   one turn (each its own content block bound to its own ref token — no spatial mapping), classifying
   each ref. **Rejected: a montage/contact-sheet grid image** — the LLM would map cell→label by
   position and an off-by-one silently misclassifies the wrong ref on a committed, downstream-trusted
   catalog. *(Revised at the review gate from an initial over-broad "one texture at a time"; the write
   path is per-ref regardless, so misattribution has no foothold. A montage survives only as a
   possible future human browse aid.)*
2. **Per-ref write-back only.** Keep `classify set <ref> …` as the sole write. **Rejected: a batch
   JSON-map-via-stdin classify** — one ref per write keeps decide→write unambiguous.
3. **Trust auto colors.** The LLM sets only `tags` + `description`; the auto-derived `colors` stand
   (`colors_source="auto"`) unless it explicitly overrides a wrong one via `--colors` (→ `"set"`).
   **Rejected: making the LLM always set colors explicitly** — needless work duplicating the free
   pixel-math already done at `sync`.
4. **Surface the path through the query verbs, not only a standalone verb** (Andrzej: "could `search`
   just return the path too automatically?"). `search`/`list` gain a `--json` (JSONL) form carrying
   `{ref, png_path, width, height, colors, colors_source, status, tags, description}`, so the producer
   that *finds* textures also *delivers* their images — classification is one call, not
   find-then-look-up. `search` also gains `list`'s status filters (`--unclassified` etc.) so
   `search --unclassified --json` is the clean unclassified-refs-with-paths producer. A thin
   `texture show <ref>` (shared resolver) covers the already-hold-a-ref case; default text output stays
   bare-ref-per-line so `search | brush poly set --texture -` is unbroken.

Resolution is **ref → the matching entry's `stem` → `<cache>/<Package>/<stem>.png`** (case-insensitive
ref match; honors 3-part `Package.Group.Name` collision refs and groupless textures; couples nothing by
string-reconstruction). The failure taxonomy is **errno-based** (a naive `os.path.exists()` masks a
permission-denied cache as "not synced"): unknown ref, ambiguous 2-part ref (lists 3-part candidates),
known-ref-but-PNG-missing (`ENOENT` → hint `sync`), and cache-unreadable (`EACCES` → distinct message,
no `sync` hint) are each a clear named non-zero error. Native (non-UCC) `sync` decode and the
root-owned-cache bootstrap wall are **separate** inbox items; this feature only reads whatever cache
`sync` populates and *reports* the wall distinctly at the boundary.

## 2026-07-18 23:01 UTC — INVARIANT: stash, prefab, and trunk MUST share ONE T3D tree format

**Decision (Andrzej):** the three on-disk T3D trees — the git **trunk** (`maps/<level>/`), a
**stash** entry (`.uedcli/stash/<id>/`), and a library **prefab** (`<prefabs-dir>/<name>/`) — **MUST
use the same per-actor layout**: `actors/<name>/{actor.t3d, order_value[, folder]}` (per-actor
directory; per-actor LexoRank `order_value` sidecar; optional per-actor `folder` sidecar; no shared
`order` file). Any per-tree extras (a stash/prefab `meta.json` — capture anchor, timestamp — and a
`packages` list) sit BESIDE the shared `actors/` tree, not in place of it. **Consistency is the
requirement**: one format, read/written through ONE shared code path (`trunk.py`'s per-actor
reader/writer, factored out for reuse), so there are not three divergent parsers/writers to keep in
sync, and a stash/prefab is structurally the same kind of T3D tree as a level.

**Supersedes the divergence** that existed here: the stash used a flat `actors/<name>.t3d` +
**shared `order`** file + `packages` (`stash_register.py` via `tree_io.read_state_dir`), and a
prefab used a **single `Begin Map` blob** `<name>.t3d` + a `<name>.json` sidecar
(`stashlib.write_prefab`). Both are replaced by the per-actor tree.

**Why extend the per-actor form to stash/prefab, which don't need it?** The per-actor `order_value`
was introduced trunk-only to make `git merge` conflict-free (2026-07-01 07:05 UTC), and the stash
(machine-local throwaway, single-writer) and prefab don't strictly need merge-freedom. But a single
shared format — and a prefab being *git-committed*, so it benefits from conflict-free merges too —
outweighs the minor simplicity of the old flat forms. **Consistency is key** (Andrzej).

**Migration (spec to design — `specs/2026-07-18-unify-t3d-trees.md`):** stash is throwaway
(gitignored `.uedcli/`) so old entries can simply be regenerated/wiped; **prefabs are git-committed
library artifacts**, so existing prefab files need a real migration path (auto-convert-on-read,
one-time bulk convert, or a `prefab migrate` verb) — flagged to Andrzej before build.

## 2026-07-18 23:01 UTC (addendum) — unify-T3D-trees sub-choices (Andrzej-decided)

Two sub-choices for the T3D-tree consistency invariant (above), decided by Andrzej from spec
`specs/2026-07-18-unify-t3d-trees.md`:

1. **Migration = HARD CUTOVER.** No dual-read of the old prefab single-blob format; existing
   committed prefabs must be **re-captured** under the new per-actor layout. *Chosen over* the
   spec's recommended auto-convert-on-read (+ `prefab migrate`) — a single format with zero
   lingering back-compat code wins on consistency (the whole point of this change), and the prefab
   library here is small/regenerable. **Requirement:** reading an old-format prefab must fail with a
   CLEAN, actionable error (exit 2, names the prefab, "old-format prefab — re-capture it"), never a
   traceback. *Rejected:* auto-convert (lingering dual-read); `prefab migrate` verb (extra surface
   for a one-off).
2. **Folder = PERSISTED per member (full trunk parity).** Each stash/prefab member carries its own
   `folder` sidecar in the tree, like the trunk; `stash/prefab apply --folder` still OVERRIDES at
   placement. *Chosen over* the spec's recommended placement-time-only folder — literal parity across
   all three trees is the consistency the invariant demands. Needs a folder channel threaded through
   the capture path (blast-radius noted in the spec).

## 2026-07-19 03:58 UTC — Texture catalog redesign: lazy native decode, content-addressed cache, similarity (Andrzej-decided; spec `specs/2026-07-19-texture-catalog-redesign.md`)

A whole-catalog redesign, not just the `texture show` add-on. **Supersedes the mechanism half of the
2026-07-18 22:25 texture-show decision** (its ref→`<Package>/<stem>.png` resolution and "reads whatever
cache `sync` populates" are replaced below); its **workflow half survives** (batched distinct reads /
no montage / per-ref write-back / trust auto-colors / enrich `list`+`search --json` + thin `show` —
carried unchanged). **Folds in and closes** three board items: the `texture show` plan item, the
"native `texture sync` decode (drop UCC-under-Wine)" spec item, and the deferred "content-addressed
texture-image cache + `texture classify clone`" spec item. Nine load-bearing calls:

1. **On-demand NATIVE decode; no mandatory `sync`.** `utexture.py` (pure-Python UE1 decoder, already
   used by native preview, documented byte-identical to UCC batchexport) decodes a package's textures
   directly when a verb needs them — no UCC, no Wine, no Docker. *Rejected: keep UCC-under-Wine;
   rejected: keep an eager sync-first model.*
2. **Lazy, stat-tuple `(path,size,mtime)` invalidation, exactly like the `class list/show` schema
   cache.** A changed tuple re-decodes that package on next access ("re-check in-flight"). *Rejected: a
   mandatory bulk pass.*
3. **Drop the `sync` verb; add `texture prewarm [--package]` (optional eager decode) + `texture gc`
   (evict orphaned/stale cache).** *Rejected: keeping `sync` as a vestigial opt-in prewarm.*
4. **Content-addressed derived cache: `images/<hh>/<pixel-hash>.png`.** The exact pixel-hash (`sha256`
   over `(width,height,raw RGB)`) is the cache key + dedup + clone identity → identical textures dedupe
   across packages. *Rejected: ref-keyed filenames (no dedup/clone); rejected: storing the derived path
   in the manifest (dangles vs the gitignored cache — the reason it was never stored).*
5. **TWO hashes.** Exact pixel-hash = crisp identity; a SEPARATE lightweight **perceptual** hash
   (Pillow-only, no new deps; recommend dHash) = similarity. *Rejected: one perceptual hash for both —
   a re-encode must not merge distinct textures.*
6. **Durable classification: per-project GIT-TRACKED, pixel-hash-keyed, SHARDED one file per texture**
   (`texture-catalog/classified/<hh>/<pixel-hash>.json` holding refs+tags+description+colors). Disjoint
   edits by concurrent agents never touch the same file → conflict-free merge (mirrors the per-actor
   `.t3d` ethos). *Rejected: a per-user shared auto-applied store (not committed with the repo);
   rejected: a single hash-keyed `classifications.json` (merge-hostile); rejected: the current
   per-package name-keyed manifest.* **`stale`/`removed` states are ELIMINATED** — changed pixels = a
   new hash = a new unclassified entry; a gone texture = an unreferenced (gc-able) classification.
7. **`texture classify clone --from <catalog\|project>` — keep-local, skip already-classified.** Fills
   only pixel-hashes unclassified locally; never overwrites local work; reports skipped conflicts.
   *Rejected: incoming-wins; rejected: error-on-conflict.*
8. **Batched distinct reads; enrich `list`/`search --json`; thin `show`.** *(Carried verbatim from the
   2026-07-18 22:25 decision.)* `search --unclassified --json` is the batch producer (ref+path+
   metadata); harness reads each image as its own file (no montage → no spatial misattribution);
   `classify set <ref>` is the sole per-ref write; auto-colors trusted unless `--colors` overrides.
9. **Visual similarity = graded perceptual-hash ranking.** `texture search --similar <ref> [--max N]`
   ranks the catalog by ascending Hamming distance on the perceptual hash; composes with `--json`.
   *Rejected: near-duplicate-detection-only; rejected: semantic/embedding search (heavier deps, against
   the Pillow-only offline ethos).*

Derived cache (`~/.uedcli/cache/textures/{images,packages}`) is regenerable + never committed; the
per-package `packages/<stem>.json` decoded index (stat tuple + `{ref,pixel_hash,phash,wh,colors}`) is
the ref↔hash bridge + enumeration source. Migration of existing name-keyed classifications → the
sharded hash-keyed store is auto-convert-on-read (or a one-shot `texture migrate` — flag at build,
parallel to the prefab-migration flag in the 2026-07-18 23:01 entry). The parallel object/sound asset
catalog (the "★ Asset catalog" `to-spec` item) MUST mirror these mechanics.

**Addendum (2026-07-19, resolving the review-gate open scope choice F):** `utexture.py` decodes **P8
only**; dropping UCC (which exported every format) would make native decode a coverage regression on
generic-UE1/UT substrates (non-P8 textures). **Andrzej's decision: require the non-P8 decoders
(RGBA8/DXT1/RGB16/imported-palette) as a BUILD PREREQUISITE** — native decode must fully match UCC's
coverage before the redesign lands, so generic-UE1 stays honest and no coverage gap ever ships.
*Rejected: ship DX-only now with non-P8 as a follow-up; rejected: keep UCC-under-Wine as a non-P8
fallback (keeps the container/Wine seam the redesign exists to drop).* The `undecodable`-row behavior
(§4a) stays as the graceful floor for a genuinely unparseable/corrupt texture, not as an
accepted-format gap. The non-P8 decoder port is now a **prerequisite** board item, not an optional
follow-up.

**Addendum 2 (2026-07-19, resolving second-gate finding on change-detection):** the first draft's
derived `changed` status was unworkable (the pre-change hash lives only in a wipeable derived cache; a
durable ref→hash ledger would reintroduce the per-hash write conflict). **Andrzej's design:** drop any
`changed` status — a changed texture shows UNCLASSIFIED (its new pixel-hash has no classification); the
prior classification becomes an **outdated entry** (a shard whose pixel-hash resolves to no current
texture), managed by `texture classify list-outdated` (shows the stored write-once `<package>.<name>`
ref) + `texture classify prune`. The shard gains a **write-once** `ref` for identification (not the
mutable `refs` list that was rejected — conflict-freedom preserved). `stale`/`removed` remain
eliminated as stored flags; change/removal is a derived query. *Rejected: a derived changed-status; a
durable ref→last-hash ledger.*

## 2026-07-19 08:58 UTC — Port `bspValidateBrush` coplanar surf-link into the native incremental CSG (`bspcsg.rs`); spike §92 stage 2

The native↔UnrealEd byte-parity residual on real levels is native OVER-producing coplanar surfs
(§92 §3: +82 surf / +146 vec). Stage 1 pinned the first over-production to UNATCO `Brush755` — a
tessellated dome CSG_Subtract whose 9 `(0,0,1)` cap facets each got their OWN `FBspSurf`, where the
editor keeps ONE. **Decode (gdb oracle + `Editor.dll 0x37290`, spec `specs/2026-07-19-unatco-dome-
csg-divergence.md`): the editor runs `bspValidateBrush` when a brush is built — it assigns each brush
poly an `iLink` so COPLANAR + same-facing + same-texture + same-axes + same-flags faces of ONE brush
SHARE a surf, which `bspMergeCoplanars` (grouped by `iLink`) then fuses.** Native re-ingesting the
T3D never ran this phase, so every facet seeded its own surf and no later merge could fuse them.

**Decision: port the `bspValidateBrush` link loop into `bsp_brush_csg`**, faithful to the decode —
the geometry gate uses each face's FINALIZED (winding-derived) normal + on-plane base (the editor
links AFTER `FPoly::Finalize`), the exact-axis `TextureU`/`TextureV` gate is KEPT (on the dome cap
the 9 facets carry identical authored axes so it passes anyway). Result: UNATCO N=105 `only-native`
28→20 (the 8 cap fragments now fuse), castle byte-identity UNCHANGED (485 surf / 1156 node / 26 vec /
43.04
## 2026-07-19 08:58 UTC — Port `bspValidateBrush` coplanar surf-link into the native incremental CSG (`bspcsg.rs`); spike §92 stage 2

The native↔UnrealEd byte-parity residual on real levels is native OVER-producing coplanar surfs
(§92 §3: +82 surf / +146 vec). Stage 1 pinned the first over-production to UNATCO `Brush755` — a
tessellated dome CSG_Subtract whose 9 `(0,0,1)` cap facets each got their OWN `FBspSurf`, where the
editor keeps ONE. **Decode (gdb oracle + `Editor.dll 0x37290`, spec `specs/2026-07-19-unatco-dome-csg-divergence.md`):
the editor runs `bspValidateBrush` when a brush is built — it assigns each brush poly an `iLink` so
COPLANAR + same-facing + same-texture + same-axes + same-flags faces of ONE brush SHARE a surf, which
`bspMergeCoplanars` (grouped by `iLink`) then fuses.** Native re-ingesting the T3D never ran this
phase, so every facet seeded its own surf and no later merge could fuse them.

**Decision: port the `bspValidateBrush` link loop into `bsp_brush_csg`**, faithful to the decode —
the geometry gate uses each face's FINALIZED (winding-derived) normal + on-plane base (the editor
links AFTER `FPoly::Finalize`, so a stale/projected authored normal must not decide coplanarity), and
the exact-axis `TextureU`/`TextureV` gate is KEPT (on the dome cap the 9 facets carry identical
authored axes so it passes anyway). Because `links` are in brush-poly space but LOOP 1 can DROP a
degenerate face, the representatives are remapped into `temp` space after compaction (else a dropped
face desyncs the indices LOOP 2 chases — cold-review finding). Result: UNATCO N=105 `only-native`
28→20 (the 8 cap fragments now fuse), castle byte-identity UNCHANGED (485 surf / 1156 node / 26 vec /
43.04%), N=104 still clean. Regression: `bspcsg::tests::validate_brush_links_fuses_coplanar_same_facing_faces`.

*Rejected: (a) an EXPERIMENTAL "drop the exact-axis gate" toggle the first cut carried, on the
hypothesis the editor unifies axes for unresolved (grey) textures before linking — measured to give
the IDENTICAL link set (only-native 20 either way), so it was dropped as an unverified assumption that
buys nothing. (b) Forcing a post-hoc `TryToMerge` on the final surf set — the §82 §10.6 route that
regressed the castle twice; the divergence is bidirectional so it is not closeable by forcing a
merge.* This is the FIRST of a handful of curved/near-coincident merge classes (`only-native` grows
28→534 across N=105→762); Stage 3+ re-bisects for the next. Dome cap is closed. *(Correction 2026-07-19,
2-agent verified — §92 §12: the remaining 20 `only-native` at N=105 are precision TWINS of editor surfs,
same normal+class differing only in plane offset 0.005–0.044.)* *(Further correction 2026-07-19, later
same-day reconcile, 2-agent verified — the "axis-aligned clip-fragmentation entering in (213,396]" /
"`only-native` grows 28→534" redirect was itself an ARTIFACT of a `unatco_subset.py` MOVER CONFOUND (28
DeusExMovers pushed through world CSG, +221 phantom surfs; fixed `cd56c1ae2`), and the "+82 surf
over-production" was measured against STALE pre-current-core `.dx` (3698 surfs). Current mover-clean native
is **3609 surfs vs golden 3616 = −7 (under-production)** — there is no coplanar over-production to bisect.
The dome-cap fix / `bspValidateBrush` link decision above STANDS; only the Stage-3 over-production redirect
is retired. Live status: `PARITY-STATUS.md`; baseline: `_scratch/baseline-reconcile/`.)*

## 2026-07-19 (water-cluster triage) — WaterZone authoring, doctor `fallthrough`, and poly-flag verb naming (Andrzej-decided)

Three choices from triaging the moat/water board cluster, all live-verified against the current CLI:

- **No bespoke WaterZone scaffold verb.** Authoring a swimmable water volume is already fully covered
  by existing primitives: `actor build Engine.ZoneInfo --prop bWaterZone=True | actor add -` (or the
  placeable `DeusEx.WaterZone` class) round-trips the properties into the trunk, schema-validated, no
  editor. *Rejected: a `zone add-water` / `--water` scaffold verb, and an `actor add --prop` — property
  setting stays on the generator (`actor build --prop`), `actor add` stays the sole trunk writer.*

- **Remove the `doctor` `fallthrough` check entirely** (`check_solidity`, `uedcli/doctor.py` 305-334).
  It WARNs on any nonsolid/semisolid brush with an upward-facing (walkable) face. A nonsolid brush is a
  legitimate deliberate authoring choice — water, decoration, or a deliberate player trap — and is NOT
  invalid geometry, so `doctor` should not flag it at all. In practice the check has been pure
  false-positives (water surfaces, zone portals, unreachable ceiling beams). *Rejected: exempting only
  `PF_PORTAL`+`PF_TRANSLUCENT` faces, or a water-texture-name heuristic, or a reachability/height gate —
  all retain a check whose premise (nonsolid up-face = suspect) Andrzej rejects.* (The watertight-on-
  portal-sheet false-positive was separately already fixed 2026-07-18 via per-poly flag OR-ing.)

- **Keep `brush poly set --add-flag` / `--remove-flag`** (do NOT rename to `--set-flag`/`--unset-flag`).
  A poly's flags are a SET (bitfield membership); add/remove describes membership change accurately,
  whereas set/unset reads like value assignment. *Rejected: the cosmetic rename — it breaks the CLI +
  tests + docs for no semantic gain.* The forthcoming `brush build sheet --flag <name>` build-time
  passthrough reuses these same flag NAMES.

## 2026-07-19 (level-design docs + AI-skills plugin) — verb-first craft guides shipped as a Claude Code plugin (Andrzej-decided)

Building the castle by hand surfaced that the `dev/docs/unrealed/leveldesign/` guides teach the
UnrealEd GUI but don't map the craft onto uedcli verbs, and that there's no DeusEx human-scale
reference. Decisions for a "level-design best-practices docs + AI skills" effort (a `[spec]` item):

- **Docs: full verb-first rewrite of the `leveldesign/` guides**, retaining short "UnrealEd GUI
  equivalent" annotations so a GUI-aware reader can map the mental model. Follows the `movers.md`
  pattern (already verb-oriented). *Rejected: (a) a layer-a-"With uedcli"-section-onto-the-GUI-prose
  retrofit — Andrzej wants verb-first primary, GUI demoted to a note; (b) leaving the GUI framing.*
  The water recipe (translucent NONSOLID zone-portal sheet over a `bWaterZone` ZoneInfo) is the first
  concrete entry; goes in the zoning guide.

- **Human-scale numbers come from a MEASUREMENT SPIKE, not invention.** A spike measures shipped DeusEx
  maps via uedcli (room/corridor/doorway/step dims, PlayerStart/eye heights) **plus the player
  collision cylinder/radius and other object sizes**, yielding grounded, citable, regenerable numbers.
  *Rejected: hand-authoring numbers from recall (unverified), and skipping them for v1 (agents keep
  guessing scale).* The DX class catalog is derived from `uedcli class list` (regenerable) + a curated
  top-N, not a hand-list that rots.

- **Skills ship as a Claude Code PLUGIN whose marketplace IS the uedcli repo.** The plugin lives at
  `Tools/uedcli/claude/plugins/uedcli/` (`.claude-plugin/plugin.json` + `skills/<name>/SKILL.md`),
  grouping Claude-integration assets under a non-hidden `claude/` dir. A `.claude-plugin/marketplace.json`
  at the repo root lists it (`source: "./Tools/uedcli/claude/plugins/uedcli"`, resolved from repo root).
  Users install via `/plugin marketplace add <repo-url>` → `/plugin install uedcli@…`; Claude Code
  clones the repo and manages updates. Thin per-task skills (build-water, build-mover, zone-a-level,
  light-a-scene, texture-surfaces, build-skybox, grid-discipline) that cite the guides — one source of
  truth in the docs, skills are ~15-line wrappers. `leveldesign/` is also wired into the `CLAUDE.md`
  "read BEFORE X" router. *Rejected: (a) bundling the plugin into the pipx/Nuitka binary — a onefile
  binary's data dir is an ephemeral temp unpack, so it can't be pointed at; the marketplace-from-repo
  path avoids binary coupling entirely; (b) a separate dedicated plugin repo — unnecessary, the repo
  doubles as its own marketplace; (c) one monolithic skill — per-task skills load on demand; (d) a
  path-print `--plugin-dir` install — breaks under onefile.* **Gotcha to honor:** a marketplace-installed
  plugin runs from a CACHED copy and CANNOT reference files outside the plugin dir (`../` blocked), so
  the craft docs must live INSIDE the plugin — done via a **within-repo symlink** from the plugin's
  docs to the canonical `dev/docs/unrealed/leveldesign/` (same-marketplace symlink targets are
  dereferenced/copied into the cache), keeping ONE source of truth. Packaging note: the sibling
  `claude/plugins/` tree is outside the `uedcli/` Python package, so it needs no packaging change for
  the marketplace path (it ships via git, not the wheel).

## 2026-07-19 (addendum) — Move uedcli into its own CLI-only repo; plugin distribution blocked on that move (Andrzej-decided)

uedcli will be extracted from the `dx_lum` mod repo into its OWN repository containing just the CLI
(plus its `claude/plugins/uedcli/` skills plugin + `docs/`). Rationale surfaced from the skills-plugin
distribution review: with the plugin's marketplace living at the `dx_lum` repo root, `/plugin
marketplace add <repo-url>` would clone the whole ~3.3 GB private mod repo just to deliver a few KB of
level-design skills. A dedicated CLI repo makes the repo-as-its-own-marketplace design (the prior
2026-07-19 entry) small and clean.

- **Plugin distribution is BLOCKED ON the repo move.** The repo-as-marketplace install path is not
  offered until uedcli lives in its own repo (tracked as a `to-spec` item). *This supersedes the prior
  entry's implicit assumption that the marketplace repo is the `dx_lum` mod repo — it will be the new
  CLI repo instead.*
- **Interim (dev) install:** symlink the plugin's `skills/` into `.claude/skills/` locally for
  development — no marketplace registration yet.
- The move's scope (which dirs travel, git-history handling, how the mod repo consumes the CLI
  afterward, the pipx/Nuitka release story) is itself the `to-spec` item; this entry records only the
  DECISION to move + the distribution dependency.

## 2026-07-19 12:30 UTC — Extend `--target KIND/NAME` to the read verbs (race escape hatch); skip generators (Andrzej-decided)

**Partly superseded by 2026-07-20 21:30 UTC.** The flag is renamed `--target`→`--tree` and the "racy
selected-level pointer" this hatch worked around is *gone* (replaced by `$UEDCLI_LEVEL`), so `--tree`
on the read verbs is now a general convenience, not a race escape. The read verbs keep the flag; the
generators still skip it.

**Context.** The CLI-usability probe (`reviews/2026-07-19-cli-usability-probe.md` §1–2) found the
machine-local selected-level pointer is a live cross-session RACE: a concurrent `level select` silently
reflags it, so every verb that defaults to "the selected level" can read/write the wrong level with no
error. `--target level/<name>` is the only race-safe workaround, yet it was missing on exactly the
verbs a designer reaches for to check "is my level OK": `actor show`, `level status`, `level doctor`,
`event graph`, `stash capture`.

**Decision.** Add `--target KIND/NAME` (via the existing `cli._target_flag`) to those FIVE read verbs,
accepting all three box kinds (`level|stash|prefab`):
- `actor show`, `level doctor`, `event graph`, and `stash capture`'s trunk branch already resolve
  through `_resolve_level_source`, so they needed only the flag on the parser.
- `level status` was rewritten to route through the seam; it now prints a `<kind>: <name>` header from
  the source's uniform **`display_name`/`kind`** (added to all three `LevelSource` classes), warns on
  duplicate `order_value`s only when `src._ranks` is non-empty (a box has none), and prints the git
  hint only for a `TrunkLevelSource`.
- `stash capture --target` names the capture **SOURCE** box; combining it with `--from-t3d`/
  `--from-stdin` (a different source) is rejected (exit 2), not silently ignored.

**Rejected — `actor build`/`brush build` (generators).** The probe table listed `actor build`, but a
generator writes a T3D snippet to stdout and reads no box; the race is on the downstream `actor add`
(which already has `--target`), so `--target` on a generator would be inert. Left absent, together with
`brush preview` (a per-kind `stash`/`prefab preview` exists) and `level materialize/preview/select`
(inherently a build/lifecycle op).

**Supersedes** the 2026-07-12 03:06 UTC scope's "deliberately absent from `actor show` and
level-lifecycle" clause for these read verbs (the mutating-verb scope and the generator/preview
exclusions stand). Architecture + `usage.md` reconciled; regressions in `test_target_flag.py`.

## 2026-07-19 19:28 UTC — Rotation CLI input is UNREAL ROTATION UNITS, not degrees (Andrzej-decided)

The rotation-taking CLI flags — `--rotate` (`actor build`/`brush build`), `--rot` and `--by`/`--to`
(`mover key add`/`rotate`), and `actor rotate --by`/`--to` — now interpret their `PITCH,YAW,ROLL`
input as **unreal rotation units** (the 16-bit FRotator field: **65536 = a full turn, 16384 = 90°,
8192 = 45°, 4096 = 22.5°**), NOT degrees. `16384` in → `Yaw=16384` stored (identity parse: round +
mod 65536; negatives wrap, so `-16384` = `49152`).

**Rejected: keep degrees** (the prior behaviour, `--rotate 0,90,0` → `Yaw=16384` via the GMath-
quantized `deg_to_uu`). **Why UU:** the whole substrate speaks FRotator units — stored `Rotation=`
values, DX props like `swingAngle`/`cameraFOV`, and the T3D itself are all byte-angles; making the
authoring flags take degrees forced a mental unit-switch and made docs/examples inconsistent (a
`--rotate 0,90,0` next to a `Rotation=(Yaw=16384)` read as a contradiction). One unit system end to
end is simpler and matches what the editor/T3D store. Degrees ergonomics (whole-number 90/45) are a
minor loss; the clean UU equivalents (16384/8192) are memorable.

**Mechanism:** `rotation.uu_field()` (identity round+wrap) replaces `rotation.deg_to_uu()` at the five
authoring call sites in `dispatch.py`. The **preview camera-pose grammar** (`rot:PITCH,YAW`, orbit
`azimuth`/`elev`) is ALSO converted (Andrzej: "all rotation" — 2026-07-19 ~19:40): `preview_shots.py`
parses those inputs as UU and `uu_to_deg`s them into the internal degrees model at parse time, so the
trig/render path is unchanged; the `look:@actor` computed angles are internal (not user input) and
stay degrees. `deg_to_uu` itself is retained (still used by the render path and the resolve step).
`--help`, `usage.md`, `architecture.md`, the `leveldesign/` docs, and all rotation tests are
reconciled; the mesh-import `#exec` 8-bit angle scale (64 = 90°) is a separate asset-pipeline unit and
unchanged.

## 2026-07-19 13:30 UTC — `actor find`: rename `--class` → `--class-exact`, add `--subclass-of` (Andrzej-decided)

**Context.** `actor find --class Light` matches ONLY the exact `Light` class — it silently SKIPS
`Spotlight` and the other Light subclasses, a footgun (an LLM reasonably expects "all lights"). The
usability probe flagged it.

**Decision.** Split the class filter into two explicit flags on `actor find`:
- **`--class-exact C`** — the old exact-match behaviour, renamed so the spelling signals "exact."
- **`--subclass-of C`** — descendant-aware: matches `C` or any class that descends from it, via the
  offline `ClassIndex.descends_from` (`dispatch._find_class_filter` expands it to every class present
  in the level that descends from a base, then ORs with `--class-exact` into the set handed to
  `list_actors`). Matches `class list --subclass-of`'s existing spelling. Needs the game `.u` schema.

**Bare `--class` is REMOVED, not silently kept.** A `_RemovedFlag` action registers `--class`
explicitly (so argparse prefix-abbreviation can't resurrect it as `--class-exact`) and ERRORS with a
message naming the two replacements — forcing the exact-vs-subclass choice instead of the silent
footgun. This is the WIDE breaking change: any `--class` call site must move to one of the two.

**Reconciled:** `cli.py` (flags + `_RemovedFlag`), `dispatch._find_class_filter`, `usage.md`,
`architecture.md`, `test_cli.py`/`test_dispatch.py`. **Deferred (inbox):** the LLM-facing
`leveldesign/` KB docs + specs/reviews still say `--class`; they're the ON-HOLD docs+skills effort's
territory, so the rename is flagged there rather than edited mid-flight.

## 2026-07-20 00:00 UTC — Move `actor scale`/`actor apply-transform` → `brush scale`/`brush apply-transform` (Andrzej-decided)

**Context.** Both verbs set/bake `MainScale`/`PostScale` — properties of `ABrush` (a mesh scales via
`DrawScale`), so they were mis-scoped under the `actor` namespace.

**Gate (verified first, as the item required).** `MainScale`/`PostScale` are brush-family: not
declared on `Engine.Actor` in the offline schema, absent from every non-brush trunk actor checked, and
`apply-transform`'s bake folds into the PolyList (inherently brush-only). So no non-brush actor
legitimately carries them → the move is sound.

**Decision.** Rename to **`brush scale`** and **`brush apply-transform`** (parsers moved from the
`actor` to the `brush` subparser; dispatch routing rekeyed `cmd=="brush"`). As a `brush`-namespace
verb they now also **reject a non-brush (point) actor** up front (all-or-nothing, matching
`brush clip` et al.) — previously `actor scale` on a Light silently set a meaningless field. `actor
rotate` STAYS on `actor` (rotation is a general actor property, not brush-specific). WIDE breaking:
every `actor scale`/`actor apply-transform` call site moves to `brush …`.

**Reconciled:** `cli.py`, `dispatch.py` (+ the non-brush guard + error strings), `transform.py`/
`doctor.py` doc refs, `usage.md`, `architecture.md`, `quirks.md`, and `test_scale_verbs`/
`test_cli_consistency`/`test_name_not_found_sweep`/`test_scale_integration` (the producer/round-trip
tests switched from Light to brush actors, since scale is brush-only now). Historical specs/plans/
reviews are frozen; `leveldesign/` KB docs deferred to inbox with the `--class` flag rename.

## 2026-07-20 00:30 UTC — Drop `class show`'s schema-cache seed so its prop walk uses the warm cache (~2.4× warm win)

**Context.** `class show`'s prop walk pre-seeded each chain package as a full `Package` object into
`resolve_class_properties(_cache=…)`, forcing a LIVE decode and bypassing the persistent per-package
schema cache. The "ancestry half" of the schema-cache rewire (super refs via `ClassIndex.ancestry` →
`_schema` → `load_package_schema`) already shipped 2026-07-19; this was the deferred prop-walk half
(gated on `dispatch.py` being quiet of CLI-surface work).

**Decision.** Drop the seed: `class show` now calls `resolve_class_properties(fqcn, resolver=…)` with
no `_cache`, so the prop walk takes the cache-ON path (`load_package_schema`). Measured **~2.1–2.4×
warm** on a depth-4 class, output byte-identical.

**Why safe (the seed's purpose is subsumed, not lost).** The seed existed to keep the `super:` line
and the prop set from diverging (a torn read showing full props beside a truncated chain). With the
seed gone, BOTH the chain (`ancestry`→`_schema`) and the prop walk (`resolve_class_properties`
cache-ON) read from the SAME `load_package_schema` disc, memoized per realpath — so they share one
super-ref source per package and CANNOT diverge (strictly MORE consistent than the seed, which used a
separate `_package` load). The degrade fallback (missing/unparseable ancestor → `SchemaError` →
own-only + note; `--category` → exit 2) is unchanged. Two cold reviewers confirmed no divergence and
no new traceback path. The `resolve_class_properties` SEED CAPABILITY stays (pinned by
`test_resolve_class_properties_schema_path_equals_seeded`) — it just has no in-tree caller now.

**Reconciled:** `dispatch.py` (`_dispatch_class`), `test_ingest_validation.py` (coupled test now
asserts `_cache is None`), `test_schema_cache.py` (comment), `architecture.md`. **Flagged (inbox):**
the non-category own-only degrade branch has no dedicated test — a PRE-EXISTING gap (not a regression),
noted for a small follow-up.

## 2026-07-20 13:48 UTC — `mover key` gains a `--from-base` base-relative coordinate frame

**Context.** A Mover keeps its base pose in `Location`/`Rotation` (KeyNum=0); keyframe *i*≥1 is
stored as a relative offset in `KeyPos(i)`/`KeyRot(i)`. The keyframe-editing verbs (`mover key
move`/`rotate`/`add`) took targets in world-absolute coords and subtracted the base to derive the
stored offset, so `--to 0,0,0` meant the world origin, not the mover's own position — and there was
no direct way to author the base-relative offset the mover actually stores (the natural frame for
mover travel: "up 128uu," "open 90°"). Spec `specs/2026-07-20-mover-key-base-relative-frame.md`.

**Decision.** Add a boolean **`--from-base`** to `move`, `rotate`, and `add`. It is a reference-frame
selector: when set, the verb's absolute-target coords (`--to`/`--at`/`--rot`) are interpreted as
measured from the base pose — i.e. written straight into `KeyPos`/`KeyRot`, skipping the
base-subtraction. On `add` it applies to whichever of `--at`/`--rot` are present (both dims, one
call). `--from-base` is rejected with `--by` (a delta-on-current, a different relative sense) with a
clear non-zero error. Default is unchanged: targets stay world-absolute.

**Why a boolean, not a `--offset` arg (rejected).** A third coordinate source `--offset` reads well
for `move`, but `add` takes position (`--at`) and rotation (`--rot`) together, so `--offset` would
fracture into `--offset` + `--rot-offset` — two bespoke names that don't pair with the existing
flags. One boolean reinterprets whatever targets the verb already accepts and composes over `add`'s
two dimensions for free. "World vs base" is a genuine reference-frame axis, not the per-command
mode-flag anti-pattern the CLI conventions warn against.

**Why world stays the default (rejected: base-relative default + `--world` opt-out).** `--to` means
"to this world position" across the whole CLI (`actor move`, `brush vertex move`, `actor rotate`).
Flipping `mover key move --to` alone to base-relative would give `--to` two meanings by verb and
silently change an already-shipped verb's behavior. The base frame is opt-in; the common case pays
one explicit, self-documenting flag.

**Reconciled (on build):** `cli.py`, `dispatch.py` (`_dispatch_mover_key` + the `--by` guard),
`usage.md`, `architecture.md`, `tests/`. Spec is ephemeral scratch.

## 2026-07-20 15:24 UTC — `mover key` keyframe model: index-addressed create-or-edit + required frame (SUPERSEDES the 13:48 opt-in flag)

**Supersedes** the 2026-07-20 13:48 entry's design (a `--from-base` boolean with world as the
default, `add`/`move`/`rotate` kept). The design grew during brainstorming; the net target below
replaces it. Spec `specs/2026-07-20-mover-key-base-relative-frame.md`; engine grounding
`spikes/2026-07-20-mover-numkeys-trailing-zero/`.

**Decision.**
1. **Drop `mover key add`.** `mover key move <i>` / `rotate <i>` become index-addressed
   create-or-edit: `i == NumKeys` creates the key (grows `NumKeys`), `1 ≤ i < NumKeys` edits it.
   Contiguous only — `i > NumKeys` is rejected (names the next index), `i == 0` rejected (base pose),
   `i ≥ MAX_KEYS` rejected. Removes the `next_key_index` "next free slot" ambiguity (a key authored to
   the base pose stores no `KeyPos` line and looked free).
2. **The coordinate frame is required, not defaulted.** `--to` must be qualified by exactly one of
   `--from-base` (coords are the offset from the base pose — written straight into `KeyPos`/`KeyRot`)
   or `--from-world` (world-absolute — the old base-subtracted math). No frame flag with `--to` is an
   error. `--by` (delta on the current offset) takes no frame and rejects one.
3. **No auto-shrink of `NumKeys`.** Zeroing a key never reduces `NumKeys`; reducing it is an explicit
   `mover key remove <i>`. This mirrors UnrealEd exactly — the spike live-verified the editor keeps a
   mover's authored `NumKeys` through `MAP IMPORTADD` + `MAP REBUILD` even with every movement key at
   base (`NumKeys` is the authoritative count, independent of which `KeyPos` lines exist).

**Why required frame, not a world default (rejected).** `--to` means "to this world position"
elsewhere in the CLI, but a mover keyframe target is conceptually *relative* travel; a world default
silently misauthors the common relative case (`--to 0,0,90` = "up 90" gives `(0,0,90) − Location`, no
error). A required explicit frame eliminates the footgun at the cost of one mandatory flag. (The
13:48 rationale for keeping world-default was judged weaker than the misauthoring risk.)

**Why create-or-edit over keeping `add` (rejected).** `add`'s implicit slot pick can't distinguish a
deliberately-base-valued key from an empty slot (zero offsets store no line), so it could overwrite a
real dwell key. Index-addressing removes the guess; a fresh mover is animated by editing key 1
(`move 1 …`), and `add`'s combined `--at`+`--rot` becomes one `move` + one `rotate`.

**Open (spec review):** whether to add a `mover key clear` convenience (truncate to base-only) on top
of `remove`. Default: no — `remove` suffices.

**Reconciled (on build):** `cli.py` (drop `add`; frame flags on `move`/`rotate`), `dispatch.py`
(`_dispatch_mover_key`: drop `add` branch, index create-or-edit + guards, frame gating), `movers.py`
(drop unused `next_key_index`), `usage.md`, `architecture.md`, `tests/`. Engine-fact pin
`test_it_keeps_numkeys_when_a_key_is_zeroed` already landed with the spike.

## 2026-07-20 16:18 UTC — `mover key`: `count` owns `NumKeys` (settable); `move`/`rotate` edit-only (SUPERSEDES the 15:24 create-or-edit)

**Supersedes** the 2026-07-20 15:24 entry's verb model (there `move`/`rotate` were index-addressed
*create-or-edit* auto-growing `NumKeys`, and `NumKeys` stayed hard-rejected). The frame design
(required `--from-base`/`--from-world`), the dropped `add`, and the no-auto-shrink finding all stand;
what changed is how `NumKeys` is managed. Spec `specs/2026-07-20-mover-key-base-relative-frame.md`.

**Decision.**
1. **`NumKeys` becomes directly settable**, and a new **`mover key count <name> [<n>]`** verb
   gets/sets it: no arg prints, `<n>` sets. **Non-destructive** — changing the count never clears key
   values (a lowered count leaves inactive keys' `KeyPos`/`KeyRot` dormant; raising restores them).
   Bounds **`2 … 8`** (`MIN_KEYS`/`MAX_KEYS`), error names the value.
2. **`count` == `actor prop set NumKeys=<n>`**, exactly — `NumKeys` comes **off**
   `propedit.HARD_REJECT`, both routes share one setter (same bound, same omit-when-2 canonical form),
   no `count`-specific side effects. `count`'s only extras are the getter + `mover key` discoverability.
   `KeyPos`/`KeyRot`/`KeyNum` **stay** hard-rejected.
3. **`move`/`rotate` are edit-only** — they edit an existing key (`1 ≤ i < NumKeys`) and never grow
   `NumKeys`; raising the count is `count`'s job. `i == 0` → base-pose error; `i ≥ NumKeys` → error
   ("raise the count first"). Drops the create-or-edit/contiguous idea entirely.

**Why (rejected alternatives).** `count` owning the count gives a clean separation vs. `move`/`rotate`
silently resizing (Andrzej's call); it also matches the editor's own flow (set `NumKeys`, then place
each key). Non-destructive because Andrzej wants a lowered count to be reversible (`count 2` then
`count 6` restores). Both routes identical so there's no "which command really sets it" confusion. A
separate `clear`/truncate verb is unneeded (`count <lower>` reduces non-destructively; `remove <i>`
deletes destructively). `NumKeys` bounded `2 … 8` rather than a raw byte because `KeyPos[8]` is fixed
and a mover needs ≥ 2 keys.

**Why `NumKeys` is settable at all (the earlier hard-reject reversed).** It is a real runtime prop
(the authoritative waypoint count — the engine can't infer it from which `KeyPos` lines exist, and
the editor never auto-decrements it: spike `spikes/2026-07-20-mover-numkeys-trailing-zero/`), and the
editor exposes it in the Mover property sheet. `KeyNum` (the view selector) stays canonicalized-away;
`KeyPos`/`KeyRot` stay `mover key`-only (they need the index + frame semantics).

**Reconciled (on build):** `cli.py` (add `count`, drop `add`, frame flags), `dispatch.py`
(`_dispatch_mover_key`: `count` branch, drop `add`, edit-only index guard, frame gating), `propedit.py`
(`NumKeys` off `HARD_REJECT` + shared bounded setter), `movers.py` (`set_num_keys`; drop
`next_key_index`), `usage.md`, `architecture.md`, `tests/`.

## 2026-07-20 21:30 UTC — Level is the ambient `$UEDCLI_LEVEL`; rename `--target`→`--tree`; drop `level select`

**Context.** The "current level" a content verb edits was a machine-local pointer file
(`<root>/.uedcli/current-level`) set by a `level select` verb (2026-07-05 19:07/19:28). The
2026-07-19 CLI-usability probe proved it a **live cross-session race**: a concurrent `level select`
silently reflags it, so any verb defaulting to "the selected level" can read/write the *wrong* level
with no error. Separately, the per-command override `--target KIND/NAME` (2026-07-12, extended
2026-07-19) reads wrong — "target" connotes a *destination*, yet on `stash capture` it names the
*source* and it collides with `materialize --out`.

**Decision (Andrzej).** Three coupled changes:
1. **Replace the pointer with an ambient env var `$UEDCLI_LEVEL`** (a bare level name), read as the
   default source. Per-process, so there is no shared mutable pointer to race on; mirrors the
   `$UEDCLI_PROJECT` **precedence order** (flag > env > fallback). The env is passed IN to
   `level_select.resolve_level(env_level=…, maps_dir=…)` (as `config.resolve_project` does), which
   `set_selected`/`get_selected`/the pointer file all removed.
2. **Rename `--target` → `--tree KIND/NAME`** (unchanged grammar/routing). The three boxes are one
   T3D-tree format (2026-07-18 23:01), so the flag names a `tree`; this answers July-12's rejection of
   `--t3d-tree`. Added to the holdouts `level materialize`/`level preview` (**level-kind only** — a
   captured stash/prefab has no world to build/walk; `stash preview`/`prefab preview` already exist).
3. **Drop `level select` and `level create --select`.** Setting the level is `export
   UEDCLI_LEVEL=<name>`; a child process cannot set the parent shell's env, so there is no verb.

**Visibility echo (Andrzej — "yes").** An env var doesn't *remove* the silent-wrong-level footgun, only
shrinks it from global to per-shell (a stale export still writes silently). So a **mutating** verb that
resolved its level from the ambient env (not an explicit `--tree`) echoes ONE line to **stderr**:
`editing level 'X' (from $UEDCLI_LEVEL)` (`materializing …` / `capturing from …` per verb). Suppressed
with explicit `--tree`; never for reads. Implemented at the mutation seam (`TrunkLevelSource.save`) so
it self-limits to writes without per-verb enumeration.

**Migration (Andrzej — clean break).** No legacy-file read: the stale `.uedcli/current-level` is simply
ignored. The "no level" error names BOTH set-methods: `no level: set the environment variable (export
UEDCLI_LEVEL=<name>) or pass a level explicitly (--tree level/<name>)`.

**Rejected.**
- *Repurpose `level select` as an eval-emitter* (`eval "$(uedcli level select foo)"` → prints `export
  UEDCLI_LEVEL=foo`) — the `ssh-agent`/`direnv` pattern; keeps a discoverable verb + set-once
  ergonomics. Andrzej chose the clean drop (one less verb; `export`/`level status`/`level list`
  suffice).
- *Keep `--target`* — retains the source-vs-destination wart and the `--out` collision.
- *Let materialize/preview accept any `--tree` kind* — meaningless for a stash/prefab (no world).

**Named tradeoffs (accepted).** `$UEDCLI_LEVEL` is per-shell (a new terminal / CI step re-exports,
unlike the cross-terminal pointer) and **global across projects** (no cwd walk-up like
`$UEDCLI_PROJECT`); a stale export in another project errors *loudly* (`level not found`), not
silently.

**Reconciled (on build):** `level_select.py` (pointer API removed; `resolve_level(env_level=…)`,
`NO_LEVEL_MSG`), `dispatch.py` (`_resolve_level_source` env fallback + `from_env`; `_resolve_level_only`
for materialize/preview; `_announce_env_level`; `level status`/`list`/`create` rewired; `level select`
deleted), `cli.py` (`_tree_flag`, materialize/preview `--tree`, `select` parser + `create --select`
removed), `architecture.md`, `direction.md`, `usage.md`, `docs/README.md`, tests
(`test_tree_flag.py`, `test_level_select.py` → env-resolver; suite-wide `set_selected`→`setenv`).
Spec: `specs/2026-07-20-tree-flag-and-env-level.md`.

## 2026-07-21 12:06 UTC — `brush build` emits ONE non-convex brush actor + `doctor` becomes T-junction-aware

**Context:** `brush build`'s non-convex builders (`staircase`, `spiral_staircase`) each emit a
**LIST of convex boxes → one brush ACTOR per step** (decisions 2026-07-18 20:09 UTC; `builders.py:18-22`).
So a staircase is N separate actors. Andrzej wants **one brush actor carrying the whole shape**. This
directly **reverses** the box-per-step decision. Interactive spec session 2026-07-21.

**Decision:** `brush build <shape>` returns a **single `Brush`** (one actor), for **all** multi-brush
builders (staircase, spiral, and any future one) — no per-shape exception. The CLI already emits one
actor when the builder returns a single `Brush` (`dispatch.py:2678`); the change is builder-side.
The single-brush form is the **UED-faithful non-convex outer hull** (base + back + per-step
tread/riser + tiled per-step convex side strips — essentially the pre-2026-07-18 `LinearStairBuilder`
replica), KEEPING the 2026-07-18 floor-anchoring (first tread at `z=rise`, whole solid at/above the
floor). Faces stay **convex** (tiled side strips, not one non-convex stepped side face — a non-convex
FPoly builds wrong in CSG), so `check_convex` still holds; the cost is **T-junctions** where the tiled
strips meet the tread/riser/base edges.

**Coupled decision (same spec, per Andrzej — "one spec"):** make `level doctor`'s `watertight` check
**T-junction-aware** so those T-junctions are not false-flagged as "open edge" holes. Only the
`watertight` check is affected — the other five (`degenerate`, `convex`, `solidity`, `csg_order`,
`scale`) are orthogonal to T-junctions and unchanged. Algorithm: replace the exact-corner-pair edge
matching with **per-edge-line interval parity** — group directed edges by their supporting line, and
require every covered sub-interval of that line to carry exactly one forward + one backward directed
edge. A T-junction (long edge `P→Q` opposed by a collinear chain `P→M→Q`) then balances and is silent;
a genuine hole (net-nonzero coverage), a back-wound face (two same-direction over a sub-interval), and
a non-manifold overlap (>2) still trip. This SUBSUMES the current three branches.

**Scope note — real T-junction *crack* detection stays deferred.** `doctor.py:9-12` documents the
static validator as T-junction-naive by design, with build-emergent T-junction *cracks* deferred to
the Phase-2 offline BSP engine (`to-build.md` #7). This decision only stops the static check from
**false-flagging a closed-but-T-junctioned brush**; it does not add crack detection.

**Rejected / accepted trade-offs:**
- *Keep box-per-step (the 2026-07-18 form)* — **rejected** by Andrzej: he wants one actor. The
  2026-07-18 rationale (clean convex boxes, zero doctor findings) is preserved differently — convex
  faces remain, and the doctor noise is fixed at the validator instead of by decomposition.
- *Per-step actor grouping is a real loss* — **rejected as a concern**: per-poly targeting
  (`brush poly find` / `poly set BRUSH:idx` / `poly align`) works on one brush regardless of brush
  count, so individual treads/faces stay addressable; only per-step *separate actors* go away, which
  is not wanted for a staircase.
- *Single non-convex stepped side FACE (no tiling)* — **rejected**: a non-convex FPoly is a genuine
  CSG defect (`check_convex` is correct to flag it). Tiled convex strips + T-junctions is the only
  clean single-brush realization.
- *Suppress watertight on builder-tagged brushes* — **rejected** in favour of the principled
  interval-parity fix, which also helps hand-authored non-convex brushes and needs no provenance
  marker.
- *Two coupled specs (builder + doctor) with a separate spike* — **rejected** by Andrzej: one spec.
  The interval-parity algorithm's correctness risk (must still catch real holes) is handled inside
  the one spec via regression tests over both real T-junctions and a real open edge.

**Fidelity note:** byte-identity is trunk-relative (native build must match UED's build of whatever is
in the trunk), so the builder's single-brush-vs-multi-box choice is free w.r.t. the parity bar. The
frozen builder-parity goldens (`stair_*`, `spiral_3`/`spiral_4` in `fixtures/builder_parity.json`)
must be **re-blessed** to the new single-brush output; axis-aligned integer staircase coords re-bless
offline (same basis as `cube_*`), the rotated spiral may need live-editor confirmation (flag in spec).
Also folds in the `[implement]` "spiral staircase builder is broken/wonky" backlog item (the redo to
proper wedge treads + central column is the spiral's single-brush geometry).

Spec: `specs/2026-07-21-brush-build-single-actor.md`.

## 2026-07-21 12:22 UTC — Addendum to the 12:06 single-brush decision: native-convex caveat + spiral split (post-review-gate)

Refines (does not supersede) the 2026-07-21 12:06 UTC entry after its two-reviewer gate.

**Native CSG core assumes convex brushes — caveat, not a blocker.** `uedcli-native/src/csg.rs:60`
`point_in_convex` classifies a point as inside iff it is behind EVERY face (the convex hull), and the
comment at `csg.rs:61` ("DX brush builders emit convex brushes, so this is exact") is now **falsified**
for builder output — a single non-convex staircase brush's concave notches classify as solid, so it
mis-builds on the native paths (`level preview --native`, native `level materialize`). This is
**confined and acceptable**: the DEFAULT `level materialize` drives UnrealEd (which builds this
non-convex brush natively — it is `LinearStairBuilder`'s own output) and the DEFAULT `level preview
--game` renders in the real engine, both correct. Only the native/experimental paths mis-build it,
joining the already-documented ~11% native solidity divergence (`architecture.md:1141`). **Follow-up
board item:** decompose non-convex brushes into convex pieces on the native CSG path (or guard+warn).
Validation of the single-brush builder uses the `brush preview` WIREFRAME renderer (`preview.py`,
convex-agnostic), NOT `level preview --native`.

**Spiral split out of the single-brush spec.** The 12:06 direction ("all multi-brush builders emit
one brush") stands, but the SPIRAL gets its own `[spec]`/`[spike]` rather than riding the staircase
change: it is net-new geometry (wedge treads + central column), carries the undiagnosed 2026-07-21
mirrored-V defect, its rotated non-axis-planar faces raise a CSG-validity question entangled with the
native-convex caveat above, and its parity golden is live-editor-gated. The staircase + the
`doctor` T-junction-aware watertight rework ship together (offline-verifiable); the spiral follows
separately. Spec `specs/2026-07-21-brush-build-single-actor.md` (staircase+doctor only).

**Doctor B2 branch precedence (correctness).** The interval-parity watertight classification is
order-sensitive: non-manifold (`f+b>2`) and same-direction back-wound (`2/0`) must be tested BEFORE
the net-flow "open edge" catch, else a back-wound face is mislabeled "open edge" (would break
`test_doctor.py:86`). The tolerant line-canonicalization key + epsilon is pinned by regression, and
the anti-masking test must include a real open edge whose supporting line coincides with a healthy
seam (the only case interval-parity can wrongly mask).

## 2026-07-21 13:42 UTC — Brush-cluster confirmations (Andrzej): unified `--from-t3d`, preview knobs, spiral split

Confirms/settles the open calls on the two 2026-07-21 brush specs.

**Spiral split — CONFIRMED.** The spiral single-brush redo stays its own `[spec]`/`[spike]`; the
staircase + `doctor` T-junction rework ship together. ("all builders → one brush" direction unchanged.)

**Unified T3D input idiom `--from-t3d <FILE…|->` (cross-verb).** One flag for T3D input on any
consuming verb: one-or-more T3D files, or `-` for a snippet on stdin. Replaces `brush preview`'s
draft `--from-t3d` (which had collided with `stash capture`) AND **migrates `stash capture`** off its
`--from-t3d FILE` + `--from-stdin` pair onto the same single flag (drops `--from-stdin` — a small
breaking change, accepted for consistency). Rules: mutually exclusive with the name source (present ⇒
T3D mode); `-` is the sole value if present (no stdin+file mix); multiple files concatenate in order.
**Supersedes the deferred `[spec]` "`stash capture -` (stdin)"** backlog item (this is that capability,
unified). *Rejected: a bespoke boolean stdin switch per verb (the draft `--from-t3d` bool / mirroring
`--from-stdin`) — inconsistent across siblings.*

**`brush preview` knobs:**
- `--zoom-poly` is **`BRUSH:idx` selector-only** — the bare-int "first brush" form is DROPPED (clean
  break), reusing `surface.parse_poly_selector`; frames exactly one poly (multi/`:all` → error).
- `--zoom-poly` **no longer highlights** — it frames only; highlighting is `--highlight-poly`
  (repeatable, set form) exclusively. (`highlight` renderer param becomes an `(actor-name, poly-idx)`
  collection, un-pinned from actor 0.)
- **`--zoom-factor <n>` added** — a zoom-tightness knob for a target: `0` = target at natural size in
  the whole-set frame, `1` = tightest framing keeping the target fully in view, interpolated between;
  modulates `--zoom-poly`/`--zoom-region`, no-op without a target.
- **bbox→`--zoom-region` bridge DROPPED** — auto-framing + `--zoom-poly` + `--zoom-factor` cover it;
  the different-set framing case was niche/unmotivated, and `--field region` would have overloaded
  `actor bbox --field`.

**One-actor build calls confirmed:** remove the now-dead multi-actor dispatch branch
(`dispatch.py:2671`); drop `stair_*` from the LIVE (editor-driven) parity suite (keep the offline
value goldens; the DEINTERSECTION capture can't reconstruct a non-convex cavity — the editor invents
interior vertices).

Specs: `specs/2026-07-21-brush-build-single-actor.md`, `specs/2026-07-21-brush-preview-ergonomics.md`.

## 2026-07-21 14:17 UTC — `brush preview` §4/§5 finalization: UED brush palette + `--zoom-factor` default

Settles the last two `brush preview` calls (spec `specs/2026-07-21-brush-preview-ergonomics.md`).

**`--zoom-factor` default = 0.8** (Andrzej). `0` = target at natural size in the whole-set frame, `1`
= tightest framing keeping the target fully in view; default `0.8` = mostly-tight-but-not-flush.
No-op without a zoom target.

**CSG-op wire colors = UnrealEd's brush-color legend** (Andrzej-provided reference, 2026-07-21).
Color the preview wireframe by full brush classification: **Subtracted = yellow/gold, Added(solid) =
blue, Semi-solid = pink, Non-solid = green, Mover = magenta/purple**; **red is reserved for the
`--highlight-poly` highlight** (consistent with UED, whose *builder* brush is red). Each hue needs a
front/back shade pair (preview encodes facing by shade) and luminance adapted for uedcli's WHITE
preview background (UED's viewport is grey/black — keep hue, adjust luminance). Durable home for the
UED hue fact = `dev/docs/unrealed/rendering.md` (add with an evidence marker citing the legend) +
a pinned RGB regression, when §4 is built. *Rejected: guessing hues, or copying UED's grey-viewport
bytes literally onto a white bg.*

## 2026-07-21 14:34 UTC — `brush preview` highlight = brush's own hue emphasized, not red

Supersedes the "red reserved for highlight" point of the 14:17 entry (Andrzej). `--highlight-poly`
draws the target in **its brush's own CSG hue, emphasized** — so a highlighted poly still reads as its
CSG type. **Realization:** max-saturation same hue + a **bolder line weight**, NOT literally
"brighter" — on uedcli's WHITE preview background lightening moves a hue toward white (loses contrast)
and collides with the front/back facing-shade axis; saturation + line weight is orthogonal and works
on white. Requires a line-weight param in `preview.py` (`_line` highlights by color only today).
**Red is now FREED** — no longer a reserved color (UED's red is its builder brush, not rendered here).
*Rejected: red highlight (loses CSG-type identity on the highlighted poly); literal "brighter" (wrong
operator on a white bg).*

## 2026-07-21 16:41 UTC — `brush preview` → `actor preview`: rename + point-actor rendering + `--show-collision`

New spec `specs/2026-07-21-actor-preview.md`; extends the ergonomics spec (same verb).

**Rename `brush preview` → `actor preview` (clean, no alias).** The verb renders any actor (point
actors too), so it moves from the `brush` group to the `actor` group. `stash preview`/`prefab preview`
keep their names and inherit the new rendering via the shared `_render_actors_to_out`. The ergonomics
spec's features (`--from-t3d`, `--zoom-poly`, `--highlight-poly`, CSG coloring, `--zoom-factor`) are
now on `actor preview`; the two specs build together. *Rejected: keeping a `brush preview` alias
(pre-1.0 internal tool — clean break).*

**Render point (non-brush) actors.** The renderer stops skipping non-brush actors (`preview.py:236`).
Branch on `DrawType` (resolved instance-or-class-default): **DT_Sprite → the real sprite** (effective
`Texture`, decoded via `utexture`, billboard quad at `Location` scaled by `DrawScale`); **DT_Mesh /
DT_None → a small labeled marker** (true mesh rendering deferred to the class-screenshot / in-engine
path). Point actors contribute to framing/bbox. Poly selectors (`--zoom-poly`/`--highlight-poly`) and
CSG coloring don't apply to point actors (no polys / no `CsgOper`) — a selector naming one is a clean
error. Sprite decode is P8-only today (fails cleanly on non-P8, per the tracked non-P8-decoder item).

**`--show-collision` — global boolean, faint red collision cylinders.** Draws a faint red cylinder
(radius `CollisionRadius`, half-height `CollisionHeight`, centered on `Location`, axis-aligned) for
every previewed actor with a cylinder (`CollisionRadius`/`Height > 0`). **Chosen over a per-name
`--show-actor-cylinder <NAME>`**: the previewed SET already selects which actors are in frame, so to
see one actor's cylinder, preview that one actor — a per-name flag re-states "operate on this actor",
the per-item-filter anti-pattern the CLI conventions reject (cf. `actor bbox` has no `--union`). Red
is free (the highlight moved to the brush's own hue, 2026-07-21 14:34). *Rejected: per-name flag;
"both".*

## 2026-07-21 17:10 UTC — `actor preview` review-gate resolution + range overlays

Folded the two-cold-reviewer findings into `specs/2026-07-21-actor-preview.md`: the real point-actor
filter is `_brush_actors_from` (`dispatch.py:434`) — relax it AND `preview.py:236`, leave the CSG/bbox
filters (354/564/623) alone; field resolution (`DrawType`/`DrawScale`/`Collision*`) happens in DISPATCH
via the `_class_defaults` seam + a `TextureResolver`, passed into `preview.py` via an extended
render-signature (new render-data dataclass); brush-only preview stays schema-free and a point actor
degrades to an unscaled marker (never `SchemaError` to the user); CSG-op coloring is gated off point
actors (`_csg_oper` defaults them to `CSG_Add`); the UED collision/DrawScale facts are cited from
`kb/actors-collision-pathing.md` + `rendering.md` (SHOW_ActorRadii: circle-top / rect-side / cylinder-
perspective). Sprite source + `DrawScale`→world-size need a spike.

**Range overlays (Andrzej):** `--show-sound-range` / `--show-light-range` join the `--show-*` family
(same shared-surface boolean pattern as `--show-collision`) — faint spheres from `SoundRadius` /
`LightRadius`. Both are 0–255 bytes needing a world-unit conversion that must be pinned by spike/web-
research first; shipped as a follow-on within the same spec after `--show-collision`.

## 2026-07-21 17:40 UTC — `actor preview` sprite/radii facts pinned (spike resolved, source-exact)

The spike gating `actor preview`'s sprite + range overlays is RESOLVED from the UE1 v200 retail source
(same lineage as Deus Ex): `spikes/2026-07-21-unrealed-sprite-radii-rendering.md`. Pinned facts:
- **Sprite:** a `DT_Sprite` actor draws its **`Texture`** prop (default `S_Actor`), world footprint
  `DrawScale·USize × DrawScale·VSize` — **1 texel = 1 UU at DrawScale 1**, billboarded on `Location`.
- **Radius→world:** `WorldLightRadius = 25·(LightRadius+1)`, `WorldSoundRadius = 25·(SoundRadius+1)`
  (bytes 0–255; the `+1` is real — `LightRadius=0` reaches 25 UU, not 0). The "×27/float" figure is
  UE2, discarded.
- **Collision:** `CollisionHeight` is a HALF-height (box = 2×); cylinder upright regardless of rotation;
  circle-top / rect-side / 8-sided-wire-cylinder-perspective (the last added in UnrealEd 2.x, which DX
  ships). UED default colors: collision + light = dark red, sound = dark blue.
- **Overlay colors:** keep collision=red, sound=blue (UED-faithful); deviate light-range to a distinct
  hue since UED's red would collide with the collision toggle. Exact faint RGBs picked at build.
These become `test_engine_facts` regressions when built (`25·(x+1)`, half-height, 1-texel-per-UU).

## 2026-07-21 18:10 UTC — brush-cluster same-page confirmations (Andrzej)

Ratified three calls I'd made (specs unchanged, now confirmed): **CSG-op coloring is the full six-way**
UED legend (add/subtract/semisolid/nonsolid/mover), not just add-vs-subtract; **`--show-collision`
draws only for actually-colliding actors** (gate on `bCollideActors`, UED-faithful — a no-collision
Light draws nothing), not literally every non-brush actor; **`actor preview --from-t3d` is
all-or-nothing** (renders the whole snippet; no name-subset, unlike `stash capture` where names subset
the source). Also confirmed heads-ups: the single-brush staircase is a SOLID filled wedge (UED
`LinearStairBuilder` union), and spec C's sprite path is heavy (new bitmap-blit + masked decode +
render-API change).

## 2026-07-22 05:29 UTC — `actor preview` labels enum + unified `--highlight`

Two coupled ergonomics changes on the shared `_preview_opts` (so `actor`/`stash`/`prefab preview`
all get them), replacing two narrower flags. Clean renames, **no aliases** — the old spellings are
gone (`--highlight-poly` errors as an unrecognized argument; `--no-label` no longer exists).

- **`--labels {none,all,highlighted}`** (default `all`) **replaces the boolean `--no-label`.** A
  three-way mode is worth more than a single omit-toggle: `all` keeps today's behaviour (a poly-index
  label on every viewer-facing face + a name label on every point actor), `none` = the old
  `--no-label`, and the new `highlighted` mode labels **only** the `--highlight` targets — the common
  "show me just the face/actor I care about, unlabelled everything else" case. Threaded into the
  renderers as a `labels: str` mode, replacing their `label: bool`. *Rejected:* keeping `--no-label`
  and bolting on a separate `--label-highlighted-only` — two booleans for one three-state choice.
- **`--highlight POLY|NAME`** (repeatable) **replaces `--highlight-poly BRUSH:IDX`**, unifying poly
  and actor highlighting under one flag **disambiguated by the colon**: a token WITH `:` is a poly
  selector (`Wall:2`, `Wall:1,2`, `Wall:all`) exactly as before; a token WITHOUT `:` is an actor
  name (case-insensitive, resolved against the previewed set — unknown → clean exit 2). A **brush**
  named bare highlights **all** its polys (whole-brush highlight, filling the poly set so it lights
  up for free through the existing poly path); a **point actor** named bare gets a **solid white
  spotlight disc** drawn UNDER its sprite/marker (the sprite's transparency then sits in the halo; a
  bare marker's grey diamond pops on the white). Dispatch resolves into two sets — `highlight_polys`
  (`(name, idx)` pairs) and `highlight_points` (names) — via the renamed `_resolve_highlights`.
  *Rejected:* a separate `--highlight-actor` flag (the colon already disambiguates cleanly, and one
  flag composes better); reusing red for the point spotlight (white reads as a spotlight and never
  collides with a CSG hue — red is UED's builder-brush colour we deliberately don't use).

## 2026-07-22 06:21 UTC — point-actor highlight: corner brackets, not a spotlight disc

The bare-name point-actor highlight (`--highlight <name>`) is drawn as **corner brackets — a
selection reticle framing the actor from outside** — via `_draw_selection_brackets`, **not** the
solid white spotlight disc of the 2026-07-22 05:29 UTC entry (which this **supersedes** on that one
point; the rest of that entry — the colon disambiguation, the two resolved sets, the whole-brush
poly-fill path — stands).

The disc was the wrong shape: a filled **circle/disc collides with the tool's radius vocabulary**
(`--show-light-range`/`--show-sound-range` draw circles, and the top-view collision cylinder renders
as a circle), and a **rectangle is the side-view collision cylinder** — so a selection mark can be
neither a circle nor a rectangle without reading as one of those overlays. **Corner brackets frame
the sprite/marker from OUTSIDE**: they mark the actor as selected without obscuring the sprite and
without colliding with any radius/cylinder shape. *Rejected:* the spotlight disc (shape collision,
and it sat a fill under a transparent sprite); a full box/ring outline (reads as a
collision/range shape).

## 2026-07-22 08:28 UTC — spiral staircase: wedge treads + central column, monotonic helix

`builders.spiral_staircase` is redone from rotated rectangular slab boxes into a real spiral stair.

**Decision:** it returns a `list[Brush]` of `steps + 1` convex brushes — `[column, wedge_0, …]`:
- a **central column** — one `cylinder` (radius `inner_radius`, `SPIRAL_COLUMN_SIDES=16` facets)
  spanning the stair's full height with its base at z=0, filling the axis all the way up;
- one **wedge (pie-slice) tread** per step — a convex 6-face prism (top + bottom trapezoid, inner +
  outer chord, two radial sides), footprint radially `inner_radius → inner_radius+step_width` with
  STRAIGHT chords over an angular span `degrees_per_step`, extruded `rise` thick over
  `z ∈ [k·rise, (k+1)·rise]`, rotated `k·degrees_per_step` about Z (the world origin / column axis).

Consecutive treads climb exactly one `rise` (tread top `k` at `(k+1)·rise`), so the tops ascend
**strictly monotonically** — a single helix. `--at` anchors the base of the column axis (everything
is in one local frame, column base at z=0). Each wedge passes `validate_brush`: rotation about Z is
orientation-preserving and keeps every face planar (trapezoids at constant z; verticals are 2-point
extrusions), so winding stays outward and no face goes off-plane after grid-snap. The parity goldens
`spiral_3`/`spiral_4` are regenerated for the new geometry and moved to `OFFLINE_ONLY` (blessed from
the builder, dropped from the LIVE capture suite) — the rotated wedge coords are not axis-aligned
integers, so the DEINTERSECTION capture invents vertices on them, the same regime as `stair_*`.
Byte-identity is trunk-relative, so this does not affect native parity.

**Context:** the old builder emitted rotated rectangular slabs (planks) around an empty hole: they
did not tessellate (gaps + a central hole), tangential size was a mid-radius chord, and a >180° turn
of slabs read in FRONT/SIDE as a mirrored-V (ascending then descending) rather than a climbing
helix. It also had no central column. Split out of the one-actor `brush build` spec (2026-07-21)
into its own redo because it is net-new geometry with rotated-non-axis-planar faces.

**Rejected:** a single non-convex brush carrying the whole spiral (the staircase's one-brush
direction) — rotated wedges + a column overlap, and the native CSG core assumes convex brushes
(`csg.rs`), so a per-brush convex list keeps every piece valid on both the editor and native paths;
arc (curved) inner/outer tread edges — straight chords keep the footprint a convex trapezoid that
validates trivially and mates cleanly with adjacent treads; live-capturing the wedge goldens — the
non-axis-aligned coords make the editor invent interior vertices (same as `stair_*`), so the offline
builder-sourced golden is the honest change-detector.

**Refs:** `builders.py` `spiral_staircase`; `tests/test_builders.py`, `tests/test_generators.py`,
`tests/builder_parity_cases.py` (`OFFLINE_ONLY`), `fixtures/builder_parity.json`;
board `to-spec.md` "Spiral staircase builder" `[spec/spike]` (now done).


## 2026-07-22 09:54 UTC — granular `--labels` grammar + density-aware label placement

The `actor preview` renderer's single `--labels {none,all,highlighted}` switch (which coupled every
label kind and scope) is replaced by a composable grammar, and label placement becomes geometry-aware.

**Decision (grammar):** `--labels` takes a comma-separated **union** of selectors `KIND[:FILTER…]`.
The model is **orthogonal**: a **bare kind means ALL of that kind** (`poly` = every face front+back,
`name` = every name brush+point); each **filter narrows**; **multiple filters on one selector
intersect** (`poly:vis:hi` = front-facing AND highlighted); **commas union** (`poly:vis,poly:hi` =
front-facing OR highlighted). Kinds `poly` / `name`; poly filters `vis` (**front-facing** — the cheap
backface cull, NOT occlusion) and `hi` (highlighted); name filters `brush`/`point` (sub-kind) and `hi`
(`highlighted` accepted as a synonym). Filters are an order-independent set; tokens are
whitespace-stripped + lower-cased. Whole-value keywords `none` / `all` (= `poly,name`, the maximal
set — every face incl. back) / `highlighted` (= `poly:hi,name:hi`). Zero effective tokens ⇒ `none`.
**Default** (flag omitted) = the ordinary value `poly:vis,poly:hi,name` (front-facing OR highlighted
faces + all names) — reproduces today's poly labeling exactly (`front or is_hi`), no special default
path. Brush-name labels are net-new (only point actors had name labels before), so any value covering
brush names — the default and `highlighted` included — now draws them. Parsed into a frozen
`LabelSpec` holding, per kind, the **set of element categories** that get a label
(`poly: frozenset[(is_front, is_highlighted)]`, `name: frozenset[(is_brush, is_highlighted)]`) with
`draws_poly`/`draws_name` predicates — so union/intersection is plain set algebra. Parsed in dispatch
so a bad value is a clean named error, not a traceback.

**Decision (`vis` = front-facing; occlusion decoupled):** `vis` selects front-facing faces
(`_is_front`, already computed) — the honest "visible" in a see-through wireframe — and **ships now,
nothing rejected at parse**. TRUE occlusion (don't label a face hidden behind geometry) is an
**optional future refinement** (a z-buffer/painter pass), decoupled from this grammar; tracked in
`board/inbox.md` `[implement] p3`. (Superseded the earlier same-session draft that had `vis` =
occlusion, rejected-at-parse, and bare `poly` = `front OR highlighted`.)

**Decision (placement):** labels are placed by **cost minimization over a coarse geometry occupancy
grid** (`DensityGrid`), not first-fit ring search. Cost = `k1·avg_geometry_density_under_box +
k2·label_overlap + k3·(leader_len/cell)`, all terms normalized to comparable ranges. `k3` weighted
high = a **moderate drift cap** (labels hug their anchor, drifting into clear space only when
crowded). Labels are NOT stamped into the density grid (k2 owns label-vs-label; no double-count).
Placement order is deterministic (crowded anchors first, stable tiebreak). All three label kinds
(poly indices, brush names, point names) route through the one pass, so point names now de-collide
too. A brush's name-anchor snaps to the nearest projected point on its own wireframe, so a concave/
hollow brush's dot lands on geometry, not in the hollow.

**Context:** raised by Andrzej mid-`actor preview` polish — wanting "brush names but not polys"-style
control and clearer label→target association ("put labels OUTSIDE areas that overlap multiple polys,
or where other actors are nearby"). A brush counts as highlighted for `name:brush:hi` iff any of its
polys is in `highlight_polys` (there is no separate brush-level highlight set).

**Rejected:** a comma-set of *kinds* plus a separate `--label-scope {all,highlighted}` flag (Andrzej
picked one flag carrying scope via `hi` filters — a raster preview is a non-composable sink, so
folding everything into one `--labels` token keeps the union expressible without a second flag); one
boolean flag per kind (`--poly-labels`/`--brush-name-labels`/…, four flags where one lived); scoped
tokens with a `:hi` grammar were the chosen shape over both. For placement: **peripheral/margin
callout layout** (labels docked in frame gutters with inward leaders — long crossing leaders in busy
scenes, big layout change); **wider ring search only** (still blind to geometry, doesn't put labels
outside overlap knots). Brush-name anchor as the raw vertex centroid (lands in the hollow of a concave
brush — the density minimizer would keep it in the void with a leader pointing at nothing). Earlier
same-session draft model (bare `poly` = `front OR highlighted`; `vis` = occlusion rejected-at-parse;
`LabelSpec` as `is_shown`/`highlighted_only` sub-specs) — superseded by the orthogonal bare-kind-is-all
model above.

**Refs:** spec `specs/2026-07-22-labels-granularity.md`; `preview.py` (`LabelSpec`, `parse_label_spec`,
`DensityGrid`, `_place_labels`, `render_brushes_pgm`); `cli.py:136` `--labels`; `dispatch.py:504/509`;
board `inbox.md` `[implement] p3` true-occlusion filter.

## 2026-07-22 20:49 UTC — Actor `label` dimension (flat, multi-valued, uedcli-side); preview `--labels`→`--annotate`

**Context.** `folder` (2026-07-18 12:14) gives a *single hierarchical path* per actor — good for "where
does this live," useless for cross-cutting concerns (a torch is `castle.tower` AND `lighting` AND
`interactive` at once). Andrzej wanted a second, *multi-valued* axis, and to use it as the referencing
handle for `actor duplicate` (whose copies otherwise carry only unpredictable random Names on stdout).
Interactive spec session 2026-07-22; spec `specs/2026-07-22-actor-labels.md`.

**Decision (Andrzej).**
1. **A new `label` dimension:** a flat, **multi-valued** set of tokens per actor, uedcli-side (a
   per-actor `labels` sidecar beside `order_value`/`folder`), **never emitted to the built map**, and
   **orthogonal** to `folder`, the engine `Group` prop, and the engine `Tag` prop. The Gmail/GitHub
   "labels" model. `Actor.labels: frozenset[str]`.
2. **Named `label`, not `tag`.** "tag" collides with the real `Engine.Actor.Tag` property (matched via
   `find --prop Tag=`) — the same overload `folder` was invented to avoid with `Group`. The word
   "label" was freed by **renaming `actor preview`'s on-image-annotation flag `--labels` → `--annotate`**
   (done: `cli.py:137`, `dispatch.py:487`) — this **supersedes the `--labels` flag-name** of the
   2026-07-22 labels-granularity entry above (the annotation *feature* is unchanged; only the flag
   spelling moved, and its internals `parse_label_spec`/`DEFAULT_LABELS`/`LabelSpec` stay label-named
   pending a follow-up rename to `annotation*`).
3. **`duplicate` stamps inherit + one fresh batch label (a UNION).** Each copy inherits its source's
   labels AND every copy in the batch gets one shared freshly-minted `dup-<rand>` label (re-rolled
   collision-free vs existing tree labels), so `find --label dup-<rand>` re-addresses exactly the batch
   *after* the pipeline ends. `duplicate --label NAME` names the batch explicitly instead (still a
   union with inherited labels — NOT the override that `actor add --label` uses). `duplicate` also gains
   `--by`/`--at` placement so copies don't silently overlap their originals.

**Rejected.**
- *Overloading `folder` with multi-membership* — turns a clean tree into a tag-set and makes "folder"
  lie; every folder op (`set`/`unset`/`find`/rename) goes ambiguous. Multi-membership is its own
  dimension.
- *Naming it `tag`* — collides with `Engine.Actor.Tag` (`find --prop Tag=`). Also weighed `keyword`,
  `mark`, `badge`; `label` won once freed.
- *Renaming preview `--labels` as a deferred separate step* (to avoid touching the in-flight
  labels-granularity work) — Andrzej did the flag rename now to take the best word immediately.
- *`duplicate --label` as an override (like `actor add --label`)* — would wipe the inherited labels the
  headline guarantee preserves; duplicate is a union.

**Open sub-choices (in the spec §11, NOT yet decided):** the `add`/`remove`/`set`/`clear`/`get` grammar
(actors-positional + `--label`-flag recommended; whether `set` earns its place; `--label` reuse across
find/mutate); `[`-class support in a `--label` pattern; whether `--by`/`--at` land in this spec or a
placement follow-up; whether the label surfaces accept `--tree stash|prefab` (recommended yes — the
sidecar exists there post-unify — unlike the possibly-stale folder guard).

**Refs:** spec `specs/2026-07-22-actor-labels.md` (revised after two cold review passes — the critical
find was the delta-write diff `dispatch.py:1446-1449`, which must gain a `labels` clause or every label
mutation silently no-ops); sibling `specs/2026-07-18-actor-folders-hierarchical.md`; `model.py` (`Actor`
field + `parse_t3d` carrier), `t3dtree.py`, `labellib.py` (new), `stashlib.py`/`stash_register.py` (the
cross-tree `labels` channel).

## 2026-07-23 05:58 UTC — Resolve the actor-`label` sub-choices (grammar, no `set`, `--tree`, patterns)

Settles the sub-choices the 2026-07-22 20:49 entry / spec `specs/2026-07-22-actor-labels.md` §11 left
open. **Decisions (Andrzej):**
1. **Grammar:** the `actor label` mutation verbs take actors positional (or `-` from stdin) and label
   values behind a **repeatable `--label`** flag — mirrors `actor folder set --to <path> <names>` (value
   is a flag, actors are the name-set) so `-` universally means "actors from stdin."
2. **No `set` sub-verb:** `add`/`remove`/`clear`/`get` only. Replace-all is `clear`+`add` (derivable) —
   dropped for a leaner surface.
3. **Mutation flag spelled `--label`**, the same token as the `find --label` filter (NOT a distinct
   `--to`-style flag). Same meaning "a label," different verb.
4. **`--by`/`--at` duplicate placement stays in the actor-labels spec** (one coherent duplicate overhaul),
   not a separate follow-up.
5. **Label surfaces ALLOW `--tree stash|prefab`** — the per-actor sidecar slot exists in stash/prefab
   post-unify (2026-07-18 23:01), so a label set/query on a box is meaningful. This does NOT reuse the
   folder guard `_reject_nonlevel_target_for_folders`, whose trunk-only premise ("flat boxes, no sidecar
   slot") is now **stale** — re-evaluating/dropping that folder guard is a separate board item.
6. **`[abc]` character-class in a `--label` pattern is supported** (free fnmatch), documented in the help.
   (Folders reject `[` via `validate_pattern`; labels are flat, so they don't.)

**Rejected:** labels positional + actors-`-`-only (breaks the mutating-verb-family convention, awkward
inline actors); keeping `set`; a distinct `--to`-style mutation flag; deferring `--by`/`--at`; rejecting
`--tree stash|prefab` to match the (stale) folder guard.

**Refs:** spec `specs/2026-07-22-actor-labels.md` (§4/§5/§7/§10/§11); board `inbox.md` "re-evaluate
`_reject_nonlevel_target_for_folders`".

## 2026-07-24 08:31 UTC — `actor duplicate` ALWAYS mints `dup-<rand>`; `--label` is purely additive

**Refines** the 2026-07-22 20:49 entry's point 3 ("`duplicate --label NAME` names the batch *instead*"),
which implied an explicit `--label` REPLACED the auto token. **Decision (Andrzej):** `actor duplicate`
**always** stamps a fresh unique `dup-<rand>` label on the batch, regardless of `--label`; an explicit
`--label` is **additive** (unioned on top), never a replacement. So copies always carry `inherited ∪
{dup-<rand>} ∪ {explicit --label values}`. Rationale: the batch is *always* isolable by a guaranteed-
unique handle (no reliance on the user picking a collision-free name), and the "which flag names the
batch" ambiguity disappears. **Rejected:** `--label` replaces the auto token (the 20:49 wording) — it
left a bare-`--label` batch addressable only by a name that might already exist elsewhere.

**Also (same session):** `duplicate --at X,Y,Z` anchors the duplicated SET's **bbox-min corner** at the
point (the `_apply_set`/`writes.union_bounds` contract), not each actor's `Origin` — uniform delta,
relative layout preserved; `--by` is the pure relative delta with no anchor ambiguity. (Origin-anchor
alternative flagged in spec §7.2, not chosen.) A bare in-place duplicate (no `--by`/`--at`) stays a
WARNING, not an error — overlap-then-move/retexture is a valid workflow and the copies are always
addressable via stdout Names + the `dup-<rand>` label.

**Refs:** spec `specs/2026-07-22-actor-labels.md` §7.1/§7.2/§12.

## 2026-07-24 08:40 UTC — `--label` patterns drop char-class; `*`-only, matching folder

**Supersedes** point 6 of the 2026-07-23 05:58 entry ("`[abc]` char-class supported"). **Decision
(Andrzej):** `actor find --label` patterns support a `*` wildcard ONLY and **reject** `?` and `[`/`]`
(clean exit 2), mirroring `folderlib.validate_pattern`'s conservative stance. Removes the
`--label`-vs-`--folder` pattern-syntax asymmetry the cold reviews flagged — both now allow `*` (folder
additionally `**`) and reject the rest. Ref: spec `specs/2026-07-22-actor-labels.md` §5.

## 2026-07-24 10:02 UTC — `actor duplicate` REQUIRES `--by` or `--at` (no same-location default)

**Supersedes** the 2026-07-24 08:31 entry's "a bare in-place duplicate stays a WARNING, not an error."
**Decision (Andrzej):** `actor duplicate` **requires exactly one of `--by`/`--at`** (a required
mutually-exclusive argparse group); a bare `duplicate <names>` with no placement is a clean **exit 2**
(`duplicate requires --by or --at`). This eliminates accidental invisible overlapping copies. The
**explicit-overlap escape hatch is `--by 0,0,0`** (a deliberate zero delta), preserving the
duplicate-in-place-then-compute-a-move workflow by making the overlap intentional. The old
same-location default and its stacked-point overlap warning are removed from `duplicate`. Ref: spec
`specs/2026-07-22-actor-labels.md` §7.2/§11.4/§12.

## 2026-07-24 10:02 UTC — Composable `find` sub-choices: `--exclude`, keep `find -`, strict unknowns

Resolves the `specs/2026-07-24-composable-find.md` §7 open sub-choices. **Decisions (Andrzej):**
the negation flag is spelled **`--exclude`** (not `-v`/`--invert`/`--not`); the no-filter **`find -`**
identity/validator form is **kept** (base of the union re-normalization `… | sort -u | find -`); and
an unknown piped name is a **strict all-or-nothing exit 2** (matching every other `-` verb). The
**grep/universe model** (`-` = the universe, filters = predicate, `--exclude` negates) is adopted for
the whole spec — *Andrzej asked what it is and is confirming; recorded as the working model.* Ref:
spec `specs/2026-07-24-composable-find.md` §2/§3.1/§7.

## 2026-07-22 21:18 UTC — `actor preview --split`: deterministic non-shadowing number groups

On-face poly numbers go ambiguous where two number decals overlap on screen (a near face's
number lands over a far face's region). **`--split` renders a one-view FILMSTRIP that partitions
the rendered numbers into groups whose decals never overlap**, so each pane's numbers are each
unambiguously on their own face. It is a *superset* of the normal render: no collisions ⇒ one
pane identical to the default; it splits only where numbers actually collide.

- **Conflict = rendered NUMBER-DECAL overlap (padded), NOT face overlap.** The load-bearing
  choice. Two faces can overlap hugely in projection while their small centered numbers never
  touch; keying on face overlap over-splits massively (spike: cube+cylinder 16 faces → 4 groups
  on face-overlap vs **1** on decal-overlap). Only faces whose number is ACTUALLY rendered (passes
  the `--annotate` filters AND the world-size gate) participate — an unrendered number has nothing
  to disambiguate.
- **Welsh-Powell greedy coloring**, highest-overlap-degree first, ties broken by the actor's
  **name** + poly index (a stable identity, NOT the input-list position — greedy coloring is
  order-sensitive, so keying on caller order would make the partition depend on it). Deterministic:
  a given number always lands in the same group regardless of input order. Welsh-Powell is a
  *heuristic* (near-minimal in practice, not provably optimal — pane count is not canonical).
  *Rejected* naive input-order greedy (more groups, and input-order-dependent).
- **Filmstrip of ONE view** (`--split` uses `--view`; it is inherently single-view, so it ignores
  the 2×2 quad). *Rejected* N separate image files (flip-between friction) and an interleaved
  single image (doesn't actually disambiguate).
- **Per-perspective** — a split is valid only for the view it was computed in.
- Within a pane the numbers keep their **normal depth-graded opacity**; the split only decides
  WHICH pane each number appears in. *Rejected* forcing full opacity per pane (loses the
  front/back cue).

**Refs:** spike `spikes/poly-split-groups/` (harness + findings; decal-overlap group counts pinned
there), spec `specs/2026-07-22-preview-split-groups.md`.

## 2026-07-23 00:00 UTC — `--split` groups are LOAD-BALANCED, not first-pane-packed

Refines the `--split` grouping (2026-07-22 21:18 UTC). The greedy coloring keeps its Welsh-Powell
node order + name-based tie-break, but the **color pick** changed: a node takes the **least-populated
group it is allowed to join**, not the lowest-index one. A new group still opens only when every
existing group conflicts, so the **pane count stays near-minimal** — almost always identical to the
lowest-index packing, though balancing can *rarely* add one pane (seeding an early node into an
otherwise-empty group can force a later node to open another; ~0.015% of random graphs, both greedy
heuristics). The faces are spread evenly (`[30,9,3]` → `[14,14,14]`, room+pillar `[8,4]` → `[6,6]`). *Rejected* the original
lowest-index pick: it dumps every non-colliding number into pane 0 and leaves later panes with 1-3
numbers each, which reads worse (a near-empty pane looks like the tool gave up, and pane 0 stays as
crowded as the un-split view). Determinism is preserved (visitation order + count-then-index tie-break
are input-order-independent). Andrzej asked for this after seeing the lopsided real-Hexagon splits.

## 2026-07-23 06:01 UTC — preview legend: reserve room + draw once per filmstrip; `--brush-colors`

Three preview refinements Andrzej asked for after the `--split` work:

- **Reserve room for the legend so it overlaps nothing.** The legend used to draw OVER the top-left
  wireframe (it only reserved space for label *placement*, not the geometry). Now the legend rows are
  measured before framing and `_framing` insets the geometry below a reserved top band
  (`_legend_reserve` → `inset_top`), so the panel overlaps nothing. *Chosen* a full-width **top band**
  (simplest guarantee; a narrow legend wastes a little top-right space) over insetting only a
  left column or growing the canvas. The band is **capped to `size/3`** (`_LEGEND_BAND_DIV`,
  `_fit_legend_rows`): a tall legend collapses its overflow into `+N MORE` instead of reserving the
  whole frame and crushing/inverting the geometry (a real regression the cold-review gate caught — a
  40-row legend drove the draw budget to 4px, negative at some sizes).
- **Legend renders ONCE per `--split` filmstrip.** Split the old single `draw_legend` into two flags:
  `reserve_legend` (inset the band) vs `draw_legend` (paint the panel). Every split pane reserves (so
  the geometry stays registered across panes) but only the first paints. *Rejected* drawing it in every
  pane (the previous behavior — repetitive) and drawing it in a separate prepended strip (more code;
  the reserve-in-all-panes approach reuses the existing panel path). `split_groups` applies the same
  `inset_top` so its grouped bboxes still match the painted panes.
- **`--brush-colors {csg,legend}`** (default `csg`). Lets the wireframe be coloured by each brush's
  per-actor legend tint instead of the CSG op — distinct colour per brush, matching the legend
  swatches, at the cost of the CSG cue. *Rejected* making `legend` the default (the CSG cue is the more
  useful default; this is opt-in). On-face number size left **as-is** (Andrzej's call — it is
  proportional to face size by design; a lone number on a narrow face stays small, accepted).

## 2026-07-23 10:00 UTC — replace `--split` with `--breakdown`; `--zoom-poly` → `--zoom`

`--split` (the non-shadowing number-group filmstrip, 2026-07-22 21:18 / 2026-07-23 00:00) is
**replaced** by **`--breakdown`**, a different multi-pane filmstrip: pane 0 is the whole scene in CSG
colour with NO on-face numbers + a **name-only legend** (the roster — every brush AND point actor, so
no name escapes); each subsequent pane is one BRUSH, rendered with `--focus <name>` + zoomed to that
brush (`--zoom <name>`), all its faces numbered, the brush name captioned at the top. Point actors get
**no pane of their own** — they are named in the overview legend and shown as their marker there.

Why the swap: `--split` fought hard (graph-coloring, load-balancing) to make many small overlapping
numbers legible in ONE frame; `--breakdown` sidesteps the overlap by giving each brush its own big,
zoomed, isolated shot — simpler and more legible, and the overview doubles as a table of contents.
*Rejected* keeping both (two multi-pane modes = redundant surface). `--split` and its group-coloring
code (`split_groups`/`_group_decals`/`_boxes_overlap`/`_SPLIT_*`) and the `render_brushes_pgm`
`only_polys` gate (added only for split panes) are **removed**; `_scene_geometry`/`_framing`/
`reserve_legend`/`brush_colors` stay. The `spikes/poly-split-groups/` spike is superseded (kept as
history; its decal-overlap finding no longer drives a shipped feature).

**`--zoom-poly` → `--zoom`** (clean rename, old name removed): `--zoom` now accepts a bare brush
**NAME** (frames that brush's whole AABB — what `--breakdown` uses per pane) OR `BRUSH:idx` (frames one
poly, the prior behaviour). *Rejected* keeping `--zoom-poly` as a deprecated alias — an LLM-facing tool
with a small footprint, so a clean rename beats carrying two names.

**Refs:** prototype `_scratch/split_build/breakdown/`; supersedes the two `--split` entries above.

## 2026-07-23 12:22 UTC — `--breakdown` is a near-square GRID, not a horizontal filmstrip

`--breakdown` (2026-07-23 10:00 UTC) initially stitched its panes into a single horizontal row; it now
lays them into a **near-square grid** (`ceil(sqrt(N))` columns) — a 1×7 strip is ~2200 px wide and
awkward, a 3×3 grid is viewable. Each pane stays a **square cell**.

*Rejected* **variable-span tiles** (a tall brush → a 1×2 cell, a wide brush → 2×1, matching its
projected aspect). Two reasons: (1) it needs rectangular pane rendering, but `preview.py` is
square-only (every buffer/primitive uses one `size` as width AND stride) — a real refactor of ~12
primitives + `_framing`; (2) it rarely triggers in the DEFAULT `iso` view, which spreads geometry so
even thin pillars project to only ~1.75:1 — extreme aspect mostly appears in `front`/`side`/`top`.
Low frequency × high cost ⇒ not worth it now (Andrzej's call, after a prototype showed iso aspects are
near-square). A bigger-square-tile approximation (extreme brush → 2×2) was also rejected — more room
but doesn't match tall-vs-wide, so it buys little over a uniform grid. If rectangular rendering lands
for another reason, revisit. *(dispatch `_render_breakdown_grid`; prototype `_scratch/split_build/grid/`)*

## 2026-07-23 12:43 UTC — on-face numbers: largest-inscribed-box placement at 75%; harder focus dim

Two preview-legibility changes (Andrzej):

- **Placement + size of the on-face number decal.** It was CENTERED on the face and sized to `_ONFACE_FILL`
  = **0.2** of the face's UV *bounding box* — small, and on a non-rectangular face it could overhang
  (the bbox exceeds the polygon). Now `_max_inscribed_box` finds the LARGEST glyph-aspect box that fits
  fully **inside the face polygon** and WHERE it sits (off-centre on a triangle/arch/L), and the decal
  is drawn at `_ONFACE_FILL` = **0.75** of that maximum. Numbers are ~3-4× bigger and never overhang.
  This SUPERSEDES the "keep decal size as-is" note in the 2026-07-23 06:01 UTC entry — a better model,
  not just a knob.
  *Faces are treated as possibly-concave*: convex (the norm) solve exactly by half-plane erosion;
  concave fall back to a bounded grid search. Convexity is NOT a hard invariant — arbitrary UnrealEd
  vertex editing can make a face concave, and 0.1–0.6% of faces in real exported maps are (measured
  `spikes/concave-faces/`, 2026-07-23). *Rejected* assuming convex (would place a decal in a concave
  notch / outside). Aspect is the number's OWN glyph aspect (so `12` sizes/places differently from `1`).
  The world-size omit rule stays, now keyed to the drawn (0.75×max) size.
- **`--focus`/`--breakdown` dim harder.** Non-focused brushes fade 0.6→**0.85** toward background, so
  the faint context no longer reads THROUGH the (translucent) focused numbers. *Rejected* changing the
  focused decals' own opacity — the fix belongs on the context, not the annotation.

**Refs:** `preview.py` `_max_inscribed_box`/`_poly_convex_2d`/`_box_fits_2d`/`_plan_onface_texture`,
`_fade(amount=)`; pinned by `test_max_inscribed_box_*`/`_box_fits_2d_*` (the box-stays-inside invariant).

## 2026-07-23 13:13 UTC — on-face numbers omit by ON-SCREEN readability; opacity 0.70/0.6

Two tweaks (Andrzej):

- **Omit is now a view-DEPENDENT, on-screen verdict.** A number is dropped when its projected glyph
  texels fall below `_ONFACE_MIN_TEXEL_PX` (=2 px), not when the face is below a world-uu size. So a
  face too small, too EDGE-ON to the camera, or too zoomed-out to read gets no number, and the SAME face
  is numbered once it's big enough on screen (zoomed in, or in its own `--breakdown` pane). This
  SUPERSEDES the world-uu, view-independent rule (2026-07-22, `_ONFACE_MIN_CELL_WORLD`; and the
  12:43 UTC entry's "world-size omit rule stays" line — its "keyed to the drawn 0.75×max" half
  survives, since the projected check keys off `cell = 0.75·max_cell`). *Rejected* the
  old world-size rule: "legible" should mean readable on THIS frame, and world-uu both drew illegible
  numbers on big-but-tiny-on-screen / edge-on faces and omitted small faces you'd zoomed into. The
  trade-off accepted: numbering varies across views/zoom (a crowded overview stays clean, detail panes
  reveal everything) — which pairs naturally with `--breakdown`.
- **Opacity grading 0.90·0.5ⁿ → 0.70·0.6ⁿ** (`_decal_opacity`, floor 0.15 kept): a visible face is 0.70
  (was 0.90), each occluding layer retains 60% (was 50%). Softer front, gentler falloff. The
  `_draw_painted_decal` default alpha followed 0.9→0.7.

**Refs:** `preview.py` `_plan_onface_texture` (projected-texel omit), `_decal_opacity`,
`_ONFACE_MIN_TEXEL_PX`; tests `test_onface_omit_is_view_dependent_on_projected_scale`,
`test_plan_onface_texture_omit_is_on_screen_size_based_and_view_dependent`, `test_decal_opacity_*`.

## 2026-07-23 13:26 UTC — dim non-focused brushes by COMPOSITING, not fade-to-bg + opaque paint

`--focus`/`--breakdown` dimmed a non-focused brush by fading its wireframe colour ~0.85 toward the
background and painting it OPAQUELY. Over the plain background that reads as low opacity, but where a
dimmed edge CROSSED another brush's edge or a painted number it HARD-OVERWROTE it with the pale colour
— the faint brush visibly "overlaid"/covered what it crossed (Andrzej spotted this on a semisolid
pillar). Now dimming draws the brush's TRUE colour COMPOSITED at `_DIM_ALPHA` (=0.15) via
`_line(alpha=…)` → `_blend_px`, so crossed edges/numbers show THROUGH the faint wireframe. Over the bg
the look is unchanged (0.15·colour + 0.85·bg == the old `_fade(0.85)`), so it's purely a crossing fix.
*Rejected* keeping the fade (opaque paint is wrong at any crossing). `_line`'s opaque path (alpha=1) is
byte-identical to before (full golden suite unchanged). `_fade` stays for the `brush_colors=legend`
back-face shade (a colour choice, not dimming).

**Refs:** `preview.py` `_line(alpha=)`, `_DIM_ALPHA`, `_scene_geometry` edge-alpha; test
`test_line_dim_alpha_composites_over_content_instead_of_overwriting`.

## 2026-07-23 15:22 UTC — on-face number decals reposition to avoid screen overlap

On-face poly-index numbers were planned INDEPENDENTLY (each at its face's roomiest spot,
`_plan_onface_texture`), so two faces projecting close together on screen — including two faces of the
SAME brush, which `--breakdown` does NOT separate — piled their numbers on top of each other. Now an
always-on, deterministic pass repositions each number WITHIN ITS OWN FACE to reduce screen overlap
with other numbers AND point-actor markers. `_onface_candidates` generates per-face placements
(candidate 0 = today's placement FIRST; then a size ladder from `_ONFACE_FILL·max` down by ×0.8 to the
`_ONFACE_MIN_TEXEL_PX` floor, several `_feasible_centers` per box, and — on HORIZONTAL faces only — a
90°-rotated glyph); `_resolve_decals` picks greedily, biggest-first, keeping candidate 0 verbatim when
its overlap is within tolerance (see below) else preferring the largest within-tolerance box, then the
earliest candidate, only minimising overlap when nothing fits within tolerance. Levers, per Andrzej:
MOVE (slide, still 0.75 size), ROTATE 90° (only floor/ceiling/cap faces — a wall number hangs by
gravity and must not read sideways; his refinement), SHRINK to the readability floor (below it → omit).
The move→shrink→(cap-)rotate preference is EMERGENT from the sort key, not a staged ladder. Three more
choices Andrzej pinned: (1) every placement keeps candidate 0's `_ONFACE_FILL` edge padding
(≈16.666%/side) — `_feasible_centers` clears the PADDED box (`cell/fill`), so a slid/shrunk number is
never flush; (2) a `_DECAL_OVERLAP_TOLERANCE` = 20% of a decal's own area is left alone (small overlaps
read fine, and it keeps the guard a broad no-op → goldens stable); (3) overlap is SUMMED PER obstacle
(`_rect_overlap_area`), so N decals stacked on one patch count N× — a reviewer had flagged this
"double-count" as a possible bug, but it is the intended semantics (dense pile-ups are worse). Overlap
set = numbers + point-actor MARKER footprints (the legend owns a reserved band decals never reach;
legacy point NAMES already flee decals via `occupied`); the 20% tolerance applies uniformly to markers
too (provisional — "up to 20% between decals" read as a general small-overlap allowance).

*Rejected:* a global optimiser (ILP) — greedy + the readability gate is enough and stays
deterministic/stdlib; three fixed size steps `{0.75,0.60,0.45}` — never reached the view-dependent
floor, so "shrink to separate" would under-deliver (superseded by the geometric ladder before build);
rotate on walls/slopes — sideways gravity text is unreadable; rotate/upsize a within-tolerance or
omitted-today face — violates "reposition only to reduce overlap" and would churn goldens; per-face
shrink without move, and cross-face moves — out of scope. Always-on (no flag): the guard makes it a
strict no-op when overlap is within tolerance.

**Refs:** `preview.py` `_onface_candidates`, `_resolve_decals`, `_feasible_centers`, `_erode_convex`,
`_rotate_bitmap_90`, `_is_horizontal_face`, `_decal_plan_at`, `_plan_px_area`, `_rect_overlap_area`,
`_overlap_fraction`, `_DECAL_OVERLAP_TOLERANCE`; tests
`test_onface_candidate*`/`test_resolve_decals_*`/`test_feasible_centers_*`/`test_rotate_bitmap_90_*`;
spec `specs/2026-07-23-decal-anti-overlap.md`.

## 2026-07-23 16:03 UTC — cap the anti-overlap shrink at 60% of full size

Follow-up to the 15:22 UTC anti-overlap resolver. In practice the resolver shrank numbers on crowded
faces (adjacent cylinder side-faces, whose numbers project onto each other) ALL THE WAY to the ~2px
readability floor: when no candidate reached the 20% tolerance, the cost minimised overlap, and the
smallest number overlaps least, so it traded a big number for a tiny clear one — leaving the face
visibly empty around a speck (Andrzej: "why didn't we draw a bigger red 20? there's room on the right").
Root cause: at full size a number has no in-face slide room (the max box is edge-tangent), so the only
overlap lever on a wall (no rotation) is shrinking. Fix: a `_DECAL_ANTIOVERLAP_MIN_SCALE` = 0.60 LINEAR
floor — a number never shrinks below 60% of its full size just to dodge overlap; below that it stays
bigger and accepts the overlap. And, per Andrzej, when nothing fits within both the floor AND the 20%
tolerance, pick the LEAST-overlap candidate among those at/above the floor (then largest) — leaning to
separation while staying big. (The readability-floor OMIT for genuinely tiny faces is unchanged — that
is candidate 0 being None, separate from this anti-overlap shrink floor.)

*Rejected:* floor at 40% (still too small — a big number could drop to ~5px); floor at 75% (barely
shrinks, keeps too much overlap); "biggest, accept overlap" as the tie (Andrzej chose least-overlap
among the allowed sizes instead). The 60%/least-overlap combo is his pick.

**Refs:** `preview.py` `_resolve_decals`, `_DECAL_ANTIOVERLAP_MIN_SCALE`; tests
`test_resolve_decals_shrinks_to_reduce_overlap_when_no_full_size_spot_is_free`,
`test_resolve_decals_will_not_shrink_below_the_floor_just_to_clear_overlap`.

## 2026-07-23 19:05 UTC — decal overlap: minimal reshuffle + white keyline + lower opacity (supersedes the elaborate resolver)

Supersedes the anti-overlap resolver of the two 2026-07-23 entries above (20%-tolerance / 60%-shrink-floor
/ cap-rotation / proportional shrink). After looking at it on real geometry, Andrzej wanted the
repositioning kept TRULY MINIMAL and legibility carried by an outline instead:

- **Minimal reshuffle.** On overlap a number may shrink at most `_DECAL_MAX_SHRINK` = 10% (linear) and
  move at most `_DECAL_MAX_MOVE_FRAC` = 10% of its own screen diagonal, picking the least-overlap
  placement within that budget; a zero-overlap number never moves. Candidates are only near-full
  (`_RESHUFFLE_SCALES` = 0.975…0.90). Removed: the deep size ladder, the 90° cap-rotation
  (`_is_horizontal_face`/`_rotate_bitmap_90` deleted), the 20% tolerance, the 60% floor, the
  proportional-severity budget.
- **Overlap keyline** (`_draw_overlap_keyline`). Where two numbers overlap on screen, draw a **constant
  1-screen-pixel WHITE ring just OUTSIDE the strokes** (4-neighbour dilation of the `on` set minus the
  set, near the overlap). Constant-width because it's drawn OUTSIDE the glyph, not on its boundary — so
  it never fills a thin stroke and never thickens with zoom (the earlier "interior-edge" idea failed:
  for a small number the 1px boundary spans the whole ~2px stroke and reads as bold; verified). WHITE
  chosen over dark after A/B on the light palette + reduced opacity — Andrzej's pick, accepting that
  it's subtle (its strength is the zoomed `--breakdown` panes, the default view).
- **Opacity down ~20%.** `_decal_opacity` base 0.70→0.56, floor 0.15→0.12 (falloff 0.6/layer unchanged).
- **`--breakdown` is the default preview** (per-brush grid): each brush alone in a zoomed pane, so
  cross-brush overlap vanishes and only same-brush overlap remains for the keyline. Recorded as a
  working preference; the CLI flag itself is unchanged.

*Rejected (this round):* dark keyline (loses to white per Andrzej, though dark reads stronger on this
palette); keyline only on the overlap-region boundary / interior edge (fills thin strokes); a larger
reshuffle budget (Andrzej wanted numbers to stay put and let the outline do the work). The
`specs/2026-07-23-decal-anti-overlap.md` spec is now largely historical — this entry is the live design.

**Refs:** `preview.py` `_resolve_decals`, `_onface_candidates`, `_draw_overlap_keyline`,
`_draw_painted_decal` (returns `on`), `_decal_opacity`, constants `_DECAL_MAX_SHRINK`/
`_DECAL_MAX_MOVE_FRAC`/`_RESHUFFLE_SCALES`/`_KEYLINE_RGB`; tests `test_onface_candidates_*`/
`test_resolve_decals_*`/`test_draw_overlap_keyline_*`/`test_decal_opacity_*`.

## 2026-07-23 20:03 UTC — size on-face numbers in a fixed 2-digit slot (single digits scale like double)

On-face numbers were sized to the largest box of the ACTUAL glyph's aspect, so a single digit (aspect
3×7, narrow-tall) sized differently from a two-digit number (7×7) on the same face — lone digits could
balloon. Now `_text_bitmap` widens any number to a fixed `_DECAL_SLOT_DIGITS` = 2 wide SLOT and centres
the actual digits in it (extra slot columns blank; underline spans the DIGITS, not the slot). So the
search/sizing (`_max_inscribed_box`, candidates) always uses the 2-digit aspect and a `5` renders at the
same scale as `12` — a neater, size-consistent look across a scene (Andrzej's call). Numbers with more
digits than the slot use their own width (the slot is a MINIMUM). `slot_digits` is a `_text_bitmap`
kwarg so a caller can opt out.

*Rejected:* slot = max digit-count across the whole scene (most consistent but needs all numbers upfront
+ more coupling; fixed 2 is simpler and covers the 0–99 common case); full-slot-width underline (looks
like the lone digit floats; underline-under-digit reads as a normal underlined number).

**Refs:** `preview.py` `_text_bitmap(slot_digits=)`, `_DECAL_SLOT_DIGITS`; test
`test_text_bitmap_centres_a_short_number_in_a_two_digit_slot`.

## 2026-07-23 20:14 UTC — breakdown SCENE overview: paint actor NAMES on-face (not just a legend)

The `--breakdown` scene overview (pane 0) labelled brushes only via the side legend (a name→tint
roster). Now it ALSO paints each brush's NAME directly on one of its own faces, so the overview is
self-labelling — you read a brush's name off the brush, not by matching a tint swatch. `_place_onface_names`
plans the name (`_plan_onface_texture`) on every FRONT face of each brush, keeps the legible ones (a face
must be big enough to read the whole name, else it's skipped), and greedily — biggest-name brush first —
picks the face with the LEAST overlap against point-actor markers + names already placed, preferring the
largest. Names paint in the brush tint at 0.9 opacity with the white overlap keyline. The legend STAYS as
a fallback (names too big to fit any face; point actors). Wired via a new `render_brushes_pgm(onface_names=)`
flag that the SCENE pane passes True.

*Rejected:* dropping the legend entirely (names that fit no face would vanish — keep it as a fallback);
leader-box names on geometry (the legacy style — a painted-on-face name reads as belonging to the brush,
like the poly numbers, and needs no leader clutter); shrinking a name to force-fit a small face (would be
illegible — better to skip and let the legend carry it).

**Refs:** `preview.py` `_place_onface_names`, `render_brushes_pgm(onface_names=)`;
`dispatch._render_breakdown_grid` SCENE pane; test `test_onface_names_paints_actor_names_in_the_scene_overview`.

## 2026-07-24 05:27 UTC — breakdown: ditch the legend, label every brush on-face, minimal 16px pad

Refines the on-face-names overview (2026-07-23 20:14). Andrzej: the `--breakdown` panes should ditch the
legend and keep padding minimal. So: (1) NO legend anywhere in the breakdown — the SCENE pane
self-labels with on-face names, per-brush panes are captioned. (2) With the legend gone as a fallback,
name placement drops its readability floor (`_plan_onface_texture(min_texel_px=0)` in `_place_onface_names`):
EVERY brush with a visible front face is labelled, even if small — a silent gap is worse than a squint,
and the per-brush panes carry legibility. (3) Every pane frames its geometry with a minimal, CONSISTENT
`_BREAKDOWN_PAD` = 16 px border (new `render_brushes_pgm(frame_pad=)` → `_framing(pad=)`), replacing the
old per-brush 16-*uu* world margin (`_BREAKDOWN_MARGIN`, removed) — so padding is the same screen size
regardless of brush size.

*Known gap:* point actors have no faces to paint a name on and no pane, so with the legend gone they are
now UNLABELLED in the breakdown (marker only). Flagged in `board/inbox.md` for Andrzej.

**Refs:** `preview.py` `_framing(pad=)`, `render_brushes_pgm(frame_pad=)`, `_place_onface_names`
(min_texel_px=0); `dispatch._render_breakdown_grid` (no legend, `_BREAKDOWN_PAD`); test
`test_it_draws_no_legend_panel_in_any_breakdown_pane`.

## 2026-07-24 06:43 UTC — breakdown SCENE overview is label-free (removed on-face names)

Andrzej: ditch brush names from the breakdown overview. So the SCENE pane is now a PLAIN CSG map with NO
labels — no legend (removed 05:27), no on-face names, no numbers (`parse_label_spec("none")`); brushes
are identified from their own captioned per-brush panes. The on-face-actor-name machinery added earlier
today (`_place_onface_names`, `render_brushes_pgm(onface_names=)`, the SCENE `onface_names=True`) is
REMOVED as now-unused (git keeps it if ever wanted). Supersedes the 2026-07-23 20:14 on-face-names
decision and its 05:27 refinement's name parts (the 16px `_BREAKDOWN_PAD` framing and legend removal from
05:27 STAND). The 05:27 point-actor-labelling inbox item is moot (nothing is named in the overview now)
and pruned.

**Refs:** `dispatch._render_breakdown_grid` (SCENE pane `labels="none"`); `preview.render_brushes_pgm`
(no `onface_names`), `_place_onface_names` deleted.

## 2026-07-24 16:27 UTC — `--facing` becomes component predicates on the visible normal (pose-grammar delimiters)

Replaces `brush poly find --facing`'s single geometric axis token (`+X|-X|+Y|-Y|+Z|-Z|slant`,
`query._poly_facing`) with a predicate grammar over the face's **visible unit normal** `(nx,ny,nz)`. The
old token had three defects: world-frame-dependent (which map direction `+X` is, is a per-map accident),
zero flexibility (6 axes + `slant`, nothing between), and — the real bug — **polarity-blind**: rooms are
`CSG_Subtract` brushes whose playable faces point OPPOSITE the geometric outward normal, so `--facing +Z`
returned a subtract room's ceiling, not its floor.

**Grammar** (single param): `--facing 'TERM[;TERM…]'`, `TERM = PRESET | AXIS:SPEC`, `AXIS ∈ nx|ny|nz`,
`SPEC = v | lo..hi | v[,v…]`. Reuses the batched **pose grammar** delimiters (`preview_shots.py:81`):
`;` = AND across terms, `:` = axis:spec (pose key:value), `,` = OR value/range list on one axis (pose
component list), `..` = range; a bare `v` means "near v within ε". One delimiter language across the CLI;
`;` needs shell quoting (same as `preview` shots). **Visible normal** = Newell outward normal (verified
CCW-from-outside winding, `t3d.md:145`) flipped for `CSG_Subtract` (via `query._csg_oper`).

**Presets** by polarity-INVARIANT surface-plane orientation (no floor/ceiling confusion): `flat`=`nz:-1,1`
(horizontal, floor or ceiling), `wall`=`nz:0` (vertical, axis-aligned AND diagonal), `ramp`=`|nz|:ε..1-ε`
(sloped). Plus polarity-AWARE refinements `floor`=`nz:1` / `ceiling`=`nz:-1` (the up/down playable
surface; these alone depend on the subtract flip). Az∩el is one param via `;`-AND (`'nz:0;ny:0.7..1'` =
north wall) — no chaining.

*Polarity flip — verified, pin it:* both cold reviews independently computed the top face of
`tests/fixtures/brush_subtract.t3d` (Newell `nz>0` → outward `+Z`, verts at `Z=+192` = room ceiling → visible
`−Z` = `ceiling`), so the flip is established from in-tree evidence; the deliverable is the committed
engine-facts regression re-asserting it (+ a `t3d.md` fact). *Symmetry (corrected):* the flip negates ALL
three components, so only predicates invariant under full negation — `wall` (`nz:0`), `flat` (`nz:-1,1`),
symmetric bands — are flip-independent. EVERY asymmetric predicate (`nx:1`, `nz:0.5`, az preds like
`ny:0.7..1`, and `floor`/`ceiling`) is flip-DEPENDENT and selects the opposite face on a subtract brush —
so the flip's correctness underpins all asymmetric queries, not just floor/ceiling (an earlier draft wrongly
scoped it to floor/ceiling only). *Transform (corrected):* `visible_normal` uses inverse-transpose of
`actor_linear` on the LOCAL outward normal (correct under rotation, non-uniform scale, shear, reflection),
unifying `list_polys` (was full-scale) and `find_faces` (was rotation-only).

*Rejected, in the order they were tried and dropped (all recorded because each was Andrzej's explicit
call):* (a) a parallel `--orientation` flag — two flags filtering the same dimension, overlap/confusion,
kept it one flag. (b) An **FRotator** value — a facing is a 2-DOF direction, not a 3-DOF orientation (roll
meaningless); UU (65536/turn) is the LEAST readable option; and a rotator converts to a vector internally
anyway. (c) An **elevation scalar** — collapses to one number, discards azimuth = "doesn't solve
versatility." (d) A **single exact scalar** (`nz` value: floor=1/wall=0/ceiling=-1) — clean but drops
azimuth AND can't express `ramp` (an in-between band, not one value). (e) A **spherical box** of
independent `yaw`+`pitch` ranges — the only model doing "the north wall" in one expression, but `yaw=0` is
an arbitrary per-map origin (the exact "+X is meaningless" flaw relocated to yaw); pitch has a canonical
zero from gravity, yaw does not. (f) **Asterisk/wildcard** vectors (`*,*,0` for wall) — cover only 3 of 4
presets (`ramp` is an annular band no wildcard expresses) and smuggle a second matching model into the
flag. (g) **comma = AND** to avoid shell-quoting — diverges from the pose grammar's comma-is-component and
breaks the natural `nz:-1,1` OR; `;`=AND matches the existing grammar and is worth the quoting (already
required by `preview`). (h) **separate floor/ceiling as the default** — role names flip with CSG polarity
(a subtract's floor is an add's ceiling geometrically), so the confusing distinction was demoted under the
polarity-free `flat` umbrella.

**Refs:** spec `specs/2026-07-24-facing-selector-grammar.md`; `query._poly_facing`/`_csg_oper`,
`polyalign.find_faces`, `dispatch.py:3468` `poly find` handler, `cli.py:981` `pfind`; delimiter precedent
`preview_shots.py:81`.

## 2026-07-24 16:28 UTC — `brush poly find` takes a brush SET (`nargs`/`-`), warns (not errors) on non-brushes

`brush poly find` gains the "verb over a set" shape of its siblings: the brush positional becomes `nargs="+"`
(matching `poly set` — NOT `"*"`, which would make a forgotten brush arg a silent no-op), so it searches many
brushes at once, and `-` reads the set from stdin (bare names or the `BRUSH:idx` lines a prior `find` prints —
strip to the brush part), the sole names source, mutually exclusive with positionals; empty stdin is a clean
no-op (exit 0). Output stays `BRUSH:idx` lines, deduped by brush (first-seen order) so `find WALL WALL` never
double-emits, spanning the whole set.

Andrzej: a **non-brush** in the set (a point actor, no `.brush`) is a **warning, not an error** — print a
stderr note naming it and skip, but still succeed for the real brushes (contrast today's `find_faces`, which
raises on a non-brush target). An **unknown** name stays a hard exit-2 error — a typo must not pass silently.

**Refs:** spec `specs/2026-07-24-facing-selector-grammar.md` ("brush poly find set input"); `cli.py:981`
`pfind`, `dispatch.py:3468`, `polyalign.find_faces`.

## 2026-07-24 16:32 UTC — `intersect`/`deintersect` reframed: in-tree brush-SET merge with a uniform background (native, no editor)

`BRUSH FROM INTERSECTION`/`DEINTERSECTION` is reimplemented **natively** (no editor) and reframed to fit
uedcli's stateless model. UnrealEd's operation is `builder-brush ∩ world-solid` — it needs a live red
builder brush AND a surrounding carved room; neither exists in uedcli. **Andrzej's reframing (this
session):** the verbs operate on an **in-tree SET of brush actors** with a *uniform assumed background*,
no room, no builder:
- **`intersect`** — background **empty**. Evaluate the set's CSG on empty space (additives make solid,
  subtractives carve it); emit the resulting solid's boundary as ONE welded brush. Additive-dominant
  (errors "no additive brushes — use deintersect", mirroring today's editor impl).
- **`deintersect`** — background **full/solid** (UnrealEd's default world). The set's subtractives define
  voids; emit the void as a solid (the "negative"/plug, faces reversed) — the door-mover use case.
  Subtractive-dominant.

**Equivalent-in-SOLID to the existing editor impl** (`dispatch._stash_intersect_impl`/
`_stash_deintersect_impl`): editor intersect prepends a wrap-**subtract** cube to force an empty
background then `builder ∩ solid`; editor deintersect uses the default **solid** world (no wrap) then
`builder ∩ empty`. The wrap-cube + bbox-builder are non-semantic scaffolding (the wrap sets the background;
the builder is any box containing the set) — the *resulting solid* is provably the same, but the exact
*face set* is NOT asserted equal; it is validated against the editor differential oracle.

**Native mechanism (CORRECTED post-review — the first draft was wrong).** The verb does the editor's
operation FAITHFULLY, synthesizing the builder (padded-bbox) + background (wrap-subtract for intersect)
INTERNALLY and running the real decoded `builder ∩ world`. This fills the existing stub `bspcsg.rs:1845`
(`if oper != Add && != Subtract { return; // Intersect/Deintersect not used by MAP REBUILD }`) with the
decoded tail; its primitives are already ported (`bsp_filter_fpoly` `:710`, `filter_ed_poly` `:570`,
`filter_world_through_brush` `:834`). New Rust code = the tail driver + the four intersect/deintersect leaf
callbacks (decode §2) + a 4-way `CsgOper` on `filter_world_through_brush`. **The whole pipeline stays at
`root_outside=false`** (the ONLY validated polarity — the wrap-subtract gives intersect its empty background,
exactly as the editor does). **REJECTED alternative (first draft):** loop `bsp_brush_csg` with
`root_outside=true` then `bsp_build_fpolys`+reverse — wrong because (a) `bsp_build_fpolys` returns the fat
repartition SOUP (`bspcsg.rs:1330`), not the editor's clean boundary; (b) `root_outside=true` is unexercised
by the CSG path; (c) a blanket face reverse over-generalizes the decode (only the deintersect Phase-2 leaf
reverses). Ground truth:
`spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`.

**Flag rule (default = faithful to `bspBrushCSG` LOOP-1, `NotPolyFlags=(CsgOper==Add)?0:0x28`):** a result
face from an **additive** source keeps that brush's solidity (semisolid stays semisolid); a face from a
**subtractive** source is forced solid (`& ~0x28` — the engine forbids a semisolid/nonsolid subtract wall);
`--solid` forces the entire merged brush clean solid. Poly flags are decided at CSG time and baked into the
faces — independent of what the brush becomes next (mover/add/subtract); `BRUSH ADDMOVER` copies polys
verbatim (confirmed live, mover-flags experiment).

**Interface (refined 2026-07-24 in design iteration):** `brush intersect`/`brush deintersect` are
**generators taking a T3D brush set on STDIN** (`-`, the `build → add -` convention — NOT a name list; the
op is self-contained, needing only the set's geometry). Every tier feeds it via its `show` verb
(`actor show`/`stash show`/`prefab show`), so **the `stash`/`prefab`/editor `intersect`/`deintersect`
wrappers are DROPPED** as redundant (`stash show s1 | brush intersect -`). Output = one brush (or, with
`--mover-class`, mover) actor T3D → `actor add -`. Being generators, they **share `brush build`'s
`_common_build_opts` output flags** (`--csg` [resolves the CsgOper stamp; default `add`], `--solidity`
[replaces the bespoke `--solid`], `--mover-class` [door-plug→mover in one command], `--texture`, `--prop`,
`--rotate`, `--base-name`, `--folder`, `--label`) — see the generator-flag-cleanup entry below; NOT `--group`
(ditched) or `--at` (result Location is intrinsic).

**Rejected:** (a) the literal editor `builder ∩ world` approach (needs a room + stateful builder brush —
does not fit the stateless generator model); (b) strip-ALL-flags default (loses deliberately-authored
additive solidity); (c) preserve-ALL default (would keep impossible semisolid/nonsolid *subtract* walls,
diverging from the engine). **Refs:** spec `specs/2026-07-24-intersect-deintersect-native-brushset.md`; RE
`spikes/2026-07-15-native-materialize/re-raw-zones/bspbrushcsg-intersect-deintersect-decode.md`;
`dispatch.py:975` (editor oracle), `bspcsg.rs:1845` (the Intersect/Deintersect stub to fill),
`bspcsg.rs:710`/`:834` (ported filter primitives).

## 2026-07-24 16:48 UTC — `level import`: native (editor-less) `.dx`/`.unr` → T3D-tree ingestion

Add a `level import MAPFILE --tree KIND/NAME [--overwrite]` verb — the inverse of `level materialize`
— that turns a compiled map file into a queryable/diffable/remixable trunk (`--tree level/NAME`) or
stash (`--tree stash/NAME`). Spec `specs/2026-07-24-level-import.md`; promotes the `to-spec.md` "level
import" backlog item. The design is deliberately **decode-only new code**: the whole write half
(`model` → `emit.emit_map` → `t3dtree.write_actor_tree`, via the `LevelSource` seam) is the exact path
materialize builds *from*, reused unchanged.

**Decisions (Andrzej, this session):**

1. **Destination is the existing `--tree` seam, not bespoke `--level`/`--stash` flags** (Andrzej: "Why
   not `--tree`?"). KIND ∈ `{level, stash}` in v1; import CREATES the box, so a create-mode resolver
   (`_resolve_import_dest`) constructs a new `TrunkLevelSource`/stash entry and **refuses to overwrite
   an existing box** (exit 2 unless `--overwrite`, mirroring materialize's `--out` guard). A
   `prefab/…` destination is REJECTED in v1 — a whole retail level is not a natural prefab; the
   uniform seam makes it a trivial later add. *Rejected:* bespoke `--level`/`--stash` flags
   (redundant with `--tree`).

2. **Fidelity = equivalence to UnrealEd/UCC `MAP EXPORT` through the CANONICAL LENS, not raw
   byte-identity.** Differences with **zero functional effect** are explicitly allowed: T3D property
   ORDERING, whole-struct vs member-diffed struct values, a property omitted because it equals the
   class default, and every field `normalize.COMPUTED_PROPS`/`_COMPUTED_PREFIXES` already drops
   (computed BSP/lighting/nav). Enum NAMES (`CsgOper=CSG_Subtract`, not `3`) and all geometry MUST
   match. This leans entirely on the existing `normalize`/`canonical_level_hash` machinery — and is
   cheap because the binary's tagged-property list is ALREADY the class-default diff (UObject
   serialization omits default-equal props), so faithful tag rendering lands near-`MAP EXPORT` output
   for free with no property-level default-diffing to re-implement. *Rejected:* literal byte-identity
   to `MAP EXPORT` text (would force replicating member-precise struct default-diffing for no
   functional gain).

3. **Native decode; UCC/editor only as the TEST oracle.** The shipping path runs neither a live editor
   nor UCC — decode is `upackage` + the promoted spike decoders (`upolys_decode.py` FPoly; the
   `2026-06-26-uproperty-typed-decode` typed-value decode). `store_export.export_dx_t3d` (UCC
   `batchexport Level T3D`) is used ONLY in the validation harness. Acceptance bar (Andrzej: "compare
   outputs to editor-export for multiple OG Deus Ex levels"): a corpus of OG `.dx` where native import
   and `batchexport` yield the same canonical level; 1–2 small committed offline goldens + an
   `-m integration` sweep over more levels live, plus `decode∘encode==identity` round-trip pins
   against the production `write_fpoly`/`write_prop` encoders (engine-fact regressions).

4. **All actors imported verbatim** — `LevelInfo`, `ZoneInfo`, the builder `Brush0`, pathnodes,
   everything; `normalize` already strips their computed fields (reachspecs, `Region`). No class
   filtering in v1. *Rejected:* filtering engine/boilerplate actors on import (opinionated; the
   `find`/query verbs already let the user carve after ingest).

**Feasibility confirmed:** UnrealEd-built retail maps retain each brush actor's authored private
`UModel`→`UPolys`→`FPoly` (exactly what `MAP EXPORT` reads), so native import recovers `PolyList`s.
(The empty-private-Model note in `inbox.md` is about uedcli's OWN native BUILD diverging from
UnrealEd, NOT a property of retail maps.)

**Open (folds into the spec, resolve before build):** a `[spike]` on the authoritative actor ORDER
(the `Engine.Level` `Actors`-array layout vs raw export-table order matching `batchexport`); and
sub-choices on the builder `Brush0` (keep vs drop), printing imported names to stdout, and
unknown-struct handling. **Caveats to document:** embedded `myLevel` textures dangle (T3D can't carry
binary blobs — warn, follow-up to extract to `.utx`); imported actors start folder/label-empty.
**Refs:** spec `specs/2026-07-24-level-import.md`; `upackage.py` (reader), `native/actor_write.py`
(encode mirror), `native/umodel.py` (Model parse), `classindex.ClassIndex.descends_from`,
`store_export.export_dx_t3d` (oracle), spikes `2026-06-26-uproperty-typed-decode` +
`2026-06-27-decontainerize-uedcli/harness/upolys_decode.py`.

## 2026-07-24 16:59 UTC — `level import`: two cold reviews refine the fidelity/validation design

Two cold reviewers checked the 16:48 `level import` spec against the code and found the first draft's
fidelity/validation plan unbuildable as written. The core decisions (16:48 §§1–4) STAND; these are
refinements folded into `specs/2026-07-24-level-import.md`. The optimistic "matching `MAP EXPORT` is
free because the binary tag list is already the class-default diff" sub-claim (16:48 §2) is **wrong for
structs** and is corrected here.

1. **Struct member-diffing is required new code, not free.** The binary stores WHOLE structs
   (`StructProperty` carries all members; `native/actor_write.struct_rotator` writes Pitch/Yaw/Roll);
   `MAP EXPORT` emits only non-default members (`Rotation=(Yaw=…)`). NO struct-member canonicalization
   exists in `normalize`/`emit` (verified). So the decoder must member-diff structs against class
   defaults (`uprops`/`classindex`) on decode. *Rejected:* a struct-member normalize pass on both
   compare sides (bigger `normalize` signature change; decode-side diffing also cleans the trunk).

2. **The acceptance compare must reuse the existing offline verify machinery, both sides through ONE
   path.** The draft's `export_dx_t3d(...) |> parse_t3d` (a) left `level.order == []` so the
   order-folded `canonical_level_hash` could never match a populated native order, (b) skipped
   `normalize_level` (builder-brush drop + re-sort), and (c) compared BARE oracle class names against
   FQCN trunk names — mismatching every actor. Fix: oracle via `store_export.export_dx_level`
   (`level_order` + `normalize_level`), native side through the SAME normalization + offline
   `classindex` requalification — i.e. reuse `verify.verify_dx_matches`'s core. Store BARE class names
   (matches `batchexport` and `normalize.is_builder_brush`, which keys on bare `"Brush"`).

3. **Decode renders T3D TEXT and reuses `model.parse_t3d`, not straight-to-`model.Actor`.** `emit`
   re-emits `Location`/`MainScale`/`PostScale` only from TYPED fields, never from `props`, so decoding
   into `Actor.props` would drop location/scale. Rendering text + `parse_t3d` (the tested inverse of
   `emit_actor`) also routes the `Brush` ref and the folder/label carriers correctly.

4. **Three decode steps the draft understated, now explicit in the spec:** (a) an actor body begins
   with a `StateFrame` (RF_HasStack) that must be skipped before `read_property_tags` (invert
   `native/actor_write.state_frame`); (b) the "typed value decode" spike (`2026-06-26`) decodes
   UProperty DEFINITION bodies (schema), not serialized values — value decode is new, with a
   dynamic-array inner-type-from-schema step (no encode mirror) and a native-vs-script struct branch
   (script structs are nested tagged-property lists); (c) FQCN comes from
   `object_path(exports[i]["cls"])` (the class ref's path), poly `Item` must be decoded
   (`pkg.names[item_index]`), and the brush's private Polys ref is `parse_model_body(...).field_0x54`.

5. **Write path mirrors `_level_create`, not `LevelSource.save`** (which requires a prior `load()` of an
   existing box): `trunk.write_level` + `append_rank` per actor; overwrite-check BEFORE load; a
   name-collision guard (exit 2 naming the offender). **New caveat:** cross-actor object refs (mover
   `Base=`, `Owner=`, event refs) render with the source map's package stem and are NOT rebased by
   `canonicalize_self_refs` (only the 4 structural self-ref classes are) — symmetric for the compare,
   but the durable trunk stores stem-pinned refs; widening self-ref canonicalization is a follow-up.

**Refs:** spec `specs/2026-07-24-level-import.md` (`[R]` marks); evidence `normalize.py`
(`is_builder_brush` bare-keyed, `canonicalize_self_refs`/`_SELF_REF_CLASSES`, `canonical_level_hash`
folds `order`), `emit.py` (Location/scale/Class emit), `store_export.export_dx_level`,
`verify.verify_dx_matches`, `upackage.object_path`/`object_class_name`, `native/actor_write.py`
(`state_frame`, `struct_*`, `write_fpoly`, `write_upolys_body`), `native/assemble.py`
(`field_0x54`), `dispatch.py` (`_level_create`, `TrunkLevelSource.save` load-guard).

## 2026-07-24 17:04 UTC — generator-flag cleanup: `--folder`/`--label` move to the generators (OFF `actor add`); `--group` ditched

A cross-cutting CLI convention change to the T3D **generators**, decided in the intersect/deintersect design
iteration (the two verbs share `brush build`'s flag set, which forced the question "what IS that set").
**REVERSES** the earlier rule that folder/label flags live on `actor add`, not the generators (`direction.md`
Folders/Labels; decisions 2026-07-18 actor-folders, 2026-07-22 actor-labels) — `direction.md` reconciled.

**The change (three parts):**
1. **Add `--folder <path>` and `--label <l>` (repeatable) to every GENERATOR** — the `brush build` shapes
   (`_common_build_opts`, `cli.py:737`) and `actor build`. They emit the already-existing on-the-wire
   carriers `// uedcli-folder:` (`model._FOLDER_CARRIER`) / `// uedcli-labels:` (`labellib._LABELS_CARRIER`),
   which `actor add` already parses into the sidecars. So `brush build cube --folder castle.wall --label lit |
   actor add -` sets organization at creation.
2. **REMOVE `--folder`/`--label` from `actor add`** — it becomes a PURE carrier-consumer (persists whatever
   carriers ride the incoming T3D; no override flag). Post-hoc changes use the existing trunk verbs
   `actor folder set` / `actor label add|remove|set|clear`. (Rationale: a generator is the single place that
   *creates* an actor's identity incl. its organization; `actor add` just persists — no second setter.)
3. **Ditch `--group` from `brush build`** (`_common_build_opts`) → use `--prop Group=X`. `--group` was a plain
   `Engine.Actor.Group` Name prop with no abstraction, so it is redundant with `--prop` (unlike `--csg`/
   `--solidity`/`--texture`/`--rotate`, which each carry semantics beyond a raw prop and stay). `actor build`
   never had `--group` (already `--prop`).

**Consequence for `brush intersect`/`deintersect`:** they inherit the resulting generator common set
(`--csg`, `--solidity`, `--mover-class`, `--texture`, `--prop`, `--rotate`, `--base-name`, `--folder`,
`--label`; not `--group`, not `--at`-as-primary).

**Rejected:** (a) keep `--folder`/`--label` on BOTH generators and `actor add` (two setters + a precedence
rule to remember — Andrzej chose the single-setter model); (b) keep `--group` as a dedicated flag for
discoverability (loses to the "no dedicated flag for a plain `--prop`" minimalism); (c) brush-build-only
scope (leaves `actor build` half-converted — apply to all generators).

**Refs:** spec `specs/2026-07-24-intersect-deintersect-native-brushset.md` §2/§7b; `cli.py:737`
(`_common_build_opts`), `cli.py:455` (`actor build`), `cli.py:478` (`actor add`),
`model.py:44`/`labellib.py:29` (the carriers). Own board item (touches `brush build`/`actor build`/`actor
add`, its own review gate).

## 2026-07-24 17:19 UTC — `level import`: decode faithfully, do NOT member-diff structs (reconcile at compare)

Reverses the decode-side struct member-diff of the 16:59 UTC entry (§1). Andrzej: "the map file
doesn't even store the defaults, so no need to check if they match a default." Correct at the property
level — UObject tagged-property serialization OMITS any property equal to its class default, so the
decoder needs zero default-matching for whole properties; it emits exactly what is present. The only
residue is **native structs**, which UE1 serializes WHOLE (`native/actor_write.struct_rotator` packs
`<iii` unconditionally — a non-default `Rotation` carries `Pitch=0,Roll=0` in the file); `MAP EXPORT`
is what text-strips default members. (Script structs are already member-stripped in the binary — a
nested None-terminated tagged-property list — so they need nothing.)

**Decision:** the decoder does NOT member-diff — it decodes faithfully, storing whole native structs
(more faithful to what the map serialized; keeps the decoder default-free). The whole-vs-partial
difference is FUNCTIONALLY NULL (import re-fills the zeros onto the class default) and is reconciled at
COMPARE time by a small **symmetric** "drop default struct members" step added to the shared canonical
lens (§7), applied to BOTH the native and the `MAP EXPORT`-oracle side — idempotent, since the oracle
is already stripped. The **materialize round-trip** acceptance variant needs even that (materialize
re-serializes the whole struct to a byte-identical `FRotator`, so the intermediate text form is
invisible). *Rejected (the 16:59 choice):* member-diffing in the decoder against class defaults — more
per-actor decode logic, and it makes the trunk LESS faithful than the serialized source. **Refs:**
spec `specs/2026-07-24-level-import.md` §3.2/§5.2c/§7; `native/actor_write.struct_*` (whole-struct
encode), `normalize` (where the symmetric member-default drop lands).

## 2026-07-24 17:56 UTC — `intersect`/`deintersect` RE-CENTER the result so it is movable; `actor add` gets no positioning flag

The intersect/deintersect result must be **relocatable** (the whole point of the deintersect→mover door
flow: carve a plug, then place it / swing it elsewhere). A brush moves by `Location` and rotates about
`PrePivot` (`world = Location + R·(vert − PrePivot)`), so it is movable in principle — but UnrealEd's faithful
output has `Location=(0,0,0)` with **world-space verts**, putting its local origin at the world origin: "place
at X" needs a hand-computed offset and a `--mover-class` mover would rotate about the world origin, not the
door. **Decision (Andrzej):**
- **RE-CENTER on emit BY DEFAULT** — `Location = anchor`, verts rebased to `vert − anchor`. Pure
  representation change (`Location + local_vert ≡ world_vert`), so world position is preserved and the §5
  face-set oracle (world-position compare) is unaffected; `Location` becomes a clean handle on the geometry.
- **`--origin center|min|max|X,Y,Z`** (default `center`) picks the anchor; `keep` retains the faithful
  `Location=0` world-vert form.
- **`--at X,Y,Z`** = set `Location` to an ABSOLUTE world position (place the anchor), same semantics as
  `brush build --at` (supersedes the earlier "`--at` translates the intrinsic result" note — with
  re-centering it is a clean placement); omitted = anchor at the carved position (world unchanged).
- **`--pivot`/`--prepivot center|min|max|<edge>|X,Y,Z`** (default = anchor) sets `PrePivot` for a **swinging**
  mover (hinge); authoring `PrePivot` on a FRESH brush is deliberate, not the forbidden rewrite of an
  existing pivot (`quirks.md` "Pivots" guards mutation of existing actors).
- **`actor add` carries NO `--at`/positioning flag** (it already has none; this pins it) — placement is
  generator-side (`--at`) or a later `actor move`. Completes the pure-carrier-consumer model (with the
  17:04 `--folder`/`--label` removal). `actor add`'s `--order` stays (trunk-sequence position is inherently
  an add-time concern, not authored spatial identity).

**Rejected:** (a) keep the faithful `Location=0` world-vert form as default (movable only by a hand-computed
offset; mover pivots at the world origin — the usability gap this feature exists to close); (b) put a
positioning flag on `actor add` (breaks the pure-consumer model; two placement setters). **Open (for
Andrzej):** ship `--pivot`/`--prepivot` in v1 (needed for *swinging* doors) or defer (v1 re-centers only —
fine for *sliding* doors). **Refs:** spec `specs/2026-07-24-intersect-deintersect-native-brushset.md` §6b;
`quirks.md` "Pivots (`PrePivot`)"; `cli.py:478` (`actor add`, no `--at`).

## 2026-07-24 18:12 UTC — `intersect`/`deintersect` refinements: no `--split`, single `--pivot`, center default confirmed, scale deferral tracked

Andrzej resolving the 17:56 open items + two more:
- **NO `--split` — dropped entirely** (not deferred). A disjoint CSG result stays ONE actor + a
  component-count stderr warning; a user wanting independently mover-izable pieces just runs the verb on
  each subset (the input is a set, so per-door pipes are natural). Removes the connected-components pass
  from scope for good.
- ~~**`--pivot` is a SINGLE flag ... SHIPS in v1**~~ **— RETRACTED (recorded in error).** Andrzej ASKED a
  *question* ("how is pivot different from prepivot?"), not a decision; I wrongly recorded a settled flag
  design off it. **The pivot-override flag is OPEN** (whether to have one at all, its name `--pivot` vs
  `--prepivot`, and semantics — undecided). The only factual finding stands: `PrePivot` is the stored
  per-actor property, "pivot" is UnrealEd's editor transform-center that ultimately writes `PrePivot`, so
  offline there is one field to set. The 17:56 "Open (for Andrzej): `--pivot` in v1 or defer" line remains
  the live status.
- **Re-center to `center` by default — CONFIRMED** (was my recommendation at 17:56; "Centering sounds
  good"). `--origin` overrides.
- **Scale deferral is legitimate + TRACKED.** Rejecting scaled source brushes is inherited from the
  bspcsg core's pre-existing gap (`bspcsg.rs:2064`; the coarse core already applies scale), so it is
  cross-cutting, not intersect-specific — captured as a prioritized board item ("bspcsg core: apply
  scaled brushes", `inbox.md`, `[implement] p2`) per Andrzej's "if we defer scale, we need a prioritized
  board item". **Refs:** spec §2/§6/§6b; `inbox.md` bspcsg-scale item.

## 2026-07-24 18:33 UTC — `--pivot` flag APPROVED (reinstated after the erroneous 18:12 retraction)

Andrzej: "`--pivot` is fine." Resolves the pivot-override flag that the 18:12 entry wrongly recorded then
retracted (it had been treated as a decision off a question — see the 18:12 retraction). Now a genuine
decision: **ship `--pivot` in v1** on `brush intersect`/`deintersect` (and it is the natural pivot flag on
any generator that authors a `PrePivot`) — a **single flag** `--pivot center|min|max|X,Y,Z` (default = the
re-center anchor) that writes the `PrePivot` property; **no `--prepivot` alias** (offline there is one field
to set — `PrePivot`; UnrealEd's "pivot" is the editor transform-center that writes it). Needed for
**swinging** movers (hinge at an edge); sliding doors use the default. No open design items remain on the
intersect/deintersect spec. **Refs:** spec `specs/2026-07-24-intersect-deintersect-native-brushset.md`
§2/§6b/§7; `quirks.md` "Pivots (`PrePivot`)".

## 2026-07-24 18:50 UTC — `class list --include-abstract` ERRORS (exit 2) where it can't act, not a warning

Supersedes the "prints a one-line stderr note" resolution in the 2026-07-19 class-flag-orthogonalization
entry (UX review 1). Andrzej: passing `--include-abstract` in a context where it does nothing — the tree,
the bare category view, or ANY `--depth` browse (all already unfiltered) — is now a **hard `_SelectionExit`
(exit 2)** with an actionable message ("is not valid here — it applies ONLY to the --flat --subclass-of
drill and the --package flat list …"), NOT a warn-and-continue. Rationale: a flag that silently succeeds
while doing nothing reads as broken (the user's own confusion prompted this); a non-zero exit forces the
mistake to the surface. The flag still ACTS only in the `--flat --subclass-of` drill and the `--package`
flat list (unchanged). **Refs:** `dispatch._dispatch_class` (the `include_abstract` guard →
`_SelectionExit`), `cli.py` `--include-abstract` help, test
`test_class_list_include_abstract_errors_where_it_has_no_effect` (`test_ingest_validation.py`).

## 2026-07-24 18:49 UTC — `level import`: decode-time UCC-exact render (supersedes 17:19) + strict validation

Round-2 cold review (two reviewers) found the `level import` spec (a) UNDER-credited what exists — a
production per-tag value decoder already handles arbitrary schema-driven structs (`uprops.render_default_tag`
+ `_decode_struct_bin`), so most of "the decode" is reuse, not new; and (b) mis-placed the struct
reconciliation. It also killed a wrong assumption (a "native-vs-script struct" branch — UE1 serializes
ALL structs positionally via `SerializeBin`, never as nested tagged lists; evidence
`unrealed/class-schema.md`), and re-credited the StateFrame skip to Spike 07
(`spikes/2026-06-27-decontainerize-uedcli/07-native-actor-bodies.md`, validated on retail `00_Intro.dx`,
3736 objects, 0 errors). Andrzej then locked two design points:

1. **UCC-text fidelity lives at DECODE time (supersedes the 17:19 compare-time choice).** `mapimport`
   renders each prop exactly as `MAP EXPORT` would: native structs **member-stripped against the class
   default** (via `uprops.resolve_class_defaults` — the default may be NON-zero, e.g. `Scale=(1,1,1)`,
   so it is a real member-diff, not zero-stripping), scalar floats in **6dp `%f`** (UCC writes
   `X=12345.000000`; `format_float`'s int-trim would mismatch). **Why (functional + safety):** the
   trunk then matches every other trunk (stripped/6dp → clean diffs, which is the feature's whole point
   — study/remix/diff retail); the deliberately schema-free `normalize`/`canonical_level_hash` hash
   path is NEVER touched, giving a contained safety blast radius (that path backs materialize's H3
   verify — making it schema-aware was the riskiest option); and the offline text compare "just works"
   with no struct-drop/float-renorm in the lens. The materialize round-trip test is the data-loss guard
   (a wrongly-stripped member surfaces as a round-trip diff). *Rejected:* compare-time drop (17:19 —
   threads a schema dependency + the `Scale=(1,1,1)` trap into the guarded hash path, and yields
   whole-struct trunks that diff noisily against conventional ones); model-level compare (most new code,
   forgoes the hardened lens).

2. **Strict class/ref validation.** Import runs `ClassIndex.qualify_and_validate` before the trunk
   write — the same gate every other creation path uses: bare→FQCN qualify + existence-validate
   classes/textures; an unresolved package fails import exit 2. Keeps the trunk FQCN-consistent (so
   `level materialize`/`actor find --class`/the compare's requalification all agree). Retail OG DX maps
   resolve (same game's packages on the path); a map referencing an off-path package fails until its
   packages are installed. *Rejected/deferred:* a lenient "import anyway, keep unresolved refs + warn"
   mode (useful for arbitrary custom maps; produces a trunk that won't re-materialize cleanly) — inbox
   follow-up.

**Other v3 corrections (mechanical, from review):** value decode REUSES `render_default_tag` (not new);
delete the native/script struct branch; StateFrame skip promotes Spike 07's `native_dx_actors.py` (cite
it); **dynamic arrays are the real new decode** and need new schema plumbing (the `ArrayProperty` Inner
element KIND isn't exposed on `uprops.Prop` today) with a retail golden as their only offline coverage;
the stash write path is ASYMMETRIC (`write_stash(id, *, full_level, order, packages, meta, …)`, a
model→disk conversion, not `save`); `decode∘encode` pins are CIRCULAR (guard our own writer, not
engine-faithfulness — the load-bearing gate is committed retail goldens compared against a
**pre-committed** UCC artifact, since `export_dx_level` is container-bound and can't run in `bin/test`);
the order spike must handle null/deleted `TTransArray` slots and must PROVE (not assume) export-table ==
`batchexport` order. **Refs:** spec `specs/2026-07-24-level-import.md` v3; `uprops.render_default_tag`/
`_decode_struct_bin`/`resolve_class_defaults`/`Prop`, `native/actor_write.state_frame`,
`classindex.qualify_and_validate`, `stash_register.write_stash`, `store_export.export_dx_level`
(container-bound), `normalize.canonical_level_hash`, spikes `07-native-actor-bodies.md` +
`harness/upolys_decode.py`, `unrealed/class-schema.md` (positional struct serialize).

## 2026-07-24 19:01 UTC — `actor preview` param cleanup: `--layout`, `--frame`, `--show`; breakdown gives point actors panes; `--out` optional

The shared preview flag helper `cli.py::_preview_opts` (used by `actor`/`stash`/`prefab preview`)
carried 17 flags with three latent messes — resolved here (net 17→13, every hidden-interaction rule
removed). A **breaking CLI change across the three verbs**; each removed spelling gets a
`_RemovedFlag` migration error (matches the `--class`/`--zoom-poly`/`--split` precedents — LLM-facing
tool, small footprint, clean rename beats a deprecated alias).

- **`--single` + `--breakdown` (two booleans) → `--layout {quad,single,breakdown}`** (default `quad`).
  One choice ⇒ mutual exclusion for free, no silent `--breakdown`-overrides-`--single` surprise.
  *Rejected* flipping the default to `breakdown` (Andrzej's stated preference, memory
  `uedcli-preview-default-breakdown`): now that point actors also get panes (below) a default
  whole-level breakdown explodes into panes, so default stays `quad` and breakdown is opt-in
  (Andrzej's call).
- **`--zoom` + `--zoom-region` + `--zoom-factor` → `--frame TARGET` + `--frame-tightness N`.** `--frame`
  is ONE input taking either a `BRUSH[:IDX]` selector OR an explicit six-field `X0,Y0,Z0,X1,Y1,Z1` world
  AABB (`_parse_frame` splits them; a real actor name is never six comma-joined numbers). This removes
  the old "region beats zoom; factor modulates only zoom" precedence. Leading-negative AABBs parse
  because `_CoordArgumentParser._parse_optional` treats a coord token as a value — load-bearing,
  regression-pinned.
- **`--show-collision`/`--show-light-range`/`--show-sound-range` (three booleans) → `--show
  collision,light-range,sound-range`** (comma-set union, matching `--annotate`/`--folder`; unknown
  member = clean named error; validated even for a brush-only set).
- **`--out` optional + temp default; `--png` help fixed.** No `--out` ⇒ a `uedcli-preview-*` temp file
  is minted (`.png` under `--png`, else `.ppm`); the absolute written path is always printed to stdout.
  `--png` is KEPT (not replaced by extension-inference — with `--out` optional there is no path to infer
  from); its stale "also writes a PNG NEXT TO `--out`" doc/help was wrong (the code REPLACES the
  extension / mints the temp suffix — PNG *instead of* PPM), now corrected.
- **`--layout breakdown` gives each point actor its own captioned pane** (was: point actors got no pane,
  named in a since-removed overview legend). breakdown = a focus-iterating layout: pane 0 is the
  label-free CSG overview, then one pane per actor in set order — a brush focused + framed to its AABB
  with faces numbered, a point actor framed to `_point_pane_region` (its `_world_aabb` expanded to at
  least `Location ± _BREAKDOWN_POINT_MARGIN`=32 UU, so a zero-extent marker-only point centres instead
  of jamming into a corner). `--annotate` needs NO breakdown-specific branch: poly indices are scoped by
  the existing `--focus` rule; names are suppressed by breakdown's `hybrid + draw_legend=False`, not by
  focus (the distinction matters if a legend is ever re-enabled). *Rejected* a pane-0 legend / naming
  point actors in a roster — the 2026-07-24 legend removal stands; identify actors by their captioned
  panes.

**Refs:** spec `specs/2026-07-24-preview-params-cleanup.md` (revised after two cold reviews);
`cli.py::_preview_opts`, `dispatch.py::_render_actors_to_out`/`_render_breakdown_grid`/`_parse_frame`/
`_parse_show_set`/`_point_pane_region`. Two cold spec reviews caught the point-pane corner-jam
(regression-pinned) + the names-vs-focus mechanism.

## 2026-07-24 19:49 UTC — Corpus study: extract ONLY brush-construction idioms from real levels

Andrzej scoped a study to distill level-**construction** best practices from the real shipped DX (and
UE1 control) maps, to inform LLM-driven `uedcli` building. Spec:
`specs/2026-07-24-corpus-brush-idioms.md`. Load-bearing choices:

1. **D1 — Scope is the brush-construction idiom vocabulary ONLY:** the shape *alphabet* (which brush
   primitives real geometry is made of), the composition *grammar* (how they assemble), and the
   complexity/BSP-safety *budget* (the poly/vertex ceiling — the one in-scope number, a ceiling not a
   dimension). *Explicitly OUT:* dimensions/spacing, lighting distributions, design philosophy. *Why:*
   the corpus's unique value is what an LLM neither already knows nor can derive. Spacing is derivable
   from the already-decoded DX player cylinder + `16 uu = 1 ft`; philosophy/feel it already has as
   prose. The narrowing is *strengthened* by the nuance that prose-philosophy doesn't constrain
   geometry at build time — construction idioms are what operationalize the knowledge it already has.
   *Rejected:* a broad measurement study (dimensions/lighting) — Andrzej "not concerned with
   measurements; concerned about common practices (geometry shapes)"; guards against the LLM building a
   20,000-vertex brush.
2. **D2 — Wireframe-primary modality.** CSG-colored per-area/per-feature brush-*set* wireframes
   (`actor preview`) are the primary source; per-brush poly/vertex counts second; lit screenshots
   (`level preview --game`) only as occasional ground-truth. *Why:* for *construction*, a textured
   screenshot HIDES brush boundaries — the wireframe skeleton IS the knowledge. A lone-brush or
   whole-map wireframe is the wrong unit (loses composition / unreadable); the per-feature set is
   right; CSG coloring resolves the add-vs-subtract/solidity ambiguity a bare wireframe has. *Rejected:*
   screenshot-primary (earlier proposal) — reversed once scope narrowed to construction.
3. **D3 — Ground the EXISTING KB, don't author a parallel doc.** Findings revise
   `leveldesign/general/brush-shapes.md` / `geometry-and-bsp.md` / `design-craft.md` (+ a thin
   `deusex/` layer). The actionable output form is **generator reverse-mapping** (map each real brush
   back to the `brush build …` invocation that reproduces it, or tag freeform). *Why:* the KB already
   has the general/DX split; reverse-mapping drops straight into the LLM's construction path.
4. **D4 — General-vs-DX by UE1 differential control.** Same extraction over Unreal Gold + UT99 (free,
   Epic-sanctioned, from archive.org/OldUnreal), installed via **per-game setup scripts** into a
   gitignored `Tools/uedcli/dev/games/` (+ `.gitkeep`). Control's role: *confirm* an idiom is general
   (present in both) and *isolate* the thin DX-specific construction layer. *Rejected:* skip-U1 +
   heuristic split (less rigorous); DX-mods-as-proxy (still DX, doesn't separate general from DX).
5. **D5 — First pass is a pilot** (4 DX archetype maps + a few UE1 maps), scaling gated on the pilot
   proving the harness + reverse-mapping.
6. **D6 — Convention: every new spec carries a board item that references it** (added to
   `board/README.md` conventions).
7. **D7 — New confidence marker `📊 = measured-from-corpus`,** used narrowly for complexity/BSP-budget
   facts, each carrying N (map count) + range/median; NOT used for dimensions.

**Dependency:** offline `.dx`→T3D `level import` (`specs/2026-07-24-level-import.md`) — unbuilt; the
pilot's brush extraction is blocked on it (interim: UCC/editor export per map). **Complementary:**
`specs/2026-07-19-leveldesign-docs-skills.md` part (B) (human-scale *dimension* corpus) — different
axis, should share ONE extraction harness. **Surfaces uedcli gaps** (spec §7 → inbox): brush shape
classification (`brush identify`), brush→generator reverse-mapping, spatial subset in `actor find`
(`--within`/`--near`), brush complexity-stats aggregation.

**Review-refinements addendum (2026-07-24, after two cold-review gates; folded into the spec — these
are AI resolutions of review findings, a few flagged for Andrzej's confirmation before planning):**

- **`level import` demoted from hard blocker to later convenience.** The pilot uses the already-proven
  editor `MAP EXPORT`->trunk route (it is `level import`'s own test oracle, and the sister
  `2026-07-19` spec already budgets it), so the study does not stall on the large unbuilt import spec.
- **The scripted classifier + reverse-mapper is the real spine, built + validated FIRST**, dependency-
  free, via a self-consistency round-trip against uedcli's OWN generators (generate->classify->recover
  params->compare). Precedes any corpus claim. Builds on existing `classify_brush()` (`preview.py:273`,
  CSG-op-only today; shape identity is the new part).
- **"Freeform" is split three ways, never one number:** (a) reproducible by an existing generator, (b)
  reproducible only by a builder uedcli LACKS (capability-gap evidence -> inbox), (c) genuine freehand.
  Collapsing (b)+(c) would conflate a tooling gap with a craft fact.
- **New capability gap surfaced: an arbitrary-polygon extrude/prism generator** (`brush build extrude`)
  — the canonical UE1 method, absent today; likely a prerequisite for an honest headline (else extrudes
  dominate bucket (b)). On the board in `to-spec.md`; the study quantifies the case for building it.
- **Reverse-mapping promise scoped honestly:** op/solidity/shape-class/build-order are robust per brush
  actor; exact params are best-effort (exact for boxes, approximate for prisms/cones, absent for
  vertex-edited).
- **BSP-safety budget = whole-map metrics** (compiled node:poly ratio via `native.umodel`; on-grid
  vertex fraction), with per-brush vertex count demoted to a supporting stat; a corpus ceiling is
  descriptive, never a validated safe bound.
- **Delivery order inverted to quantitative-first; wireframes secondary.** For the 4-map pilot, HAND-
  SELECT brush names into `actor preview` — the parked `find-spatial` spec is a *scaling* gate, not a
  pilot blocker. `actor preview` verified to draw authored polys directly (no native CSG core), so it
  is safe on scaled/concave brushes.
- **Pilot delivers a validated harness + method write-up ONLY; durable craft-doc numbers gated on the
  scaled run.** Raw evidence lives dev-side (`dev/docs/unrealed/leveldesign/kb/`), distilled prose
  user-side (`docs/leveldesign/`). Study's real done-condition is a **behavioral acceptance eval**
  (LLM builds with vs. without the idioms, scored on brush count / freehand rate / on-grid).
- **UE1 control: Unreal Gold single-player is primary** (true construction analogue); UT99 is arena —
  use sparingly, flag the genre-vs-engine confound, don't launder arena idioms into `general/`.
- **Shared-harness ownership resolved:** THIS spec owns building the `MAP EXPORT`->trunk brush harness;
  `2026-07-19` Half B2 (human-scale dimensions) consumes it — no parallel fork.

## 2026-07-24 21:44 UTC — `actor find --within-bbox` BUILT (containment; the rest of find-spatial stays parked)

Andrzej: "let's do `--within-bbox` for now, and defer `--overlapping-bbox` for later." Implemented the
`--within-bbox` slice of the (parked) `specs/2026-07-24-find-spatial.md` — a spatial selector for the
corpus brush-idiom study (pick a region's brushes to pipe into `actor preview`), which superseded the
abandoned global-clustering approach (that harness collapsed a subtractive DX interior to one blob; see
`spikes/2026-07-24-corpus-brush-idioms/README.md` negative result).

- **`--within-bbox X0,Y0,Z0,X1,Y1,Z1` = FULL CONTAINMENT, edge-inclusive** (resolves find-spatial
  sub-choice §7.2 in favor of containment-only). Match iff the actor's world AABB is inside the box.
  Decimal predicate `writes.aabb_within` over `writes.actor_bounds` (full transform honoured; a point
  actor is a zero-size box at Location), in the dispatch find handler alongside `--prop` (NOT in
  `list_actors`); `cli.py parse_bbox6` normalizes the two-corner token (any corner order) to Decimal
  `(lo, hi)`. Single-valued; ANDs with the other filters; composes with the `-` universe. Negative
  coords parse as a value via the inherited `_CoordArgumentParser`. Tests: `tests/test_find_spatial.py`
  (containment/edge/straddle-excluded/corner-order/zero-box/compose/negative-coords/malformed→exit 2).
- **Rationale for containment (vs also-intersects):** "within" reads as contained; it's the precise
  selector. *Rejected/deferred:* the intersects variant (grabs straddling brushes — better for loose
  region-grab) is split out as **`--overlapping-bbox`**, a NEW `to-spec.md` item, per Andrzej.
- **Scope:** ONLY `--within-bbox` landed. `--near`, `--overlapping <actor>`, and `--within-brush`
  remain in the parked find-spatial spec (untouched). **Refs:** `writes.aabb_within`/`actor_bounds`,
  `cli.parse_bbox6`, dispatch find handler, `docs/usage.md`, `architecture.md`.

## 2026-07-24 21:46 UTC — `uedcli docs` serves the user-facing docs from the CLI (tool documents itself)

Add a top-level **`docs`** verb — `docs list` / `docs show <topic>` / `docs search <query>` — that
serves the repo's **user-facing** prose docs (`usage.md`, `leveldesign/**`, `README.md`; everything
under `docs/` **except `dev/docs/**`**) straight from the CLI. Spec:
[`specs/2026-07-24-docs-command.md`](specs/2026-07-24-docs-command.md).

**The load-bearing choice — the docs are an asset of the TOOL, served by it, not bundled into the
skill.** A shipped Claude skill routes to the docs by *querying the binary* (`uedcli docs …`), so the
skill/plugin ships **zero** doc copies. One source of truth (`docs/`); the docs a user reads are the
ones baked into the binary they have (version-locked, offline, cross-platform). This is the
`git help <topic>` / `rustc --explain` / `perldoc` pattern. *Rejected:* bundling the craft KB under
the skill's `references/` (duplication + ownership inversion — docs would live under `skills/` — plus
a bake/sync step); URL-referencing hosted docs (runtime network dependency + skill-vs-docs version
drift). *Why it matters:* surfaced designing the skills-plugin distribution (`to-spec.md`) — the
`docs` command is its prerequisite.

**Resolution — one resolver, three environments, ships COMPLETE in v1:** `UEDCLI_DOCS_DIR` override →
`importlib.resources.files("uedcli") / "_docs"` (wheel / pipx / Nuitka one-file) → source tree
`Tools/uedcli/docs` (editable dev). `bin/uedcli` uses the source-tree branch with **no build step**;
the `_docs` branch is dormant until packaging exists. Source of truth stays `Tools/uedcli/docs/`; the
`_docs` copy (served subset = `docs/` minus `dev/`) is a **generated build artifact**.

**Forks resolved (all Andrzej, 2026-07-24 chat):**
1. **`docs show <topic>` only** — no bare `docs <topic>` sugar (positional ambiguity with subverbs).
2. **Serve `usage.md` too**, not just `leveldesign/**` — a fresh agent benefits from the CLI reference
   being queryable the same way.
3. **`_docs` is gitignored + generated at build**, not committed (no generated artifact in git; dev
   uses the source fallback). *Rejected:* committing `_docs` + a CI sync-check.

**Deferred (NOT built in v1; Nuitka/wheel packaging doesn't exist yet):** the `_docs` generation step,
its `.gitignore` entry, `--include-data-dir`/package-data wiring, and a drift-guard CI check — added
when packaging lands, with **no change to the `docs` command code** (the resolver is already
complete). Logged for the packaging work. **Refs:** the spec above; enables the `to-spec.md`
skills-plugin-distribution + standalone-repo items.

## 2026-07-24 21:57 UTC — NO BACK-COMPAT CRUFT: uedcli is unreleased, so a removed thing is DELETED

**uedcli has never been released.** There are no external users, no pinned versions, no scripts in
the wild that a change could break. Therefore **nothing is ever kept for backward compatibility.**
When a flag, verb, option value, output format, or code path is removed or renamed, it is **deleted
outright** — the new spelling is the only spelling, from the same commit.

Concretely, NONE of these may be introduced or retained:

- **Deprecated aliases** — the old flag name still working, silently or with a warning.
- **Migration-error shims** — a flag defined purely to `parser.error("X was renamed to Y")`. This
  explicitly includes the existing **`_RemovedFlag`** action in `cli.py` and every one of its
  9 call sites (`--single`, `--breakdown`, `--zoom`, `--zoom-region`, `--zoom-factor`,
  `--show-collision`, `--show-light-range`, `--show-sound-range`, `--class`). They were a
  reasonable instinct for a shipped tool; for an unreleased one they are dead weight in the parser
  and in `--help`'s shadow. **They are swept** (board: "CLI cruft sweep").
- **No-op flags** kept "so existing invocations don't break."
- **Dual-format / dual-path support** kept only to avoid re-writing callers (e.g. still writing PPM
  because something might read PPM).
- **Legacy branches** in code, tests, or docs describing "the old way" alongside the new.

**Why:** every shim is permanent maintenance surface, a second thing to keep true in docs, and a
source of exactly the stale-help bugs this board keeps collecting (the `--png` help text described
behavior the code hadn't had for months). An unreleased tool's one advantage is that it can simply
change; spending that advantage on compatibility nobody needs is pure loss.

**Scope:** applies to the whole uedcli surface — CLI flags/verbs, output formats, on-disk tree
layouts (trunk/stash/prefab), config keys, and internal APIs. The T3D trees are the one place to
think before deleting, since a user's *content* lives there — but the rule still holds: change the
format and migrate or regenerate the trees, don't teach the reader two layouts.

**This is superseded the day uedcli is released** — at that point a real deprecation policy
replaces it, and this entry gets a successor rather than an edit.

*Rejected:* keeping `_RemovedFlag` "because the error message is friendly" — the friendliness is for
users who don't exist; the sole real consumer is Andrzej plus the agents working this repo, both of
whom read `usage.md` and the commit. *Rejected:* a deprecation window (warn now, remove later) —
that's a released-software ritual with no meaning here. **Refs:** `CLAUDE.md` "Code & CLI
conventions"; `direction.md` "No back-compat cruft".

## 2026-07-24 21:58 UTC — Board triage of the cheap-item shortlist (10 items)

Andrzej's calls on the ten cheap/promotable board items surfaced in the 2026-07-24 board review.
Recorded because three of them **changed the item's shape**, not just its queue:

1. **`class show` — the degrade fallback is REMOVED, not tested.** The item was "add a regression for
   the graceful-degrade path" (a missing/unparseable ANCESTOR package → own-only props + a stderr
   note + exit 0). Andrzej: **error instead — no fallbacks.** An unreadable ancestor is now a clean
   exit 2 naming the package. This deletes the degrade branch (`dispatch.py` `_dispatch_class`), its
   `--category`-rejects-degrade special case, and `test_class_show_category_rejects_degraded_schema`;
   the new test asserts the error. *Why:* a half-answer that looks like a full one is worse than a
   refusal — the note goes to stderr and scrolls away, leaving the caller believing a class has no
   inherited props. *Rejected:* keeping the fallback behind a `--allow-partial` flag (a flag to opt
   into a wrong answer).
2. **The `stash intersect/deintersect` `CalledProcessError` leak is DITCHED, not fixed.** The item
   (add `subprocess.CalledProcessError` to the stash path's except tuple, `dispatch.py:3087`) is
   obsoleted by the already-decided **native intersect/deintersect** (2026-07-24 16:32) — that path
   stops spinning an editor container at all, so the exception it fails to catch stops existing.
   Fixing it now is work on code scheduled for deletion.
3. **`actor preview --png` is REMOVED; PNG is the DEFAULT output.** The self-rendered wireframe
   previews (`actor`/`stash`/`prefab preview` — one shared `_preview_opts`) now always write PNG.
   *Why PPM existed:* `preview.py` is a stdlib-only rasterizer (no PIL/numpy) and P6 is a 15-byte
   header plus raw RGB — writable with no encoder. *Why it goes:* Pillow is already uedcli's sole,
   REQUIRED third-party dep (texture-catalog PCX decode; `--layout breakdown` hard-fails without
   it), so PPM-on-disk bought nothing; PPM is unviewable by a browser, most viewers, and an LLM —
   the audience these previews exist for; and `level preview --game` already returns PNG, so the
   offline tier was the lone outlier. **`preview.py` keeps returning PPM bytes internally** (the
   stdlib-only guarantee; `--layout breakdown` stitches PPM panes in memory) — only the disk-write
   boundary changes. Per the no-cruft rule above, `--png` is **deleted outright**, not shimmed. A
   `--out` path is written as PNG at its stem regardless of the extension given; there is **no way
   to get PPM from the CLI**. *Rejected:* honoring a `.ppm` extension as an escape hatch — nothing
   consumes PPM downstream, and a format with no consumer is how the next stale-docs bug starts.
   This also kills a second wart: `--out` previously ignored the extension entirely and wrote PPM
   bytes into a file named `.png`/`.svg`.
4. **`mover key`'s mover check goes schema-aware** (descends-from-`Engine.Mover`, replacing
   `movers.is_mover`'s `bare.endswith("Mover")` name guess) — promoted to build despite the flagged
   ripple that `is_mover` is shared with `level doctor` and a schema-aware predicate needs a class
   resolver (and therefore the games config). The resolver/config question is an open build-time
   item in `inbox.md`, not a blocker.
5. **The two spike-harness-dependent `test_native_materialize.py` tests are marked SKIPPED** (they
   need the spike env's `line_check`/`utexture_decode`), not repaired — a permanently-red suite
   trains everyone to ignore red. *Rejected:* adding the spike harness dir to the test `sys.path`.
6. Promoted unchanged: `driver.map_save` file-written check; `actor folder set/unset` become
   stdout producers; builder positive-dimension guards; the preview-annotation `label`→`annotation`
   internals rename; a `uedcli cache gc` CLI surface over the already-shipped `schema_cache.sweep()`.

**Refs:** board `to-build.md` items 9-10; `inbox.md` (the `is_mover` resolver question).

## 2026-07-24 22:28 UTC — `uedcli docs`: a README folds to its directory's topic key (root → `index`)

Refines the `docs` command (21:46 UTC). A served `README.md` is the **index of its directory**, so its
**topic key is the containing directory's path** — `leveldesign/deusex/README.md` → `leveldesign/deusex`
(`docs show leveldesign/deusex` = the deusex overview); the root `docs/README.md` → the reserved key
**`index`**. The six redundant `…/README` keys disappear and identical `README` basenames stop
colliding in `--json`. *Rejected:* leaving the `/README` suffix (redundant, six same-named topics);
renaming to `…/index` (still a suffix, less natural than the bare folder path). **Collision rule:** if a
`X/README.md` and a sibling `X.md` both claimed key `X`, enumeration **hard-errors naming both files**
(the "no silent half-answer" rule, direction.md 2026-07-24 21:58) rather than silently picking one; no
such collision exists today. **Refs:** `specs/2026-07-24-docs-command.md` §2.1/§3/§5/§7/§9.

## 2026-07-25 — `Rotation` folded at COMPARE time; the underlying class-default bug class opened

**The reported bug.** `level materialize` aborted on the H3 post-verify — writing NOTHING — for any
actor with an axis-only rotation. uedcli's producers write all three FRotator components
(`(Pitch=0,Yaw=16384,Roll=0)`); UnrealEd re-exports the same rotator with members equal to the class
default omitted (`(Yaw=16384)`). `Rotation` is a raw prop string compared verbatim, so the spellings
never converged. Every yaw-only door, mover or angled decoration hit it.

**Decision: fold `Rotation` to the editor's spelling on the THROWAWAY COMPARE COPY**
(`normalize._prep_actor_for_canonical`, beside the float32/`Normal` prep), **never in
`normalize_actor`.** `normalize_actor` feeds `canonical_actor_t3d`, which is the durable git-tracked
trunk emit AND the `MAP IMPORT` payload AND `actor show` — folding there rewrites authored data.
Consequences of this placement, all deliberate: the trunk is byte-untouched (no migration; the 4
existing trunk actors carrying the verbose form need nothing), trunk bytes never vary with which
packages are installed, and no class-defaults resolver enters the hash path (`canonical_level_hash`
is also the `preview_game` build-CACHE KEY, so a resolver-dependent hash would cause stale-preview
collisions). *Rejected:* folding in `normalize_actor` (the first attempt — it rewrote the trunk and
the import payload, the exact failure a 2026-07-14 cold review established this seam to prevent);
fixing the producers + migrating trunks (rewrites authored files, leaves hand-edited/imported trunks
unfixed, and makes every future producer a place to forget the rule).

**Guard: components are folded TEXTUALLY, never reduced mod 65536.** The editor preserves
over-range/full-turn values — `Yaw=-65536`, `Yaw=-131072`, `Yaw=-81920` all occur in the committed
retail corpus — so `emit_frotator(parse_frotator(v))` would rewrite a real rotator to zero and CAUSE
the mismatch it is meant to fix. ⚠ This is verified for the EXPORT leg only; `rotation.compose_uu`'s
docstring asserts the opposite for IMPORT ("a materialize import normalizes mod 65536 anyway"). The
two claims cannot both be true and a live probe is pending — if import does normalize, no ingested
retail actor with an over-range rotation can ever pass post-verify.

**The bug class this exposed (OPEN).** The engine rule is "omit what equals the CLASS DEFAULT";
uedcli tests against ZERO. They coincide for almost every class, which is why this hid. Where a
class default is non-zero and uedcli OMITS the property, the engine substitutes its default — the
built map is WRONG and post-verify PASSES, because both compare sides share the mistake. Verified
offline over 1346 actor classes:
- **`TNM.LavaSpitter` defaults `Rotation=(Pitch=16384,Yaw=0,Roll=0)`** — the only class that
  defaults `Rotation` at all. (This supersedes the claim, written earlier the same day from a
  scan whose key lookup was wrong, that no class defaults `Rotation` non-zero.)
- **228 classes default `RotationRate` non-zero** (`DeusEx.Rat` = `(Pitch=4096,Yaw=65530,Roll=3072)`).
- **`Engine.Camera` defaults `Location=(X=-500,Y=-300,Z=300)`.**

Two live silent-corruption paths follow, both filed and NOT fixed by this change: `dispatch.py` drops
`Rotation` when the result is identity (so `actor rotate --to 0,0,0` on a LavaSpitter re-imports it
pitched 90°), and `normalize_actor` clears an all-zero `Location` into the trunk/import payload (so
an `Engine.Camera` at the origin re-imports 500 units away). The compare-time fold above cannot cause
either — on a throwaway copy the worst case is a spurious ABORT, never a wrong map.

**Refs:** `rotation.canonical_rotation_value`, `normalize._prep_actor_for_canonical`,
`unrealed/t3d.md` "Partial struct/array property values", spec
`specs/2026-07-25-rotation-compare-canonicalization.md`, inbox `[debug]` item (closed by this).
## 2026-07-25 — `intersect`/`deintersect` BUILT: the editor's wrap/builder cubes COINCIDE (spec §4 corrected)

Building the native verbs turned up a factual error in the spec's reading of the editor-driven
generator it was ported from, plus two pre-existing core gaps. Recording the corrections, since the
spec is ephemeral and its §4 claim is load-bearing for anyone re-deriving the scaffolding.

**1. The wrap-subtract and the builder are the SAME BOX in world space.** Spec §4 read
`_stash_intersect_impl`'s wrap placement `(cx−32, cy−32, cz−32)` against the builder's `(cx, cy, cz)`
as "they are DIFFERENT boxes; the −32 offset is load-bearing (coincident faces are where CSG
classification is fragile)", and required the native port to reproduce it. That is **wrong**: the
−32 is the standing compensation for UnrealEd's **`EDIT PASTE` +32uu drift on all three axes**
(`unrealed/quirks.md` "EDIT PASTE drift"), which the pasted wrap goes through and the
`BRUSH IMPORT`ed builder does not. In WORLD space both cubes are `bbox+64` centred on the set.

Reproducing the offset natively (no paste, so no drift) would leave the builder poking out of the
carved void into untouched solid background, and Phase 1 would weld a hollow 32-thick shell of
scaffolding onto every result. **Verified against the live editor** 2026-07-24: driving the (then still
present) editor path over one additive 256×256×128 cube returns the SOURCE box — 6 faces,
x/y ∈ [−128,128], z ∈ [−64,64] — not the [−160,160] shelled form the offset reading predicts. That
probe is now the committed regenerator `tests/editor_oracle.py` +
`tests/test_integration_intersect_oracle.py`, and its output the committed goldens under
`tests/fixtures/intersect/` (case `a_add_with_notch` is the same geometry with a notch added), so
the finding is re-derivable rather than resting on a scratch script. So
the native path uses `BUILDER_PAD == WRAP_PAD == 32` (`brushcsg.py`), and the coincident-face case
resolves correctly anyway: a builder face cospatial with the void boundary classifies
`COSPATIAL_*`/`COPLANAR_OUTSIDE`, none of which Phase-1 intersect accepts.

*Rejected:* porting the −32 verbatim "for faithfulness" — it is faithful to a paste artefact, not to
the operation.

**2. A non-brush or Mover in the piped set is REFUSED (exit 2), not skipped.** The spec (§2/§6)
specified warn-on-stderr-and-skip, following the `brush poly find` rule (2026-07-24 16:28). That
predates **"No silent half-answers"** (2026-07-24 21:58), which this follows instead: a merge quietly
missing a brush hands back a T3D the caller reads as complete while the warning scrolls away. The
error names every offending actor and points at `actor find --kind brush`.

**3. Two PRE-EXISTING core gaps surfaced, neither introduced here; BOTH now resolved** — every
committed golden matches the live editor face-for-face, with no xfails.

- **The repartition left every node `NF_IsNew`, so Pass-2 detail (semisolid/nonsolid) brushes were
  silently dropped from the world.** `NF_IsNew` is a per-brush transient that makes `IsCsg()` report
  a node non-solid (so a brush cannot cut itself); `bsp_brush_csg` clears it per brush via
  `bsp_cleanup`, but the repartition builds its whole tree through `bsp_add_node(…, NF_IS_NEW)` and
  nothing cleared it before Pass 2. A detail brush therefore descended a world where nothing was
  CSG-solid, every face classified `F_INSIDE`, and the Add leaf dropped it. **FIXED in the core**:
  `bsp_cleanup` after the repartition, mirroring the engine's own per-brush cleanup. This also
  restores detail brushes to `level materialize`. The castle byte-identity golden never caught it
  because the castle has 0 detail brushes.
- **`first_add_seed` treats any leading `CSG_Add` as the convex world SHELL** (seeding its faces as
  reversed root nodes instead of classifying them). Right for the brush every real level opens with,
  wrong for an Add that is a small solid inside what a later subtract voids — the seeded faces
  survive as splitters. **The core shortcut is UNCHANGED** (it is editor-verified for the shell case
  it exists for); `deintersect` instead prepends a small **seed-subtract placed far outside the
  builder**, so the set's first brush never meets an empty tree and the shortcut cannot fire. It is
  inert by construction: Phase 2 prunes the world by the builder's bound sphere, so its faces are
  never reached, and its planes are too distant to split anything in the working region.

*Rejected* for the second: a leading no-op wrap-**ADD** — measured, an additive's faces land INSIDE
the builder hull, so Phase 2 collects them as caps and the doorway plug came back as the whole padded
box. The seed must be a subtract, and it must be outside the hull.

**Refs:** `brushcsg.py`; `bspcsg.rs` `intersect_brushset`; goldens `tests/fixtures/intersect/`;
spec `specs/2026-07-24-intersect-deintersect-native-brushset.md`.
## 2026-07-25 00:14 UTC — `brush build extrude` + `brush build revolve`: the 2D-profile generator family (Andrzej-decided)

The speccing Q&A for the arbitrary-polygon extrude gap (raised by the corpus brush-idiom study,
`specs/2026-07-24-corpus-brush-idioms.md` §7 gap 6). Spec:
`specs/2026-07-25-brush-profile-generators.md` (ephemeral — this entry is the durable record).

Context: `brush build` offers six *fixed parametric* shapes (`cube`/`cylinder`/`cone`/`sheet`/
`staircase`/`spiral`) — you choose sizes, never a silhouette. UnrealEd's canonical method is the
**2D shape editor**: draw a closed polygon, then **Extrude** (sweep it straight) or **Revolve**
(sweep it around a pivot axis). uedcli had neither, so any non-box/non-n-gon cross-section (arch
voussoir, L-ledge, cornice, curved corridor) was unbuildable short of hand-authored T3D or chained
`brush clip` planes.

**D1 — Extrude and revolve are TWO verbs specced TOGETHER; extrude builds first.** They share the
profile grammar, the orientation rule, the anchor rule, winding, and cap generation. *Rejected:
extrude alone, revolve specced later* — the shared grammar would have been settled twice and drifted.

**D2 — The profile is a repeatable `--point U,V` flag**, argument order = ring order, ring implicitly
closed. *Rejected: a single `--profile "u,v u,v …"` string* (quoting-sensitive, invisible in
`--help`). *Rejected: a point list on stdin via `-`* — uedcli deliberately has exactly TWO stdin
conventions (a newline-separated name list; a T3D snippet) and `CLAUDE.md` requires keeping them
distinct; a bare coordinate list would be a third, blurring what `-` means per verb. Adding stdin
later stays possible.

**D3 — `--axis x|y|z` (default `z`) names the axis the profile plane is NORMAL to** — equivalently the
direction the sweep grows. `(u,v)` maps to the other two world axes by right-handed cyclic order
(`z`→X,Y; `x`→Y,Z; `y`→Z,X), so `u × v = +axis` always and one winding rule serves all three. This is
also the naming precedent the parked `brush build cylinder/cone --axis` item must adopt. *Rejected:
`--plane xy|xz|yz`* (reuses `sheet`'s word, but for a swept solid the natural parameter is the sweep
direction, and the cylinder/cone item would then need a different word for the same concept).
*Rejected: XY-only in v1* (reproduces the `--rotate` axis-guessing the `--axis` item exists to kill).

**D4 — `--at` is the world point that profile coordinate `(0,0)` lands on.** Local vertices are the
authored profile coordinates verbatim (no re-centering); the sweep grows `0..depth` along `+axis`.
This is a documented SECOND exception to the `--at` "geometric centre on every axis" contract, beside
the existing `staircase` one. *Rejected: geometric centre, ±depth/2* — uniform with the other shapes
and needing no exception, but it discards the authored 2D coordinate system, which is the whole point
of a profile (a ring of voussoirs laid out at known offsets would collapse onto one centred brush).
*Rejected: anchor on the profile's FIRST point* (Andrzej's own first proposal) — same
lands-where-you-drew-it property, but re-ordering the ring silently moves the brush, and revolve has
no meaningful first point (it anchors on a pivot axis), so the verbs would need different rules.

**D5 — A revolve emits ONE brush, not one per segment.** Its swept inner wall is concave; the caps
tile into convex faces (D6). Andrzej: this matches UnrealEd, where every 2D-shape-editor operation
yields the single red builder brush. *Rejected: one convex brush per segment* (the `spiral`
precedent) — correct in all three tiers including the offline `--native` draft and kinder to CSG, but
it diverges from UED's output, emits N actors per sweep, and seams the solid internally.

**D6 — A concave profile (or one whose cap would exceed the engine's 16-vertex `FPoly` limit) is
TILED into convex cap faces, emitting one brush** — the `staircase` precedent: a non-convex BRUSH of
convex FACES, which `doctor`'s per-face convexity test accepts (`_is_convex`, run inside
`check_degenerate` under `category="convex"`), UnrealEd's `level materialize` builds
correctly, and the `--game` preview renders correctly. Ear-clip then merge across diagonals while the
piece stays convex (Hertel–Mehlhorn), so a convex ≤16-vertex profile still yields exactly ONE cap
piece per end. Tiling adds only diagonals, so no T-junctions appear. *Rejected: splitting into
multiple convex brushes* (correct in every tier, but N actors and internal seams). *Rejected:
rejecting concave profiles outright* — arches and L-profiles are much of why the gap was raised.
**Known caveat, accepted:** the offline `level preview --native` tier classifies solidity with
`uedcli-native/src/csg.rs` `point_in_convex` (inside = behind every face plane), which is valid only
for convex solids, so it draws a concave notch FILLED. UnrealEd and the `--game` default are correct;
`staircase` already carries this caveat, and it must be repeated in `--help` and `usage.md`.

**D7 — Angle units: UU everywhere, generalizing the 2026-07-19 19:28 UTC decision to BUILDER angles.**
That decision ("one unit system end to end") reached the rotation flags but not builder geometry, so
the tool mixed units: `cylinder`/`cone --angle-offset` and `spiral --degrees-per-step` took degrees
while `--rotate` took UU. Now: `revolve --angle` is UU, and `spiral --degrees-per-step` is **renamed**
`--angle-per-step` in UU (no alias — `direction.md` "No back-compat cruft"), default `8192` (45°)
rather than the exact-but-unreadable `5461`. UU also divides better for segmentation (`65536/16 =
4096` exactly, vs `360/16 = 22.5`). Conversion happens at the CLI/dispatch boundary
(`rotation.uu_field`/`uu_to_deg`), leaving `builders.py` internally in degrees — the pattern
`preview_shots.py` already uses for the camera-pose grammar.

**D8 — Taper/bevel/loft is OUT of scope.** UED's *Extrude to Point* / *Extrude to Bevel* scale the far
cap. Excluded because a **trapezoid profile** already yields wedges, voussoirs and tapered blocks (the
taper lives in the profile plane) and `brush clip` covers a single chamfer plane. The genuine
remnant is taper ALONG the sweep axis — a frustum/loft, which neither extrude nor clip nor
`brush build cone` (apex-only, no `CapHeight` truncation) can make; that is a one-flag follow-up
(`--taper S`), so the p3 `inbox.md` "cube --taper / wedge builder" item is **re-scoped to the
remnant**, not closed. Also out: profiles with holes (in UE1 a hole is a subtracted brush), sweeping
along an arbitrary path (Tarquin's `Extruder`), and a revolve profile touching/crossing the pivot axis
(v1 rejects it; needed for solids of revolution).

**D9 — `cylinder`/`cone --angle-offset DEG` is replaced by the boolean `--align-to-side`**, which
applies a half-segment offset (`180/sides` degrees). The flag's only purpose — undocumented until now
— is to turn a FACE rather than a VERTEX toward the axis so an n-gon pillar sits flush against an
axis-aligned wall instead of meeting it on a corner. Every documented use (`usage.md`,
`leveldesign/general/brush-shapes.md`, the `octagonal-column.md` recipe) is exactly that case; an
arbitrary offset merely duplicates `--rotate`, which is the right tool for any other orientation. The
bool matches `CylinderBuilder`'s own **`AlignToSide`** checkbox 1:1, removes the units question for
this flag entirely, and sharpens `brush identify` reverse-mapping (a bool to recover, with any other
cross-section rotation falling out as a `--rotate`). *Rejected: keep the free angle, converted to UU*
(no documented need, overlaps `--rotate`). *Rejected: delete it and use `--rotate`* — that
reintroduces the pitch/yaw/roll guesswork the `--axis` item exists to remove (for an X-built prism the
equivalent is roll, not yaw) and spends the actor's single `Rotation` field on a shape concern.

**Refs:** `specs/2026-07-25-brush-profile-generators.md`, `builders.py` (`_face`/`make_brush_actor`),
`geometry.validate_brush`, `doctor._is_convex` (inside `check_degenerate`)/`check_watertight`,
`unrealed/leveldesign/kb/geometry-builders.md`, `unrealed/leveldesign/kb/csg-bsp.md` (the 16-vertex
`FPoly`), decisions 2026-07-19 19:28 UTC (rotation units) and 2026-07-24 21:57 UTC (no back-compat
cruft).

## 2026-07-25 00:36 UTC — Class-default contraction at the compare seam; the write side NEVER omits to mean zero

> **Superseded in part by 2026-07-25 02:15 UTC** ("the H3 post-verify compares TYPED effective
> values"): the CONTRACTION MECHANISM described as decision 1 below — `normalize.contract_actor`
> and `classdefaults.values_equal` — was deleted and replaced by a typed effective-value compare,
> which subsumes every rule listed here. Decisions 2-4 (the pure schema-free identity hash, the
> up-front no-fallback class resolution, and the write side never omitting to mean zero) STAND.

Closes the bug class opened by the 2026-07-25 entry "`Rotation` folded at COMPARE time; the
underlying class-default bug class opened", which fixed
the `Rotation` symptom and filed the general defect. The engine rule is **"omit what equals the
CLASS DEFAULT"**; uedcli tested against **ZERO**. The two coincide for almost every class, which is
why it hid for so long, and they part company in two directions — one loud, one silent.

**Decision 1 — the compare contracts BOTH sides against the real class defaults, generically.**
`normalize.contract_actor` (fed by `classdefaults.ClassDefaults`, memoized per class over one shared
package map: ~0.19 s cold, ~0.014 s amortized) drops a whole property equal to the class default,
folds `Rotation` members against the default member, drops a default-equal `Location`, drops a struct
property whose every member is a numeric zero where the class does not default it (`PrePivot`, which
`transform.bake` and `actor prop set` write in full — all-members-zero IS the type default), and drops
the editor's `Tag=<bare class>` default-stamp — the last **only** where the class does not itself default
`Tag`, since `TNM.Trestkon` defaults `Tag='Player'` (5 TNM classes do) and there `Tag=Trestkon` is
authored event-wiring content. Value equality is numeric-then-exact, so the trunk's `StayOpenTime=4.0`
matches a default rendered `4`, while enum names and object refs still compare verbatim. This alone
un-aborts five default-equal properties measured in this repo's own trunks (`MoverGlideType`,
`StayOpenTime`, `LightPeriod`, `LightEffect`, `SoundRadius`) — none of them a struct, so no
`Rotation`-shaped fix could ever have covered them. It runs ONLY on the throwaway compare copy.

**Decision 2 — the identity hash and the compare view are SPLIT.** `canonical_level_hash` is now
pure and schema-free (no prep, no contraction, no class defaults); the post-verify uses a separate
`normalize.compare_view(level, *, defaults)`, and `verify._first_diff` consumes that SAME view
instead of hand-mirroring it. The hash is the preview build-CACHE KEY
(`materialized__<level>__<hash12>.dx`), so every equivalence folded into it is a chance to serve a
map built from a different level; a stricter hash can only cost a rebuild. *Rejected:* one hash
serving both roles (the shape it had) — it forces the cache key to inherit every compare-time
equivalence, and would have put a package-dependent resolver in the cache key.

**Decision 3 — an unresolvable class is a HARD FAIL, resolved before the editor starts.**
`run_materialize` resolves every distinct class's defaults up front, so a bare/unqualified class
costs ~0.1 s and `exit 2` naming the ACTOR and the class, instead of surfacing after a ~100 s build.
`verify_dx_matches` takes `defaults` as a REQUIRED argument. *Rejected:* falling back to "assume the
default is zero" for an unresolvable class — that is precisely the bug being removed, reintroduced
on the one path whose job is to detect wrongness (and it is the silent half-answer `direction.md`
forbids). Bare names do reach this path: `qualify.requalify_classes_to_loaded` leaves a class bare
when the live editor offers 0 or 2+ candidates.

**Decision 4 — no write path may omit a property to mean "zero".** An omitted property re-imports as
the class default, and no write path has a resolver to prove the value equals it, so every write is
explicit and the compare-side contraction absorbs the equivalence. Four omissions were removed;
three were live silent-corruption paths that built a WRONG map which post-verify PASSED, because
both compare sides shared the same mistake:
- `actor rotate --to 0,0,0` (and `--by` composing to identity, and `brush build --rotate 0,0,0`)
  dropped the `Rotation` prop → a `TNM.LavaSpitter` (defaults `(Pitch=16384,Yaw=0,Roll=0)`, the only
  one of 1346 actor classes that defaults `Rotation`) was built pitched 90°;
- `normalize_actor` cleared an all-zero `Location` → an `Engine.Camera` (defaults
  `(X=-500,Y=-300,Z=300)`) at the origin was built 655 uu away;
- `normalize_actor` deleted a `Tag` equal to the bare class name → an authored `Tag=Trestkon` was
  erased and the actor came back tagged `Player`;
- `transform.bake` dropped a `PrePivot` the transform mapped to zero (17 classes default it
  non-zero) — needs a degenerate/zero-scale transform to reach, never observed, fixed anyway.

The cost is a few more explicit lines in the trunk (`Rotation=(Pitch=0,Yaw=0,Roll=0)`,
`Location=(X=0,Y=0,Z=0)`, the editor's own `Tag`) — exactly what UnrealEd's importer accepts and
what its export contracts away again. *Rejected:* giving the write paths a defaults resolver so they
can omit correctly — it makes trunk bytes depend on which packages are installed (the invariant that
keeps `canonical_actor_t3d` reproducible), for a saving of one line per actor.

**Known remnant, filed not fixed:** `model.parse_t3d` zero-fills a partial `Location=(X=100,Y=200)`,
so an `Engine.Camera` whose export omits an at-default axis loses that axis on INGEST. Fixing it
needs a class-defaults resolver at parse time — a much larger change (parse is schema-free by
design), and the failure is LOUD (a post-verify mismatch), not silent. Filed p1 on `board/inbox.md`.

**Supersedes** the 2026-07-06 claim that the preview cache key is "the same oracle verify uses":
after Decision 2 they are two different reductions, deliberately.

**Cold-review round (2 reviewers, 2026-07-25), resolved:** the compare view is a dict keyed by the
canonical actor name, so a non-LevelInfo actor literally named `LevelInfo` would have had one body
silently overwrite the other — a FALSE PASS, demonstrated by a reviewer — and now raises instead;
the class-default lookup parses the `KeyPos(1)` array index off the prop key rather than assuming
index 0 (assuming 0 made every indexed element look un-defaulted, so rule 2 would have dropped an
all-zero element of a class that defaults it non-zero); `transform.bake`'s `Rotation` deletion was
the same omission as its `PrePivot` one and is fixed with it; and the exit-2 message now names the
two remedies, because this check refuses builds that used to succeed (a bare class the live editor
would have resolved, or a package missing from `paths`).

**Deliberately NOT extended to zero-valued SCALARS** (`LightRadius=0`, `bHidden=False`), which the
editor also omits: `parse_t3d` discards quoting, so `Foo="0"` and `Foo=0` are the same text in the
model, and dropping a string property that happens to read `0` could hide a real difference — a
false pass traded for a spurious abort. The principled fix is to compare against the type's zero
from the decoded SCHEMA rather than from the text; filed on `board/inbox.md`.

**Refs:** `normalize.contract_actor`/`compare_view`/`canonical_level_hash`, `classdefaults.py`,
`apply._level_defaults`, `verify.verify_dx_matches`, `unrealed/t3d.md` "Partial struct/array property
values", `architecture.md` "The compare view vs the identity hash".

## 2026-07-25 01:05 UTC — `brush build revolve` has NO `--pivot` flag: the axis IS the profile's `v` axis (Andrzej-decided)

Addendum to the 2026-07-25 00:14 UTC profile-generator entry (D1–D9); spec
`specs/2026-07-25-brush-profile-generators.md` §4.

**D10 — the revolve axis is fixed at `u = 0`** (the profile plane's own `v` axis, passing through
profile coordinate `(0,0)`), and there is **no `--pivot` parameter**. Distance from the axis is
expressed in the profile coordinates themselves: a profile drawn at `u ∈ [64, 192]` revolves at radii
64 to 192. UnrealEd's "move the green pivot away from the cross-section"
(`unrealed/leveldesign/kb/geometry-builders.md` §4) is spelled by drawing the profile away from
`u = 0`.

Andrzej's observation, and it is strictly better than the scalar `--pivot` the spec first carried,
not merely equivalent:

- **A pivot flag is redundant** — with the axis fixed parallel to `v`, shifting the profile's `u`
  coordinates and moving the axis are the same operation.
- **It sharpens the anchor (D4).** Profile `(0,0)` now lies ON the revolve axis, so `--at` is the
  world position of the **bend centre** — the point an author actually wants to place. Under a
  `--pivot`, `--at` anchored some unrelated point and positioning a bend meant carrying the offset by
  hand.
- **It tightens the family.** Extrude and revolve take exactly the same profile, `--axis` and `--at`,
  differing only in `--depth` vs `--angle`/`--segments`.
- **It simplifies validation.** The strictly-off-axis rule collapses to "every `u` strictly positive,
  or every `u` strictly negative".

Cost accepted: a point list authored for an extrude (which typically wants `(0,0)` at a corner) needs
its `u` values re-written to be reused for a revolve.

*Rejected: a scalar `--pivot U`* (the spec's first form) — redundant per the above. *Rejected: a free
in-plane axis, `--pivot U,V` + a tilt angle* — it would allow conical sweeps (a tapering curved duct,
a splayed arch ring) without pre-rotating the profile, but costs two flags, a coordinate that is
redundant whenever the axis is untilted, and a general point-line side test in validation; the same
shapes are reachable by rotating the authored points. Filed as a follow-up if a real use case appears.

**No generality is lost by fixing the axis parallel to `v`.** The profile plane always contains the
revolve axis, and the three `--axis` values give the three possible axis directions: `--axis z`
revolves about Y, `--axis x` about Z, `--axis y` about X. Since the author writes the `(u,v)`
coordinates, transposing them reaches any layout.

## 2026-07-25 00:43 UTC — `actor move` takes a SET (`-`/stdin); `--by` any count, `--to` one actor

`actor move` was the only actor/brush transform verb that could not take a set — single positional
`name`, no `-` — while `actor rotate` and `brush scale` already take `names… | -`. So
`actor find … | actor move -` failed, violating the compose-verbs philosophy. `move` gains the sibling
contract. Spec: `specs/2026-07-25-actor-move-set.md` (two cold reviews, resolved).

**Decision — `move` accepts `names… | -`; the two flags split by arity.**
- **`--by DX,DY,DZ`** (relative delta) applies to **any** count — a rigid translation of the whole
  group; no `--all`/`--set` flag (the set IS the operation).
- **`--to X,Y,Z`** (absolute point) **rejects a set: >1 resolved actor → exit 2** naming the count and
  pointing at `--by`. Moving a set to one point stacks them — the silent half-answer `direction.md`
  forbids. **0** actors is the standard empty-stdin no-op (exit 0); **exactly 1** keeps today's
  behaviour. The gate is checked at **dispatch, after dedupe** (the count is unknown at parse time),
  mirroring `rotate --to` rejecting `--pivot` at dispatch.
- **Dedupe on canonical names** (a repeated name is one actor; `--by` twice would double-move) — so a
  single name piped twice with `--to` dedupes to one and succeeds.
- **No `--pivot`** — translation has no pivot (unlike rotate/scale, which orbit Location about one).
- **No brush re-validation** — move touches only Location, never the local PolyList; movers translate
  rigidly (keyframes are base-relative). The stderr summary unifies to `moved N actor(s)`.

The positional `name`→`names` rename and the `args["name"]`→`args["names"]` save-shape change break
several existing tests; they change outright (unreleased CLI, no compat shim), and the deliberate
"move does NOT accept `-`" test is removed — **this supersedes that earlier choice.**

*Rejected — group-anchor `--to`* (move a set so its centroid / bbox-min / a named actor's Location
lands at the point): a real feature, but with an ambiguous anchor and its own `--anchor` flag surface;
deferred to a follow-up (filed on `board/inbox.md`), not overloaded onto `--to` now. The board item
(consistency-audit H2, `--by`-only for sets) scoped v1 this way.

## 2026-07-25 00:43 UTC — Folder/label stay under `actor`; add `folder list` + `label list` (no top-level promotion)

The board carried a `[spec]` to promote the actor-organization verbs (`actor folder …`,
`actor label …`) into their OWN top-level verb families (`uedcli folder …` / `uedcli label …`).
**Decision (Andrzej): do NOT promote — keep them under `actor`.** They organize actors; `actor` is
where a user looks for them, and a parallel top-level namespace duplicates the query surface
(`actor find --folder/--label` already lives on `actor`). The promote item is closed.

**But add enumeration** — today you can `actor find --folder X` (find actors BY a folder/label) but
cannot ask *what folders/labels exist*. Add two read verbs under `actor`:
- **`actor folder list`** — print the distinct folder paths in use (one per line, sorted; the pipe-
  friendly producer form). Exact output shape (counts? a `--tree` view rendering the hierarchy?) is the
  spec's to settle — see the fresh `to-spec.md` item.
- **`actor label list`** — print the distinct labels in use (labels are flat, so no tree).

Filed as a new `[spec] p2` on `to-spec.md`. *Rejected:* the top-level `folder`/`label` families, and
the `--from-group`/`folder rename`/exact-single-node items stay separately parked (someday/to-spec).

## 2026-07-25 00:43 UTC — `find` vs `search`: a naming RULE, not a rename

The board carried "unify `find`/`search` into one CLI-wide name" (today `actor find`, `brush poly
find`, but `texture search`). **Decision (Andrzej): they are two DIFFERENT verbs by a principled rule,
so nothing is renamed —**

- **`find` = a deterministic query over concrete T3D-TREE STATE** — actors, polys, brushes that
  actually exist in the trunk. Exact match, produces a name/selector SET to pipe into a mutating verb.
  (`actor find`, `brush poly find`.)
- **`search` = ranked / fuzzy DISCOVERY over a catalog or corpus** — textures, the coming asset
  catalog, docs. You are finding out *what exists* by relevance, not enumerating a known set.
  (`texture search`, and the future `catalog search` / `docs search`.)

So `texture search` was correct all along; `actor find` is correct; the fix is to **codify the
distinction as a naming convention** (added to `direction.md` "Explicit, discoverable, model-side" and
the `CLAUDE.md` conventions), not to rename anything. This **pre-decides the Asset-catalog spec's
discovery verb** as `search`. The "unify to one name" board item is closed by this rule.
*Rejected:* renaming everything to `find`, or everything to `search` — either erases a real semantic
distinction (deterministic tree query vs ranked corpus discovery) that the two names usefully carry.

## 2026-07-25 01:40 UTC — Profile-generator spec: cold-review refinements (D1–D10 unchanged)

The two-reviewer cold gate on `specs/2026-07-25-brush-profile-generators.md` (both reviewers, spec
given cold). **No Andrzej decision was overturned** — D1–D10 stand as recorded. What the gate caught
was defects in the spec's own engineering, recorded here because several are engine/CLI facts that
outlive the spec:

- **Per-face outward directions are NOT shared between the two verbs.** The spec gave one rule for
  both; it is correct only for extrude. `builders._face` FLIPS a ring whose Newell normal disagrees
  with the supplied outward hint, so a wrong hint emits a backwards-wound face — `doctor`'s
  "inverted solid → CSG crash / HOM". In a revolve every face is rotated: the far cap's outward is the
  profile tangent rotated by the sweep (for 90°, exactly perpendicular to the extrude hint, so the
  flip is sign-indeterminate AND `_tex_basis` derives texture axes from a non-face normal), and each
  side quad's outward is the in-plane edge normal rotated by its segment's mid-angle. Un-rotated hints
  would invert roughly half a full-turn revolve's side faces.
- **A sweep MAGNITUDE must never be parsed with `rotation.uu_field`/`uu_to_deg`.** Both wrap mod
  65536 because they parse an FRotator *field*, which is inherently modular; a magnitude is not.
  `uu_to_deg(65536) == 0.0`, so the closed full turn would silently become a zero sweep. Sweep angles
  are range-checked on the raw integer, then converted as `uu * 360/65536` with no modulo.
- **`--at` anchoring at profile `(0,0)` changes what `--rotate` pivots about.** An actor's `Rotation`
  applies about its local origin; with vertices authored verbatim, that origin can be far outside the
  brush, so `--rotate` swings the brush through an arc instead of turning it in place. Correct under
  D4, but must be documented in `--help` and `usage.md`.
- **`--at` already had THREE meanings before this work, and its help documents one.**
  `builders.spiral_staircase` anchors at the base of the column axis (centred in XY, bottom in Z), not
  the geometric centre the help claims; `brush intersect`/`deintersect` give `--at` a further sense.
  The help is rewritten to name all of them.
- **A revolve is off-grid by construction** (every vertex off `θ=0` is `r·cos/sin θ`), which
  `kb/csg-bsp.md` §5.5 identifies as the primary BSP-hole cause for a *solid* brush. Hence a stderr
  advisory when an emitted brush is both off-grid and solid, and `--solidity semisolid` guidance in
  the curved-corridor recipe. `cylinder`/`cone` share the property and get a board item.
- **Revolve faces need per-profile-edge `ItemName`s** (`Side<k>`, stable across segments), not one
  `Side`: with a single label, all `n × s` faces of a curved corridor share an item and inner/outer
  walls are both `slant` to `--facing`, leaving no selector for "the inner wall". Extrude matches for
  consistency. Cheap now, impossible later without breaking committed goldens.
- **`TryToMerge`'s gate is on `NV1 + NV2`, applied BEFORE splicing** — not on the fused ring. Two
  9-vertex tiles fuse to a legal 16-vertex ring yet are rejected at `18 > 16`. The spec's coplanar
  merge-back prediction was written against the wrong quantity. It also does not require "exactly one
  shared edge": it takes the first shared point whose forward *or* backward neighbour also matches.
- **`brush build` does NOT run `geometry.validate_brush`** — the dispatch branch validates only class
  and texture existence; geometry validation happens downstream at `actor add` (`writes.py:105`). The
  two profile verbs therefore call it in the builder, a deliberate deviation from the other
  generators, justified by their vertices coming from arbitrary user input (two points 0.4 uu apart
  collapse only after `emit.clean`'s grid snap) and by generator output that can bypass `actor add`
  entirely (`> file.t3d`, `| brush intersect`).
- **Native *materialize* is NOT affected by the concave-brush caveat.** It defaults to `core="bspcsg"`
  (`native/materialize.py:822`), the incremental `bspBrushCSG` port, which never calls
  `point_in_convex`; only the `--native` *preview* uses the coarse core (`csg.rs:62`). `builders.py`'s
  `staircase` docstring states the broader, stale claim and is corrected in the same change. (Caveat
  that does hold: `bspcsg.rs` flags a non-convex *first Add* as unhandled.)
- **"UU divides better than degrees" is false** and is dropped as a rationale for D7 (which stands on
  unit consistency alone). `65536 = 2¹⁶`, so only power-of-two counts divide exactly; every threefold
  division is exact in degrees instead (`360/3 = 120` vs `65536/3 = 21845.33…`). A 60°/120° bend is
  therefore not exactly representable — worth one line in `usage.md`.
- **Non-simple profiles need more than a crossing test.** A ring that revisits a vertex
  (`A B C A D E`) or whose non-adjacent edges merely *touch* passes both a consecutive-duplicate weld
  and a strict crossing test, yet ear-clipping it yields overlapping/inverted pieces silently. The
  test is widened to any non-adjacent intersection (crossing, touching, collinear-overlap) plus any
  vertex repeated anywhere in the ring.
- **Degenerate `--angle`/`--segments` combinations** were unguarded: a facet of ≥180° is flat
  (zero volume, coincident caps), and a full turn in <3 segments collapses. Both now rejected, mirroring
  `spiral_staircase`'s existing `0 < degrees_per_step < 180` guard.
- **Negative-`u` revolve profiles are rejected**, narrowing D10's "one side of the axis" to the
  positive side: the sweep rotation is fixed, so a negative-`u` profile bulges toward `−axis`,
  inverting the shared "the shape grows toward `+axis`" model and every cap hint. Mirror the profile
  instead. (The spec's earlier "or the opposite `--axis`" escape hatch does not exist — `--axis` takes
  `x|y|z`.)
- **A full-turn revolve is genus-1 (a torus)**, which the `staircase` precedent does not cover — that
  is a simply-connected hull. UE1 CSG behaviour on a genus-1 brush is unevidenced in this repo, so it
  is kept but listed for live verification, with two 180° revolves as the fallback.
- **Unevidenced UnrealEd claims marked as such**, per the "every claim carries its evidence" rule: the
  2D shape editor is *one of* two standard methods (the kb documents the native builders in full and
  the 2D editor only under a 📖 heading), "16 pieces = 360°" is 📖-level, and "every 2D-editor
  operation yields one builder brush" — the sole justification for D5 — is Andrzej's assertion with no
  spike behind it, now on the verify-live list.

**Naming correction for the record:** `doctor` has no `check_convex` function. The per-face convexity
test is `_is_convex` (`doctor.py:177`), called inside `check_degenerate`, reporting under
`category="convex"`. Earlier entries in this ledger (2026-07-21/22, the staircase work) use the wrong
name in prose; they are left as written (append-only), and this is the correction.

## 2026-07-25 03:40 UTC — The unified asset catalog: one engine, four kinds (Andrzej-decided)

Andrzej asked to spec a **unified class/texture/sound/music catalog** (session `uedcli:catalog`).
This supersedes the whole of the 2026-07-19 03:58 texture-catalog-redesign entry's *scope* (its
mechanics survive, generalized) and consolidates the `to-spec` ★ Asset-catalog item plus the inbox
annotated-class-catalog item. Spec: `specs/2026-07-25-unified-asset-catalog.md` (review-gated,
2 cold reviewers, all findings folded).

**The decisions (each with what was rejected):**

1. **Per-kind nouns over ONE shared engine.** `texture`/`class`/`sound`/`music` each carry the same
   verb family; "unified" means one implementation, not one noun. *Rejected: a single `catalog` noun
   with `--kind`* — it would delete the `texture` verbs and rewrite every doc and pipe that names
   them, to buy a cross-kind query that is rarely what is wanted. *Rejected: shipping both surfaces*
   — two spellings of one operation is exactly the permanent maintenance surface the no-back-compat
   rule exists to prevent.
2. **The unified spec SUBSUMES the unbuilt texture-catalog redesign.** *Rejected: build the texture
   redesign as specced, then generalize* — it was specced and review-gated but never built, so
   nothing is owed to it; building the storage engine for one kind and refactoring it for four is
   pure waste.
3. **Identity: content-hash where content exists, name where it does not.** Texture → pixel-hash,
   sound → sample-hash, class → `Package.Class`, music → `Package.Name`. *Rejected: name-keying
   everything* — loses cross-package dedup and `classify clone` by identity for textures. *Rejected:
   content-hashing everything* — a class fingerprint over default properties is brittle, and any
   game patch would orphan the curated description. (Music was moved from content-hash to name-key
   during the review gate: `TLazyArray` headers embed ABSOLUTE FILE OFFSETS, so hashing a raw export
   body makes a repacked-but-identical package hash differently and orphan its classification.)
4. **The audio arm rests on how the shipped game USES each asset**, plus the ref name, with a
   spectrogram as a secondary category cue. Rationale: an LLM cannot listen, and a spectrogram
   supports *category* (tonal / broadband / impulsive / speech-like, duration, loopability) but not
   *identity* — "laughing" vs "coughing" is not readable off one. *Rejected: metadata + name only*
   (too thin — guessing from `DXAmbient.WindLoop3`). *Rejected: clip export as the PRIMARY path* —
   human-grade quality, but it makes the human the bottleneck for thousands of assets; it survives
   as an opt-in `sound export`.
5. **Class thumbnails render NATIVELY, not through the game container.** Settled by spike
   `2026-07-25-native-mesh-decode` (below). *Rejected: the specced container render harness* (temp
   level, one subtract box per actor, materialize, deliver into the warm `preview --game`
   container) as the thumbnail path — it remains available for real-lighting hero shots. The open
   "can DeusEx render fullbright" spike is thereby **moot for thumbnails**: a native render controls
   its own lighting by construction.
6. **`show` (metadata) and `preview` (image artifact) are SEPARATE VERBS** on every kind. This
   matches the existing `actor preview`/`level preview` naming, and it dissolves the `class show`
   collision outright — `class show` keeps its UnrealEd property-browser view and `--category` keeps
   meaning the property category. *Rejected: one `show` with a `--preview` flag* — overloads one
   verb with two output shapes and stays ambiguous for kinds with several or zero artifacts.
7. **Only `preview` produces artifacts.** `list`/`search --json` report `preview: <path>|null` for
   already-cached artifacts only. *Rejected: rendering inline for "cheap" kinds* — a per-kind
   asymmetry the caller must memorize, and measurement showed a cold catalog-wide `class list
   --json` would have rendered 657 meshes inline (~11 min) on an agent's first exploratory command.
8. **`classify set -` reads JSONL from stdin** (`{ref, tags, description}`), one shard write per
   row, mirroring `actor add -`. A cold invocation is ~0.3 s, so per-ref processes make classifying
   thousands of assets process-bound and turn-bound rather than compute-bound. *Rejected: single-ref
   writes only.*
9. **Cache eviction goes on the EXISTING `cache` noun** (`cache gc`), already planned in
   `schema_cache.py`, sweeping every derived sub-cache including catalog previews. *Rejected: a
   `catalog gc` verb* — a second maintenance surface over one cache root, and it would reintroduce
   the `catalog` noun decision 1 rejected.
10. **No curated "role"/"category" taxonomy for classes.** Andrzej: *the superclass already makes it
    clear what a class is for* (`ScriptedPawn`, `Decoration`, `Weapon`, `Mover`), and
    `--subclass-of` already exists. "Commonly placed" is likewise **derived**, from a stock-map
    placement histogram over 157,898 real actors, rather than hand-curated. Curation collapses to a
    **description plus overrides where the derived answer is wrong**. *Rejected: curating a role
    taxonomy over ~1,900 classes* — redundant with the hierarchy and a standing maintenance burden.
    This also avoids a second meaning for `--category`.
11. **`class preview` angles:** `iso` (front-¾) is the default SINGLE shot; `--angles` opts into
    `front, back, left, right, top, bottom, iso`. **"side" is deliberately spelled `left`/`right`**
    — a mesh is not symmetric in general. One angle by default because a render measures ~300 ms,
    not the ~20 ms first assumed. *Rejected: 3 angles always* (~11 min to prewarm the mesh classes).

**Corpus-scope facts that shaped the design** (measured during the review gate, cited so they are
re-verifiable): Sound exports on the composed path total **10,826** — only 151 in `.uax`, 399 in
`DeusExSounds.u`, ~10,200 conversation VO — so "sounds live in `.uax`" is wrong and "every package"
is unusable; the rule is `.uax` + `.u` minus conversation-audio packages (≈550). Texture
enumeration must follow **descent from `Engine.Texture`**, not an exact class match, or 49 stock
`FireTexture`/`WetTexture`/`WaveTexture` surfaces are invisible. The stock-map sweep and class
defaults find **202** and **236** distinct sound refs respectively with little overlap — neither
half suffices, because UnrealEd omits any property equal to the class default.

**Prerequisite made explicit:** uedcli **cannot read map actor bodies today** — `dxpkg.parse_header`
reads only name/import tables, and bodies need the `RF_HasStack` StateFrame skip that currently
lives in a spike harness and is scoped into the unbuilt `level import` spec. The usage index is
gated on promoting that reader into `uedcli/`, jointly owned with `level import`.

## 2026-07-25 03:40 UTC — UE1 meshes decode and render natively; `umodel.exe` is not needed to READ a mesh

Andrzej asked, while speccing the catalog's class arm, whether we can decode how Deus Ex / Unreal
store meshes and render them ourselves — instead of driving the OG Deus Ex UnrealEd or reverse-
engineering the stub pipeline's `umodel.exe` export. **Answer: yes, directly; neither fallback is
needed.** Spike `spikes/2026-07-25-native-mesh-decode/`, regression `tests/test_mesh_decode.py`.

The complete `UMesh`/`ULodMesh` body decodes in pure Python, verified **consume-to-exact-end on 902
meshes** (466 retail Deus Ex v68 + 436 UED22 v69) with zero failures, and renders textured
thumbnails offline (z-buffered, affine-UV, Pillow-only). `Keypad3` decodes to 18 wedges / 10 faces,
matching umodel's recorded ground truth.

**The consequence for the catalog** is decision 5 above: class thumbnails need no editor, no
container and no `umodel.exe`. `umodel.exe` survives only inside the stub pipeline it already
serves.

**Findings that are standing facts** (each pinned by a test, detail in the spike):
- The **vertex stride is self-describing** via the `Verts` TLazyArray's skip offset — 8 bytes
  (Deus Ex `int16 X,Y,Z,pad`) vs 4 (stock Unreal packed dword). So ONE decoder serves both with no
  per-substrate flag, which is what the generic-UE1 direction needs.
- `FMeshAnimSeq.Group` is a **single FName**, not UT's later `TArray<FName> Groups`, and the
  serialized order puts **`Notifys` before `Rate`**.
- `UMesh` re-serializes its own bounds **inline** after `Connects`; the per-frame bounds are plain
  `TArray`s, not lazy arrays.
- **`SpecialVerts` sit at the FRONT of each frame** — a wedge's `iVertex` is relative to
  `frame_base + SpecialVerts`. Decorations have 0, so they render correctly without it; the bug
  appears only on meshes with attachment points, and appears as a shredded spike-ball rather than an
  obviously-shifted mesh.
- The 5-byte `ULodMesh` tail is **stock UE1, not a licensee addition** — the UT-lineage v69 packages
  carry it too. Its INT equals `FrameVerts` in retail v68 but is 0 in the v69 stubs, so only the
  field's PRESENCE is invariant; a decoder must not validate on the value. *(This corrects the
  spike's own first reading, which the v69 cross-check disproved.)*
- **Class thumbnails take their skins from CLASS defaults** (`MultiSkins[i]`/`Skin`), not the mesh's
  own `Textures` array — Deus Ex characters carry none (32/100 resolve mesh-side, vs 178/178 for
  decorations).

## 2026-07-25 02:30 UTC — Profile-generator BUILD PLAN: cold-review refinements + D11/D12

The two-reviewer cold gate on `plans/2026-07-25-brush-profile-generators-plan.md`. Two new decisions
(D11, D12) plus corrections the gate forced. **No Andrzej decision was overturned** — D1–D10 stand.

**D11 — the builder-angle units retrofit narrows the CLI SURFACE ONLY; `builders.py` signatures are
untouched.** `cylinder`/`cone` keep `angle_offset: float` (degrees) and `spiral_staircase` keeps
`degrees_per_step: float`; only `cli.py`/`dispatch.py` change. **Why:** four call sites pass those
parameters by keyword to produce goldens captured against the REAL editor —
`tests/builder_parity_cases.py:87` (`angle_offset=30`), `:95` (`angle_offset=25`), `:100-101`
(`degrees_per_step=30|45`), and `native/csg_golden.py:88` (`angle_offset=15`). Three of those offsets
are **not** half-segments, so they cannot be expressed as `--align-to-side` at all. *Rejected:
renaming the builder parameters* (spec §7's first form) — it would force an editor re-bless of the
parity goldens for zero user-visible gain, and "degrees" is an accurate name for a degrees-valued
internal API.

**D12 — the spiral's USER-FACING range check moves to the CLI/dispatch boundary in UU; the builder
keeps a defensive one in degrees.** `builders.py:373-375` currently raises `"spiral staircase needs
0 < degrees_per_step < 180, got …"`; post-retrofit that names a deleted flag in units the user never
typed. Dispatch checks `0 < angle_per_step < 32768` UU naming `--angle-per-step`; the builder's guard
stays as an **internal-API** error naming the parameter, because D11 leaves four direct callers.
Consequence recorded because it is easy to lose: the retained guard is unreachable from the CLI, so
the build gate must call `builders.spiral_staircase(..., degrees_per_step=200)` **directly** — an
unreachable, untested guard is a second thing to keep true with nothing enforcing it.

**Corrections the gate forced (spec amended in the same change):**

- **The revolve NEAR-cap outward direction does NOT rotate — spec §5.7 was wrong.** It gave the near
  cap as "the profile-plane tangent at `θ=0`, not `−w`", spelled `−v̂ × t̂(0)`. Wrong twice: the sweep
  tangent at `θ=0` **is** `+ŵ`, and that cross product evaluates to `−û` in a right-handed frame.
  Under the sweep map the `θ=0` cap lies in the `(û,v̂)` plane with the solid growing toward `+ŵ`, so
  its outward is `−ŵ` — **identical to extrude's**. Only the far cap (`+ŵ` rotated by `angle`) and the
  side quads (by segment mid-angle) rotate. As originally written, `_face` would have inverted the
  near cap and `_tex_basis` would have derived texture axes from a non-face normal. Both reviewers
  caught this independently. It also corrects the mutation test: feeding extrude hints must NOT make
  the near cap fail, and a full-turn revolve omits both caps, so cap hints are only exercised by
  partial sweeps.
- **Profile coordinates are `Decimal` for validation and `float` at the builder boundary.**
  `builders._newell` starts at `0.0` and raises `TypeError` on the first Decimal×float side quad (cap
  faces survive, side quads die); revolve is trig and cannot stay exact. Nothing is lost:
  `emit.clean`'s `_to_decimal` is `Decimal(str(value))`, so a float round-trips to the authored
  decimal.
- **`ProfileError` must subclass `geometry.GeometryError`.** `dispatch()`'s handler chain
  (`dispatch.py:3071-3105`) has no bare `ValueError` arm, so a plain `ValueError` subclass tracebacks
  — failing the very "exit 2, no traceback" rule it exists to satisfy. Relatedly, the `--point` token
  parser must be called **from dispatch, not as an argparse `type=`**: argparse catches `ValueError`
  and replaces the message with `invalid parse_point value: …`, destroying the mandated wording.
- **`profile.py` owns `WELD`, not `builders.py`.** `builders.WELD` is defined *below* its import
  block, so `profile` importing it while `builders` imports `profile` is a load-time cycle that breaks
  every `uedcli` invocation. Where `builders` needs `profile`, use a function-local import (the
  pattern already at `builders.py:256`, `:458`).
- **The off-grid advisory must be gated on shape AND on non-mover.** Ungated in the shared
  `brush build` branch it turns `tests/test_generators.py:281-286` red — that test builds a solid
  8-gon cylinder (inherently fractional vertices) and asserts stderr is empty. And a mover lands on
  `poly_flags == 0` because it rejects `--solidity`, so it would draw a BSP advisory although a mover
  never partitions the world.
- **Docs land in the commit that changes the behaviour**, not in a trailing sweep. Deferring them
  would leave `usage.md`/`brush-shapes.md`/`octagonal-column.md` documenting `--angle-offset` and
  `--degrees-per-step` after argparse stopped accepting them — the exact stale-help bug class
  `direction.md`'s "No back-compat cruft" cites as its motivation.
- **`writes.py:105` is DEAD CODE** — `writes.add_actor` has no callers. The live `actor add` geometry
  validation is `dispatch.py:1995` inside `_ingest_actor_t3d`. Any doc citing the former is wrong.
- **The cube-oracle test needs an explicit normalization**: `cube` is origin-centred while extrude
  sweeps `0..depth`, so raw vertex sets can never match — translate by `−depth/2` along `--axis`
  first, and pin the per-axis dimension mapping (for `--axis y`, `u→Z` and `v→X`).
- **`Side<k>` numbering is not rotation-invariant.** Winding normalization makes *exact reversal*
  invariant, but a clockwise spelling starting at a different vertex normalizes to a cyclic rotation,
  renumbering every `Side<k>`. Since the numbering is user-visible and frozen by a committed golden,
  this is documented as a property rather than discovered later.
- **The new builders get no editor-blessed parity oracle.** All six existing shapes are pinned by
  `builder_parity_cases.py` against real-editor captures; the profile verbs' goldens are self-blessed
  and pin **drift, not correctness**. A parity case needs the gated integration run — recorded as a
  follow-up so nobody assumes coverage that does not exist.
- **Seven six-shape lists exist in the tree, not four** — the spec's doc sweep missed
  `builders.py:1-2` (module docstring), `docs/README.md:86`, `architecture.md:89`, and two recipe
  indexes; `recipes/shapes/README.md` additionally asserts `cylinder --sides N` is "the only way to
  get anything round", which `revolve` falsifies.

## 2026-07-25 05:10 UTC — The tool does NOT infer: uedcli is a faithful data layer, the LLM supplies meaning (Andrzej-decided)

Mid-review of the unified asset catalog, Andrzej rejected the direction BOTH review rounds were
pushing — that the tool should compute more about assets — and set the governing principle for the
whole catalog: *"Why does the tool work anything out by itself? It should be passed classification
data, that's it! The LLM will figure out where assets are used and what they are!"*

**The principle.** uedcli does exactly four things: **lists** what exists on the composed search
path; **reports facts literally stored in the package** (image dimensions, mesh bbox, collision
radius/height, pivot, parent class, `DrawType`); **produces the picture** (decodes a texture, renders
a mesh); and **stores + queries the classification it is handed**. It never infers meaning — not what
an asset is for, not where it is used, not whether it is "commonly placed", not how relevant one
asset is to another. The LLM looks, investigates, decides, and hands the answer back.

**What this DELETED from the spec:** a tool-computed stock-map usage index (sweeping 120 maps for
sound/music refs), a class placement histogram over 157,898 actors, a derived "commonly placed"
signal, a curated-vs-derived override model for `placeable` — and, with them, an entire build
prerequisite (a native map-actor reader with the `RF_HasStack` StateFrame skip). *Rejected
explicitly*, not deferred: a number the tool computed is unreviewable and uncorrectable, whereas an
LLM's finding recorded in a description is durable, reviewable and fixable. `placeable` therefore
keeps ONE definition — the existing file-fact proxy (non-abstract, descends from `Actor`) — with its
help text corrected to say exactly that instead of implying judgement, which also keeps `class list`
offline, maps-free and ~0.4 s.

**The single deliberate exception: texture colours.** The tool pre-fills a small fixed palette of
base colour names per texture, **ordered by importance** (descending share), because it reads nothing
but that texture's own pixels — reading the file, not scanning the corpus — and because it makes
`texture search --color brown` useful on a fresh clone *before* any classification exists. An LLM
classification overrides it (`colors_source: "set"`) and the override wins.

**The corollary that reverses a review finding.** Two cold reviewers measured the existing
`texture-catalog/` — 4,791 entries, **0 classified**, untracked by git — and concluded that nobody
will ever classify, recommending less classification machinery. That is backwards: nothing has been
classified because nothing ever made it possible (there is no way to SEE a texture today).
Classification is not a side feature that may stay empty; it is the product, and the verbs that write
and read it are the core. What the measurement DOES settle is decision 13 below.

**Two further decisions from the same round:**

- **No migration; the legacy catalog is deleted.** `texture-catalog/` holds no authored data and is
  untracked, so a `texture migrate` verb, its convert-before-move ordering contract, a
  hash-equivalence regression and four test bullets would all protect regenerable cache data.
  Deleted outright per the no-back-compat-cruft rule; colours re-derive from pixels on demand.
  *Rejected: a defensive migration that converts only non-empty entries* (today: zero).
- **The contact-sheet ban STANDS.** *Rejected: an opt-in indexed sheet* (`preview --sheet N` with
  numbered cells + JSONL keyed by cell index), proposed to cut the agent's per-asset image-read
  context cost. Misattribution is the failure mode that silently corrupts a catalog, and a numbered
  grid still depends on the model reading cell numbers correctly. One asset, one image file.
  Classification-as-byproduct (`preview --skeleton` emits a fill-in row for exactly the refs just
  previewed) is the answer to volume instead of a bulk campaign.

**Build order set value-first** (Andrzej): (1) engine + enumeration + `list`/`show` + ObjectProperty-ref
validation — which fixes a live bug that silently ships broken levels; (2) class arm; (3) texture arm;
(4) audio phase (a); (5) audio phase (b). *Rejected: texture-arm-first* — its justification was the
migration that decision 13 dissolves.

**Sound and music are name-keyed** (`Package.Name`), not content-hashed — resolving the open question
the first gate left. `.uax` decoding is unresolved, so a content key would leave phase (a) with no
identity at all, and adopting one later would re-key and orphan every tracked sound shard. Music
cannot be content-keyed regardless: `TLazyArray` headers embed absolute file offsets, so a
repacked-but-identical package hashes differently. Textures keep the pixel-hash, which earns its
keep through cross-package dedup and `classify clone`.

## 2026-07-25 02:15 UTC — The H3 post-verify compares TYPED effective values, not canonicalized text; contraction is deleted

**Decision (Andrzej).** The compare seam stops *canonicalizing text* and starts *comparing values*.
Every property of both compare sides resolves to its **effective typed value** — the stored value if
the actor states one, else the class default — decoded according to the property's **declared type**
from the offline-decoded schema. Two actors are equal iff they would import to the same object. The
class-default **contraction** introduced eight hours earlier (2026-07-25 00:36 UTC, below) is
DELETED, not kept alongside: `normalize.contract_actor`, `normalize._is_all_zero_struct`,
`classdefaults.values_equal` and `rotation.canonical_rotation_value` are gone (no-back-compat-cruft
rule — one mechanism, never two).

**Why (Andrzej's reasoning).** Contraction *tolerated* a spelling mismatch with a numeric equality
predicate: `values_equal` had to be told that the text `4.0` and the text `4` mean the same thing.
If the values are parsed **type-aware** they simply ARE the same value, and a whole class of
problems dissolves instead of being papered over. Everything the contraction rules enumerated —
whole-property equality, the `Rotation` member fold, the all-numeric-zero struct rule, the
`Location` rule — falls out of one uniform rule (effective value per property, member-wise expansion
per struct), and three defects it could not reach are fixed by construction:

1. **`4.0` vs `4`** — a `FloatProperty` compares numerically (and at float32, the precision UnrealEd
   stores every float at), so no text predicate is needed.
2. **Absent means DEFAULT, not zero** — `parse_t3d` filled an omitted `Location` axis with 0, so an
   `Engine.Camera` export `Location=(X=100,Y=200)` (default `(X=-500,Y=-300,Z=300)`) ingested as
   Z=0, silently dropping 300 uu. A struct now expands member-wise from the class default.
3. **Zero-valued scalars/bools** — contraction deliberately skipped them, because `parse_t3d`
   discards quoting and dropping anything that merely *reads* as zero could hide a real difference;
   so `actor prop set X LightRadius=0` then `level materialize` ABORTED. The type's zero now comes
   from the **schema** (`ByteProperty` → `0`, `StrProperty` → `""`), which distinguishes them
   exactly.

**Layering (a hard constraint, not an implementation detail).**
- `model.parse_t3d` stays **schema-free** — it is also the trunk, stash, prefab and
  generator-snippet reader, and generators run with no project context, so they cannot resolve a
  schema. What it changed is only to stop DESTROYING information: `Actor.location_text` records the
  verbatim `Location=` text beside the (still 0-filled) numeric triple the geometry math needs. It
  is **self-invalidating** — trusted only while it still parses back to the current `location` — so
  a mutation automatically reverts the compare to "all three axes stated" and no mutation site has
  to remember to clear it. *Rejected: making `location`'s axes optional* (ripples through bbox,
  preview, transforms and CSG); *rejected: a presence flag maintained by every mutation site* (one
  forgotten site is a silent wrong compare).
- The typed layer sits **above** parse, at the compare seam only: `typedprops.py` is pure value
  semantics (a `Field` type tree + the text→value decode, no packages, no resolver), and
  `classdefaults.ClassDefaults` compiles the decoded `.u` schema + defaults into it, memoized per
  class over ONE shared package map (the whole perf story: each distinct class resolves once).
- `canonical_actor_t3d` (durable trunk emit + `MAP IMPORT` payload + `actor show`) and
  `canonical_level_hash` (the preview build-cache key) stay **byte-identical and schema-free**.

**Kept from the contraction design, because they are still right:** no zero fallback (an
unresolvable class exits 2 naming the actor, resolved BEFORE the editor container is created); the
`Tag=<bare class>` default-stamp drop, guarded on the class not defaulting `Tag`; the write-side
rule that uedcli never omits a property to mean zero.

**Also fixed on the way (they were separate `board/inbox.md` items):** the general
member-diff-against-class-default for EVERY struct property (`PrePivot`, `RotationRate`,
`MainScale`, `KeyPos(i)`…), not just `Rotation`; and an enum compares by ORDINAL, so the T3D enum
NAME and a struct-member default that `uprops` decodes as a raw byte (`SheerAxis=0` vs `SHEER_ZX`)
are one value.

**Diagnostic.** `verify._first_diff` still names the actor, and now names the differing PROPERTY
plus both sides — each shown as the text it authored or, when it omits the line, as the class
default it therefore resolves to ("`LightRadius` omitted (class default 64)"). A line number would
be meaningless once the compare is over values rather than text.

**Refs:** `typedprops.py`, `classdefaults.py`, `normalize.compare_view`/`_actor_values`,
`model.Actor.location_text`, `verify._first_diff`, `unrealed/t3d.md` "Partial struct/array property
values", `test_typedprops.py`, `test_normalize.py`. Supersedes the contraction MECHANISM of
2026-07-25 00:36 UTC (its no-fallback, write-side and Tag-stamp decisions stand).

## 2026-07-25 03:07 UTC — mover `SavedPos`/`SavedRot` are stripped as computed, NOT authored into the trunk

**Decision.** `normalize.COMPUTED_PROPS` gains **`SavedPos` and `SavedRot`**, joining
`BasePos`/`BaseRot`. `SavedTrigger` is deliberately **not** added.

**Problem.** `level materialize` (and `preview --game`'s internal build) aborted on *every* map
containing a mover: the rebuilt map's re-export carries two properties the authored T3D trunk never
emits — `SavedPos=(X=-12345.000000,Y=-12345.000000,Z=-12345.000000)` and
`SavedRot=(Pitch=123,Yaw=456,Roll=789)` — and neither is a class default, so the typed compare read
"trunk `(0,0,0)` / built map `(-12345,…)`" and the H3 post-verify refused to write.

**Why they are computed, with evidence.** `AMover::PostLoad()` overwrites both with those exact
constants on **every load of a Mover object**, unconditionally — no guard, no test of the stored
value, right after `Super::PostLoad()`. Disassembled by name out of both shipped engines (UED22
`Engine.dll` `?PostLoad@AMover@@UAEXXZ` @ RVA `0x171140`; the DX-shipped `Engine.dll` @ `0xaf7e0`).
So no authored value can survive a round trip. Corroborated by the corpus: **487 `SavedPos` and 487
`SavedRot`** lines across the git-tracked editor exports, **exactly one distinct value each** over
three Mover-derived classes — against 224 distinct `BasePos` values, the control. (651 each if the
gitignored `_scratch/` working copies are counted; 487 is the number a later reader can reproduce.)
Every retail map that holds a mover — 81 of the 130 `DX/Maps` map files — carries the sentinel at
exactly 3 floats per rotator, one per mover (6861 / 2287 overall, ratio 3.00). Confirmed end-to-end live
(2026-07-25): a `brush build`-authored mover materializes to a `.dx` holding **no** sentinel bytes,
yet the post-verify's own offline UCC re-export of that same file comes back carrying **both** — so
the injection happens at the reader's package load, exactly as `PostLoad` predicts, and with the
strip `level materialize` now passes and writes the map. Spike:
`spikes/2026-07-25-mover-savedpos-savedrot-engine-stamped/findings.md`.

**Rejected: author the sentinels into the trunk** (`actor prop set <mover> SavedPos=…` per mover),
the workaround that originally confirmed the diagnosis. It writes engine *runtime* state into the
durable git-tracked source of truth, has to be repeated for every mover forever, and encodes a magic
constant that belongs to the engine build rather than to the level. The `Saved*` family is build
output in the same sense as lightmaps and BSP (`direction.md` "Lighting and BSP are build output").

**Rejected: adding `SavedTrigger` at the same time — and it must NEVER be added.** `COMPUTED_PROPS`
is keyed by BARE NAME across every class, and `Engine.TriggerLight` declares its own `SavedTrigger`
(it is a placeable Actor: `TriggerLight -> Light -> Actor`). Adding the name would therefore silently
strip a real authored property from every TriggerLight on the durable trunk emit — the exact class of
bug this ledger already records twice. It also buys nothing: `PostLoad` never touches `SavedTrigger`
and it appears zero times in the corpus, so it cannot cause a mismatch. A test pins the exclusion so
that adding it later has to be a deliberate act with evidence attached.

This makes the bare-name keying a standing constraint on the set: **a name may be added only when
stripping it is right for EVERY class that declares it.** Audited for this change — `SavedPos` is
declared by `Engine.Mover` alone; `SavedRot` also by `DeusEx.LaserIterator`, which descends from
`Core.Object` rather than `Actor` and so can never appear in a level T3D. Both additions are exact.

**Two adjacent suspicions from the bug report, checked and DISPROVED.** `bDynamicLightMover` and
the `KeyPos[]` array were flagged as possibly injected too. A live materialize of a mover carrying
`NumKeys=3`, `KeyPos(1)=(Z=112)` and `bDynamicLightMover=True` re-exports all three **verbatim**:
they are authored content and must NOT be stripped. The mover injected-field set is therefore closed
at `BasePos`, `BaseRot`, `SavedPos`, `SavedRot`.

**One downstream consequence, deliberately accepted.** A trunk INGESTED from a retail map carries
`SavedPos`/`SavedRot` lines today (they were serialized into the shipped `.dx`); after this change
its emit omits them, so a byte-diff of a re-materialized retail map against the original will differ
in those two properties. That is correct — `PostLoad` restores the sentinel on load, so the objects
are identical — but it is worth knowing before the native build's byte-identity work reads such a
diff. It also changes `canonical_level_hash` for those trunks, which merely invalidates a cached
preview `.dx` (one rebuild, never a wrong map — the hash errs strict by design).

**Safety of stripping on the WRITE side.** `normalize_actor` also feeds the durable trunk emit and
the `MAP IMPORT` payload, where an omitted property means "use the class default" — the trap that
silently mis-built an `Engine.Camera` and a `TNM.Trestkon` `Tag` (2026-07-25 02:15 UTC). Here the
class default is the type zero and `PostLoad` overwrites zero with the sentinel on the very next
load, so the omission is unobservable by construction.

**Refs:** `normalize.COMPUTED_PROPS`, `movers.py`, `unrealed/t3d.md` "Authored-vs-computed field
taxonomy", `test_engine_facts.py::test_amover_postload_unconditionally_stamps_the_savedpos_savedrot_sentinels`,
`test_normalize.py` (three new regressions).

## 2026-07-25 03:05 UTC — UnrealEd's 2D shape editor yields ONE brush: attested, not open (Andrzej)

Closes the last open question behind **D5** (`brush build revolve` emits one brush, not one per
segment — 2026-07-25 00:14 UTC).

**Andrzej, from direct UnrealEd use (2026-07-25): every 2D-shape-editor operation — extrude, revolve,
sheet — produces the single red BUILDER BRUSH, faceted, which you then Add/Subtract once.** It is not
one brush per facet or per segment.

The plan-review addendum (02:30 UTC) had this on the verify-live list, on the grounds that no spike or
kb entry covered what the 2D editor emits and D5 rested on it. **It is now closed as an attested
engine fact, not by a spike.** Recorded durably in
`unrealed/leveldesign/kb/geometry-builders.md` §4 tagged **✅** with explicit provenance ("Andrzej,
from direct UnrealEd use, 2026-07-25"), because the spec and plan that currently carry it are both
ephemeral.

**Provenance note for the confidence-marker scheme.** `CLAUDE.md` defines ✅ = uedcli-used /
live-verified, 🔬 = live-probed, 📖 = extracted from the binary string table. Andrzej's own hands-on
knowledge of the editor is none of those three literally, and it is stronger than 📖. It is filed as
✅ **with the human attestation spelled out inline**, so a later reader knows exactly what backs it
rather than assuming an automated verification exists. If author-attested facts become common, a
fourth marker is worth adding to the scheme — flagged in `inbox.md`, not decided here.

Still open on this feature (neither blocks the build): the cap merge-back prediction (spec §6.1) and
whether UE1 CSG handles a full-turn revolve's genus-1 torus (spec §4.7).

## 2026-07-25 06:30 UTC — Texture decode derives layout from the DATA; no per-game format table (Andrzej-decided)

Andrzej: *"We should support all UE1 formats!"* — then, on being offered a design that read each
game's `ETextureFormat` enum out of its `Engine.u`: *"I think `.u**` format is universal and should
be read from any other engine. We should make that work WITHOUT USING ANY SUCH TABLE if that means
it won't be universal for any texture file."* Spec:
`specs/2026-07-25-native-texture-formats.md` (review-gated, 2 cold reviewers).

**1. Layout is derived from the data; a format table is never required.** The mip chain is
self-describing: block-compressed formats store `ceil(w/4)×ceil(h/4)` blocks so their mips **floor**
at one block, while linear formats scale to `w×h×N`. Measured: a `Format=7` texture's 2×2 and 1×1
mips are **16 bytes each**, where P8's are **4 and 1** — both are 1.0 bytes/px at mip 0 and thus
indistinguishable there, but the tail of the chain separates them decisively. The numeric `Format`
code is read and reported as a hint and a diagnostic label, never as the authority.
*Rejected: reading `ETextureFormat` from each game's `Engine.u`* — it makes decoding depend on
having that game's code package, so a lone `.utx` from an unknown engine would not decode, which
defeats the universality that is the entire point. *Rejected: hardcoding one game's table* —
measured wrong across installs (below). This is the same shape of finding as the self-describing
mesh vertex stride (2026-07-25 03:40): the file already tells us, if we look.

**2. Slot numbers are NOT portable — the evidence that killed the table.** `ETextureFormat` dumped
from three installs on this machine: **Unreal Gold v69** `0 P8, 1 RGB32, 2 RGB64, 3 DXT1, 4 RGB24,
5 RGBA8, 6 DXT3, 7 DXT5`; **UED22/227** `0 P8, 1 BGRA8_LM, 2 R5G6B5, 3 BC1, 4 RGB8, 5 BGRA8, 6 BC2,
7 BC3, 8 BC4…`; **Deus Ex v68** five slots only, `0..4`. **Slot 2 is 8 bytes/px in Unreal Gold
(`RGB64`) but 2 bytes/px in 227 (`R5G6B5`)** — a hardcoded table would mis-slice real data and then
emit a *bogus* "size mismatch", turning an honest-failure story into a wrong diagnosis. Both
authorities also settle that **7 = DXT5/BC3 and 6 = DXT3/BC2**, corroborated by the observed alpha
block `0005ffffffffffff` (the textbook BC3 opaque block).

**3. Implement the measured layouts now — P8, BC1, BC2, BC3, and the `CompMips` array.**
*Rejected: implementing the unsampled linear slots from their definitions* — no samples exist
anywhere on this machine and the slot meanings disagree across installs, so a guess returns a
plausible **wrong image** (swapped channels) instead of an error, against "never a wrong pixel".

**4. The remaining layouts get a `p1` board item to spike and implement** (Andrzej) — acquire real
samples first, verify, then implement. Until then an unrecognised layout is a named
`unverified-format` error that carries its own uncertainty.

**5. `bHasComp`/`CompFormat`/`CompMips` — and a correction to the record.** `UTexture` serializes
**two** mip arrays; the second holds a compressed copy of the same image. This is the true cause of
every "trailing bytes" decode failure (147/147, parsing exactly to EOF). **A claim in the first
draft of this spec — "Deus Ex is 100 % P8, so this work buys nothing on the project's own
substrate" — was FALSE**, and the priority call was taken partly on it: **30 of the failures are in
`LUM/Textures/LUM_CoreTex.utx`, the project's OWN authored texture package**, invisible to uedcli
today and drawn as a checkerboard by the preview renderer. The correction argues *more* strongly for
the work. Prefer `Mips` (the higher-fidelity original) over the lossy `CompMips`.

**6. A second, unrelated trailing-bytes cause: `FireTexture`** stores `TArray<FSpark> Sparks` (8
bytes/spark, matching `NumSparks` exactly) — 208 more failures in Deus Ex, 153 in Unreal. A first-draft
claim that "all failures are class `Texture`, so this is not a subclass problem" was a **tautology**
of a sweep that could only match `class == "Texture"`.

**7. Errors are a typed result from the decode layer; the CLI chooses the disposition.**
*Rejected: "every failure exits non-zero"* — it contradicts the asset catalog's requirement that an
undecodable asset stays enumerable, and would stop a whole map preview because one odd texture
exists (`preview_native.py` degrades to a checkerboard by design). Per-ref requests exit 2;
enumeration records an `undecodable` row; preview degrades and warns.

**8. Testing must not be circular.** A synthesized fixture only proves the decoder agrees with our
own encoder. Two independent oracles exist and are used instead: the **`CompMips` pairs** (147
textures storing the same image as both P8 and DXT1, encoded by the original tools — measured mean
absolute error 0.58/255) and **Pillow's DDS decoder** (already the venv's sole dependency).

## 2026-07-25 10:20 UTC — The profile verbs rely on `actor add`'s validation; the "0.4 uu collapse" premise was FALSE (Andrzej-decided)

Drops spec §5.8 of `specs/2026-07-25-brush-profile-generators.md` (the "geometry validation runs in
the builder — a deliberate deviation" section), and with it the last open confirm on that spec.

**The factual error that motivated §5.8.** The spec claimed the two profile verbs need
`geometry.validate_brush` inside the builder because "two authored points 0.4 uu apart collapse onto
each other after `emit.clean`'s grid snap". **`emit.clean` does no such thing.** It snaps a coordinate
to the nearest integer **only when within `CLEAN_EPS = 0.001`** of it, and preserves anything further
at 6-dp precision — deliberately, per its own comment: "Brushes — typically semisolids — can carry
fractional vertices, and the editor itself emits them (e.g. `-479.999969`); we only clean the sub-grid
noise, never force real fractions onto the grid." `geometry.py`'s `_check_coincident` says the same in
as many words — "genuine sub-grid-distinct corners (0.4 apart) do **not**" coincide — and the spec's
`0.4` was lifted from that comment with its meaning inverted.

The residual real case is far narrower: two vertices within ~0.002 of each other **and straddling an
integer** (e.g. `15.9995` / `16.0005`, both snapping to `16`). `builders._dedup_ring` already welds
*consecutive* vertices closer than `WELD = 1e-3`, so what remains is a **non-adjacent** pair
straddling an integer — unreachable by hand, and conceivable only from a computed profile.

**Decision: the profile verbs validate nothing extra; geometry is checked where it always was.**
`brush build` (every shape) and `brush intersect`/`deintersect` validate only class + texture existence
(`_validate_ingest_actors`); geometry is validated when it ENTERS THE TRUNK at `actor add`
(`dispatch.py:1995`, inside `_ingest_actor_t3d`) and on the trunk-mutating verbs (`clip`, `replace`,
`vertex move`, `bake`) plus at materialize. **The whole generator family stays uniform.**

**Why dropping costs nothing.** Trace the failure: `brush build extrude --point … | actor add -` on
genuinely degenerate geometry still exits 2 with the *identical* message, because it is the same
function and `brush.model_name` is still the constant `"Model"` at builder time either way. The only
difference is which stage of a one-line pipeline prints it. The single real gap is output that never
reaches `actor add` (`> shape.t3d`, or `| brush intersect`) — a rare path. Meanwhile `builders._face`
already raises on <3 distinct vertices and zero-area faces at build time, so obvious degeneracy is
caught in the builder regardless.

*Rejected: the two-verb exception* (what §5.8 specced) — two verbs validating while `cube`,
`cylinder`, `spiral` and `intersect` do not is exactly the family inconsistency the CLI conventions
exist to prevent, and it was justified by a false premise. *Rejected: applying validation
family-wide* (one call in the shared `brush build` tail + the intersect tail) — defensible, and the
clean way to get early geometry validation if it is ever wanted, but it is a behaviour change to four
existing verbs and has no business riding inside a new-feature build. Filed as an `inbox.md` question
instead.

## 2026-07-25 11:20 UTC — Addendum to "texture decode derives layout from the DATA" (2026-07-25 06:30): three measured corrections

Planning that decision (`plans/2026-07-25-native-texture-formats-plan.md`) re-measured its premises.
**The decision stands** — no per-game format table is required, and the `Format` code is only ever a
tiebreaker between data-fitted candidates — but two of the claims supporting it were overstated and
one was simply wrong. Recorded here because the spec is ephemeral and these are the load-bearing
facts:

1. **"The tail of the mip chain separates layouts decisively" holds for ~54 % of the corpus, not
   all of it.** Measured over 18,176 texture exports, **8,327 (45.8 %) fit two or more layouts**: any
   mip whose width and height are both 4-aligned is byte-identically P8 and BC2/BC3, so a texture
   whose chain stops before a non-aligned mip is genuinely ambiguous from data alone. The `Format`
   code as tiebreaker is therefore the **primary path for nearly half the corpus**, not the edge case
   the spec's open question A described. Read the decision as *"derive the candidate set from the
   data, then disambiguate"*, never *"the data always decides"*.
2. **`bHasComp`/`CompFormat` are TAGGED PROPERTIES, not raw bytes after `Mips`.** Verified:
   `LUM_CoreTex.utx` decodes `{'bHasComp': (3, True), 'CompFormat': (1, 3)}`. The spec's raw-byte
   reading fails on 39/39 Deus Ex cases; reading them from the property list and parsing `CompMips`
   immediately after `Mips` is EOF-clean on 207/207.
3. **The failure counts are corpus-dependent and were never pinned to a root.** 39 over
   `DX/{System,Textures}` (30 of them in the project's own `LUM_CoreTex.utx`), 207 over the wider
   tree including Unreal. The "147/147" recorded earlier does not reproduce against any single root
   and should not be cited.

Also settled while planning: **`CompFormat` is DXT1 in 69/69 observed cases** (closing the spec's
open question B), and **a from-scratch `.utx` fixture IS buildable** in ~60 lines over the in-tree
`native/pkg_write.build_package` — which contradicts the asset-catalog plan's "there is no package
writer in the tree" note and makes the synthesized-fixture decision (2026-07-25 06:30 §8) cheap.

## 2026-07-25 10:18 UTC — `movers.is_mover` goes schema-aware: ONE predicate, and `level doctor` may require the games config

**The choice (Andrzej, 2026-07-25).** `movers.is_mover` decided mover-ness by a NAME GUESS — the
class's bare name had to end in `Mover` (`movers.py`, `bare.endswith("Mover")`). Replace it with a
real hierarchy test: an actor is a mover iff its class **is `Engine.Mover` or descends from it**,
resolved against the offline `classindex.ClassIndex` over the game's own `.u` packages.

The guess was wrong in **both** directions, but only one direction has live instances (measured on
this substrate's composed path while building, 2026-07-25):
- It **rejected real movers** — LIVE, and the reason the item exists. `CaroneElevatorSet.CEDoor` and
  `CaroneElevatorSet.CaroneElevator` both extend `DeusEx.DeusExMover` → `Engine.Mover`, yet
  `mover key add CEDoor0` answered "CEDoor0 is not a Mover". The base game alone carries two more:
  `DeusEx.BreakableGlass` and `DeusEx.BreakableWall` (both `DeusExMover` descendants), and
  `BreakableGlass` leaked into world CSG in the native build for exactly this reason.
- It **would accept non-movers** — a class whose name merely ends in `Mover` without descending from
  it. **THEORETICAL on this substrate**: all 12 classes ending in `Mover` on the composed path
  really are movers, so no live instance was found. The rule is still wrong (a mod class can be
  named anything), and the regression pins it with a synthetic class rather than a fabricated live
  one.

**Measurement correction (2026-07-25 11:31 UTC).** The two counts above are wrong; the decision they
support is unaffected. Re-measured against the real composed search path (2034 classes) with the same
`ClassIndex` the predicate uses: **9** classes have a bare name ending in `Mover` **case-sensitively**
(`Engine.Mover`, `DeusEx.DeusExMover`/`ElevatorMover`/`MultiMover`, `TNM.DamageRotateMover`/
`InertialMover`/`KnockableMover`/`StaringMover`/`TrackMover`) — 12 only if the match is made
case-INsensitively, which the retired `bare.endswith("Mover")` was not, adding `TNM.fanmover`/
`platformmover`/`weakmover`. There are **17** real `Engine.Mover` descendants, so the retired guess
rejected **8** real movers, not the four named above: `CaroneElevatorSet.CEDoor`,
`CaroneElevatorSet.CaroneElevator`, `DeusEx.BreakableGlass`, `DeusEx.BreakableWall`, `TNM.Barricade`,
`TNM.fanmover`, `TNM.platformmover`, `TNM.weakmover` — the lowercase three being rejected purely by
`endswith`'s case-sensitivity, against UE1 `FName`s that are case-insensitive. The
"no false positive on this substrate" half stands: **0** of the 9 name matches is a non-mover.

**The sub-question it forced, and the answer: "Doctor may require config."** `is_mover` is shared
with `level doctor`, which until now needed nothing but an actor; a schema-aware predicate needs a
class resolver, hence a project and `~/.uedcli/config.toml`. Andrzej's call: **accept that
`level doctor` gains a class-resolver requirement and fails clearly (exit 2, naming the verb and
what is missing) when no games config is present. One predicate, no split.**

*Rejected: keep `doctor` resolver-free by applying the schema-aware gate ONLY where a resolver
already exists (`mover key`) and leaving `doctor` on the name-suffix heuristic* — rejected because
it means **two predicates to keep true**, diverging silently the moment one is fixed and the other
isn't.

*Rejected (implied by the above and by `direction.md` "No silent half-answers"): an OPTIONAL resolver
that falls back to the name guess when absent* — a fallback answers a question it cannot answer, and
the wrong answer is invisible.

**So the predicate answers or it RAISES (`classindex.ClassRefError` → clean exit 2) — it never
returns `False` for "don't know".** Four cases, all found by the cold reviews as silent-`False`
traps rather than by design: the index cannot resolve `Engine.Mover` at all (no resolver); the
actor's OWN class is not on the composed path; its ancestor chain truncates before the `Core.Object`
root (`ClassIndex.ancestry` truncates silently at a missing/unparseable ancestor package); or a bare
class name resolves to several classes that DISAGREE about mover-ness. Each of those returning
`False` would report a real mover as a static brush — invisibly, since nothing downstream re-checks:
`doctor` skips its watertight check, the native build carves the mover into world CSG (re-opening
the doorway-fill bug this predicate exists to prevent), and `mover key` prints a factually false
"does not descend from Engine.Mover".

**Blast radius, accepted deliberately.** "One predicate" means every call site takes the index, so
the resolver requirement extends past `doctor`. The verbs that NEWLY require a project + the
per-user games config are: `mover key`, `level doctor`, `event graph`, `stash capture`,
`brush scale`, `brush apply-transform`, `brush intersect`/`deintersect`. (`level materialize` and
BOTH `level preview` tiers already hard-required one before this change — `_level_preview` exits 2
on a missing games config before it ever reaches the mover gate.) `dispatch._mover_index` is the ONE
seam that builds the index, so the verb-named error wording exists once.

**Supersedes** the 2026-06-25 mover decision 8 ("Mover detection by ONE shared `is_mover` predicate
(class bare-name equals/ends in `Mover`)") — the "ONE shared predicate" half stands, the name-suffix
definition does not. It also closes that entry's deferred *"a subclass registry (needs a
per-substrate class graph)"* alternative from the other end: no per-substrate registry is needed,
because the class graph is already readable offline out of the game's own `.u` (`classindex`).

**Refs:** board `to-build.md` item 9.4 (deleted on completion); the answered `inbox.md` flag
"Schema-aware `is_mover` needs a class RESOLVER"; `architecture.md` "Mover support" +
"World-CSG brush selection".

## 2026-07-25 11:31 UTC — `map_save`'s write verification: four stacked signals, and liveness by sentinel not exit code

**The problem.** `driver.map_save` had to answer "did `MAP SAVE` finish?" from the written file
alone (the console reports nothing). Its rule was "the size is non-zero and equal across two polls,
and `stat` exiting 1 means the file is not there yet". Two cold reviews (2026-07-25) showed that rule
cannot tell the three outcomes apart:
- **finished vs stalled** — a wedged editor's truncated map holds a steady size exactly like a
  finished one, so "two equal reads" accepted a 12-byte file (measured against a frozen stub with the
  real 600 s timeout: it returned 12 after one poll).
- **file-missing vs container-dead** — measured on this machine and re-verified live: a *stopped*
  container, a *missing* container and a permission error ALL make `docker exec` exit **1**, the same
  code `stat` uses for "no such file". The `!= 0` raise branch was therefore unreachable in practice
  and every real container death was reclassified as "not written yet" — a ten-minute stall ending in
  a diagnosis blaming the editor.
- and the poll's `subprocess.run` had **no `timeout=`**, so the 600 s bound was not real.

**The choice.** Verify with FOUR independent signals rather than one, and let each answer the
question it can actually answer: (1) a **pre-`MAP SAVE` stat** the file must differ from — kills
"a complete map from an earlier run is sitting at that path"; (2) **N equal readings across a minimum
settle window** (`stable_reads=3`, `settle=3.0 s`) — kills "the writer paused for one poll"; (3) a
**structural check of the written package** (magic + the three object-table `(count, offset)` pairs
must land inside the file) — the ONLY signal that separates *finished* from *stalled*, because no
amount of stability can; (4) **liveness from a probe SENTINEL** (`printf uedcli-probe` as the
in-container snippet's first act) plus a per-probe `subprocess` timeout — kills "the exit code is
ambiguous" and "dockerd hangs forever".

*Rejected: keep using the exit code and just widen the "docker failed" set (125/126/127)* — the
measurement says the failures land on 1, so any exit-code rule is guessing; the sentinel is a
positive proof of liveness instead of a blacklist of failure codes.

*Rejected: raise as soon as a stable file fails the structural check* — a slow flush would false-fail.
An incomplete-but-stable file is simply "not accepted yet"; polling continues to `timeout` and the
structural reason is then reported in the failure message.

*Rejected: verify by fully parsing the package (`upackage.load_package`)* — it needs the bytes on the
HOST (the file is container-local until `docker cp`) and judges content, not completeness. The header
check costs one 36-byte read and stays inside the driver's "nothing but a container" dependency.

*Rejected: keep the `(size)`-only `container_file_size`* — "did this file change?" needs the mtime, so
the probe returns `(size, mtime_token)`. The mtime stays an OPAQUE STRING: `stat -c %.9Y` renders the
fraction with the container locale's decimal separator and echoes the directive back verbatim on a
coreutils build without `%.N` precision, and equality is all the check needs.

**Consequences.** `container_file_size` is GONE (no back-compat shim), replaced by `container_stat` +
`container_file_head` + `package_problem` over the shared `_container_probe`. Two tests that could not
fail were rebuilt rather than patched: both passed `timeout=0.0`, so the deadline fired on iteration
one and the logic under test never ran, and the docker-failure test mocked a `returncode=126` +
"container is not running" pairing docker never emits. The replacements drive a fake clock (sleeping
is what advances time) so the real 600 s/1 s/3 s defaults are exercised in zero wall-clock seconds.
Driver's OTHER `docker exec` calls (`_wine_ctl`, `dexec_bash`, `set_clipboard`, `log_size`,
`read_log_since`) are still unbounded — logged as an `inbox.md` chore, not fixed here, because
`_wine_ctl exec` drives genuinely long editor verbs and needs its own bound chosen.

**Mechanism correction (2026-07-25 12:40 UTC, from the build review).** The entry above justified
signal #3 by asserting that a part-written map holds a steady size "exactly like a finished one",
leaving the reader to assume the truncation appears at the destination path. That is not how this
editor saves. Extracted from `core.dll`'s string table and re-verified independently:
`UObject::SavePackage` serializes into a temp file, runs `RewriteSummary` (the header is patched LAST,
*in the temp*), then `Moving '%s' to '%s'` onto the destination — and `core.dll` imports no
`MoveFile*`/`CopyFile*`, so the move is a read/write COPY. So at the destination a serialization
wedge leaves NO file (or the previous, complete one), and the reachable truncation is a half-finished
COPY: a valid header whose tables run past EOF. **The decision stands and the check is unchanged** —
that copy-phase truncation is exactly what signals 1–2 cannot see and #3 does — but the never-filled-in
header is defence in depth, not the motivating case, and the fixed `Save.tmp` name is now a documented
UnrealEd fact (`unrealed/commands.md` "`MAP SAVE` writes `Save.tmp`").

**Correction to the correction (2026-07-25 14:05 UTC, second review round).** The note directly above
over-read its own evidence twice, and both halves are withdrawn:
1. *"core.dll imports no `MoveFile*`/`CopyFile*`, so the move is a read/write COPY"* — **wrong
   inference.** Its PE import table also has **no `ReadFile`** and no file-mapping API, yet the DLL
   demonstrably reads packages; so its file I/O does not go through the import table (it imports
   `GetProcAddress`) and the missing `MoveFile*` proves nothing. **Whether a truncated file can reach
   the destination at all is UNKNOWN**, and no truncated destination has ever been observed — the one
   historical report was retracted by `spikes/2026-07-15-native-materialize/sections/`
   `91-leaves-overproduction.md`. Signal #3 is therefore kept as cheap insurance (one 36-byte read at
   the accept point, plus it rejects a stale non-package at the path), NOT as the fix for a
   demonstrated failure mode. **The decision itself still stands** on defect (a), the exit-code
   liveness misdiagnosis, and (c), the missing `subprocess` timeout, both of which were measured live.
   Settling the mechanism is now an `inbox.md` `[spike]`.
2. The list of still-unbounded `docker exec` calls above omits **`dismiss_blocking_dialog`** (three
   calls); the real count is 8 calls across 6 methods in `driver.py`. `inbox.md` carries the full
   scope, which also includes all three docker subprocesses in `xfer.py` (`remove` plus the two
   `docker cp`s); `driver.py` and `architecture.md` deliberately enumerate only the driver's own six
   methods, since that is what their surrounding text is about.

Also from that round: the structural check gained a minimum-table-size rule, because "every table
offset is inside the file" alone is nearly blind at the tail. Measured over the 264 packages the real
composed path resolves (harness: `spikes/2026-07-25-map-save-mechanism/measure_header_window.py`),
for the 101 EDITOR-written maps (excluding the 19 `Native*.dx` this tool's own build wrote, which
`MAP SAVE` never produced) the required end moves from 93.5–98.9 % of the real size (median 98.3 %,
offsets only) to 98.4–99.7 % (median 99.5 %) — several times smaller, NOT closed: a truncation in the
last ~1.6 % of a map still passes. Closing it needs a full table parse on the host after `docker cp`,
which is out of the driver's scope (it checks a container-side file) and largely redundant with
`apply`'s post-verify. *(Third-round correction: this paragraph first quoted 230 packages and a
92.0–99.8 % offsets-only range, both from an ad-hoc glob rather than the composed path; the
committed harness is now the single source of these figures. The per-entry minimums were also
tightened to their true lower bounds — name 5 / import 7 / export 12 — which is where 98.3 % comes
from.)*

**`direction.md` reconcile: deliberate no-op.** Checked when this entry landed and again in the third
review round — `direction.md` states the *target*, and nothing in it covers how the driver verifies a
container-side write; its one adjacent claim (which verbs need a class resolver, under "Explicit,
discoverable, model-side") already matches the corrected `usage.md` list. Recorded because the rule
asks for the check to be visible, not because anything changed.

**Refs:** `architecture.md` "Editor driver"; `unrealed/commands.md` "Driving is fire-and-forget" +
"`MAP SAVE` writes `Save.tmp`"; `spikes/2026-07-25-map-save-mechanism/` (harnesses + write-up, pinned
by `test_engine_facts.py`); the `inbox.md` `[debug] p1` entry this closes.

## 2026-07-25 17:20 UTC — The review gate is LOOSENED: Opus reviewers, three moments, a hard 2-round ceiling (Andrzej-decided)

**Decision:** the review gate in `CLAUDE.md` keeps its structure (cold reviewers, context-not-priming,
the observability test for what blocks, the batching rules) but its *cost shape* changes on four axes:

1. **Reviewers run Opus** (`Agent(model: "opus")`). Previously the model was unspecified.
2. **Three gate moments, not two** — a **plan** review joins the spec and build reviews. It is bound
   to the *pipeline*, not to whether a plan file happens to exist: specced pipeline work goes through
   a plan doc and therefore gets a plan round, while stage-less `[chore]`/`[debug]` work and one-file
   fixes have none. Not writing a plan is not a way to skip the round (`to-build.md` takes a
   *reviewed* plan).
3. **Fixed per-moment headcounts replace the old floor-and-tier scheme.** Round 1: spec = 3 Opus,
   plan = 2 Opus, build = 2 Opus — each **plus one Haiku reviewer**, additive, never filling an Opus
   slot, its findings held to the same observability test. Round 2 shrinks (spec 3→2, plan/build
   2→1), no Haiku, and is smaller in **headcount only** — its reviewers still get the full updated
   artifact plus the since-round-1 diff, and a finding anywhere in the work counts. A **trivial**
   change gets **1 Haiku and nothing else**, one round only. "Trivial" means *changes no reader's
   understanding and no tool behavior* (typo, formatting, comment, `help=` rewording, test rename,
   broken link) — deliberately NOT "not code": every change to `CLAUDE.md`, `direction.md`,
   `decisions.md`, `architecture.md`, `unrealed/*.md`, a spec/plan or a spike write-up is non-trivial
   at any size, because a future agent acts on what it says. Nor is anything that changes behavior,
   deletes anything, or edits a code path. When it is arguable it is not trivial, and a batch takes
   its least-trivial member's tier.
4. **Two rounds is a hard CEILING, and round 2 is conditional on the ARTIFACT CHANGING.** Round 2
   exists because the fixes are unreviewed, so it runs iff resolving round 1 changed the artifact: a
   clean round 1 — or one whose findings were all logged/escalated without touching the artifact —
   passes the gate immediately. (Explicitly *not* a licence to log in-scope defects to dodge round 2;
   the disposition rule, which requires each left-standing finding's reason on the board or in the
   commit message, is unchanged.) After round 2 the gate is passed, with anything still standing
   fixed, logged to `board/inbox.md`, **or escalated** — all three outlets stay open. No round 3.
   A **structural** finding in *either* round ends the gate early by escalation to Andrzej;
   escalation replaces the remaining round rather than adding one.

**Context:** the gate as written was unbounded in the expensive direction — "EVERY change gets
reviewed, no trivial exemption", two-as-a-floor rising to four, and "keep looping until a round comes
back clean" with the explicit expectation that a clean gate "take more than two rounds". Andrzej
wanted the cost cut without losing the parts that actually catch defects. The two structural
observations that survive the cut are why the loosening lands where it does: cold reviewers **diverge**
(so breadth, not depth, is what headcount buys — hence Haiku is additive rather than a substitution),
and **round 2's NEW material is small** (the fixes and their fallout, on top of work already read once
by its round-1 peers) — hence shrinking its headcount costs little.

**Rejected:**
- *Loop until clean, unbounded* (the prior rule) — the tail rounds were the bulk of the cost for the
  least return; a third cold pass over a twice-fixed artifact buys less than it costs.
- *Round 2 at the same headcount as round 1* (Andrzej's first sketch was a flat 2×2 / 2×3) — dropped
  in favour of a shrinking round 2, since the breadth argument for headcount is weak over a small fix
  diff. Against that flat sketch it takes **~15–25 % off a worst-case (two-round) gate**: a spec gate
  6 Opus + 1 Haiku → 5 + 1, a build gate 4 + 1 → 3 + 1. (Round 2 *in isolation* falls by a third to a
  half; the earlier "roughly a third off a worst-case gate" here conflated the two and was corrected
  in this change's own round-1 review.)
- *A full trivial-change exemption* (skip the gate entirely) — rejected in favour of a Haiku-only
  round: at this scale the cheap pass is close to free and occasionally catches something, so "every
  change gets reviewed" survives rather than being abandoned.
- *Keeping the four-reviewer risky-change tier* — in uedcli's wording, a change that "moves an
  identity key or an on-disk format, a broad deletion sweep, anything whose failure mode is silent";
  in uplayctl's, an on-disk format **or wire protocol**, a broad deletion sweep, or a silent failure
  mode. Both are dropped, folded into the flat per-moment headcounts. This is a deliberate reduction
  in coverage on
  exactly the riskiest class of change; the compensating controls are the spec and plan rounds ahead of
  it and the trivial-tier definition, which explicitly refuses to let a one-line load-bearing change
  take the cheap path.
- *A severity scale to decide what round 2 must fix* — still rejected, for the reason the original
  gate gives: cold reviewers can't apply one consistently and it invites arguing findings down a tier.
  The observability test is unchanged.

**Refs:** `CLAUDE.md` "Review gates" (the operative rule). `Tools/uplayctl/CLAUDE.md` carried a
near-verbatim copy of the old gate text and **took the same loosening** in the same batch, at Andrzej's
call — per-tool gates stay independent by design, but the two are not allowed to drift into two
processes to remember (`Tools/uplayctl/docs/dev/decisions.md`, 2026-07-25 17:25 UTC).

**`direction.md` reconcile: deliberate no-op.** `direction.md` is the compiled target for the *tool*
(what uedcli does); the review gate is a *process* rule that lives only in `CLAUDE.md`. Nothing in
`direction.md` describes the gate, so there is nothing to reconcile. Recorded because the maintenance
rule asks for the check to be visible, not because anything changed.

## 2026-07-25 17:45 UTC — Texture layout arbitration is a tiebreak-and-veto; `format-disagreement` is deleted, and a code-less BC2/BC3 does NOT decode (Andrzej-decided)

Two decisions taken over the third review round of `specs/2026-07-25-native-texture-formats.md` and
its plan. They **amend** the 2026-07-25 06:30 entry ("Texture decode derives layout from the DATA")
— which stands — by settling exactly what the `Format` code is allowed to do.

**AD1. The code breaks ties and VETOES; it never contradicts the data. `format-disagreement` and the
stored-vs-defaulted `format_source` axis are both deleted.** The whole arbitration, for the mip array
being judged (`Format` for `Mips`, `CompFormat` for `CompMips`), where "the code" means the stored
byte if the property is present and otherwise **0** (UE1 serializes a property only when it differs
from the class default, and `Engine.Texture` declares none — slot 0 is `TEXF_P8` in all three enums
measured):

1. the data fits exactly one layout → **use it** (`layout_source: data`; the code is not consulted);
2. the data fits several → the code **breaks the tie** by naming a fitted candidate;
3. the data fits several and no code names a fitted candidate → a **named error**, never a guess
   (`ambiguous-layout`; `ambiguous-alpha` for the BC2-vs-BC3 shape);
4. the code names **no layout we decode** → a **named error** (`unverified-format`) *even when the
   data fits exactly one layout* — the veto, checked first so no fit branch can bypass it.

**Why the disagreement case went.** A `Format` property is physically stored on **11 of 18,176**
texture exports across the four corpora on this machine, and **all 11 agree with their own chain's
fit** (ten `Format=7` over `bc16` chains, one `Format=3` over a `bc8` chain — all in Unreal Gold). So
the machinery — an error case, a result field, a table branch, a fixture pair and a sweep assertion —
fired on **zero** real files, while *manufacturing* a contradiction every time the implied P8 code met
a non-P8 chain. The stored-vs-defaulted asymmetry existed only to stop that manufactured
contradiction from breaking every foreign non-P8 file; with the contradiction gone, a stored 0 and an
absent 0 behave identically and the provenance field distinguishes nothing.
*Rejected: keep `format-disagreement` as a fixture-only diagnostic.* A case reachable only by files we
construct to reach it is not a guard rail, it is a second thing to keep true in code, tests and docs.
*Rejected: keep the `stored | class-default` provenance for reporting.* Nothing consumes it once the
contradiction is gone, and a field that exists "in case" is how the asymmetry grows back.

**Why the veto stays — the measured collision that forces it.** 227's `ETextureFormat` slot **8** is
`TEXF_BC4` (dumped 2026-07-25 from the git-tracked `uned/UED22/Engine.u`: `0 TEXF_P8, 1 BGRA8_LM,
2 R5G6B5, 3 BC1, 4 RGB8, 5 BGRA8, 6 BC2, 7 BC3, 8 BC4, 9 BC4_S, 10 BC5, 11 BC5_S`, 122 slots). BC4 is
a single-channel **8-byte-block** format, so its mip chain is byte-for-byte the size of BC1's and fits
the `bc8` layout *uniquely*. Without rule 4, a file whose own code says `8` — "not BC1" — would be
decoded as BC1 and drawn confidently wrong. Slot 9 collides the same way; slots 10/11 are 16-byte
blocks and collide with `bc16`. Consequence recorded honestly: **an *uncoded* `bc8` chain is decoded
as BC1 by ASSUMPTION, not deduction** — sound only because a genuine BC4 export must store
`Format = 8 ≠ 0` and the veto then catches it.

**AD2. A `bc16` chain that no code resolves is `ambiguous-alpha` — a named error and no pixels — and
this is a stated LIMIT on "reads any texture from any engine".** BC2 and BC3 have identical block
sizes and identical mip chains and differ only in how each block's alpha half is encoded; nothing in
the data separates them. **A code-less BC2/BC3 file does not decode. A code-less BC1 file does**
(8-byte blocks are unambiguous), and so does P8, and so does any chain fitting exactly one layout.
Every argument for a rule in these documents is therefore worked through **BC1**, never BC3 — an
earlier draft justified a rule with "a foreign 227/UT BC3 `.utx` must decode", which the rule does not
achieve. The limit must be stated wherever the universality claim is made (docs, error text, code
comment), not buried as a corner case.
*Rejected: assume BC3 for a code-less `bc16` chain.* BC3 is commoner, so the guess would often be
right — and silently, unrecoverably wrong otherwise, producing a plausible image with wrong alpha,
against "never a wrong pixel".
*Rejected: decode both ways and pick by "alpha plausibility".* A heuristic dressed as a measurement:
no ground truth exists to validate it (zero BC2 samples anywhere on this machine), it would decide
inconsistently across one texture set, and it contradicts the standing "the tool does not infer"
principle (2026-07-25 05:10).

**Measured cost of the whole arrangement: nothing on real content.** Of 8,327 ambiguous chains,
**zero** lack P8 among their candidates when no code is stored, so the implied-0 tiebreak resolves
every one; every stored code is `3` or `7`, both mapped, so the veto rejects **zero** real textures;
and `ambiguous-alpha` fires on **zero** of the 18,176 exports here. The limit bites only on foreign,
code-less, block-compressed content we have never seen.

**One interpretation the recording session made explicit, because it is load-bearing.** AD1's third
line was phrased "data fits several and **no stored code** → named error". Read strictly ("stored"
meaning a physically present property), it would turn the 8,324 ambiguous chains that today resolve
via the implied 0 — including 1,137 in `uned/UED22` and 1,362 in Deus Ex's own `System`+`Textures` —
into errors, i.e. ~46 % of every corpus would stop decoding, and AD2 would not be *the* limit worth
naming. Recorded here as: **an absent property is not the absence of a code; by UE1's serialization
rule it IS the byte 0, and 0 is P8 in every enum measured**, so it breaks ties exactly as a written 0
would. That reading is what makes rule 1 and rule 2 the status quo for real content and AD2 the only
real limit. Flagged on `board/inbox.md` for Andrzej to overrule if he meant the strict reading.

**Refs:** `specs/2026-07-25-native-texture-formats.md` §0b/§2 D8+D9/§3b (the arbitration and its
ordered table); `plans/2026-07-25-native-texture-formats-plan.md` §0d/§0c D8+D9/S3; the 2026-07-25
06:30 entry it amends and its 11:20 addendum. **`direction.md` reconcile:** the compiled target's only
statement about texture decoding is the asset-catalog section's "produces the picture (decodes a
texture …)"; the plan's S7 reconciles that clause with the `ambiguous-alpha` limit when the work
lands, since nothing decodes any of it yet.

## 2026-07-25 17:58 UTC — Feature work moves to git WORKTREES; the repo-root `CLAUDE.md` is DELETED; docs get a 1-round gate (Andrzej-decided)

**Decision:** three related process changes, all Andrzej's calls in one sitting.

1. **A feature is built in its own git worktree** under `.claude/worktrees/<slug>` (gitignored) and
   **squash-merged back into the branch it was branched from** — which is simply the branch the main
   checkout is already on. **The agent does NOT ask which branch and never switches the main
   checkout's branch**, superseding the prior "confirm the merge target with Andrzej BEFORE starting
   work" rule. Everything else about feature branches survives: never push the feature branch, gate
   before merging, squash-merge from the main checkout, and ask before deleting the local branch.
   The full procedure lives in `CLAUDE.md` "Feature worktrees".
2. **The repo-root `CLAUDE.md` is deleted; `Tools/uedcli/CLAUDE.md` is the repo's canonical rule
   file**, with `Tools/uplayctl/CLAUDE.md` mirroring the shared rules. The root file's live content
   (repo layout, the `_scratch/` rule, the repo-level `TODO.md` scope, the "After every change"
   checklist) was folded into both tool files first — nothing was dropped.
3. **A docs-only change gets ONE review round, maximum** — no round 2 even when the round produced
   fixes. Docs-only = touches no code and no test; a **spec** or **plan** keeps its own row, because
   those moments exist to catch a design before it is built. Also added, to close a hole round 2
   found: **`build` is the DEFAULT row** for any non-trivial change that is not a spec or a plan
   (ledger entries, chore sweeps, board work), so nothing is left without a headcount.

**Context:** (1) several agent sessions work this repo concurrently, and `git checkout` in the shared
checkout swaps files under every other session mid-edit — a worktree structurally cannot, which is
also why the process forbids switching the main checkout's branch. Andrzej explicitly did not want to
be asked about the branch. (2) He wanted one rule file, not a root file plus two tool files with a
delegation seam between them; the seam had already produced a stale-quote board item. (3) Cost again:
the two-round ceiling was still spending a second Opus round on prose whose failure mode is a stale
sentence, not a silent defect.

**Also settled in this batch (from that same round 2):** a structural escalation **parks the work**
rather than passing the gate (it was accidentally readable as a free "fix-free round 1" that
authorised a merge); **"the artifact"** is defined as the files under review excluding
`dev/docs/board/*` and the commit message, so logging to the board never itself triggers round 2;
**refuted** is now an explicit fourth disposition, admissible only with the disproving check recorded;
the trivial tier's NOT-trivial lists explicitly **win** over its examples, and a `help=` rewording is
docs-only rather than trivial; and **reviewer counts may never be restated outside `CLAUDE.md`** —
the direct cause of the stale-gate instructions found in seven plan/spec files.

**Rejected:**
- *Keeping a repo-root `CLAUDE.md` as the shared-rules home* — rejected by Andrzej. It is the obvious
  de-duplication (one worktree process, not two mirrored copies), but a session working in a tool dir
  loads both files and the seam invites the two to disagree; the cost accepted instead is that the
  two tool files must be kept mirrored by hand. **Known consequence:** a session working outside
  `Tools/` (in `Maps/`, `LUM_Core/`, `Prefabs/`) now loads NO `CLAUDE.md` at all, so the `_scratch/`
  rule and the commit rules do not reach level-design work. Flagged to Andrzej rather than silently
  worked around.
- *A full trivial-style exemption for docs* (no review at all) — rejected; one round is cheap and
  docs are where this repo's knowledge lives.
- *Sibling worktrees outside the repo* (`../LUM-worktrees/<slug>`) — rejected in favour of
  `.claude/worktrees/`, which the harness's own `EnterWorktree`/agent isolation already uses (so
  there is one convention, not two) and which is already ignored. Verified safe: the game's asset
  paths in `~/.uedcli/config.toml` are absolute and outside the repo, and a project's own `paths` are
  relative to whichever root you are in, so a worktree resolves its packages correctly wherever it
  sits.
- *Letting `EnterWorktree` keep its default base* — rejected; its default `worktree.baseRef` is
  `fresh` (branches from `origin/<default-branch>`), which contradicts "branch off the branch we are
  on". The repo now commits `.claude/settings.json` with `worktree.baseRef: "head"`.

**Refs:** `CLAUDE.md` "Feature worktrees" + "Review gates" + "The repo this tool lives in" + "After
every change"; `Tools/uplayctl/CLAUDE.md` (mirror); `.claude/settings.json`; `.gitignore`
(`.claude/worktrees/`); supersedes the branch-confirmation half of 2026-07-25 17:20 UTC. Round-2
findings left standing are logged on `board/inbox.md`.

## 2026-07-25 18:42 UTC — Review-gate headcount: 2 Opus (3 for specs), Haiku only in the trivial tier

**Decision (Andrzej).** The review-gate table shrinks to **2 Opus reviewers per round as the
ceiling, except a spec round-1, which gets 3**, and the **additive Haiku reviewer is removed from
every row**. Haiku survives in exactly one place: the trivial tier's single one-round pass, which is
unchanged (1 Haiku, no round 2). Round 2 is unchanged (spec 2 Opus, plan/build 1 Opus, docs-only
never). Nothing else about the gate moves: the three moments, the two-round ceiling, the
observability test, the four dispositions, the context-not-priming rule and the batching rules all
stand.

**Why.** A round's headcount is its parallel width, and the width is capped by the hardware, not by
the token budget. Measured on this machine (2026-07-25): an **Intel i5-2400, 4 cores, no SMT**, 7.7
GiB RAM with **167 MiB free and 1.9 of 2.0 GiB swap in use**, and **five concurrent `claude`
processes** holding 1.9 GB RSS. Subagent concurrency is capped at `min(16, cores - 2)` = **2** here,
so the old `3 Opus + 1 Haiku` first round could not run 4-wide: two reviewers ran and two queued,
turning one round into two rounds' wall-clock while still counting as one. Cutting the round to its
real parallel width removes the queueing without removing a round — the gate's actual defect-catching
structure (cold, independent, two-round-max) is untouched.

The **spec** moment keeps the third slot because it is the one artifact whose defects propagate: a
bad spec is inherited by the plan and by the build behind it, so breadth is worth the queueing
exactly there and nowhere else.

The **Haiku ride-along** is dropped rather than kept as a fourth/third slot because its whole
justification was that it was free — additive, cheap, occasionally catching what Opus walked past.
On a box with 2 concurrent slots it is not free: it either occupies a slot an Opus reviewer wanted
or it queues behind them, and in both cases it costs wall-clock time. Its findings were never
discounted and that standard still holds where it remains (the trivial tier).

**Rejected:**
- *Keeping `+ 1 Haiku` on the first round of every row* — rejected. It is only defensible while the
  slot is free, and the measurement above shows it is not on this hardware.
- *Dropping to 1 Opus for build/docs-only rounds* — rejected. Headcount buys **breadth** (cold
  reviewers diverge sharply on what they notice), so a single reviewer per round is where coverage
  actually degrades; 2 is the floor that keeps two independent readings of the artifact.
- *Widening spec round-1 to 4+ Opus now that Haiku is gone* — rejected; 3 already exceeds the
  2-slot concurrency cap, and the freed capacity is meant to reduce queueing, not to be re-spent.
- *Raising the concurrency cap / adding swap so wide rounds run truly parallel* — not rejected, but
  out of scope for this decision: it is a machine change (more RAM, zram, fewer concurrent sessions),
  filed on `board/inbox.md` alongside the other measured slowness causes (root-level `rg` reading
  ~500 MB of tracked binaries at 3.6 s/search; 698 MB of session transcripts).
- *Deleting the trivial tier's Haiku pass too* ("one model everywhere") — rejected; the trivial tier
  exists precisely to be cheap, and a 1-Haiku pass is what makes "nothing ships unlooked-at"
  affordable for a typo.

**Refs:** `CLAUDE.md` "Review gates" (the table + "How many reviewers, and which model" + the
NO-Haiku bullet) — the counts live there and nowhere else, per that section's own rule;
`Tools/uplayctl/CLAUDE.md` "Review gates" (mirror, kept in step by hand) + that tool's own ledger
entry of the same timestamp; amends the headcount half of 2026-07-25 17:20 UTC (uedcli) /
17:25 UTC (uplayctl). Machine-level causes filed on `board/inbox.md`.
## 2026-07-25 18:15 UTC — `--class-exact` is renamed `--exact-class`, because deleting the `_RemovedFlag` shims re-opened a prefix-abbreviation hole

**Context.** The no-back-compat rule (2026-07-24 21:57) says a removed spelling is DELETED, not kept
as a migration-error shim. uedcli had nine such shims, implemented by a `_RemovedFlag` argparse
action that did nothing but `parser.error("X was renamed to Y")`. They were all deleted.

**The problem that surfaced.** `_RemovedFlag` was doing a *second* job its name does not advertise.
argparse expands any **unambiguous prefix** of a defined option, so a *defined* `--class` was also
what stopped `--class` from abbreviating into the surviving `--class-exact`. Delete the shim and
`uedcli actor find --class Light` silently parses as `--class-exact Light` — an exact-only match —
resurrecting precisely the exact-vs-subclass footgun the 2026-07-19 rename existed to kill. Measured
against the built parser rather than reasoned about: after the deletion `--class Light` parsed to
`cls=['Light']`, while the other eight deleted spellings (`--single`, `--breakdown`, `--zoom`,
`--zoom-region`, `--zoom-factor`, `--show-collision`, `--show-light-range`, `--show-sound-range`)
prefix nothing that survives and failed cleanly as unrecognized arguments.

**Decision.** Rename the SURVIVOR: `--class-exact` → **`--exact-class`**. It shares no prefix with
`--class`, so the old spelling is genuinely unrecognized and the hazard is closed structurally
rather than by a flag defined only to complain. No alias, no shim — uedcli is unreleased.

**This rename is load-bearing, not taste.** `--class-exact` reads at least as naturally, so someone
"tidying" the name back would silently restore the footgun. That is why the reason lives here and in
the regression `test_parser_find_rejects_bare_class_as_unrecognized`, which asserts the
*unrecognized-argument* error rather than a bare `SystemExit` — a bare `SystemExit` also passes when
the abbreviation is accepted and the parse fails later for an unrelated reason.

**Rejected alternatives.**
- *Keep the `--class` `_RemovedFlag` shim and delete only the other eight* — an explicit carve-out
  from the no-back-compat rule, and it leaves the hazard permanently one deletion away.
- *Turn off argparse prefix abbreviation globally (`allow_abbrev=False`)* — a behavior change across
  every flag in the CLI to fix one collision, and it removes abbreviations that work today.
- *Leave `--class-exact` and accept the abbreviation* — that is the 2026-07-19 footgun, restored.

**Refs:** extends the 2026-07-19 `--class` rename (supersedes nothing). `architecture.md` (the
`actor find` class filter), `docs/usage.md` (`actor find` filters).

## 2026-07-25 18:40 UTC — The preview-annotation internals are renamed `annotation*`; the drawn-text machinery KEEPS "label"

**Supersedes** the parenthetical in the 2026-07-22 20:49 actor-labels entry ("its internals
`parse_label_spec`/`DEFAULT_LABELS`/`LabelSpec` stay label-named pending a follow-up rename to
`annotation*`"). That follow-up has now landed, so the ledger must not keep telling readers the
internals are still `LabelSpec`. Everything else in that entry stands.

**What was renamed.** The *selection* type and its helpers: `LabelSpec` → **`AnnotationSpec`**,
`parse_label_spec` → **`parse_annotation_spec`**, `DEFAULT_LABELS` → **`DEFAULT_ANNOTATIONS`**, and
the `labels=` keyword every `render_*` takes → **`annotations=`**.

**What deliberately KEEPS "label", and why.** The *drawing* machinery — `_LabelItem`,
`_PlacedLabel`, `_place_labels`, `_label_size`, `_LABEL_WEIGHTS`, `poly_labels`,
`_SceneGeom.poly_labels`. A "label" there means **one concrete piece of text laid out on the
canvas**, which is a genuine and useful sense: annotations are *decided*, labels are *placed*. The
two-sense split is now stated explicitly at the top of `preview.py` and in `architecture.md`,
including the third, unrelated sense (the actor `label` dimension in `labellib.py`).

**This is a deviation from the `to-build.md` §10.3 spec**, which listed the drawing machinery's
prose alongside the three symbols and motivated the whole item with "'label' now means two
unrelated things in one codebase". Under the chosen split a cold reader still meets "label" in
`_place_labels` meaning something unrelated to `--label`. The judgement was that renaming the
placement machinery to `annotation*` would be *worse*: it would erase a real distinction (a spec is
not a drawn box) and leave no word for the thing being placed. **Flagged for Andrzej** rather than
settled here — it is a naming-taxonomy call the spec made one way and the build made another.

**Rejected alternative:** rename everything in `preview.py` to `annotation*`, leaving no term for a
laid-out text box — considered and rejected for the reason above.

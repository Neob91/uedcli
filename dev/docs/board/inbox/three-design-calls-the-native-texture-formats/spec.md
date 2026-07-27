# Spec: native texture decode for any UE1 package — self-describing, no format table

**Status:** specced, **review-gated three times** (2026-07-25: 2 cold reviewers over the first draft,
2 more over this spec *and* its plan, then 2 more over the result — every round found load-bearing
errors, and the third round arrived together with two decisions from Andrzej, **AD1** and **AD2**,
which removed a whole error case and named a limit; all folded, see §10). A plan exists:
board item `native-texture-decode`. **Supporting spike (durable, survives this spec's
deletion):** `dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py` — the committed,
self-verifying from-scratch `.utx` builder every offline test is written against (§5a).
**Requested by:** Andrzej (2026-07-25, session `uedcli:catalog`) — "We should support all UE1
formats!", then: *"`.u**` format is universal and should be read from any other engine. We should
make that work WITHOUT USING ANY SUCH TABLE if that means it won't be universal for any texture
file."*
**Ephemeral:** this file is scratch for designing the work and is deleted once the work lands. The
durable record afterwards is `decisions.md` (the choices + rejected alternatives),
`dev/docs/unrealed/package-format.md` (the format facts) and `architecture.md` (what the code does).

**This document is SELF-CONTAINED.** Everything needed to build the feature — the binding decisions
and their rejected alternatives, the on-disk byte layout, the measured corpus numbers, the house
rules that constrain the change, and where the corpora live — is stated here. Source code may be
read; **no other document needs to be opened.** Provenance pointers (`recorded in decisions.md
2026-07-25 06:30 UTC`, and so on) are given for the archaeological record only.

**Replaces** the `inbox` item *"Native non-P8 texture decoders (RGBA8/DXT1/RGB16/imported-palette)"*,
which named formats speculatively.

---


> **ADDED 2026-07-26 (owner-directed) — NOT YET RE-REVIEWED. Mesh skins are a first-class consumer of this
> decoder.** This spec is written around textures as *surfaces*, but the asset catalog's **class arm** renders
> mesh thumbnails textured from a class's `MultiSkins[i]`, through the same `utexture` path (the mesh spike's
> `render_class.py` builds a `TextureResolver` for it). So every format this spec adds must be reachable from
> the skin path too, and its coverage must include **one mesh-skin case**, not only surface reads — otherwise
> a class thumbnail silently loses its texture on exactly the formats this spec exists to fix (30 invisible
> today in `LUM_CoreTex.utx`). Owner ruling: a skin that cannot be decoded is an **error**, per
> `direction/asset-catalog.md` "Produce the picture, or a named error — never a wrong pixel" — so the decoder's
> typed failure result must carry enough to name the offending skin ref to its caller. This spec was
> review-gated 2026-07-25; **this addition has not been through a round** (`board/inbox/`).

## THE LIMIT ON "reads any texture from any engine" — read this before anything else

This decoder is deliberately **not** universal, and the exception is small, sharp and permanent.
State it wherever the universality claim is made:

> **A BC2 or BC3 (DXT3/DXT5) texture that does not store a `Format` code does NOT decode.** It
> returns the named error `ambiguous-alpha` and no pixels. BC2 and BC3 are byte-for-byte the same
> *size* — 16-byte blocks, identical mip chains — and they differ only in how the alpha half of each
> block is encoded. Nothing in the data distinguishes them, and this design never guesses, so a file
> that does not say which one it is cannot be drawn.
>
> **BC1 (DXT1) in the same situation DOES decode**: its blocks are 8 bytes, no other layout we decode
> shares that size, so a code-less BC1 file is resolved by its data alone. So is P8, and so is every
> chain whose mip sizes fit exactly one layout.

Two consequences that must not be lost:

1. **Every argument for a design rule in this document uses BC1 as its worked example, never BC3** —
   because BC1 is the case the rules actually rescue. An earlier draft argued a rule with "a foreign
   227/UT `.utx` holding a BC3 texture must decode"; it does not decode, and the argument was
   rewritten around BC1, which does. *(Andrzej's decision **AD2**, 2026-07-25 — `decisions.md`
   "Texture layout arbitration is a tiebreak-and-veto".)*
2. **In practice this fires on no file measured on this machine**: every one of the 18,176 texture
   exports across the four corpora either fits a single layout or is resolved by its code. The limit
   is real, but it is a limit on *foreign, code-less block-compressed content we have never seen*,
   not on the content this project works with.

---

**One thing depends on this work:** the unified asset catalog's texture arm. Its texture shard
filenames are `sha256(width, height, RGB bytes)` — a *frozen, unversioned* identity — so any later
change to what the decoder outputs silently re-keys every shard, and every classification an LLM has
authored reads back as "unclassified". That arm therefore cannot start until this decoder is final.
Practically: **land this work before any texture is classified**, and treat "which mip array wins"
and "what the mask means" as decisions that must not move afterwards.

---

## Environment: where the corpora live, and which are reachable offline

The tool lives at `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli`. The git repo root is
`/home/neob91/Games/LutrisDX/drive_c/DX/LUM` (the `LUM` Deus Ex mod). Everything below is on this
machine; a fresh checkout on another machine has only the **committed** rows.

| corpus                                                    | path | committed? |
|-----------------------------------------------------------|------|---|
| **Deus Ex install**                                       | `/home/neob91/Games/LutrisDX/drive_c/DX/{System,Textures,Maps}` | **no** — it sits *outside* the repo (the repo root is a subdirectory of it). Reachable in-tree only through the symlink `Tools/uedcli/uned/DeusExAssets → /home/neob91/Games/LutrisDX/drive_c/DX`, and that symlink is itself gitignored (`.gitignore:9`). |
| **The project's own texture packages**                    | `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures/*.utx` — notably `LUM_CoreTex.utx` (17 MB) | **PARTLY.** `git ls-files Textures/` lists exactly four packages — `France.utx`, `LUM_CharacterTex.utx`, `LUM_CoreTex.utx`, `LUM_InfoPortraits.utx` (384 `Texture` exports). `CoreTexSky.utx` and `CoreTexWater.utx` sit in the same directory **untracked** (34 more exports), and it is a live content directory sessions add to. See the count-stability rule below. |
| **Unreal Gold** (patched 227i; its `System/Engine.u` is still the stock 8-slot build) | `/home/neob91/Games/Unreal/pfx/drive_c/Unreal` | **no** — outside every repo, and there is **no in-tree pointer to it at all** |
| **UED22 editor substrate**                                | `Tools/uedcli/uned/UED22/` — 214 tracked files, 34 of them packages this parser reads, 1,998 `Texture` exports | **yes** |
| **Existing test fixtures**                                | `Tools/uedcli/uedcli/tests/fixtures/{CoreTexWater,LUM_InfoPortraits}.utx` | **yes** |

Consequences for test placement, and they are not negotiable:

- **Anything asserted over the Deus Ex install or the Unreal Gold install is an integration test**
  (`-m integration`), because a fresh checkout cannot see either.
- **Everything else must be asserted offline**, against `uned/UED22/*`, the tracked
  `LUM/Textures/*.utx`, the existing fixtures, and any new committed fixture.
- **The corpus guard rail is therefore TWO-TIER, not integration-only.** `Textures/LUM_CoreTex.utx`
  — which holds **all 30** of the LUM textures this work exists to fix (re-measured 2026-07-25:
  253 `Texture` exports, 30 failing today, and the other three tracked packages fail zero) — and
  `uned/UED22/` are both git-tracked. A single `-m integration` sweep would deselect by default the
  criterion for the very bug that motivates the work. The offline tier runs over both corpora; the
  integration tier runs over the two installs.
- **COUNT-STABILITY RULE — where an exact expected count is legitimate, and where it is not.**
  An offline test may assert an **exact count** only over material a fresh checkout is guaranteed to
  have *and* that nothing else writes: `uned/UED22/` (fully tracked, 34 packages / 1,998 `Texture`
  exports) and the committed fixtures under `uedcli/tests/fixtures/`. It may **not** assert an exact
  count over `<repo>/Textures/`: that directory is only partly tracked (4 of the 6 packages present
  on this machine) and is live content that sessions add packages to, so any total measured there is
  a snapshot, not a contract. Over `Textures/` a test asserts **invariants** instead — 0 parse
  failures, 0 `unrecognised-layout`, 0 `size-mismatch`, 0 `ambiguous-layout`, 0 `ambiguous-alpha`,
  and every export either decodes or names a case. The **one** exception is the motivating-bug
  clause, which is exact because it is pinned to a single tracked package: `LUM_CoreTex.utx` goes
  from **30** `Texture`-class parse failures to **0**.
- The DX install is located by `install_root()` in `uedcli/tests/conftest.py` (env override
  `UEDCLI_TEST_INSTALL`; its no-env fallback anchors on `conftest.py`'s own location). **There is no
  equivalent pointer for the Unreal install** — the build must add one
  (`UEDCLI_TEST_UNREAL_INSTALL`) and skip cleanly when it is unset. The two tracked corpora need no
  env pointer: the build adds two conftest helpers beside `install_root()`, anchored the same way —
  `ued22_root()` = `Path(__file__).resolve().parents[2]/"uned"/"UED22"` and `repo_texture_root()` =
  `Path(__file__).resolve().parents[4]/"Textures"` (`parents[2]` is `Tools/uedcli`, `parents[4]` is
  the repo root; both verified 2026-07-25). `repo_texture_root()` returns a directory whose contents
  vary per machine — see the count-stability rule above before asserting anything numeric over it.
- Every "Done when" clause in the plan is tagged **(offline)** or **(integration)** for exactly this
  reason.

**On line numbers in this document.** Anchors into files that other sessions edit (`architecture.md`,
`docs/usage.md`, `dev/docs/board/*`, `dispatch.py`) go stale within a day — every such anchor in the
first draft was off by 40–135 lines a day later. They are therefore given as **grep-able text**, with
any line number marked as a 2026-07-25 sighting. Anchors inside `utexture.py` and
`native/pkg_write.py` were re-verified 2026-07-25 and are exact.

**Note on paths in older material:** the developer docs tree was renamed `docs/dev/` → `dev/docs/`
(so that `docs/` is physically all user-facing). Older commits, older docs and older board lines may
still spell the old path; `dev/docs/` is the current one and `docs/dev/` no longer exists.

## The house rules this change must satisfy

These are the uedcli conventions that actually bind this work. They are reproduced here so the
builder does not have to open `CLAUDE.md`.

**Running the tests.** From `Tools/uedcli`, run **`bin/test`**. It runs pytest *host-native* in the
auto-managed dev venv (`bin/_venv.sh` → `.venv/`, Python 3.12 + `Pillow` + `pytest`) — the same
runtime `bin/uedcli` uses — and then the Rust golden suite (`cargo test`). It needs `python3.12` on
PATH; the venv self-creates on first run. Extra args pass straight through, and it must be invoked
path-qualified because bare `test` is a shell builtin:

```
cd Tools/uedcli && bin/test              # the whole offline suite
cd Tools/uedcli && bin/test -k texture -x
```

Tests marked `-m integration` need material this machine has and a checkout does not; `pytest.ini`
carries `addopts = -m "not integration"`, so they are **deselected**, not skipped, in a default run.
A new integration module must therefore not change the skip count.

**Committing.** Commit each completed change without being asked. Stage **only the files you
touched, by explicit pathspec** (`git commit -- <path> <path>`); never `git add .`, never `git add
-A`, never `git commit -a` — a concurrent session may have staged its own work. One **short
imperative subject line**, no `type:` prefix, **no AI attribution**. Push after committing.
**Never rewrite history**, locally or on `origin`: no `--amend`, no `rebase` of pushed commits, no
force-push in any form. Mistakes are fixed with a new commit or a `git revert`.

**No back-compat cruft.** uedcli is unreleased — no external users, no scripts in the wild — so
nothing is ever kept for backward compatibility. When a flag, verb, option value, output format, or
code path is removed or renamed, **delete it outright in the same change** that introduces the
replacement; the new spelling is the only spelling. Forbidden: deprecated aliases, no-op flags,
migration-error shims (a flag defined only to `parser.error("X was renamed to Y")`), dual-format
support kept to avoid rewriting callers, and "old way" branches in code, tests or docs. This is why
§4's return-type change **deletes** `TextureResolver.resolve_masked` rather than keeping it beside
the new seam.

**No silent half-answers.** A command that cannot fully satisfy a request **exits 2 naming the
offending value** rather than printing a partial result plus a stderr warning — stderr scrolls away
and the caller mistakes the partial answer for a complete one. (This rule and the degrade-and-warn
requirement of §4 are not in conflict: they apply to different layers, and §4 says exactly which.)

**No Python exception ever reaches the user.** A bad ref, a corrupt package, a hostile mip count —
each must produce a clear error naming the offending value and a non-zero exit, never a bare
`KeyError`/`IndexError`/`MemoryError`/`struct.error` traceback. Every such path gets a regression
test.

**Every command and argument needs a real `help=`** that says what it does, not one that restates
the flag's name. (This spec adds no CLI surface, so this rule is inherited, not exercised.)

**Docs move with the change.** User-facing docs (`docs/usage.md`, `docs/leveldesign/`) are updated
in the same commit as any behaviour a user can observe; developer docs (`dev/docs/architecture.md`
= what *is*, `dev/docs/unrealed/*.md` = verified engine facts) are updated in the same commit as the
implementation. A user-facing doc must **never** link to a developer doc. Engine facts in
`dev/docs/unrealed/*.md` carry a confidence marker: ✅ uedcli-used / live-verified, 🔬 live-probed,
📖 extracted from a binary string table.

**Pin the finding, or it rots.** Whenever this work establishes a *checkable* fact about the engine
or the file format — a byte-layout field order, an enum's slot list, a block signature — it must
also land a **committed regression that re-asserts that fact**, so a later change trips a red test
instead of drifting unnoticed. The prose cites the evidence; the test enforces it.

**Markdown tables** are padded so the interior pipes line up in a plain-text editor — every column
except the last, whose content stays unpadded so a prose column does not spawn 200-character lines.

---

## 0. The governing idea: derive the layout from the data, never from a table

A first draft proposed reading each game's `ETextureFormat` enum out of its `Engine.u`. Andrzej
rejected the dependency: **the package format is universal, so decoding must work for any texture
file — including a lone `.utx` from a game whose `Engine.u` we do not have.**

That is largely achievable, because **the mip chain is self-describing.** Block-compressed formats
store `ceil(w/4) × ceil(h/4)` blocks, so their mips *floor* at one block; linear formats scale down
to `w × h × bytes-per-pixel`. Re-measured on this machine 2026-07-25:

| mip                                                    | 8×8  | 4×4  | 2×2      | 1×1 |
|--------------------------------------------------------|------|------|----------|---|
| `Format=7` (`DmRiot.unr:Poster01`, Unreal Gold)         | 64 B | 16 B | **16 B** | **16 B** |
| `Format` unset ⇒ P8 (`LUM_CoreTex.utx:ClenGreyWndow_C`) | 64 B | 16 B | **4 B**  | **1 B** |

Both are 1.0 bytes/pixel at mip 0 — indistinguishable there — but the tail of the chain separates
them.

**It does not always tell us, and this spec must not overclaim it.** Re-measured over 18,176 texture
exports (one `Mips` chain each — see §1e for what is being counted), **8,327 (45.8 %) fit two or
more layouts**: any mip whose width and height are both 4-aligned is byte-identically P8 and
BC2/BC3, because `(w/4)·(h/4)·16 = w·h`. A texture whose chain stops before a non-4-aligned mip is
therefore genuinely ambiguous from the data alone. **The `Format` code as tiebreaker is the PRIMARY
path for nearly half the corpus, not an edge case** — §8's open question A was written as though it
were two odd samples, and that was wrong. The design still stands (no format *table* is ever
required, and the code only ever breaks a tie between candidates the data already fitted), but
"derive from the data" must be read as **"derive the candidate set from the data, then
disambiguate"**, never "the data always decides".

**What "the code" is, exactly.** UE1 serializes a tagged property only when its value differs from
the class default, and `Engine.Texture` declares **no** default for `Format`, so its default is the
type's zero — slot 0, which is `TEXF_P8` in every enum measured (§1a). Measured: a `Format` property
is physically present on **11 of 18,176** texture exports (0.06 %) — exactly Unreal Gold's ten
`Format=7` and one `Format=3`. **An absent `Format` is therefore not a missing code: by UE1's own
serialization rule it is the byte 0, i.e. the positive claim "this is P8".** That is what breaks the
45.8 % tie for essentially the whole corpus, and it is why the rule below is expressed over the
property's **effective** value (stored byte if present, else 0), with no second axis recording which
of the two it was.

> **Provenance is deliberately NOT tracked** (Andrzej's decision **AD1**, 2026-07-25). An earlier
> draft carried a `format_source: stored | class-default` field and gave only a *stored* code the
> power to contradict the data, producing a `format-disagreement` error. Both are gone: a code never
> contradicts the data at all, so a stored 0 and an absent 0 do exactly the same thing and there is
> nothing left for the field to distinguish. §0b is the whole rule; §2 D8 records the decision and
> what was rejected.

### 0a. The `Format` code → layout map — the ONE place slot semantics are assumed

Making the code the decider for 45.8 % of the corpus, and the only possible BC2-vs-BC3 selector,
requires turning a number into a layout. That map is small, and it must be **stated**, not left
implicit in the code, where it would look like the format table §2's **D1** forbids:

| effective code | layout |
|----------------|--------|
| `0`            | `linear1` + palette (P8) |
| `3`            | `bc8` (BC1 / DXT1) |
| `6`            | `bc16` with **explicit** 4-bit alpha (BC2 / DXT3) |
| `7`            | `bc16` with **interpolated** alpha (BC3 / DXT5) |
| anything else  | **recognised but unsampled** — names no layout **we decode**, and VETOES the array |

"Recognised but unsampled" means the byte is a legal enum slot in *some* engine, we have no sample
and no verified semantics, so it can never name a layout. A code in that row does not merely fail to
help — **it stops the array from decoding at all**, even when the data fits one layout perfectly.
That veto is the subject of §0b's row 2 and it is not optional:

> **The measured case that forces it.** 227's `ETextureFormat` slot **8** is `TEXF_BC4`
> (re-verified 2026-07-25 by dumping the enum out of the git-tracked `uned/UED22/Engine.u`, whose
> first twelve slots are `P8, BGRA8_LM, R5G6B5, BC1, RGB8, BGRA8, BC2, BC3, BC4, BC4_S, BC5,
> BC5_S`). BC4 is a **single-channel 8-byte-block** format: its mip chain is byte-for-byte the same
> size as BC1's, so a BC4 texture fits `bc8` *uniquely and identically*. Without the veto, a file
> whose own code says "this is BC4 — not BC1" would be decoded as BC1 and produce a confident,
> completely wrong image. Slots 9/10/11 (`BC4_S`, `BC5`, `BC5_S`) collide the same way — `BC5` and
> `BC5_S` are 16-byte blocks, so they collide with `bc16` as well.

**And therefore: an uncoded `bc8` chain is decoded as BC1 by ASSUMPTION, not by deduction.** The
data cannot tell BC1 from BC4 — only the code can, and the assumption is safe *because* of UE1's
serialization rule: a genuine BC4 export has `Format = 8 ≠ 0`, so the byte is written to disk, so
the veto catches it. What the assumption really rests on is that no writer emits a non-BC1 8-byte
block chain while omitting its `Format`. Recorded as an assumption so that a future BC4 sample is
known to be a test of it. *(Measured: `bc8` is the unique fit of all 69 `CompMips` arrays and one
Unreal Gold export, and every one of them carries a code of 3.)*

**Justification** (re-verified 2026-07-25 by dumping each install's real `ETextureFormat` via the
existing `uprops.enum_values` — the full dumps are §1a):

- All three installs agree that slot **0** is `TEXF_P8` and slot **3** is `DXT1`/`BC1`.
- The two installs that *define* slots 6 and 7 — Unreal Gold and UED22/227 — agree on both:
  `DXT3`/`BC2` and `DXT5`/`BC3`. DXT1 ≡ BC1, DXT3 ≡ BC2, DXT5 ≡ BC3; two vendors, one set of layouts.
- Deus Ex's enum has only **5** slots, so it **does not define** 6 or 7. Be precise about this: it is
  *not* true that "all three agree on 6 and 7" — one of them is silent, which is consistent but is
  not corroboration. The build pins all three dumps, including that silence (§6).
- The slots that genuinely *disagree* across installs — notably slot 2, `RGB64` at 8 B/px in Unreal
  Gold vs `R5G6B5` at 2 B/px in 227 (§1a) — are exactly the ones this map refuses to assign.

**Why this is not the format table D1 rejects.** A format *table* is load-bearing: without the right
game's table you cannot decode at all, and a game whose table you lack decodes nothing. This map is
**never used to size a chain** — the sizes come only from the mip data — and it does exactly two
things: it breaks a tie among candidates the data already fitted, and it names the codes whose
layouts we cannot decode so that those arrays fail honestly instead of being mis-decoded (the BC4
collision above). A chain the data settles on its own decodes with the map unconsulted
(`layout_source: data`). That is the whole dependency: four slots that three independent engine
builds agree on, plus an explicit "everything else is out of our depth".

### 0b. The arbitration rule: the code breaks ties and vetoes — it NEVER contradicts the data

*(Andrzej's decision **AD1**, 2026-07-25; `decisions.md` "Texture layout arbitration is a
tiebreak-and-veto". §2 D8 records it with its rejected alternatives.)*

The whole rule, in four lines:

1. **The data fits exactly one layout → use it.** (`layout_source: data`. The code is not consulted,
   so it cannot object.)
2. **The data fits several → the code breaks the tie**, by naming one of the fitted candidates.
3. **The data fits several and no code names a fitted candidate → a named error.** Never a guess.
4. **The code names no layout we decode → a named error**, *even when the data fits exactly one
   layout*. This is the veto of §0a, and it is checked **first** so nothing can bypass it.

Three terms, defined once and used everywhere below:

| term         | definition |
|--------------|---|
| `code`       | the byte the file carries **for the array being judged** — `Format` for `Mips`, `CompFormat` for `CompMips` (§1c). Absent property ⇒ the byte `0` (§0). `detect_layout` additionally accepts `code=None`, meaning *no code is available at all*; production always passes a byte, and `None` exists for callers judging a bare mip array and for the tests that check the data-only path |
| the map      | §0a's four slots: `{0: linear1+palette, 3: bc8/BC1, 6: bc16/BC2, 7: bc16/BC3}` |
| candidates   | every layout whose size rule fits **every** mip in the chain: `n == w·h·N` for `linear{N}` (`N ∈ {1,2,3,4,8}`), `n == ⌈w/4⌉·⌈h/4⌉·B` for `bc{B}` (`B ∈ {8,16}`) |

**Why the rule is shaped this way.** A code that contradicts the data was tried and removed: the
data is the primary evidence (it is the actual bytes, and it is what any decoder must slice
correctly), whereas the code is a one-byte label. Where they disagree there is nothing to arbitrate
*with* — but there is also nothing to lose by trusting the data, because the disagreement never
happens: all 11 stored codes in the whole corpus agree with their own chain's fit (§1b), so the
machinery only ever fired on hypothetical files while inventing a contradiction on real ones. What
*is* worth keeping is the veto: an unknown code is not a disagreement, it is an admission that the
file is using a layout we have never verified, and that is exactly when a decode must stop.

**What the rule buys, in one worked example each:**

- **A foreign 227/UT BC1 `.utx` that stores no `Format`** — 8-byte block floor, `bc8` is the unique
  fit, rule 1 decodes it, and the implied P8 code (which fits nothing) is never consulted. This is
  the "read any texture from any engine" case the spec exists to serve, and it works.
- **A Deus Ex P8 texture whose chain stops at 4×4** — `linear1` and `bc16` both fit; rule 2 uses the
  implied code 0 to pick `linear1`. Measured: 8,324 of the corpus's 8,327 ambiguous chains resolve
  exactly this way, and **zero** ambiguous chains lack `linear1` among their candidates when no code
  is stored, so the tie is always broken.
- **A code-less BC2/BC3 file** — `bc16` is the unique fit, but "bc16" is two decoders; no code
  selects one, so rule 3 gives `ambiguous-alpha` and no pixels. This is the documented limit at the
  top of this spec.
- **A 227 `TEXF_BC4` texture** — `bc8` fits uniquely and identically to BC1, but the stored code `8`
  names no layout in the map, so rule 4 vetoes and returns `unverified-format` naming the code. The
  alternative would be a confident wrong image on a file that told us not to.

**So the decoder's layout detection is:** compute `len(data)` against `w × h` across the *whole* mip
chain; a floor at 8 or 16 bytes means block-compressed (BC1 = 8, BC2/BC3 = 16); a clean `w × h × N`
means linear with N bytes per pixel. The numeric `Format` code is read and reported, but it is a
**tiebreaker, a veto and a diagnostic label, never a sizer** — which also immunises us against the
trap that a slot number means different things in different games (§1a). The full ordered procedure,
including which case each outcome produces, is §3b.

**Where data alone cannot decide, we say so rather than guess** (§4).

## 1. Measured ground truth

Method: `utexture.load_package` plus a body parse that reads the tagged-property list, then `Mips`,
then — when `bHasComp` is true — `CompMips`, over every package under each root. Every number in
this section was **re-measured on 2026-07-25** and reproduced exactly unless flagged as a
correction. Both cold reviewers had independently reproduced the original census.

### 1a. The slot numbers are NOT portable — which is why we do not depend on them

`ETextureFormat` is a plain `UEnum` export, decodable with the existing parser
(`uprops.enum_values`). Dumped from three installs on this machine:

| package                                   | ver | slots |
|-------------------------------------------|-----|---|
| Unreal Gold `System/Engine.u`             | 69  | 8 slots: `0 TEXF_P8, 1 RGB32, 2 RGB64, 3 DXT1, 4 RGB24, 5 RGBA8, 6 DXT3, 7 DXT5` |
| UED22 / 227 `uned/UED22/Engine.u` (**committed**) | 69 | **122** slots: `0 TEXF_P8, 1 BGRA8_LM, 2 R5G6B5, 3 BC1, 4 RGB8, 5 BGRA8, 6 BC2, 7 BC3, 8 BC4, 9 BC4_S, 10 BC5, 11 BC5_S, …` |
| Deus Ex `System/Engine.u`                 | 68  | 5 slots: `0 TEXF_P8, 1 RGB32, 2 RGB64, 3 DXT1, 4 RGB24` |

*(Correction: an earlier draft said the 227 enum has 118 slots. It has 122.)*

Restricted to the four slots §0a's map assigns, and with the disagreeing slot 2 alongside for
contrast:

| slot | Unreal Gold | UED22 / 227 | Deus Ex | agree? |
|------|-------------|-------------|---------|---|
| 0    | `TEXF_P8`   | `TEXF_P8`   | `TEXF_P8` | **yes, all three** |
| 2    | `TEXF_RGB64` (8 B/px) | `TEXF_R5G6B5` (2 B/px) | `TEXF_RGB64` (8 B/px) | **NO — this is why there is no table** |
| 3    | `TEXF_DXT1` | `TEXF_BC1`  | `TEXF_DXT1` | **yes, all three** (DXT1 ≡ BC1) |
| 6    | `TEXF_DXT3` | `TEXF_BC2`  | *(undefined — 5-slot enum)* | **yes, both that define it** |
| 7    | `TEXF_DXT5` | `TEXF_BC3`  | *(undefined — 5-slot enum)* | **yes, both that define it** |
| 8    | *(undefined — 8-slot enum)* | `TEXF_BC4` | *(undefined)* | n/a — **the size collision that forces §0b's veto** |

**Slot 8 is why an unknown code must be able to stop a decode.** 227's `TEXF_BC4` is an 8-byte-block
format, so its mip chain is byte-for-byte indistinguishable from BC1's and fits `bc8` *uniquely*. A
design in which "a unique data fit always wins" would draw a BC4 texture as BC1 — a confident wrong
image on a file whose own `Format` byte says it is not BC1. §0b rule 4 is the answer, and it is
ordered first so no fit branch can reach around it. `TEXF_BC4_S` (9) collides the same way;
`TEXF_BC5` (10) and `TEXF_BC5_S` (11) are 16-byte blocks and collide with `bc16`.

**Slot 2 is 8 bytes/px in Unreal Gold (`RGB64`) but 2 bytes/px in 227 (`R5G6B5`).** A hardcoded
table would mis-slice real data and then emit a *bogus* "size mismatch" — an honest-failure story
turned into a wrong diagnosis. The data-derived approach (§0) reads 8 or 2 bytes/px straight off the
mips and is simply right in both cases. §0a's map assigns **only** the rows that agree, and this
table is exactly the evidence for it — including the honest note that Deus Ex is *silent* on 6 and 7
rather than agreeing about them.

This also **closes the first draft's open question**: `7 = DXT5 (BC3)` and `6 = DXT3 (BC2)`, per both
authorities that define them. The draft's claim that 7 "is not in the classic enum, suggesting an
OldUnreal-227 extension" was wrong — it is in stock Unreal Gold's own `Engine.u`. Corroborated by
the data: all **4,096** alpha halves of `DmRiot.unr:Poster01`'s mip 0 are the single value
`0005ffffffffffff`, the textbook BC3 opaque block (a0=0, a1=5, `a0 ≤ a1` ⇒ index 7 = 255), which
reads as 0/85/255 noise under BC2.

### 1b. What is actually out there

| layout                                    | evidence | samples |
|-------------------------------------------|----------|---|
| **P8** (1 B/px + palette)                 | decoded today, proven pixel-exact vs `UCC batchexport` | **18,165** of 18,176 — all of Deus Ex, all of LUM, all of UED22, ~99.9 % of Unreal Gold |
| **DXT1 / BC1** (0.5 B/px, 8-B blocks)     | size + block-floor confirmed | 1 as a stored `Format` (`DmExar.unr:Screenshot`, 256×256 in 32,768 B = 0.5 B/px, decidable from a single mip), **plus every `CompMips` payload** (§1c) |
| **DXT5 / BC3** (1.0 B/px, 16-B blocks)    | both enums + alpha-block signature + coherent render | 10 (`DmRiot.unr` posters; `UnrealShare.u:TranslatorHUDHD` 2048², 12 mips) |
| **DXT3 / BC2**                            | in both enums, adjacent to BC3, shares BC3's colour half | 0 observed |
| slots 1, 2, 4, 5 and 227's 8+             | names and sizes disagree across installs | **0 observed** |

**The eleven stored codes, in full** (re-measured 2026-07-25; this is the *complete* set of texture
exports in any corpus that physically carry a `Format` property, so it is worth enumerating —
everywhere else the effective code is the implied 0):

| export                          | code | mip 0 | fitted candidates |
|---------------------------------|------|-------|---|
| `UnrealShare.u:TranslatorHUDHD` | 7    | 2048×2048, 4,194,304 B | `bc16` only |
| `DmRiot.unr:Poster01`           | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Poster02`           | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Poster03`           | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Screenshot`         | 7    | 512×512, 262,144 B | `bc16` only |
| `DmRiot.unr:SolMurJonction`     | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Fenêtres`           | 7    | 256×128, 32,768 B | `bc16` only |
| `DmRiot.unr:SolModifié`         | 7    | 128×128, 16,384 B (**single mip**) | `linear1` + `bc16` |
| `DmRiot.unr:Flotte`             | 7    | 64×64, 4,096 B (**single mip**) | `linear1` + `bc16` |
| `DMBeyondTheSun.unr:Uebergang3` | 7    | 256×128, 32,768 B (**single mip**) | `linear1` + `bc16` |
| `DmExar.unr:Screenshot`         | 3    | 256×256, 32,768 B (**single mip**) | `bc8` only |

**Every one agrees with its own data**, and every one names a layout in §0a's map (`3` and `7`
only). Two things follow, both load-bearing:

- **It is why the "code contradicts the data" machinery was deleted** (§0b, D8): the only inputs on
  which it could ever have fired are these eleven, and none of them fires it.
- **It is why the veto costs nothing measured**: no export in any corpus stores a code outside the
  map, so §0b rule 4 rejects **zero** real textures while blocking the BC4 mis-decode.

All eleven live in the *gitignored* Unreal Gold install, so every offline test involving a stored
code must construct one with the fixture builder (§5a, `fmt=…`).

### 1c. `bHasComp` / `CompFormat` / `CompMips` — the finding that inverts this spec's value

`UTexture` serializes **two** mip arrays. `bHasComp` and `CompFormat` are **tagged properties** in
the ordinary property list — verified: `LUM_CoreTex.utx` decodes `{'bHasComp': (3, True),
'CompFormat': (1, 3)}` — and `CompMips`, a second `TArray<FMipmap>` holding a **compressed copy of
the same image**, follows **immediately** after `Mips`, with nothing in between.

*(An earlier draft of this spec placed `bHasComp`/`CompFormat` as raw bytes after `Mips`. That
reading fails on **39/39** Deus Ex cases — 20 of them as a mip skip-offset mismatch, 19 as a non-EOF
body. Reading them as properties and parsing `CompMips` straight after `Mips` is EOF-clean on
**207/207** failing exports over the whole `drive_c/DX` tree, and consumes **zero** bytes when
`bHasComp` is absent or false.)*

This is the true cause of every "trailing bytes" failure on class `Texture`: parsing that second
array lands **exactly** on the declared end.

**Counts are corpus-dependent and must always be stated with their root** — the "147/147" in §10
named no corpus and does not reproduce against any single root. Re-measured:

Every row counts **`Texture`-classed exports** (one `Mips` chain each), not mip arrays; §1e gives
the per-array counts.

| root                                                  | pkgs | `Texture` exports | fail with a one-array parse | explained by `CompMips` |
|-------------------------------------------------------|------|-------------------|-----------------------------|---|
| DX `System`+`Textures`(+`Maps`, which adds no textures) |  232 |             5,018 |                          39 | 39 / 39 |
| whole `drive_c/DX` tree (includes LUM and the TNM mod)  | 1,154 |            33,262 |                         207 | 207 / 207 |
| `LUM/Textures`, **git-tracked packages only**          |    4 |               384 |                          30 | 30 / 30 |
| `LUM/Textures`, as it happens to sit on THIS machine   |    6 |               418 |                          30 | 30 / 30 |
| …of which `LUM_CoreTex.utx` alone (**tracked**)        |    1 |               253 |                      **30** | 30 / 30 |
| `uned/UED22` (**fully tracked**)                       |   34 |             1,998 |                           0 | — |
| Unreal Gold install                                    |  268 |            10,742 |                           0 | — |

*(The two `LUM/Textures` rows differ by the untracked `CoreTexSky.utx` + `CoreTexWater.utx`, 34
exports, 0 failures. **All 30 failures are in the tracked `LUM_CoreTex.utx`**, which is what makes
the motivating-bug criterion both offline and exactly countable — see the count-stability rule in
the Environment section. The four-corpora totals used throughout this spec — 18,176 exports —
include the two untracked packages, because they are totals measured on this machine, not offline
test expectations.)*

Verified end to end on two real textures:

- `LUM_CoreTex.utx:quadrocks_logo_02` (v69): `Mips` = P8 512×128 (65,536 B) → 1×1 (1 B), ten mips;
  `CompMips` = DXT1 512×128 (32,768 B) → 1×1 (**8 B**), ten mips. EOF-clean.
- `System/TNM.u:SmallToolButtonWindow_Normal` (v68): `Mips` = P8 **128×32** (4,096 B) → 1×1, eight
  mips; `CompMips` = DXT1 128×32 (2,048 B) → 1×1 (8 B). EOF-clean. *(An earlier draft gave this
  texture `quadrocks_logo_02`'s 512×128 dimensions; it is 128×32.)*

**Every** `bHasComp` texture measured is `(Format unset ⇒ 0, CompFormat = 3)` — a P8 original with a
DXT1 compressed copy — in 39 + 30 = **69 of 69** Deus Ex + LUM cases and **207 of 207** over the
whole tree. That answers §8 open question B. Deus Ex's own v68 enum has only five slots, so slot 3 is
`TEXF_DXT1` there too.

**This is a live bug in Andrzej's own project, not generic-UE1 hygiene.** All 30 of the LUM failures
are in **`LUM/Textures/LUM_CoreTex.utx` — the project's own authored texture package, and it is
git-tracked** (the other three tracked packages fail zero). They resolve to `None` today (`utexture.py:188` `decode_texture` raises on the
unparsed trailing bytes; `utexture.py:362` `_decode_ref` swallows the exception), so uedcli cannot
see them and the native preview renderer draws them as a magenta/black checkerboard. The first
draft's claim that "Deus Ex is 100 % P8, so this buys nothing on the project's own substrate" was
**false**, and the priority decision was taken on that wrong premise — it turns out to argue *more*
strongly for doing the work. Because the package is tracked, **"30 → 0" is an OFFLINE criterion**;
filing it under `-m integration` would deselect it by default.

Two consequences for the design:

1. The census must be over `(Format, CompFormat)`, not `Format` alone; and "only the interpretation
   of `Data` changes" is wrong — **which array you are in decides which format applies**.
2. **Layout detection must be told which code to judge an array by, explicitly.** All 69 measured
   `CompMips` arrays fit `bc8` while their `Mips` fit `linear1` — one texture, two layouts. A
   detector that reached into the texture and read `Format` would judge every `CompMips` array
   against a P8 code; under §0b that code names `linear1`, which is not a candidate for a `bc8`
   chain, so all 69 would take rule 3's error branch instead of decoding — i.e. it would break
   exactly the textures this work exists to fix. So the detection entry point takes the code as a
   **parameter**: `Format` for `Mips`, `CompFormat` for `CompMips`. Measured 2026-07-25: all 69
   `CompMips` arrays fit `bc8` **uniquely** (so the data alone decides them under rule 1) and all 69
   carry `CompFormat = 3` (so the code, when consulted, corroborates).

**Which array wins — array SELECTION happens before layout detection, and both halves are defined.**
This ordering is part of the contract, not an implementation detail, because detection over an empty
chain would index mip 0 of an empty list and raise (against "no Python exception ever reaches the
user"):

1. **Selection first.** An array **carries data** iff it is non-empty *and* at least one of its mips
   has `len(data) > 0`. Choose `Mips` if it carries data; else `CompMips` if it is present and
   carries data; else neither, and the result is `no-mip-data` — detection is never invoked.
   *("`Mips` is absent" is deliberately not a term: the two shapes that would have hidden behind it —
   a zero-length `Mips` array, and a `Mips` array whose every mip is empty — are treated identically,
   and both are just "does not carry data".)*
2. **Detection second**, over the selected array only, with **that array's** code.
3. The result records which array it came from (`array: mips | comp-mips`), so a caller — and the
   asset catalog, whose texture identity is frozen on the decoded pixels — can see that a lossy copy
   was used.

`Mips` is preferred because it is the higher-fidelity original; `CompMips` is a lossy copy by
construction. **The fallback fires only on the selection rule above — never because `Mips` decoded
to an error.** A `Mips` array that carries data and then fails detection or decode reports its
typed error; it does not silently hand the caller a picture from the other array. *(Rejected:
falling back on any `Mips` failure. It would let a real corruption be papered over by a lossy copy
and make the result's provenance unpredictable — the "no silent half-answers" shape. Measured cost
of the strict rule: zero, since all 69 `bHasComp` textures have a perfectly decodable P8 `Mips`.)*

### 1d. A second, different trailing-bytes cause: `FireTexture`

`utexture.textures()` (`utexture.py:245`) matches `class == "Texture"` **exactly**, so the first
draft's "all 69 failures are class `Texture`, therefore not a subclass problem" was a **tautology of
the sweep**, not evidence. Widening it to every `*Texture`-named class: **208 `FireTexture` failures
over the whole `drive_c/DX` tree** (of which **40** are in `System`+`Textures`) and **153 in Unreal
Gold**, whose trailing bytes are `TArray<FSpark> Sparks` — 8 bytes per spark, matching `NumSparks`
exactly (`BP_FX_03`: 252×8+2 = 2,018 = the trailing count). That is procedural-texture state,
entirely unrelated to `CompMips`.

Separately, and importantly for §4's `no-mip-data` case: **procedural textures carry mips whose
`DataCount` is `0`**. Measured over the whole DX tree: 208 `FireTexture`, 42 `WetTexture`, 14
`WaveTexture`, 8 `IceTexture`, 50 `ScriptedTexture`, 4 `TNMScriptedTexture`; over Unreal Gold: 153
`FireTexture`, 78 `WetTexture`, 7 `IceTexture`, 4 `WaveTexture` — every one of them, all mips empty.
Only `FireTexture` also carries trailing bytes; the others parse cleanly to EOF. So "no pixel data"
is detectable **from the data** (`len(mip.data) == 0`), never from a class name.

### 1e. The fit census — and exactly what it counts

Every "N chains fit one layout / M fit two or more" figure in this document is a **per-texture**
count: one `Mips` chain per `Texture`-classed export. It is the natural unit for "how often does the
data decide", because that is the array a caller normally gets. But it is **not** the number of mip
arrays the decoder will actually classify, because a `bHasComp` texture has two — and a build that
quietly conflates the two units will write a test expectation it cannot meet. Both are given.
*(Re-measured 2026-07-25; the four corpora are those of the Environment section, with `LUM/Textures`
counted as it sits on this machine unless a row says "tracked only".)*

**Per texture — one `Mips` chain each:**

| corpus                                 | `Mips` chains | fit exactly one layout | fit ≥ 2 |
|----------------------------------------|---------------|------------------------|---|
| DX `System`+`Textures`+`Maps`          |         5,018 |                  3,656 | 1,362 |
| `LUM/Textures` — **tracked only**      |           384 |                    382 | 2 |
| `LUM/Textures` — this machine (6 pkgs) |           418 |                    416 | 2 |
| `uned/UED22` (**fully tracked**)       |         1,998 |                    861 | 1,137 |
| Unreal Gold install                    |        10,742 |                  4,916 | 5,826 |
| **total** (with the 6-package row)     |    **18,176** |              **9,849** | **8,327** (45.8 %) |

**Per mip ARRAY — `Mips` plus every `CompMips`:**

| corpus                            | arrays (`Mips` + `CompMips`) | fit exactly one layout | fit ≥ 2 |
|-----------------------------------|------------------------------|------------------------|---|
| DX `System`+`Textures`+`Maps`     |       5,057 (5,018 + **39**) |                  3,695 | 1,362 |
| `LUM/Textures` — **tracked only** |           414 (384 + **30**) |                    412 | 2 |
| `LUM/Textures` — this machine     |           448 (418 + **30**) |                    446 | 2 |
| `uned/UED22`                      |               1,998 (+ **0**) |                   861 | 1,137 |
| Unreal Gold install               |              10,742 (+ **0**) |                 4,916 | 5,826 |
| **total**                         |                   **18,245** |              **9,918** | **8,327** (45.6 %) |

**The `CompMips` arrays, counted separately because they are the arrays this work adds:** **69**
across the four corpora (39 in DX `System`+`Textures`, 30 in `LUM_CoreTex.utx`, none in `uned/UED22`
or Unreal Gold; 207 over the whole `drive_c/DX` tree). **All 69 fit `bc8` uniquely** — so §0b rule 1
decides every one of them from the data — and **all 69 carry `CompFormat = 3`**, which corroborates
without being needed. They add no ambiguity at all, which is why the "≥ 2" column is identical in
both tables.

## 2. Decisions (Andrzej, 2026-07-25) — with their rejected alternatives

*(Recorded in `decisions.md` 2026-07-25 06:30 UTC, with three measured corrections appended
2026-07-25 11:20 UTC. Stated in full here; the ledger need not be opened.)*

**D1. Derive the layout from the data; never require a format table** (§0). The numeric `Format`
code is a hint, a tiebreaker and a diagnostic label — not the authority.
*Rejected: reading each game's `ETextureFormat` out of its `Engine.u`.* It makes decoding depend on
having that game's code package, so a lone `.utx` from an unknown engine would not decode — which
defeats the universality that is the entire point.
*Rejected: hardcoding one game's table.* Measured wrong across installs (§1a): slot 2 is 8 B/px in
Unreal Gold and 2 B/px in 227.
This is the same shape of finding as the self-describing mesh vertex stride (`decisions.md`
2026-07-25 03:40): the file already tells us, if we look.

**D2. Implement the measured layouts now: P8, BC1, BC2, BC3, and the `CompMips` array.**
*Rejected: implementing the unsampled linear slots from their definitions.* No samples exist
anywhere on this machine and the slot meanings disagree across installs, so a guess returns a
plausible **wrong image** (swapped channels) instead of an error — against "never a wrong pixel".

**D3. The remaining layouts get a `p1` board item to spike and implement** (Andrzej) — acquire real
samples first, verify each layout, then implement. Until it lands, an unsampled slot is a named
`unverified-format` error that carries its own uncertainty. The item already exists at
`dev/docs/board/inbox/` — grep it by its title, **`[spike/implement] p1 The REMAINING UE1 texture
layouts`** (at `:603` on 2026-07-25; the board moves constantly, so grep, never seek by line).

**D4. The trailing-bytes work is folded in** (§1c/§1d) — same file, same decoder, same goal.

**D5. This stays a build prerequisite for the asset catalog's texture arm.** Strengthened, not
weakened, by §1c: it fixes 30 of the project's own textures.

**D6. Errors are a typed result from the decode layer; the CLI chooses the disposition** (§4).
*Rejected: "every failure exits non-zero".* It contradicts the catalog's requirement that an
undecodable asset stay enumerable, and it would stop a whole map preview because one odd texture
exists — `preview_native.py` degrades to a checkerboard by design.

**D7. Testing must not be circular** (§5). A synthesized fixture only proves the decoder agrees with
our own encoder. Two independent oracles exist and are used instead.

**D8. The code breaks ties and vetoes; it never contradicts the data. There is no
`format-disagreement` case and no stored-vs-defaulted provenance** (Andrzej, **AD1**, 2026-07-25 —
`decisions.md` "Texture layout arbitration is a tiebreak-and-veto"). The arbitration is §0b's four
lines; a code that names a layout we cannot decode stops the array (§0a's veto), and a code that
merely names a different layout than the data fitted is impossible to act on and is not treated as
an event.
*Rejected: keeping `format-disagreement` as a fixture-only diagnostic.* It is machinery — an error
case, a result field, a branch in the ordered table, an offline fixture pair, and a sweep assertion
— whose measured firing rate on real content is **zero** (all 11 stored codes agree with their own
chain's fit, §1b), and it does that while *manufacturing* a contradiction whenever the implied P8
code meets a non-P8 chain. A case that can only fire on files we construct to make it fire is not a
guard rail, it is a second thing to keep true.
*Rejected: the stored-vs-defaulted asymmetry* (`format_source`, with only a stored code allowed to
contradict). It existed **solely** to stop `format-disagreement` from destroying the feature.
Delete the contradiction power and the field has nothing left to distinguish — a stored 0 and an
absent 0 behave identically — so it goes with it.

**D9. A `bc16` chain that no code resolves is `ambiguous-alpha` — a named error and no pixels; and
this is a stated limit on universality** (Andrzej, **AD2**, 2026-07-25, same ledger entry). BC2 and
BC3 are identical in size and mip shape, so the data cannot choose; we do not guess. See the block
at the top of this spec, which must stay prominent: a code-less BC2/BC3 file does **not** decode,
while a code-less BC1 file does.
*Rejected: assume BC3 for a code-less `bc16` chain.* BC3 is the commoner format, so the guess would
usually be right — and would be silently, unrecoverably wrong the rest of the time, producing a
plausible image with wrong alpha. "Never a wrong pixel" is the principle the whole design rests on.
*Rejected: decode both and pick by "alpha plausibility"* (e.g. prefer the interpretation whose alpha
is smoother or more often fully opaque). It is a heuristic dressed as a measurement: it has no
ground truth to be validated against (we have zero BC2 samples anywhere), it would decide
differently for two halves of the same texture set, and it contradicts the standing "the tool does
not infer" principle — uedcli reports what is stored and leaves meaning to the caller.

**Three corrections the planning pass measured** *(appended to the ledger 2026-07-25 11:20 UTC; the
decision itself stands)*:

1. "The tail of the mip chain separates layouts decisively" holds for **~54 %** of the corpus, not
   all of it — 8,327 of 18,176 exports (45.8 %) fit two or more layouts (§0).
2. `bHasComp`/`CompFormat` are **tagged properties**, not raw bytes after `Mips` (§1c).
3. The failure counts are **corpus-dependent** and were never pinned to a root; "147/147" does not
   reproduce and should not be cited (§1c).

## 3. What the decoder does

### 3a. The `UTexture` body, byte by byte

*(Established by spike `spikes/2026-06-27-decontainerize-uedcli/01-native-texture-decode.md`, which
proved the P8 path **pixel-exact against `UCC batchexport`** across the entire Deus Ex install —
`CoreTexMetal.utx` 175/175, `CoreTexDetail.utx` 17/17, `DeusExItems.u` 185/185, package versions 61,
68 and 69. Reproduced verbatim here so the layout need not be looked up.)*

A UE1 object's serial body is a **tagged-property list** terminated by the name `None`, then
class-specific trailing data.

```
UTexture body
  <tagged property list>        # carries Format, Palette, bHasComp, CompFormat, bMasked, …
  None                          # property-list terminator (a name-table compact index)
  Mips     : TArray<FMipmap>    # compact-index count, then count × FMipmap
  [if bHasComp]
  CompMips : TArray<FMipmap>    # SAME encoding; present iff the bHasComp property is true
```

```
FMipmap (per mip)
  WidthOffset : uint32   # TLazyArray skip offset: the ABSOLUTE file offset just past Data.
                         # PRESENT when Ar.Ver >= 63 (v68/v69); ABSENT in v61.  <- the single
                         # version difference, and the original v61 decode failure.
  DataCount   : compact index    # number of pixel bytes in this mip
  Data        : byte[DataCount]  # palette indices (P8) or block bytes (BC1/BC2/BC3)
  USize       : uint32           # mip width
  VSize       : uint32           # mip height
  UBits       : uint8
  VBits       : uint8
```

```
UPalette body
  <tagged property list> None    # normally empty (just None)
  Colors : TArray<FColor>        # compact-index count (= 256), then 256 × {R,G,B,A} bytes
```

```
FPropertyTag (the tagged-property encoding), repeated until a "None" name
  Name : compact index           # index into the name table; "None" => end of list
  Info : uint8                   # bits 0-3 = type, bits 4-6 = size code, bit 7 = array/bool
  [if type == Struct(10)] StructName : compact index
  size = {0:1, 1:2, 2:4, 3:12, 4:16, 5:<u8>, 6:<u16>, 7:<u32>}[size code]
  [if bit7 and type != Bool] array index : 1/2/4-byte special encoding
  value : size bytes             # a Bool's value IS bit 7; it has no value bytes
  Type nibble on disk: 1 Byte, 2 Int, 3 Bool, 4 Float, 5 Object, 6 Name, 7 Str, 10 Struct
```

Generic size-skipping means a value type never has to be understood to be stepped over. Only a
handful are interpreted: `Format` (Byte), `Palette` (Object), `bHasComp` (Bool), `CompFormat` (Byte).

Mip 0 is full resolution. For v68/v69 the `WidthOffset` gives a free internal check: after reading
`Data`, the cursor must equal `WidthOffset`. For v61 (no offset) the whole-body-to-EOF check is the
integrity guard instead. **Both guards now apply across both arrays.**

**Reading a property's effective value.** A tagged property appears in the list only when its value
differs from the class default. `Engine.Texture`'s effective defaults (resolved from Unreal Gold's
`Engine.u` via the existing `uprops.resolve_class_defaults`) state **none** of `Format`, `bMasked`,
`bAlphaTexture`, `bHasComp` or `CompFormat`, so each defaults to its type's zero: `Format = 0`
(`TEXF_P8`), the three flags `False`. Measured, `Format` is physically present on only **11 of
18,176** texture exports. So every rule below that speaks of "the `Format` code" means the
**effective** value — stored byte if present, else 0 — and *absence is not the same as "no usable
code"*: absence is the byte 0, which is a real claim ("P8") in every enum measured. **The result
does NOT record which of the two it was** (D8): with the code stripped of any power to contradict
the data, a stored 0 and an absent 0 produce the same answer by construction, so there is nothing
for a provenance field to distinguish.

### 3b. Layout detection

**Detection and decodability are two separate questions.** Keeping them apart is what resolves the
first draft's contradiction between "a unique data fit wins even when the code names no implemented
layout" and "an unsampled slot whose chain fits `linear4` yields `unverified-format`":

- **`detect_layout(mips, *, code)` → a layout, or a detection failure.** Pure. Knows nothing about
  which layouts have decoders. Takes the code **for the array being judged** — `Format` for `Mips`,
  `CompFormat` for `CompMips` (§1c) — as an `int` (the effective value, §3a) or `None` meaning *no
  code available at all*. Production always passes an `int`; `None` is for a caller judging a bare
  mip array and for the tests that check the data-only path.
- **The decode step** then asks whether a decoder exists for the detected layout. If not, that is
  `unverified-format` — a *decode* failure over a *successful* detection. Both are true at once and
  they do not conflict.

**Candidates.** A layout `L` is a candidate iff **every** mip in the chain satisfies its size rule:
`n == w·h·N` for `linear{N}`, `N ∈ {1, 2, 3, 4, 8}`; `n == ⌈w/4⌉·⌈h/4⌉·B` for `bc{B}`, `B ∈ {8, 16}`.
Evaluate across the **whole** chain, not just mip 0.

**The ordered procedure.** This is §0b's four-line rule spelled out. `code` is §3a's effective value
(or `None`); the map is §0a's four rows. **The rows are ordered, and they are mutually exclusive by
construction** — rows 5 and 6 partition "exactly one candidate" on whether that candidate is `bc16`;
rows 7 and 8 partition "two or more candidates" on whether the code names one of them; row 2 is
checked before any of them and is the only row that can look at the code without looking at the
data.

| #  | condition | result |
|----|-----------|---|
| 0  | *(selection, §1c)* neither `Mips` nor `CompMips` carries data | `no-mip-data`; detection is never invoked. Otherwise the selected array and its own code are what every row below judges |
| 1  | every mip in the selected array is empty | `no-mip-data` (redundant with row 0 for a texture, but `detect_layout` is callable on any array, so it holds the line itself) |
| 2  | `code is not None` **and** `code` is not one of the map's four slots | **`unverified-format`** — the VETO (§0a/§0b rule 4). Names the code, and for diagnostics the candidates the data fitted, but returns **no pixels even when there is exactly one**. This is the row that stops a 227 `TEXF_BC4` (code 8) chain — which fits `bc8` uniquely and identically to BC1 — from being drawn as BC1. **It is checked before every fit row precisely so that no fit can bypass it.** Measured firing rate on real content: zero (all 11 stored codes are 3 or 7) |
| 3  | no layout fits **mip 0** | `unrecognised-layout` — names the code and mip 0's measured bytes/px |
| 4  | mip 0 fits something but no layout fits the **whole** chain | `size-mismatch` — internally inconsistent; names the mip that breaks it |
| 5  | **exactly one** candidate, and it is `bc16` | code `6` → BC2, code `7` → BC3, `layout_source: format-code`; **any other code (including the implied 0 and `None`) → `ambiguous-alpha`**, no pixels. The documented limit at the top of this spec |
| 6  | **exactly one** candidate, otherwise | that layout, `layout_source: data`. The code is **not consulted** — this is what lets a foreign code-less BC1 `.utx` decode (§0b). It is also where `bc8` is decoded as BC1 by assumption (§0a) |
| 7  | **≥ 2** candidates, and the code names one of them | that layout, `layout_source: format-code`. If that layout is `bc16`, the same code (`6`/`7`) also names its alpha variant. **45.8 % of the corpus** — a first-class branch, and the implied 0 is what resolves 8,324 of the 8,327 ambiguous chains |
| 8  | **≥ 2** candidates, and no code names one of them — the code is `None`, or names a layout that is not among the candidates | `ambiguous-layout` — the data left a genuine choice and nothing legitimate breaks it, so we say so rather than guess (§0b rule 3). Names the candidates and the code. Measured frequency on real content: **zero** (no ambiguous chain lacks `linear1` when no code is stored, so the implied 0 always resolves it) |
| 9  | *(decode step)* the detected layout has **no decoder** — `linear2`/`linear3`/`linear4`/`linear8` | `unverified-format`, naming the **detected layout**, the code and the bytes/px. Never a decoded image |
| 10 | *(decode step)* detected `linear1` and the `Palette` ref does not resolve | `missing-palette` |

Row 9 is why the two draft statements can both stand: a `linear4` chain **detects** successfully
(`layout_source: data`) and **fails to decode**, and the result names the layout, so a diagnostic can
say *"a 4 bytes/pixel linear texture we have no verified decoder for"* rather than *"unknown"*.
(Rows 2 and 9 share a case name on purpose: both mean "this array uses a layout we have not verified
and will not guess at", one learned from the code and one from the data.)

### 3c. Decode rules for the implemented layouts

- **P8** — 1 byte/px, index into the referenced `UPalette` (256 entries): `rgb[i] =
  Colors[Data[i]][:3]`.
- **BC1** — 8-byte blocks: two RGB565 endpoints + 2-bit indices; when `c0 ≤ c1` the fourth index is
  transparent black (the punch-through mode).
- **BC2 / BC3** — 16-byte blocks sharing BC1's colour block at **offset 8** (confirmed by a coherent
  render). Alpha differs: BC2 = 16 explicit 4-bit values; BC3 = two 8-bit endpoints + 3-bit indices,
  with the `a0 ≤ a1` six-interpolant mode. Distinguishing them is the one thing the data cannot do
  (identical size, identical chain), so the `Format` code selects via §0a's map (`6` → BC2,
  `7` → BC3). Any other code — **including the implied 0, which names P8 and therefore names no
  16-byte layout at all** — leaves it `ambiguous-alpha`, never a coin flip. **This is the one place
  the "any texture from any engine" claim is knowingly broken** (D9, and the block at the top of this
  spec): a `bc16`-only chain with no code is exactly a foreign 227/UT BC2-or-BC3 file, and it does
  not decode. A foreign **BC1** file in the same position does, because 8-byte blocks are
  unambiguous — that, not BC3, is the case the design rescues.

### 3d. Traps that must be handled

Each is where naive implementations break, and each is exercised by real data on this machine:

- A mip smaller than 4×4 still occupies a **full block** — 2×2 and 1×1 are 16 B for BC3 (measured on
  `Poster01`) and 8 B for BC1 (measured on `ClenGreyWndow_C`'s `CompMips`).
- **Non-square and partial-block** mips are real: `quadrocks_logo_02` bottoms out at 8×2, 4×1, 2×1,
  and `DmRiot.unr:Fenêtres` (256×128) at 4×2 = 16 B, 2×1 = 16 B. This is where a `bw*4` row write
  walks off the edge.
- `DataCount` is authoritative for length; bytes-per-pixel is a **check**, and a mismatch is a named
  error, never a silent reinterpretation.
- A non-P8 texture still carries a non-zero `Palette` ref (`Poster01` has `pal=952`) — palette
  presence does **not** imply P8.
- **The parser REPORTS body integrity; it does not adjudicate it.** `FireTexture` has both
  zero-length mips *and* trailing `FSpark` bytes, so an "EOF check first" order would classify all
  208 as `corrupt-body` and "a `FireTexture` yields `no-mip-data`" would be unmeetable — but the
  guard as written (`utexture.py:217-219`, `if pos != end: raise ValueError("texture body not at
  EOF…")`) **raises before any other logic runs**, so nothing downstream can get in front of it.

  The resolution is **not** to weaken the guard for the empty-mips case (an earlier draft did exactly
  that, and it left every *other* trailing-bytes shape unguarded on the v61 path, where body-to-EOF
  is the only integrity signal there is). Instead the parser reports **both facts, always, for every
  body**, and never raises for this condition:

  | field                  | meaning |
  |------------------------|---|
  | `trailing_bytes: int`  | `end - pos` after the mip array(s) — `0` for a clean body. Recorded for **every** texture, empty-mipped or not, v61 or v69 |
  | `no_mip_data: bool`    | true iff no mip in either array carries any bytes |

  The **typed layer** (§4) then makes the call, which is where it belongs, because classification is
  that layer's whole job: `no_mip_data` ⇒ `no-mip-data`; else `trailing_bytes != 0` ⇒ `corrupt-body`.
  Nothing is lost relative to today — a body with unparsed trailing bytes still refuses to produce
  pixels — and something is gained: the integrity signal survives as data instead of an exception, so
  a caller can say *how many* bytes were left over. The parser still raises where it genuinely cannot
  continue (a `WidthOffset` cursor mismatch, a structurally impossible count); the typed layer maps
  those to `corrupt-body` too.

## 4. Errors: a typed result from the decode layer; the CLI decides disposition

The first draft said every failure "exits non-zero". That contradicts both the asset catalog's rule
that an undecodable asset **stays enumerable** as an `undecodable` row, and two live callers that
must degrade: `preview_native.py:300-304` warns once per distinct ref and renders a checkerboard;
`dispatch.py`'s sprite path (grep `resolver.resolve_masked(bare)`, ~`:824`, and `is not
P8-decodable`, ~`:837`) falls back to a marker. Exiting non-zero there would stop a whole map preview
because one odd texture exists.

**So the layering is explicit:** the decode layer returns a **typed result** — a decoded texture or a
typed error object naming its case — and the *caller* chooses the disposition. Per-ref requests exit
2 naming the ref; enumeration records an `undecodable` row and continues; preview degrades and
warns. **No Python exception reaches the user.**

This does not weaken "no silent half-answers": that rule governs the **command** layer, and every
degrade above is a caller that has been explicitly designed to degrade (a preview frame, a sprite
billboard) rather than a command silently returning half of what was asked for.

**The union has TWO layers, and both are defined here.** The decode layer's cases are about a body
that was found; the **ref layer**'s cases are about not getting that far. The ref layer is not
somebody else's problem to name later: `TextureResolver.resolve` produces those misses **today**, as
a bare `None` each time, and four committed tests assert exactly that `None`
(`test_utexture.py`'s `test_resolve_group_mismatch_is_miss` `:95`, `test_resolve_bare_ref_is_miss`
`:99`, `test_resolve_unknown_package_and_texture_are_misses` `:105`,
`test_resolve_corrupt_package_is_miss` `:128`). If this spec left them to "the asset catalog", those
four tests would have no defined expectation the moment `resolve` stops returning `None` — so they
are defined here and the catalog **reuses** them.

**Decode-layer cases** (eight). The **needs detection** column matters for sequencing: three cannot
be raised at all until layout detection (§3b) exists, so a build step that introduces the typed
result before detection can only produce the others (plus `unverified-format` as an interim stand-in
for the P8-only gate it is replacing — see the note below the table).

| case                                  | needs §3b? | meaning |
|---------------------------------------|------------|---|
| `corrupt-body`                        | no         | the body cannot be trusted: a `WidthOffset` cursor mismatch, an impossible declared count, an unparseable property list, **or** `trailing_bytes != 0` on a body that does carry mip data (§3d) |
| `missing-palette`                     | no         | a P8 texture whose `Palette` ref does not resolve (or whose palette body will not decode) |
| `size-mismatch`                       | no         | mip 0 fits a layout but a later mip fits none — the chain is internally inconsistent (§3b row 4). On the surviving P8 path: `DataCount != w·h` |
| `no-mip-data`                         | no         | neither array carries any pixel bytes (procedural textures — `FireTexture` et al.); read off the parser's `no_mip_data`, §3d |
| `unverified-format`                   | **partly** | the code names no layout in §0a's map — the **veto**, §3b row 2 — *or* a detected layout with no decoder (§3b row 9). *"format 8 recognised but unverified, no sample available"* |
| `unrecognised-layout`                 | **yes**    | mip 0 fits no known layout at all — names the code and the measured bytes/px (§3b row 3) |
| `ambiguous-alpha`                     | **yes**    | 16-byte blocks and no code selects BC2 vs BC3 (§3b row 5). **The documented universality limit** |
| `ambiguous-layout`                    | **yes**    | two or more candidates and no code names any of them (§3b row 8). Distinct from `ambiguous-alpha`, which is one candidate with two decoders; measured frequency on real content: zero |

**Ref-layer cases** (four). Today's `_decode_ref` has **seven** bare `return None`s plus a
package-load `except` that swallows an eighth miss into the same value; these are what they become.
*(Verified 2026-07-25 by reading `utexture.py`; an earlier draft of the plan said five.)*

| case                | what produced it today | meaning |
|---------------------|------------------------|---|
| `unqualified-ref`   | `return None` on a 1-part or >3-part ref | a `Package[.Group].Name` qualifier is required; a bare name is refused rather than scanned for (a cross-package stem scan is ambiguous), and an over-dotted ref can never match |
| `unknown-package`   | `pkg is None` after `_package(stem)` | no package of that stem on the composed search path |
| `package-unreadable`| the `except (OSError, ValueError, struct.error, IndexError)` inside `_package` | the package **is** on the path but will not open or parse. Today it is indistinguishable from `unknown-package`; splitting them is part of this change, because "your search path is wrong" and "this file is damaged" need different fixes |
| `unknown-texture`   | the loop's final `return None` (name never matched, or matched with a different `Group`) | no `Texture`-classed export of that name in that package. A group mismatch is this case, and the message names the group that was asked for |

The remaining `_decode_ref` misses are decode-layer cases, not new ones: a `decode_texture`
exception ⇒ `corrupt-body`; a `Palette` ref that is out of range or fails to decode ⇒
`missing-palette`; the `t.fmt != 0` gate ⇒ `unverified-format` until §3b replaces it.

**Cases the asset catalog mints, and that this work must not**: `ambiguous-ref` (a bare name matching
several packages — unreachable here, since this layer refuses bare refs outright with
`unqualified-ref`) and `cache-unreadable` (`EACCES` ≠ `ENOENT` on its own cache). The catalog reuses
the four ref cases above verbatim rather than defining its own.

**A miss must never be an image.** `_decode_ref`'s gate is `if t.fmt != 0 or not t.mips` — and a
`mips` list holding *empty* mips is truthy, so the gate lets it through and `mip0_to_rgb` returns
`w·h·3` zero bytes: **a silent, fully black image**. (Verified live 2026-07-25: `mip0_to_rgb(Mip(64,
64, b""), pal)` returns 12,288 zero bytes.) It cannot happen today only because the parser raises on
those bodies first — which is exactly what §3d changes. So the "no mip carries data" check must be
explicit and must come **before** the layout gate, in the same change that stops the parser raising.

**One sequencing constraint the build must respect.** `utexture.py:390`'s
`if t.fmt != 0 or not t.mips` P8-only gate is what currently stops a block-compressed chain reaching
`mip0_to_rgb`, which would read block bytes as palette indices and produce a **wrong image**. It must
**survive** the typed-result change and only be removed by the step that lands §3b. Introducing the
typed result changes its *return* — a bare `None` becomes the typed `unverified-format` case naming
the effective code and the measured bytes/px — not its condition.

## 5. Testing without circularity

A synthesized fixture only proves the decoder agrees with **our own encoder**. Two independent
oracles exist and must be used instead:

1. **The `CompMips` pairs are free third-party DXT1 ground truth.** 69 textures across Deus Ex + LUM
   (207 across the whole tree) store the same image twice — P8 *and* DXT1, encoded by the original
   tools. Decode both halves and compare; no encoder of ours is involved. **The agreement bound is
   per-texture, not universal** — see §6.
2. **Pillow decodes DXT1/DXT3/DXT5** from a hand-built 128-byte DDS header, and Pillow (12.3.0 here)
   is uedcli's *only* third-party runtime dependency (`pyproject.toml:13`, `Pillow>=11`) — so it is
   an independent decoder for all three block layouts at zero new dependency cost. Verified on this
   machine: it decodes all three FourCCs at 4×4, 2×2, 1×1, 8×2, 4×1, 2×1 and 512×128, always to
   `RGBA`; its RGB565→888 expansion is **bit-replication** (`(v<<3)|(v>>2)` and `(v<<2)|(v>>4)`,
   checked against all 32 and all 64 values with zero mismatches, *not* `round(v·255/31)`); and its
   1/3–2/3 interpolants are the plain integer `(2a+b)/3` (measured 170 and 85 between white and
   black). **Byte-exactness against Pillow is therefore achievable**, not merely a tolerance.

Synthesized fixtures remain useful for the *layout-detection* logic and for edge shapes, and a
from-scratch `.utx` **is** buildable — see §5a — but **their expected RGB must be hand-computed or
third-party-produced**, never generated by running our own decoder once, which would assert nothing.

### 5a. A from-scratch `.utx` fixture is cheap, and the working prototype is COMMITTED

The tree already contains a UE1 package **writer**: `uedcli/native/pkg_write.py:92` `build_package`,
with `NameTable` (`:31`), `ImportRec` (`:72`) and `ExportRec` (`:80`) (anchors verified 2026-07-25).

**The fixture builder on top of it is committed as
`dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py`** — a self-verifying script;
the build promotes it (minus its `sys.path` shim and `main()` self-check) to
`uedcli/tests/pkgfixture.py`. Run it and it builds and re-parses every shape this work needs:

```
cd Tools/uedcli && .venv/bin/python \
    dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py
```

Do not re-derive it from this prose. Its `texture_package(...)` keyword surface — `mips=`,
`comp_mips=`, `comp_format=`, `fmt=`, `palette_ref=`, `trailing=`, `declared_mip_count=`,
`version=` — *is* the fixture API every offline test in §6 is written against.

What it proves, all re-verified 2026-07-25: a synthetic **v69 `.utx`** of ~1.4 KB carrying one
`Engine.Texture` export (a P8 `Mips` chain, `bHasComp`, `CompFormat=3`, and a DXT1 `CompMips` chain)
plus one `Engine.Palette` export **parses under `utexture.load_package`**, its classes resolve
through the import table (`class_of_export` returns `Texture` and `Palette`), its absolute
`TLazyArray` skip offsets validate, and the two-array body parse lands exactly on the declared body
end. Turning `bHasComp` off consumes zero bytes after `Mips`, stays EOF-clean, and decodes under
*today's* decoder; a zero-length mip plus trailing bytes reproduces the `FireTexture` shape; a
`Palette` ref pointing past the export table reproduces the missing-palette shape; a lying `Mips`
count reproduces the hostile-input shape (today: a bare `ValueError` out of the decoder).

It is ~150 lines because the **only** back-patching needed is each mip's absolute skip offset, and
`build_package` lays export bodies contiguously from a `dataoff` that is computable before any body
is built (`dataoff = header_len + len(encoded name table)`) — which is why every name must be
interned *before* the table is encoded. Two traps worth recording, both now encoded in the
prototype: (a) a property tag's **size code must match the encoded value's real length** — an
`ObjectProperty` whose ref encodes to one compact-index byte must use size code 0, not 2, or the
property list silently mis-parses; (b) a `BoolProperty`'s value **is** bit 7 of the info byte and it
carries no value bytes at all, though the size code is still written.

**This makes the entire build testable offline**, and it contradicts the asset-catalog plan's note
that "there is no UE1 package writer in the tree" — true for meshes, false for textures.

### 5b. The evidence must outlive this spec — a spike `.md` is a deliverable, not a nicety

This spec and its plan are **ephemeral and get deleted** when the work lands. The spike directory
`dev/docs/spikes/2026-07-25-native-texture-formats/` is durable — but today it contains exactly one
file, `pkgfixture_proto.py`, and **no markdown**. So on the day the spec is deleted, everything the
design was justified with dies with it: the fit census and its method (§1e), the three
`ETextureFormat` dumps (§1a), the eleven stored codes (§1b), the `CompMips` measurements (§1c), the
P8-vs-DXT1 agreement/error table and its wrong-decode controls (§6), and the pinned Pillow
conventions (§5). Some of it survives as constants inside tests, which is not the same thing: a
constant records *what* we expect, never *how it was measured* or *over which corpus*.

**Requirement:** before anything is deleted, the build lands a spike markdown in that directory
capturing the measurements, the method (which roots, which parser, which date) and the oracle
conventions. The *format facts* — the `UTexture`/`FMipmap` byte layout, the property-gated
`CompMips`, the layout-detection rule — go to `dev/docs/unrealed/package-format.md` with confidence
markers, which is their durable home; the *evidence* goes to the spike. The plan makes this a
Done-when in the slice that lands the engine-fact pins, and gates the deletion slice on it.

## 6. Test coverage the build must add

**First, re-measure the test baseline** — do not trust a number written in a spec or plan. The tree
has many concurrent writers and the *passed* count is stale by the time you read it. Run `bin/test`
once before touching anything and record the result; that number is the baseline every later change
compares against. What is load-bearing are the **invariants**, not the count: **1 skipped** (the one
standing skip is legitimate — "no NEW skips" is the criterion, never "zero skips"), **64 deselected**
(the integration tests — a new integration module must move *this* number, not the skipped one),
**1 xfailed**, **0 failed**, the Rust goldens green in the same wrapper, and *passed* only ever going
up. *(For calibration only, and already going stale: on 2026-07-25 the wrapper reported 2435 passed,
1 skipped, 64 deselected, 1 xfailed in 89 s, plus `cargo test` 58 passed. Two earlier drafts recorded
2389 and 2394 — which is exactly why this paragraph replaces the number.)*

- **Layout detection**: a block-format chain (floor at 8/16 B) and a linear chain (`w×h×N`) are
  classified correctly **without** consulting `Format` — assert that literally by calling
  `detect_layout(chain, code=None)` and getting the same layout as with `code=0`; an ambiguous chain
  falls back to the effective code and, where that cannot resolve it, errors honestly. Cover §3b rows
  3 and 4 separately — `unrecognised-layout` (mip 0 fits nothing) and `size-mismatch` (mip 0 fits, a
  later mip does not) must be distinguishable.
- **The veto (§0b rule 4 / §3b row 2), asserted as a pair on one fixture** — this is the test that
  keeps a BC4 texture from being drawn as BC1: a chain that fits `bc8` **uniquely** decodes as BC1
  when no `Format` is stored (`fmt=None`, `layout_source == "data"` — the foreign code-less BC1 case
  the design exists to serve), and the **same chain** with `fmt=8` stored yields `unverified-format`
  naming code 8 and **no pixels**. One flag, two answers; without the pair, the veto can be dropped
  without a red test.
- **Detection succeeds, decode fails (§3b row 9)**: a chain fitting `linear4` uniquely with **no**
  stored code detects as `linear4` / `layout_source == "data"` **and** returns `unverified-format`
  naming `linear4` and 4 bytes/px. Assert both halves — a test that only checks the error would not
  notice detection silently failing. *(Use `fmt=None`, not `fmt=5`: a stored 5 is vetoed at row 2
  before detection reports anything, which is a different — also correct — outcome, and worth its own
  one-line assertion.)*
- **The array/code pairing (§1c)**: the `CompMips` array is judged against `CompFormat`, not
  `Format`. The `CompMips` fixture's two arrays detect as `linear1` (from `Mips`) and `bc8` (from
  `CompMips`), and neither one's code interferes with the other's array.
- **Array selection before detection (§1c)**: a texture whose `Mips` array is empty and whose
  `CompMips` carries data decodes **through the fallback**; a texture where neither carries data is
  `no-mip-data` and detection is never called (assert no exception, and assert the case — an empty
  chain reaching detection would index mip 0 of an empty list); and a texture whose `Mips` carries
  data but fails to decode reports **its** error rather than falling through to `CompMips`.
- **A miss is never a black image (§4)**: a texture whose only mip is zero-length resolves to the
  typed `no-mip-data` case, and the assertion is on the case — explicitly **not** satisfied by a
  `w·h·3` buffer of zeros, which is what today's code path would hand back once the parser stops
  raising.
- **Per layout**: P8, BC1, BC2, BC3 decode byte-exact against the §5 oracles.
- **`CompMips`**: `bHasComp` textures parse to EOF; both arrays decode; `Mips` is preferred over
  `CompMips`; the P8-vs-DXT1 agreement check holds. **The bound is a loose structural one, not
  "≤ ~1/255"** — re-measured mean absolute channel error against Pillow-DDS:
  `quadrocks_logo_02` mip 0 = **0.605**/255, but `ClenGreyWndow_C` mip 0 = **1.98**, mip 1 = **4.32**
  (max channel delta 74), mip 2 = **5.72**, mip 3 = **8.47**. Use **≤ 8/255 on mip 0 only**. It still
  discriminates: three deliberately wrong decodes of the same data scored **20.3**, **35.9**,
  **39.3** and **62.0**, so the gap at mip 0 is about tenfold — but the earlier claim that a wrong
  decode "scores 60–80" is **not** general, and the bound does not hold at deeper mips.
- **Edge shapes**: sub-block mips (2×2, 1×1) and **non-square / partial-block** mips (8×2, 4×1, 2×1)
  — the row-write overrun case.
- **Honest failure**: each §4 case is distinct and named; a `FireTexture` yields `no-mip-data`, not a
  wrong pixel; an unsampled slot yields `unverified-format`; a hostile mip count or dimension yields
  `corrupt-body` in bounded time and memory rather than an `IndexError`/`MemoryError`.
- **The ref layer's four cases (§4)**, one test each, and they are the same four the existing tests
  already exercise — so the migration is a re-pointing, not new coverage:
  `test_resolve_bare_ref_is_miss` (`:99`) → `unqualified-ref`;
  `test_resolve_unknown_package_and_texture_are_misses` (`:105`) → `unknown-package` and
  `unknown-texture` respectively; `test_resolve_group_mismatch_is_miss` (`:95`) → `unknown-texture`
  naming the group; `test_resolve_corrupt_package_is_miss` (`:128`) → `package-unreadable`, which is
  a **new distinction** (today it is indistinguishable from `unknown-package`) and therefore needs a
  second assertion that a genuinely absent stem still gives `unknown-package`.
- **The body-integrity report (§3d)**: `trailing_bytes == 0` on both committed fixtures; a
  constructed body with real pixel data + 24 trailing bytes gives `trailing_bytes == 24`,
  `no_mip_data is False`, and the typed case `corrupt-body`; the same body with an empty mip gives
  `no_mip_data is True` and the typed case `no-mip-data`. The parser raises in neither.
- **Disposition**: preview degrades and warns naming the case; the sprite path degrades to a marker;
  neither exits non-zero. *(A per-ref `texture show` verb does not exist — see §8's resolution table
  — so the "exits 2" half of the layering cannot be asserted by this work.)*
- **Corpus sweep — TWO TIERS.** Every texture-classed export either decodes or produces a named case:
  **zero silent misses, zero exceptions**. This is the test that would have caught both the fmt-7 gap
  and `CompMips`.
  - **Offline tier (no marker)** over the two corpora a checkout can reach — but with **exact counts
    only where they are stable** (the count-stability rule in the Environment section):
    - `ued22_root()` — **fully tracked**, so exact: 34 packages, 1,998 `Texture` exports, 1,998 mip
      arrays (it has no `CompMips` at all), **861** fitting one layout and **1,137** ambiguous,
      0 parse failures, 0 `unrecognised-layout`, 0 `ambiguous-layout`, 0 `ambiguous-alpha`.
    - `repo_texture_root()` — **partly tracked and live**, so **invariants only**: every export
      either decodes or names a case, 0 parse failures, 0 `unrecognised-layout`, 0 `size-mismatch`,
      0 `ambiguous-layout`, 0 `ambiguous-alpha`, and no unhandled exception. Do **not** assert a
      package or export total here; the directory holds 4 tracked packages (384 exports) plus
      whatever else the machine has (6 packages / 418 exports today), and it is content sessions add
      to. The one exact clause is the motivating bug, pinned to a single tracked file:
      **`LUM_CoreTex.utx` goes from 30 `Texture`-class parse failures to 0.**

    Exact counts where they are legitimate are what turn a silent regression into a red test; a "no
    exceptions" sweep passes happily while everything degrades to a named error. An exact count over
    a directory a fresh checkout populates differently is the opposite — a test that fails for the
    wrong reason and gets edited until it stops.
  - **Integration tier (`-m integration`)** over the Deus Ex install and the Unreal install.
  - **The sweep needs its OWN export matcher, and must say so.** `utexture.textures()` matches
    `class == "Texture"` **exactly** (`utexture.py:245`), so `FireTexture`/`WetTexture`/
    `ScriptedTexture` are never enumerated through it — and widening it is explicitly a non-goal
    (§7). The sweep therefore defines a **test-local** matcher (`(pkg.class_of_export(i) or
    "").endswith("Texture")`) and asserts the `no-mip-data` criterion over *that*, plus — in the same
    test — that the shipped `utexture.textures()` still returns none of them, so the widening cannot
    leak into production.
- **Non-regression**: `test_utexture.py:39` `test_decode_v69_pixel_exact` and `:48`
  `test_decode_v61_pixel_exact` still pass with unchanged digests. `test_utexture.py:57`
  `test_decode_all_mips_reach_eof` **encodes the old one-array assumption** and must be *updated* for
  the two-array contract, not deleted — and it gets stronger rather than weaker: where it relied on
  `decode_texture` raising, it now asserts `trailing_bytes == 0` on every texture in both fixtures,
  which is the same guarantee stated positively. `test_utexture.py:115`
  `test_resolve_caches_per_instance` asserts **object identity** on the resolver cache
  (`assert r.resolve("CoreTexWater.dirtywater") is first`), so the new result type must stay
  identity-cached — the cache returns the same object, never an equal rebuild.
- **Three other modules the return-type change breaks, and they are easy to miss:**
  - `uedcli/tests/test_actor_preview.py` — `_FakeResolver` (`:352`) implements exactly
    `resolve_masked(ref)` (`:359`) and `exists(ref)` (`:362`) and is fed 4-tuples `(w, h, rgb, mask)`
    (`:374`, `:463`); `:405` asserts the **literal string** `"not P8-decodable"` in stderr. Rewrite
    the fake onto the new seam and re-point that assertion at the case name; per the no-back-compat
    rule, do not keep `resolve_masked` as an alias.
  - `uedcli/tests/test_ingest_validation.py:70` — `assert r.resolve("Weird.RGBA7Tex") is None`, inside
    `test_texture_exists_is_existence_not_decodability`; becomes an assertion on the typed case
    **`corrupt-body`**, and no other. The fake package that test builds gives its exports
    `soff=0, ssize=0` over `buf=b""`, so the body has no property list at all and `decode_texture`
    raises `IndexError` (verified live 2026-07-25) — despite the `RGBA7Tex` name, nothing in that
    fixture is a *format* miss, so asserting a format case there would be asserting a fiction. What
    the test is really pinning is unchanged: `exists()` says True while decode fails.
  - `uedcli/tests/test_utexture.py` — the nine `TextureResolver` tests from `:82` (after the
    `_resolver()` helper at `:77`).
- **Enum dump as evidence, and as the pin for §0a's map**: the three `ETextureFormat` slot lists of
  §1a are re-asserted per the "pin the finding" rule — used as *evidence*, never as a runtime
  dependency (assert that no production module reads them). Specifically: the UED22/227 dump asserts
  `{0: TEXF_P8, 3: TEXF_BC1, 6: TEXF_BC2, 7: TEXF_BC3}` **and `8: TEXF_BC4`** (the veto's evidence —
  the slot that proves an unmapped code can collide byte-for-byte with `bc8`) and 122 slots; Unreal Gold asserts
  `{0: TEXF_P8, 3: TEXF_DXT1, 6: TEXF_DXT3, 7: TEXF_DXT5}` and 8 slots; Deus Ex asserts
  `{0: TEXF_P8, 3: TEXF_DXT1}` and exactly **5** slots — i.e. that it *does not define* 6 or 7, so
  its silence is pinned as silence rather than as agreement. **Together these three are the assertion
  that §0a's four-row map is justified**; if a substrate ever breaks the agreement, this is the test
  that goes red. **The UED22/227 dump is offline** (`uned/UED22/Engine.u` is git-tracked); the Unreal
  Gold and Deus Ex dumps are integration and skip cleanly when their installs are absent.

## 7. Non-goals

- **Encoding** textures (this is a decoder; the §5a fixture builder is test-only and never ships).
- **Implementing the unsampled linear slots** — D3's board item owns them.
- **Requiring or shipping a per-game format table** (D1).
- **Changing which exports count as textures.** `utexture.textures()` matches `class == "Texture"`
  exactly; widening it to `Engine.Texture` descendants belongs to the asset catalog. But note §1d:
  those subclasses fail for their own reason, so this spec's `no-mip-data` case is what keeps them
  honest when that lands. **Consequence the build must not paper over:** a procedural texture is
  therefore *unreachable through the shipped API*, so any "a `FireTexture` yields `no-mip-data`"
  criterion has to run through the sweep's own test-local matcher, or over a constructed fixture —
  never through `textures()`. §6 says which.
- **Lightmap formats inside `Model`** rather than as `Texture` exports.
- **Migrating `utexture`'s private package parser onto the shared `upackage.py` core** — a
  pre-existing, separate board item (`architecture.md`, grep `migrate as a board follow-up`).

## 8. Open questions — all now resolved

| # | Question | Resolution |
|---|----------|---|
| A | Single-mip textures whose chain cannot be fitted uniquely | **Answered and resized.** This is not an edge case: 8,327 of 18,176 exports (45.8 %) fit ≥ 2 layouts. The **effective** `Format` code (stored byte, else the implied 0) breaks the tie through §0a's map; if it names no layout in the map the array is vetoed with `unverified-format`; if it names nothing among the candidates — or there is no code at all — `ambiguous-layout`; if it leaves BC2-vs-BC3 open, `ambiguous-alpha`. Three real single-mip block samples exercise it — `DmRiot.unr:SolModifié` (128×128), `:Flotte` (64×64), `DMBeyondTheSun.unr:Uebergang3` (256×128) — not the two the draft named, and all three store `Format=7`. |
| B | Is `CompFormat` ever anything but DXT1 in the wild? | **Answered: no.** `(Format ⇒ 0, CompFormat = 3)` in 69/69 Deus Ex + LUM cases and 207/207 over the whole tree (§1c). |
| C | Is a data-vs-`Format` **disagreement** an error or a note? | **Neither — the case is GONE** (Andrzej, AD1: §2 D8). A code never contradicts the data; it breaks ties (§3b rows 5/7) and vetoes an unknown layout (row 2). The question dissolved with the machinery: the disagreement fired on zero of 18,176 real exports while inventing a contradiction on every non-P8 chain that stored no code. |
| D | Mask semantics for the block formats | **Resolved below — the decoder emits the mask the data carries and never consults `bMasked`/`bAlphaTexture`.** |

### 8-C. *(withdrawn)* — the disagreement case no longer exists

This section defined `format-disagreement` and the stored-vs-defaulted provenance that made it
survivable. **Andrzej deleted both** (AD1, 2026-07-25): see §0b for the arbitration that replaces
them and §2 D8 for the decision with its rejected alternatives (keeping the case as a fixture-only
diagnostic; keeping the provenance axis). The heading is kept because other sections cite "§8-C";
nothing here is design any more.

### 8-D. Mask semantics: the decoder emits the mask the data carries, and ignores `bMasked`

**Decision.** The transparency mask a decode returns is derived **only from the pixel data**:

- **P8** — unchanged from today: palette index 0 = transparent, 1 = opaque
  (`utexture.py:359`). The P8 data carries no alpha, so this convention *is* the data's mask.
- **BC1** — the punch-through alpha: in the `c0 ≤ c1` mode, index 3 is transparent; otherwise fully
  opaque.
- **BC2 / BC3** — the block's own alpha values.

The `bMasked` and `bAlphaTexture` properties are **read and reported as facts on the result**, and
the decoder never applies them.

**Rationale.** uedcli's standing principle is that **the tool does not infer**: it reports what is
literally stored and produces the picture, and leaves meaning to the caller. Alpha bits inside a
BC1/BC2/BC3 block are literally in the data; `bMasked`/`bAlphaTexture` are *engine render policy*
that belongs to whoever is drawing. Folding them into the decoder would make the same bytes decode
to two different images depending on a flag the renderer, not the pixel layer, owns — and dropping
real stored alpha because a flag is unset is data loss the caller cannot undo. Keeping the P8 rule
exactly as it is also protects the invariant that the `CompMips` slice must not move a single
decoded pixel.

*Rejected: gate the block-format alpha on `bMasked`/`bAlphaTexture` inside the decoder.* An unflagged
BC3 texture would then decode to a fully-opaque image that silently discards stored alpha; and the
decoder's output would depend on a property that has nothing to do with how the bytes are laid out,
which is the beginning of exactly the per-game-semantics table D1 rejected.

**Status: builder-decided under Andrzej's "do whatever it takes" delegation. Reversible** — the flags
are on the result object either way, so honouring them later is an additive change at the one caller
that wants it.

## 9. Board item this spec creates (D3)

`p1 [spike/implement]` — **the remaining UE1 texture layouts** (Unreal Gold's
RGB32/RGB64/RGB24/RGBA8; 227's BGRA8_LM/R5G6B5/RGB8/BGRA8, and BC4+). No samples exist on this
machine, and the slot numbers are not portable (§1a), so this needs sample acquisition first — a
UT/227 content set, or a purpose-built export. Until it lands, those slots produce the
`unverified-format` error. *(Already filed in `dev/docs/board/inbox/` — grep
`The REMAINING UE1 texture layouts`.)*

## 10. Review gates

### Round 3 (2026-07-25, two cold reviewers over the spec **and** its plan) + two Andrzej decisions

Round 3's findings were resolved together with two decisions Andrzej took over the same material.
The decisions came first and dissolved several of the findings outright:

| finding / decision | resolution |
|--------------------|---|
| **AD1 (Andrzej)** — drop `format-disagreement` and the stored-vs-defaulted `format_source` axis; a code breaks ties and vetoes but never contradicts the data | **§0b** is the whole rule now; **§2 D8** records it with both rejected alternatives; the §3b table is rewritten with non-overlapping rows and the provenance field is gone everywhere |
| **AD2 (Andrzej)** — a `bc16` chain no code resolves is `ambiguous-alpha`, and that is a **stated limit on universality** | the block at the **top of this spec**, plus **§2 D9**, **§3c** and **§3b row 5**. Every rule argued with a "foreign BC3 file" example is rewritten around **BC1**, which the rules do rescue |
| **A stored code naming a layout we do NOT decode must veto a unique data fit** — 227 slot 8 is `TEXF_BC4`, whose 8-byte blocks fit `bc8` identically to BC1, so "a unique fit always wins" would draw a BC4 texture as BC1 | **§0a** (the measured collision, incl. slots 9–11) and **§3b row 2**, ordered ahead of every fit row. §0a also records that an *uncoded* `bc8` chain is BC1 by **assumption** |
| `<repo>/Textures/` is **not** fully tracked — 2 of its 6 packages are untracked — so every "offline exact count" over it was wrong and unstable | **Environment §** count-stability rule; every count re-derived (tracked: 4 packages / 384 exports, not 6 / 418). Exact counts now only over `uned/UED22` + fixtures + the single tracked `LUM_CoreTex.utx` (30 → 0) |
| The typed union had no case for the **ref-level** misses `TextureResolver.resolve` actually produces — `_decode_ref` has **seven** bare `return None`s (not five), and four committed tests assert that `None` | **§4** defines four ref cases (`unqualified-ref`, `unknown-package`, `package-unreadable`, `unknown-texture`), maps each existing test onto one, and states that the asset catalog reuses them |
| The design shipped a **black-image** path: the gate `if t.fmt != 0 or not t.mips` passes a list of *empty* mips, and `mip0_to_rgb` then returns all-zero RGB (verified live) | **§4** "A miss must never be an image" + a §6 criterion asserting the case, explicitly not satisfied by a zero buffer |
| The body-to-EOF guard was being weakened just so a fixture could produce `no-mip-data` | **§3d** — the parser now **reports** `trailing_bytes` + `no_mip_data` for every body and never raises for this condition; the typed layer classifies. The v61 integrity signal is preserved for *all* bodies, not sacrificed |
| The "only `CompMips`" case had no defined path — "`Mips` is absent" was never defined, selection-vs-detection order was unstated, and detection over an empty chain would `IndexError` | **§1c** "Which array wins" — selection is defined (carries data / does not), ordered before detection, with the no-fallback-on-error rule and its rejected alternative |
| The census never said whether it counted textures or mip arrays | **§1e** — both, with `CompMips` arrays counted separately (69, all `bc8`-unique) |
| Two Done-whens were uncheckable ("the same answer when the code is withheld" with no withheld state; "asserts the typed case" without naming it) | **§6** — `detect_layout(chain, code=None)`, and the ingest test's case named (`corrupt-body`, verified live) |
| The spike dir S7 keeps holds only `pkgfixture_proto.py` — the census, enum dumps, oracle tables and Pillow pins would die with the spec | **§6/§5a + the plan's S6/S7** — a spike `.md` capturing the evidence lands **before** anything is deleted |

### Round 2 (2026-07-25, two cold reviewers over the spec **and** its plan)

*(Historical. Two of its resolutions were later replaced by AD1/AD2 above — the
`stored`/`class-default` provenance row and everything that mentions `format-disagreement`. They are
left as written because this is a record of what the round found, not current design.)*

Both reviewers converged on the same three design holes. All resolved above; recorded here because
each was a real hole in the design, not a wording problem:

| finding | resolution |
|---------|---|
| **The `Format` code → layout map is never written down** — yet the design makes the code the decider for 45.8 % of the corpus and the only BC2/BC3 selector, which needs a `{code → layout}` map: the very artifact "no format table" says must not exist | **§0a** — the map is stated (`{0: P8, 3: BC1, 6: BC2, 7: BC3}`, everything else recognised-but-unsampled), named as THE one place slot semantics are assumed, justified from the three measured enums, scoped so it never sizes a chain and decoding survives its absence, and **pinned** by §6's enum regressions |
| **A defaulted `Format` out-voted a unique data fit**, so a foreign 227/UT BC3 `.utx` storing no `Format` — like 99.94 % of all textures — would return `format-disagreement` and no pixels | **§0b** — `stored` vs `class-default` provenance on the result; only a stored code may contradict a unique fit or raise `format-disagreement`. Measured cost: zero (no ambiguous chain lacks `linear1` when no code is stored). It also makes `ambiguous-alpha` reachable again |
| **"Data-decisive but unimplemented" was self-contradictory** — a unique fit was said to win *and* an unsampled slot fitting `linear4` was said to yield `unverified-format` | **§3b rows 6 + 10** — detection and decodability separated: detection succeeds (`linear4`, `layout_source: data`), the decode step then fails with `unverified-format` naming the detected layout |
| The `no-mip-data`-before-EOF rule was unimplementable as sliced — the guard raises before any layout logic | **§3d** — the rule moves *into* the guard (record a flag, don't raise), so layout detection never reopens it |
| The `CompMips` array was to be judged against `Format`, which would land all 69 target textures in `format-disagreement` | **§1c** — the detector takes the code for *that array* as an explicit parameter; §6 asserts one texture detecting two layouts from its two arrays |
| The corpus guard rail was integration-only, deselecting by default the criterion for the motivating bug — both `LUM_CoreTex.utx` and `uned/UED22/` are git-tracked | **Environment §** and **§6** — two-tier sweep: offline over the tracked corpora with exact counts, integration over the two installs |
| Removing the P8-only gate too early would emit wrong images for two slices | **§4** — the gate survives until layout detection lands; only its *return* changes |
| Test modules the map never listed (`test_actor_preview.py`'s `_FakeResolver` + its `"not P8-decodable"` string assertion, `test_ingest_validation.py:70`, and `test_utexture.py:115`'s object-identity cache assertion) | **§6** — all three enumerated with the specific edit each needs |
| Cross-file line anchors stale by 40–135 lines; pinned test baseline stale (2394 vs a measured 2435) | anchors re-derived and converted to grep text (Environment §); the baseline replaced by a re-measure instruction plus its invariants (**§6**) |
| Self-containment failed at `pkgfixture.py` — a described prototype that was not in the tree | **§5a** — the working prototype is **committed** at `dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py` and is self-verifying |
| Board instructions obsolete (`board/to-plan/` line is a tombstone; `board/to-build/` still calls this "an untriaged inbox item") | recorded in the plan's S7, which now deletes the tombstone and fixes the stale prerequisite note |
| "Procedural classes reporting `no-mip-data`" unreachable — `textures()` matches `class == "Texture"` exactly and widening it is a non-goal | **§6/§7** — the sweep gets its own test-local matcher, and asserts in the same test that production stays exact-match |

### Round 1 (2026-07-25, two cold reviewers over the first draft)

Both reviewers reproduced the census and both found load-bearing errors in the first draft. Folded:

| finding | resolution |
|---------|---|
| `fmt=7` is **DXT5/BC3** and `6` is DXT3/BC2, provable from the games' own `Engine.u`; the draft's "not in the classic enum / OldUnreal extension" was wrong | §1a — identified, corroborated by the alpha-block signature; the draft's BC2-vs-BC3 experiment deleted |
| **`bHasComp`/`CompFormat`/`CompMips`** is the real cause of the trailing bytes | §1c — measured layout replaces the draft's three hypotheses (the reviewers' "147/147" is itself corrected there) |
| "Deus Ex is 100 % P8, so this buys nothing here" is **false** — 30 of LUM's own textures are invisible today | §1c — value story corrected; it strengthens D5 |
| The per-format name/size table was UT99 naming asserted over substrates that disagree (slot 2: 8 B/px vs 2 B/px) | §0/§1a — resolved by Andrzej's own steer: derive from data, no table at all |
| "All 69 failures are class `Texture`" was a tautology of the sweep; `FireTexture` has a different cause (`TArray<FSpark>`); the count 69 didn't reproduce | §1d — both causes separated, counts restated with their corpus |
| Fixture plan was circular; better oracles exist (the P8↔`CompMips` pairs; Pillow-DDS) | §5 — rewritten around non-circular oracles |
| "Exits non-zero" contradicts the catalog spec and breaks `preview`'s degrade-and-warn | §4 — typed result from the decode layer, caller chooses disposition; case list unified |
| Formats 1/2/4/5 would be implemented from a guess, returning wrong pixels rather than errors | D2 + D3 — implement measured layouts; the rest become a `p1` board item (Andrzej) |
| Fixtures missed the non-square/partial-block mip case | §3d trap list + §6 edge shapes |
| No `no-mip-data` case for procedural textures | §4 |
| `test_decode_all_mips_reach_eof` encodes the old assumption | §6 non-regression note |

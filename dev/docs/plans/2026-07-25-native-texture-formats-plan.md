# Plan: native texture decode for any UE1 package

**Spec:** `specs/2026-07-25-native-texture-formats.md` (review-gated three times, 2026-07-25; rounds
2 and 3 reviewed this plan alongside it, and round 3 arrived together with two decisions from
Andrzej — **AD1** and **AD2** — that removed an error case and named a limit. Everything is folded
below; the spec's §10 has the round-by-round record).
**Supporting spike (durable — survives the deletion of this plan):**
`dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py`, the committed,
self-verifying from-scratch `.utx` builder every offline Done-when below is written against (§0e2).
**Ephemeral:** scratch for sequencing this build; delete when the work lands. The durable record
afterwards is `decisions.md` (the choices) + `dev/docs/unrealed/package-format.md` (the format
facts) + `architecture.md` (what the code does).

**This plan is SELF-CONTAINED.** Everything needed to build the feature — the binding decisions and
their rejected alternatives, the on-disk byte layout, the environment, the house rules, and every
measured number — is stated here. Source code may be read; **no other document needs to be
opened.** Provenance pointers are given for the archaeological record only. (The plan and the spec
overlap deliberately: either one alone is sufficient.)

---

## THE LIMIT ON "reads any texture from any engine" — read this before building anything

The decoder this plan builds is deliberately **not** universal, and the exception is small, sharp and
permanent. It must be stated wherever the universality claim is made, in code comments, docs and
error text:

> **A BC2 or BC3 (DXT3/DXT5) texture that stores no `Format` code does NOT decode.** It returns the
> named error `ambiguous-alpha` and no pixels. BC2 and BC3 have byte-identical sizes and mip chains
> and differ only in how each block's alpha half is encoded; nothing in the data separates them, and
> this design never guesses.
>
> **A BC1 (DXT1) file in the same position DOES decode** — 8-byte blocks are shared with no other
> layout we decode, so the data alone settles it. So does P8, and so does any chain whose mip sizes
> fit exactly one layout.

*(Andrzej's decision **AD2**, 2026-07-25 — `decisions.md` "Texture layout arbitration is a
tiebreak-and-veto". §0c D9 states it with its rejected alternatives.)*

**Consequence for how this plan argues.** Every justification below uses **BC1** as its worked
foreign-file example, never BC3 — because BC1 is the case the rules actually rescue. An earlier draft
justified a rule with "a foreign 227/UT BC3 `.utx` must decode"; it does not decode, and the argument
was rewritten. If a future edit reintroduces a BC3-based justification, it is wrong.

Measured consolation: across all 18,176 texture exports on this machine, **zero** hit this limit —
every one either fits a single layout or is resolved by its code. The limit bites only on foreign,
code-less, block-compressed content we have never seen.

---

Governing principle this plan must not drift from: **the layout is read off the data; the numeric
`Format` code breaks ties and vetoes unknown layouts, but never contradicts the data and never sizes
a chain.** Where the data alone cannot decide and no code resolves it, we say so with a named error
rather than guessing (decisions D1, D6, D8, D9 below).

Two corollaries that are easy to lose and that this plan states explicitly, because a build that
drops either produces a decoder that fails on exactly the files it was written for — or, worse,
succeeds wrongly:

1. **The tiebreak needs a `{code → layout}` map, and it is four slots.** §0d writes it down, names it
   as THE one place slot semantics are assumed, justifies it from three measured `ETextureFormat`
   dumps, and scopes it so it is not the format *table* D1 rejects.
2. **A code naming a layout OUTSIDE that map stops the decode — even when the data fits exactly one
   layout.** 227's slot 8 is `TEXF_BC4`, whose 8-byte blocks fit `bc8` identically to BC1, so a
   "unique fit always wins" decoder would draw a BC4 texture as BC1: a confident wrong image on a
   file whose own code says it is not BC1. §0d states the veto and S3 orders it ahead of every fit
   branch.

**One thing depends on this work:** the unified asset catalog's texture arm
(`plans/2026-07-25-unified-asset-catalog-plan.md` slice `S8a`, which that plan gates on this one as
its `P1`). That arm names every tracked texture-classification shard `sha256(width, height, RGB)` —
a **frozen, unversioned identity** — so any later change to what this decoder outputs silently
re-keys every shard, and every classification an LLM has authored reads back as "unclassified".
Practically, and this is the whole of what the dependency means: **land this work before any texture
is classified**, and treat "which mip array wins" and "what the mask means" as settled once shipped.

---

## 0. Shape of the build

**Seven slices, each one commit whose tests pass with no NEW skips versus the pre-slice baseline.**

**Re-measure the baseline at the start of S1 — do not trust a number written here.** The tree moves
under this plan (concurrent sessions land tests continuously), so the *passed* count is stale by the
time you read it. Run `bin/test` once before touching anything and write the result into the S1
commit message; that number, not this paragraph, is the baseline every later slice compares against.

What is load-bearing, and what every slice must hold, are the **invariants**, not the count:

- **1 skipped** — the one standing skip is legitimate; "no NEW skips" is the criterion, never "zero
  skips".
- **64 deselected** — the integration tests. S6's new integration module must move *this* number, not
  the skipped one (see §0b).
- **1 xfailed**, **0 failed**, and the Rust goldens green in the same wrapper (`cargo test`).
- The *passed* count only ever goes **up**.

*(For calibration only, and already going stale: on 2026-07-25 the wrapper reported 2435 passed,
1 skipped, 64 deselected, 1 xfailed in 89 s, plus `cargo test` 58 passed. Two earlier drafts of this
plan recorded 2389 and 2394 — which is exactly why the instruction above replaces the number.)*

Order is **value-first**: the live bug (69 textures invisible across Deus Ex + LUM, 30 of them in
the project's own `LUM_CoreTex.utx`) is fixed in S1, before any new pixel format is decoded.

```
S1  CompMips: parse BOTH mip arrays; prefer Mips     <- fixes the live bug, 69 textures
S2  Typed decode results + caller dispositions        <- the error layering
S3  Layout detection from the mip chain               <- D1, the governing idea
S4  BC1 decode                                        <- makes the CompMips fallback real
S5  BC2 / BC3 decode + ambiguous-alpha
S6  Corpus sweep (offline tier + integration tier) + engine-fact pins
S7  Docs, board, spec deletion
```

### 0a. The environment: where the corpora live, and what is committed

The tool lives at `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli`. The git repo root is
`/home/neob91/Games/LutrisDX/drive_c/DX/LUM` (the `LUM` Deus Ex mod). A fresh checkout on another
machine has only the **committed** rows.

| corpus                             | path | committed? |
|------------------------------------|------|---|
| **Deus Ex install**                | `/home/neob91/Games/LutrisDX/drive_c/DX/{System,Textures,Maps}` | **no** — it sits *outside* the repo (the repo root is a subdirectory of it). Reachable in-tree only through the symlink `Tools/uedcli/uned/DeusExAssets → /home/neob91/Games/LutrisDX/drive_c/DX`, which is itself gitignored (`.gitignore:9`). |
| **The project's own textures**     | `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Textures/*.utx` — notably `LUM_CoreTex.utx` (17 MB) | **PARTLY.** `git ls-files Textures/` lists four packages: `France.utx`, `LUM_CharacterTex.utx`, `LUM_CoreTex.utx`, `LUM_InfoPortraits.utx` (384 `Texture` exports). `CoreTexSky.utx` + `CoreTexWater.utx` are in the same dir **untracked** (34 more), and sessions add content there. See the count-stability rule below |
| **Unreal Gold** (227i-patched; its `System/Engine.u` is still the stock 8-slot build) | `/home/neob91/Games/Unreal/pfx/drive_c/Unreal` | **no** — outside every repo, and there is **no in-tree pointer to it at all** |
| **UED22 editor substrate**         | `Tools/uedcli/uned/UED22/` — 214 tracked files, 34 of them packages this parser reads, 1,998 `Texture` exports | **yes** |
| **Existing fixtures**              | `Tools/uedcli/uedcli/tests/fixtures/{CoreTexWater,LUM_InfoPortraits}.utx` | **yes** |

**Offline vs integration is decided entirely by that column.** Every corpus-wide criterion over the
Deus Ex install or the Unreal Gold install is `-m integration`; everything else must run against
committed material. Each Done-when clause below is tagged **(offline)** or **(integration)**.

**Two of the four corpora are reachable offline, so most corpus criteria are OFFLINE.**
`Textures/LUM_CoreTex.utx` (which holds **all 30** of the LUM textures this build exists to fix) and
`uned/UED22/` (34 packages, 1,998 `Texture` exports, 1,137 of them ambiguous) are both in git —
verified with `git ls-files` on 2026-07-25. An earlier draft filed the whole corpus sweep as
integration-only, which would have **deselected by default the criterion for the very bug that
motivates the build**. S6 therefore runs the sweep in **two tiers** (§S6), and S1's "30 → 0" clause
is **offline**.

**COUNT-STABILITY RULE — where an exact expected count is legitimate, and where it is a bug.**
An offline test may assert an **exact count** only over material a fresh checkout is guaranteed to
have *and* that nothing else writes:

- ✅ `uned/UED22/` — **fully tracked**: 34 packages, 1,998 `Texture` exports, no `CompMips` arrays,
  861 chains fitting one layout / 1,137 ambiguous.
- ✅ the committed fixtures under `uedcli/tests/fixtures/`.
- ❌ **`<repo>/Textures/`** — only 4 of the 6 packages present here are tracked, and it is live
  content sessions add packages to. **Any total measured there is a snapshot, not a contract.** Over
  that root a test asserts **invariants** instead: 0 parse failures, 0 `unrecognised-layout`,
  0 `size-mismatch`, 0 `ambiguous-layout`, 0 `ambiguous-alpha`, every export either decodes or names
  a case, no unhandled exception.
- ✅ **the one exception**: the motivating-bug clause is exact because it is pinned to a single
  tracked *file* — `LUM_CoreTex.utx` goes from **30** `Texture`-class parse failures to **0**
  (re-measured 2026-07-25: it holds 253 `Texture` exports and all 30 of the tracked failures; the
  other three tracked packages fail zero).

An earlier draft asserted "6 packages / 418 exports" over that directory as an offline expectation.
Both numbers include untracked files, so the assertion was wrong on a fresh checkout and unstable on
this one. **Re-derive every count before writing it into a test.**

The DX install is located by `install_root()` in `uedcli/tests/conftest.py` (env override
`UEDCLI_TEST_INSTALL`; its no-env fallback is `Path(__file__).resolve().parents[2]/"uned"/
"DeusExAssets"`). **There is no equivalent pointer for the Unreal install** — S6 adds
`UEDCLI_TEST_UNREAL_INSTALL` and skips cleanly when it is unset. The two **tracked** corpora need no
env pointer at all and S6 adds two conftest helpers beside `install_root()` for them, anchored the
same way on `conftest.py`'s own location:

```python
def ued22_root() -> Path:      # Tools/uedcli/uned/UED22 — git-tracked, 34 packages
    return Path(__file__).resolve().parents[2] / "uned" / "UED22"

def repo_texture_root() -> Path:   # <repo>/Textures — PARTLY tracked (4 of 6 pkgs here) and live:
    return Path(__file__).resolve().parents[4] / "Textures"   # invariants only, never exact counts
```

(`parents[2]` is `Tools/uedcli`, `parents[4]` is the repo root — both verified 2026-07-25.)

**Note on paths in older material:** the developer docs tree was renamed `docs/dev/` → `dev/docs/`
(so `docs/` is physically all user-facing). Older commits, docs and board lines may still spell the
old path; `dev/docs/` is current and `docs/dev/` no longer exists.

### 0b. The house rules this build must satisfy

Reproduced here so the builder does not have to open `CLAUDE.md`.

**Running the tests.** From `Tools/uedcli`, run **`bin/test`**. It runs pytest *host-native* in the
auto-managed dev venv (`bin/_venv.sh` → `.venv/`, Python 3.12 + `Pillow` + `pytest`) — the same
runtime `bin/uedcli` uses — and then the Rust golden suite (`cargo test`). It needs `python3.12` on
PATH; the venv self-creates on first run. Extra args pass straight through, and it must be invoked
path-qualified because bare `test` is a shell builtin:

```
cd Tools/uedcli && bin/test              # the whole offline suite
cd Tools/uedcli && bin/test -k texture -x
```

Tests marked `-m integration` need material a fresh checkout does not have; `pytest.ini` carries
`addopts = -m "not integration"`, so they are **deselected**, not skipped, in a default run. S6's new
integration module must therefore move the *deselected* count, not the *skipped* count.

**Committing.** Commit each completed slice without being asked. Stage **only the files you touched,
by explicit pathspec** (`git commit -- <path> <path>`); never `git add .`, never `git add -A`, never
`git commit -a` — a concurrent session may have staged its own work. One **short imperative subject
line**, no `type:` prefix, **no AI attribution**. Push after committing. **Never rewrite history**,
locally or on `origin`: no `--amend`, no `rebase` of pushed commits, no force-push in any form.
Mistakes are fixed with a new commit or a `git revert`.

**No back-compat cruft.** uedcli is unreleased — no external users, no scripts in the wild — so
nothing is kept for backward compatibility. When a flag, verb, option value, output format, or code
path is removed or renamed, **delete it outright in the same change** that introduces the
replacement; the new spelling is the only spelling. Forbidden: deprecated aliases, no-op flags,
migration-error shims, dual-format support kept to avoid rewriting callers, "old way" branches in
code/tests/docs. This is why S2 **deletes** `TextureResolver.resolve_masked` instead of keeping it
beside the new seam, and why S1 **deletes** the dead `TEXF` dict rather than fixing it.

**No silent half-answers.** A command that cannot fully satisfy a request **exits 2 naming the
offending value**, rather than printing a partial result plus a stderr warning — stderr scrolls away
and the caller mistakes the partial answer for a complete one. This governs the *command* layer;
S2's deliberate degrade-and-warn callers (a preview frame, a sprite billboard) are the designed
exception and are enumerated there.

**No Python exception ever reaches the user.** A bad ref, a corrupt package, a hostile mip count —
each produces a clear error naming the offending value and a non-zero exit, never a bare
`KeyError`/`IndexError`/`MemoryError`/`struct.error` traceback. Every such path gets a regression
test.

**Every command and argument needs a real `help=`** that says what it does, not one that restates
the flag's name. *(This plan adds no CLI surface, so the rule is inherited, not exercised.)*

**Docs move with the change.** User-facing docs (`docs/usage.md`, `docs/leveldesign/`) are updated in
the same commit as any user-observable behaviour; developer docs (`dev/docs/architecture.md` = what
*is*, `dev/docs/unrealed/*.md` = verified engine facts) in the same commit as the implementation. A
user-facing doc must **never** link to a developer doc. Engine facts in `dev/docs/unrealed/*.md`
carry a confidence marker: ✅ uedcli-used / live-verified, 🔬 live-probed, 📖 extracted from a binary
string table.

**Pin the finding, or it rots.** Whenever this build establishes a *checkable* engine or
file-format fact — a byte-layout field order, an enum's slot list, a block signature — it must also
land a **committed regression re-asserting that fact**, so a later change trips a red test instead of
drifting unnoticed. That is what S6's engine-fact pins are.

**Markdown tables** are padded so interior pipes line up in a plain-text editor — every column except
the last, whose content stays unpadded.

### 0c. The binding decisions, with their rejected alternatives

*(Recorded in `decisions.md` 2026-07-25 06:30 UTC — "Texture decode derives layout from the DATA; no
per-game format table (Andrzej-decided)" — with three measured corrections appended 2026-07-25
11:20 UTC. Stated in full here; the ledger need not be opened.)*

The trigger was Andrzej's *"We should support all UE1 formats!"*, then, on being offered a design
that read each game's `ETextureFormat` enum out of its `Engine.u`: *"I think `.u**` format is
universal and should be read from any other engine. We should make that work WITHOUT USING ANY SUCH
TABLE if that means it won't be universal for any texture file."*

**D1. Derive the layout from the data; never require a format table.** The mip chain is
self-describing: block-compressed formats store `ceil(w/4)×ceil(h/4)` blocks so their mips **floor**
at one block, while linear formats scale to `w×h×N`. The numeric `Format` code is read and reported
as a hint, a tiebreaker and a diagnostic label — never the authority.
*Not in conflict with the four-slot code→layout map of §0d*, which is what the tiebreak turns a
number into: it is consulted only against candidates the data already fitted, never to size a chain,
and decoding works when it is absent or unknown. §0d states the map, its evidence, and its scope in
full — that section is where the tension is resolved, not this one.
*Rejected: reading `ETextureFormat` out of each game's `Engine.u`.* It makes decoding depend on
having that game's code package, so a lone `.utx` from an unknown engine would not decode, defeating
the universality that is the entire point.
*Rejected: hardcoding one game's table.* Measured wrong across installs — see D2's evidence.
Same shape of finding as the self-describing mesh vertex stride (`decisions.md` 2026-07-25 03:40):
the file already tells us, if we look.

**D2. Slot numbers are NOT portable — the evidence that killed the table.** `ETextureFormat` dumped
from three installs (re-verified 2026-07-25 via the existing `uprops.enum_values`): **Unreal Gold
v69**, 8 slots, `0 TEXF_P8, 1 RGB32, 2 RGB64, 3 DXT1, 4 RGB24, 5 RGBA8, 6 DXT3, 7 DXT5`;
**UED22/227 v69**, **122** slots, `0 TEXF_P8, 1 BGRA8_LM, 2 R5G6B5, 3 BC1, 4 RGB8, 5 BGRA8, 6 BC2,
7 BC3, 8 BC4, 9 BC4_S, 10 BC5, 11 BC5_S, …`; **Deus Ex v68**, 5 slots, `0..4` ending `RGB24`.
**Slot 2 is 8 bytes/px in Unreal Gold (`RGB64`) but 2 bytes/px in 227 (`R5G6B5`)** — a hardcoded
table would mis-slice real data and then emit a *bogus* "size mismatch", turning an honest-failure
story into a wrong diagnosis. Both authorities also settle that **7 = DXT5/BC3 and 6 = DXT3/BC2**,
corroborated by the observed alpha block `0005ffffffffffff` (the textbook BC3 opaque block).

**D3. Implement the measured layouts now — P8, BC1, BC2, BC3, and the `CompMips` array.**
*Rejected: implementing the unsampled linear slots from their definitions.* No samples exist anywhere
on this machine and the slot meanings disagree across installs, so a guess returns a plausible
**wrong image** (swapped channels) instead of an error — against "never a wrong pixel".

**D4. The remaining layouts get a `p1` board item to spike and implement** (Andrzej) — acquire real
samples first, verify, then implement. Until then an unsampled slot is a named `unverified-format`
error carrying its own uncertainty. The item is already filed in `dev/docs/board/inbox.md` — grep it
by its title, **`[spike/implement] p1 The REMAINING UE1 texture layouts`** (it was at `:603` on
2026-07-25; the board moves constantly, so grep, never seek by line).

**D5. `bHasComp`/`CompFormat`/`CompMips` — and a correction to the record.** `UTexture` serializes
**two** mip arrays; the second holds a compressed copy of the same image, and it is the true cause of
every "trailing bytes" decode failure on class `Texture`. **A claim in the first draft of the spec —
"Deus Ex is 100 % P8, so this work buys nothing on the project's own substrate" — was FALSE**, and
the priority call was taken partly on it: **30 of the failures are in `LUM/Textures/LUM_CoreTex.utx`,
the project's OWN authored texture package**, invisible to uedcli today and drawn as a checkerboard
by the preview renderer. The correction argues *more* strongly for the work. Prefer `Mips` (the
higher-fidelity original) over the lossy `CompMips`.

**D6. Errors are a typed result from the decode layer; the CLI chooses the disposition.**
*Rejected: "every failure exits non-zero".* It contradicts the asset catalog's requirement that an
undecodable asset stay enumerable, and it would stop a whole map preview because one odd texture
exists (`preview_native.py` degrades to a checkerboard by design). Per-ref requests exit 2;
enumeration records an `undecodable` row; preview degrades and warns.

**D7. Testing must not be circular.** A synthesized fixture only proves the decoder agrees with our
own encoder. Two independent oracles exist and are used instead: the **`CompMips` pairs** (textures
storing the same image as both P8 and DXT1, encoded by the original tools) and **Pillow's DDS
decoder** (already the venv's sole third-party dependency).

**D8. The code breaks ties and vetoes; it never contradicts the data. `format-disagreement` and the
stored-vs-defaulted provenance are DELETED** *(Andrzej, **AD1**, 2026-07-25 — ledger entry "Texture
layout arbitration is a tiebreak-and-veto")*. The arbitration is §0d's four lines and S3's ordered
table; there is no `format_source` field, no `format-disagreement` case, and no rule that treats a
stored code differently from an implied one.
*Rejected: keeping `format-disagreement` as a fixture-only diagnostic.* It costs an error case, a
result field, a table branch, a fixture pair and a sweep assertion, and its measured firing rate on
real content is **zero** — all 11 stored codes in the corpus agree with their own chain's fit (§2c)
— while it *manufactures* a contradiction every time the implied P8 code meets a non-P8 chain. A
case that can only fire on files we build to make it fire is not a guard rail.
*Rejected: the stored-vs-defaulted asymmetry* (`format_source`, only a stored code allowed to
contradict a unique fit). It existed solely to keep `format-disagreement` from destroying the
feature; with the contradiction gone, a stored 0 and an implied 0 do the same thing and the field
distinguishes nothing.

**D9. A `bc16` chain that no code resolves is `ambiguous-alpha` — a named error, no pixels — and
this is a STATED limit on universality** *(Andrzej, **AD2**, 2026-07-25, same ledger entry)*. See the
block at the top of this plan; it is not a footnote and must stay prominent in the docs the build
writes.
*Rejected: assume BC3 for a code-less `bc16` chain.* BC3 is commoner, so the guess would often be
right — and silently, unrecoverably wrong otherwise, producing a plausible image with wrong alpha.
*Rejected: decode both ways and choose by "alpha plausibility".* A heuristic dressed as a
measurement: no ground truth exists to validate it (zero BC2 samples anywhere), it would decide
inconsistently across one texture set, and it violates the standing "the tool does not infer"
principle.

**The three corrections the planning pass measured** *(ledger addendum 11:20 UTC; the decision
stands)*: (1) "the chain separates layouts decisively" holds for ~54 % of the corpus, not all of it —
45.8 % fit two or more layouts, so the `Format` tiebreak is a **primary path**; (2)
`bHasComp`/`CompFormat` are **tagged properties**, not raw bytes after `Mips`; (3) the failure counts
are corpus-dependent and the earlier "147/147" reproduces against no single root.

### 0d. The `UTexture` / `FMipmap` byte layout, and how a `Format` code is read

*(This section holds three things the rest of the plan leans on constantly: the on-disk byte layout,
the stored-vs-defaulted rule for effective property values, and the four-slot `Format` code → layout
map. References below to "§0d's map" or "§0d's rule" mean the last two.)*

*(Established by spike `spikes/2026-06-27-decontainerize-uedcli/01-native-texture-decode.md`, which
proved the P8 path **pixel-exact against `UCC batchexport`** across the whole Deus Ex install —
`CoreTexMetal.utx` 175/175, `CoreTexDetail.utx` 17/17, `DeusExItems.u` 185/185, over package versions
61, 68 and 69. Reproduced here so the layout need not be looked up.)*

A UE1 object's serial body is a **tagged-property list** terminated by the name `None`, then
class-specific trailing data.

```
UTexture body
  <tagged property list>        # carries Format, Palette, bHasComp, CompFormat, bMasked, ...
  None                          # property-list terminator (a name-table compact index)
  Mips     : TArray<FMipmap>    # compact-index count, then count x FMipmap
  [if bHasComp]
  CompMips : TArray<FMipmap>    # SAME encoding; present iff the bHasComp PROPERTY is true

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

UPalette body
  <tagged property list> None    # normally empty (just None)
  Colors : TArray<FColor>        # compact-index count (= 256), then 256 x {R,G,B,A} bytes
  Decode P8: rgb[i] = Colors[Data[i]][:3]

FPropertyTag, repeated until a "None" name
  Name : compact index           # index into the name table; "None" => end of list
  Info : uint8                   # bits 0-3 = type, bits 4-6 = size code, bit 7 = array/bool
  [if type == Struct(10)] StructName : compact index
  size = {0:1, 1:2, 2:4, 3:12, 4:16, 5:<u8>, 6:<u16>, 7:<u32>}[size code]
  [if bit7 and type != Bool] array index : 1/2/4-byte special encoding
  value : size bytes             # a Bool's value IS bit 7; it has no value bytes
  Type nibble on disk: 1 Byte, 2 Int, 3 Bool, 4 Float, 5 Object, 6 Name, 7 Str, 10 Struct
```

Generic size-skipping means a value type never has to be understood to be stepped over; only
`Format` (Byte), `Palette` (Object), `bHasComp` (Bool) and `CompFormat` (Byte) are interpreted.
Mip 0 is full resolution. For v68/v69 the `WidthOffset` is a free internal check: after reading
`Data`, the cursor must equal it. For v61 the whole-body-to-EOF check is the integrity guard
instead. **Both guards now apply across both arrays.**

**Effective property values — what "the `Format` code" means everywhere below.** UE1 serializes a
tagged property only when it differs from the class default. `Engine.Texture`'s effective defaults
(resolved from Unreal Gold's `Engine.u` through the existing `uprops.resolve_class_defaults`) state
**none** of `Format`, `bMasked`, `bAlphaTexture`, `bHasComp`, `CompFormat` — so each defaults to its
type's zero: `Format = 0` = `TEXF_P8`, the flags `False`.

Re-measured 2026-07-25 over all four corpora: `Format` is physically present on **11 of 18,176**
texture exports (0.06 %). All eleven are in Unreal Gold — ten `Format=7` and one `Format=3` — and
they are listed individually in §2c.

So "the `Format` code" always means the **effective** value: the stored byte if the property is
present, else **0**. An absent property is not a missing code — by UE1's own serialization rule it is
the byte 0, which is `TEXF_P8` in all three enums measured, i.e. a real claim. The decode result
records `format_code` and nothing else about where it came from.

> **There is deliberately NO provenance field** *(D8 / Andrzej's AD1)*. An earlier draft carried
> `format_source: stored | class-default` and let only a *stored* code contradict a unique data fit,
> raising `format-disagreement`. Both are deleted. Once a code can no longer contradict the data at
> all, a stored 0 and an implied 0 produce identical answers by construction and there is nothing for
> the field to distinguish. **If a build step finds itself needing to know whether the code was
> written, something has drifted back to the old design.**

**The arbitration, in four lines** (the ordered, non-overlapping table is S3):

1. **Data fits exactly one layout → use it** (`layout_source: data`; the code is not consulted).
2. **Data fits several → the code breaks the tie** by naming one of the fitted candidates
   (`layout_source: format-code`). The implied 0 does this for 8,324 of the corpus's 8,327 ambiguous
   chains.
3. **Data fits several and no code names a fitted candidate → a named error** (`ambiguous-layout`, or
   `ambiguous-alpha` for the BC2-vs-BC3 case). Never a guess.
4. **The code names no layout in §0d's four-slot map → a named error** (`unverified-format`), *even
   when the data fits exactly one layout* — the **veto**, checked first.

**Why the veto is not a nicety — it is the difference between an error and a wrong picture.** 227's
`ETextureFormat` slot **8** is `TEXF_BC4` (re-verified 2026-07-25 out of the tracked
`uned/UED22/Engine.u`; its first twelve slots are `P8, BGRA8_LM, R5G6B5, BC1, RGB8, BGRA8, BC2, BC3,
BC4, BC4_S, BC5, BC5_S`). BC4 is a single-channel **8-byte-block** format, so its mip chain is
byte-for-byte the size of BC1's and fits `bc8` *uniquely*. Without rule 4, a file whose own code says
`8` — "not BC1" — would be decoded as BC1 and drawn confidently wrong. Slot 9 (`BC4_S`) collides the
same way; slots 10/11 (`BC5`, `BC5_S`) are 16-byte blocks and collide with `bc16`.

**And therefore: an uncoded `bc8` chain is decoded as BC1 by ASSUMPTION, not deduction.** The data
cannot separate BC1 from BC4; only the code can. The assumption is safe *because* a genuine BC4
export has `Format = 8 ≠ 0` and therefore writes the byte, which rule 4 catches — so what is really
being assumed is that no writer emits a non-BC1 8-byte-block chain while omitting `Format`. Say so in
the code comment; a future BC4 sample is a test of it.

Measured, the whole arrangement costs nothing on real content: of the 8,327 ambiguous chains,
**zero** lack `linear1` (= P8) among their fitted candidates when no code is stored, so the implied-0
tiebreak resolves every one of them; all 11 stored codes are `3` or `7`, both in the map, so the veto
rejects **zero** real textures; and the deleted `format-disagreement` would have fired **zero** times.

**The `Format` code → layout map — the ONE place slot semantics are assumed.** D1 forbids a *format
table*, and this is not one, but the tiebreak and the BC2-vs-BC3 selector both need to turn a number
into a layout, so the assumption must be written down rather than left implicit in the code:

| effective code | layout |
|----------------|--------|
| `0`            | `linear1` + palette (P8) |
| `3`            | `bc8` (BC1 / DXT1) |
| `6`            | `bc16` with **explicit** 4-bit alpha (BC2 / DXT3) |
| `7`            | `bc16` with **interpolated** alpha (BC3 / DXT5) |
| anything else  | **recognised but unsampled** — names no layout we decode, and **VETOES the array** |

"Recognised but unsampled" means: the byte is a legal enum slot in *some* engine, we have no sample
of it and no verified semantics, so it can never name a layout. Such a code does not merely fail to
help — it **stops the array from decoding at all**, even when the data fits exactly one layout
(rule 4 above, and it is why `TEXF_BC4` cannot be mistaken for BC1). The result is
`unverified-format` naming the code — never a guess, and never pixels.

*Justification (re-verified 2026-07-25 by dumping each install's real `ETextureFormat` through the
existing `uprops.enum_values`):*

| install               | slots | 0 | 3 | 6 | 7 | 8 (NOT in the map) |
|-----------------------|-------|---|---|---|---|---|
| Unreal Gold `Engine.u` (v69) | 8   | `TEXF_P8` | `TEXF_DXT1` | `TEXF_DXT3` | `TEXF_DXT5` | *(undefined)* |
| UED22 / 227 `Engine.u` (v69) | 122 | `TEXF_P8` | `TEXF_BC1`  | `TEXF_BC2`  | `TEXF_BC3` | **`TEXF_BC4`** — 8-byte blocks, collides with `bc8` |
| Deus Ex `Engine.u` (v68)     | 5   | `TEXF_P8` | `TEXF_DXT1` | *(undefined)* | *(undefined)* | *(undefined)* |

DXT1 ≡ BC1, DXT3 ≡ BC2, DXT5 ≡ BC3 — the same four layouts under two vendors' names. **All three
enums agree on slots 0 and 3; the two that define slots 6 and 7 agree on both, and Deus Ex's 5-slot
enum simply does not define them, so it cannot contradict.** (Be precise about this: it is *not*
true that "all three agree on 6 and 7" — one of them is silent.) The slots that *do* disagree across
installs — notably slot 2, `RGB64` at 8 B/px in Unreal Gold vs `R5G6B5` at 2 B/px in 227 (D2) — are
exactly the ones this map refuses to assign. S6 pins the three dumps so the agreement cannot rot.

*Why this does not violate D1.* A format **table** would be load-bearing: you could not decode
without it, and a game whose table you lack would not decode at all. This map is **never used to size
a chain** — sizes come only from the mip data — and it does exactly two things:

- **breaks a tie** among candidates the data already fitted (rule 2), including the BC2-vs-BC3
  choice, the one distinction the bytes genuinely cannot make;
- **names the codes we cannot decode** so those arrays fail honestly instead of being mis-decoded
  (rule 4 — the `TEXF_BC4` collision).

A chain the data settles on its own decodes with the map unconsulted (`layout_source: data`, code
absent or not). That is the whole of the dependency, and it is four slots that three independent
engine builds agree on, plus an explicit "everything else is out of our depth".

### 0e. Three sequencing facts that are not obvious

1. **`bHasComp` and `CompFormat` are TAGGED PROPERTIES, not raw trailing bytes.** The spec's §3 body
   sketch used to read as though the body were "`Mips`, then `bHasComp`/`CompFormat`/`CompMips`" laid
   out in sequence. It is not. Re-measured: reading two raw bytes after `Mips` and then a second
   `FMipmap` array **fails** (20 mip skip-offset mismatches + 19 non-EOF bodies over the DX
   `System`+`Textures` corpus; 107 + 100 over the whole tree); reading `bHasComp`/`CompFormat` out of
   the tagged-property list and parsing `CompMips` **immediately** after `Mips` lands exactly on the
   declared end for **207 / 207** failing `Texture` exports over the whole DX tree, and consumes 0
   bytes when `bHasComp` is absent or false. The body is therefore
   `props … "None"; Mips; if bHasComp: CompMips`. **Build S1 against this layout.**
2. **There IS a from-scratch UE1 package writer in the tree, and the fixture builder on top of it is
   COMMITTED** — `uedcli/native/pkg_write.py:92` `build_package`, with `NameTable` (`:31`),
   `ImportRec` (`:72`), `ExportRec` (`:80`) (line anchors verified 2026-07-25).

   The working prototype is committed as
   **`dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py`** — *do not re-derive
   it.* It is a self-verifying script; run it and it builds and re-parses every shape this build
   needs:

   ```
   cd Tools/uedcli && .venv/bin/python \
       dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py
   ```

   S1 promotes it (cleaned up, without the `sys.path` shim and the `main()` self-check) to
   `uedcli/tests/pkgfixture.py`. What it proves, all re-verified 2026-07-25: a synthetic **v69
   `.utx`** of ~1.4 KB carrying one `Engine.Texture` export (P8 `Mips` + `bHasComp` + `CompFormat=3`
   + DXT1 `CompMips`) and one `Engine.Palette` export parses under `utexture.load_package`;
   `class_of_export` resolves both classes through the import table; every absolute `TLazyArray` skip
   offset validates; the two-array parse lands exactly on the declared body end. With `bHasComp` off
   it consumes zero bytes after `Mips` and stays EOF-clean and decodes under *today's* decoder; a
   zero-length mip plus trailing bytes reproduces the `FireTexture` shape; a `Palette` ref past the
   export table reproduces the missing-palette shape; a lying `Mips` count reproduces the hostile
   shape. Its `texture_package(...)` keyword surface *is* the fixture API the Done-whens below assume
   (`mips=`, `comp_mips=`, `comp_format=`, `fmt=`, `palette_ref=`, `trailing=`,
   `declared_mip_count=`, `version=`).

   It is ~150 lines because the only back-patching needed is each mip's absolute skip offset, and
   `build_package` lays bodies contiguously from a `dataoff` that is computable before the bodies
   exist (`dataoff = header_len + len(encoded name table)`) — which is why every name must be
   interned **before** the table is encoded. **Two traps, both learned the hard way and both now
   encoded in the prototype:** (a) a property tag's *size code must match the encoded value's real
   length* — an `ObjectProperty` whose ref encodes to one compact-index byte needs size code 0, not
   2, or the whole property list silently mis-parses; (b) a `BoolProperty`'s value **is** bit 7 of
   the info byte and it carries no value bytes at all, though the size code is still written.
   **This makes the entire build testable offline.** *(It also contradicts the asset-catalog plan's
   S1 note that "there is no UE1 package writer in the tree … hand-building a `.u` would be a slice
   in itself" — true for meshes, false for textures. S7 fixes that note.)*
3. **Offline vs integration is decided by what is git-tracked** — see §0a.

### 0f. Docs move with the slice

**Cite these by grep, not by line.** Every cross-file line number in the first draft of this plan was
stale by 40–135 lines within a day (the tree has many concurrent writers), so each anchor below is
given as **searchable text**. Line numbers, where quoted at all, are a 2026-07-25 sighting only.

Per the repo rule, each slice updates the docs it invalidates in its own commit — principally
`dev/docs/unrealed/package-format.md` §`Object body layouts (byte-exact)` and these five
`architecture.md` passages (all five re-derived by grep 2026-07-25; the line numbers are a snapshot):

| grep for (a literal substring)                | what it is | ~line |
|-----------------------------------------------|------------|---|
| `textures decode natively`                     | the native preview's texture decode → checkerboard degrade | 737 |
| `migrate as a board follow-up`                 | the `utexture`/`dxpkg`-onto-`upackage` follow-up note | 1046 |
| `utexture.TextureResolver.exists`              | the ingest-validation existence check | 1207 |
| `the native` + `UTexture/UPalette decoder`     | the `utexture.py` module description | 1762 |
| `utexture.TextureResolver.resolve_masked`      | sprite decode in `_preview_render_data` | 1963 |

S7 keeps only the cross-cutting sweep (`decisions.md` addendum, board moves, spec deletion).

There is **no CLI surface change in this plan**, so `docs/usage.md` needs only the point-actor
bullet — grep **`or, for DT_Mesh/DT_None (or a missing/undecodable sprite)`** (~`:874`) — checked in
S2.

---

## 1. Module map

Line anchors **inside `utexture.py` and `pkg_write.py` were re-verified 2026-07-25 and are correct**;
every anchor in another file is given as grep text (see §0f for why). Each row names the **slice**
that touches it — a file appearing in more than one slice is called out, because taking an edit in
the wrong slice is how the "wrong pixel" invariant gets broken (see the `:390` row).

**Changed**

| file | slice | what |
|--------------------------------|-------|---|
| `uedcli/utexture.py`           | S1    | `TEXF` (`:33`) **deleted** — dead (no in-tree reader) and already wrong: it says `1 RGBA7, 2 RGB16, 4 RGB8` where every enum measured says `1 RGB32, 2 RGB64, 4 RGB24` (Unreal Gold / Deus Ex) or `1 BGRA8_LM, 2 R5G6B5, 4 RGB8` (227). `decode_texture` (`:188`) grows the second mip array, `comp_mips`/`comp_format` on `TextureObj`, and the `no_mip_data`/`trailing_bytes` flags — see the EOF-guard row |
| `uedcli/utexture.py` `:217-219` | **S1** | the body-to-EOF guard (`if pos != end: raise ValueError("texture body not at EOF…")`). S1 turns it into a **report, not a judgement**: `decode_texture` records `trailing_bytes = end - pos` (0 when clean) and `no_mip_data` on **every** body and never raises for this condition. It is NOT weakened — the integrity signal is preserved for every texture, v61 included, and S1's `_decode_ref` treats `trailing_bytes != 0` as a miss exactly as the raise did. S2 turns the two fields into `no-mip-data` / `corrupt-body`; S3 only reads them |
| `uedcli/utexture.py` `:390`    | **S1 (empty-mip check) then S2, S3** | the `if t.fmt != 0 or not t.mips` P8-only gate. **The `fmt != 0` half must survive S1 and S2 intact.** Deleting it before S3 lands detection sends non-P8 chains straight into `mip0_to_rgb`, which renders block bytes as palette indices — a *wrong image*, for two whole slices. But `not t.mips` is **not** the emptiness check it looks like: a list of *empty* mips is truthy, so once S1 stops raising, this gate passes and `mip0_to_rgb` returns an all-zero buffer — **a silent black image** (verified live 2026-07-25: `mip0_to_rgb(Mip(64, 64, b""), pal)` → 12,288 zero bytes). S1 therefore adds an explicit "no mip carries data" miss **ahead of** the gate. S2 replaces the gate's `return None`s with typed cases; S3 replaces the `fmt` condition with the detector's answer |
| `uedcli/utexture.py`           | S2    | `TextureResolver._decode_ref` (`:362-402`) loses its **seven** bare `return None`s — count re-verified 2026-07-25 (bare/over-dotted ref, unknown package, `decode_texture` raised, the fmt gate, palette ref out of range, `decode_palette` raised, name never matched) — plus the miss `_package` (`:286-297`) swallows when a package will not open or parse. `resolve` (`:299`) and `resolve_masked` (`:346`) collapse into one result-returning seam sharing one cache |
| `uedcli/utexture.py`           | S4    | `mip0_to_rgb` (`:250`) generalises past P8. The mask expression at `:359` stays as-is for P8 (see §5) |
| `uedcli/preview_native.py`     | S2    | `:300-304` (`self._resolver.resolve(ref)` + the `not resolvable on the composed search path` warning) — the checkerboard degrade now prints the named case |
| `uedcli/dispatch.py`           | S2    | grep `resolver.resolve_masked(bare)` (~`:824`) and `is not P8-decodable` (~`:837`) in `_resolve_point_render`'s sprite path. `_texture_resolver` (grep the `def`, ~`:764`) unchanged |
| `uedcli/tests/test_utexture.py` | S1/S2 | `test_decode_all_mips_reach_eof` (`:57`) encodes the pre-`CompMips` assumption — **updated in S1, not deleted**. The nine `TextureResolver` tests (`:82` onward, after the `_resolver()` helper at `:77`) move to the result union in S2. **`test_resolve_caches_per_instance` (`:115`) asserts OBJECT IDENTITY** (`assert r.resolve("CoreTexWater.dirtywater") is first`), so S2's new result type must stay **identity-cached** — return the cached object, never an equal-but-rebuilt one |
| `uedcli/tests/test_actor_preview.py` | **S2** | **not in the first draft's map, and S2 breaks it.** `_FakeResolver` (`:352`) implements exactly `resolve_masked(ref)` (`:359`) + `exists(ref)` (`:362`) and is constructed with 4-tuples `(w, h, rgb, mask)` (`:374`, `:463`) — all of which S2's merged seam changes. `:405` asserts the **literal string** `"not P8-decodable"` in stderr, which S2 replaces with the case name. Rewrite `_FakeResolver` onto the new seam and re-point that assertion; do not keep the old method as an alias (§0b) |
| `uedcli/tests/test_ingest_validation.py` | **S2** | **not in the first draft's map.** `:70` asserts `r.resolve("Weird.RGBA7Tex") is None` inside `test_texture_exists_is_existence_not_decodability` — under S2 `resolve` no longer returns `None`, so this becomes an assertion on the typed error case. **`exists()`'s own contract does not change** and the rest of the module stands |

**New**

| file | what |
|----------------------------------------------|---|
| `uedcli/tests/pkgfixture.py`                 | test-only `.utx` builder — **promoted from the committed prototype** `dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py`, not written from scratch (S1) |
| `uedcli/tests/fixtures/LUM_CompMips.utx`     | ~10 KB, real payload lifted from the **tracked** `Textures/LUM_CoreTex.utx:ClenGreyWndow_C` (S1) |
| `uedcli/tests/test_utexture_layout.py`       | layout detection (S3) |
| `uedcli/tests/test_utexture_blocks.py`       | BC1/BC2/BC3 vs the Pillow oracle (S4/S5) |
| `uedcli/tests/test_utexture_corpus.py`       | the **offline** tier of the corpus sweep, over the two git-tracked corpora (S6) |
| `uedcli/tests/test_utexture_corpus_installs.py` | the `-m integration` tier + the two install-gated engine-fact pins (S6) |

**Deliberately untouched:** `texture_catalog.py` / `texture.py` (the legacy PCX catalog — deleted by
the asset-catalog plan, not here); `upackage.py` / `dxpkg.py` (migrating `utexture`'s private parser
onto the shared core is a pre-existing separate board follow-up, noted in `architecture.md` — grep
`migrate as a board follow-up`);
`utexture.textures()`'s exact `class == "Texture"` match at `:245` (widening it to `Engine.Texture`
descendants belongs to the asset catalog).

---

## 2. Measured ground truth (re-measured for this plan, 2026-07-25)

Method: `utexture.load_package` plus a body parse that reads the tagged-property list, then `Mips`,
then — when `bHasComp` is true — `CompMips`, over every package under each root. Every figure below
was reproduced on 2026-07-25 and is quoted with the root it was measured against.

### 2a. What fails today, and why

Every row counts **`Texture`-classed exports** (one `Mips` chain each), never mip arrays; §2b gives
both units.

| corpus                                                    |  pkgs | `Texture` exports | fail today | explained by `CompMips` |
|-----------------------------------------------------------|-------|-------------------|------------|---|
| DX `System`+`Textures`(+`Maps`, which adds no textures)    |   232 |             5,018 |         39 | 39 / 39 |
| whole DX tree (`drive_c/DX`, incl. LUM + the TNM mod)      | 1,154 |            33,262 |        207 | 207 / 207 |
| `LUM/Textures` — **git-tracked packages only**             |     4 |               384 |         30 | 30 / 30 |
| `LUM/Textures` — as it sits on THIS machine                |     6 |               418 |         30 | 30 / 30 |
| …of which the tracked `LUM_CoreTex.utx` alone              |     1 |               253 |     **30** | 30 / 30 |
| `uned/UED22` (**fully tracked**)                           |    34 |             1,998 |          0 | — |
| Unreal Gold install                                        |   268 |            10,742 |          0 | — |

*(The two `LUM/Textures` rows differ by the untracked `CoreTexSky.utx` + `CoreTexWater.utx` — 34
exports, 0 failures. **All 30 failures sit in the tracked `LUM_CoreTex.utx`**, which is what makes
the motivating-bug criterion both offline and exactly assertable; see §0a's count-stability rule.
The four-corpora totals quoted elsewhere — 18,176 exports — include the two untracked packages,
because they are measurements of this machine, not offline test expectations.)*

Every `bHasComp=True` texture measured is `(Format ⇒ 0, CompFormat = 3)` — a P8 original with a DXT1
copy: 39 + 30 = **69 of 69** over Deus Ex + LUM, **207 of 207** over the whole tree. That answers the
spec's open question B, and Deus Ex's own v68 `ETextureFormat` has only five slots, so slot 3 =
`TEXF_DXT1` there too.

Two real end-to-end `CompMips` samples, both EOF-clean:

- `LUM/Textures/LUM_CoreTex.utx:ClenGreyWndow_C` (v69) — `Mips` = P8 64×64 → 1×1, **seven** mips
  (4096, 1024, 256, 64, 16, 4, 1 B); `CompMips` = DXT1, seven mips (2048, 512, 128, 32, 8, **8**,
  **8** B — the 8-byte block floor).
- `LUM/Textures/LUM_CoreTex.utx:quadrocks_logo_02` (v69) — `Mips` = P8 512×128 → 1×1, ten mips,
  bottoming out at **8×2, 4×1, 2×1**; `CompMips` = DXT1 512×128 (32,768 B) → 1×1 (8 B).

Separately, **procedural textures carry mips whose `DataCount` is `0`** — over the whole DX tree: 208
`FireTexture`, 42 `WetTexture`, 14 `WaveTexture`, 8 `IceTexture`, 50 `ScriptedTexture`, 4
`TNMScriptedTexture`; over Unreal Gold: 153 `FireTexture`, 78 `WetTexture`, 7 `IceTexture`, 4
`WaveTexture`. **Only `FireTexture` also has trailing bytes** (`TArray<FSpark>`, 8 B/spark matching
`NumSparks`); the others parse cleanly to EOF. So `no-mip-data` is detectable **from the data**
(`len(mip.data) == 0`), never from a class name. *(Restricted to DX `System`+`Textures` + Unreal Gold
the procedural counts are 193 `FireTexture`, 86 `WetTexture`, 7 `IceTexture`, 5 `WaveTexture` — same
facts, smaller root.)*

### 2b. The census the spec did not originally have: how often the chain is decisive

The governing idea holds — but **not as often as the spec's §0 originally implied.** A single mip of
`w×h` with `w·h` bytes is byte-identically explained by P8 (`w·h·1`) and by BC2/BC3
(`⌈w/4⌉·⌈h/4⌉·16`) whenever `w` and `h` are both multiples of 4, because `(w/4)(h/4)·16 = w·h`. The
chain only becomes decisive once it descends **below one block**.

**WHAT IS BEING COUNTED — state it in every criterion.** The census below counts **textures**: one
`Mips` chain per `Texture`-classed export. That is the natural unit for "how often does the data
decide", but it is *not* the number of mip arrays the decoder classifies, because a `bHasComp`
texture has two. A test expectation that mixes the units cannot be met. Both are given.

**Per texture — one `Mips` chain each** (re-measured 2026-07-25):

| corpus                                 | chains     | fitting exactly ONE layout | fitting >= 2 (need the tiebreak) |
|----------------------------------------|------------|----------------------------|---|
| DX (S+T+M)                             |      5,018 |                      3,656 | 1,362 |
| `LUM/Textures` — **tracked only**      |        384 |                        382 | 2 |
| `LUM/Textures` — this machine (6 pkgs) |        418 |                        416 | 2 |
| `uned/UED22` (**fully tracked**)       |      1,998 |                        861 | 1,137 |
| Unreal Gold                            |     10,742 |                      4,916 | 5,826 |
| **total** (with the 6-package row)     | **18,176** |                  **9,849** | **8,327 (45.8 %)** |

**Per mip ARRAY — `Mips` plus every `CompMips`:**

| corpus                            | arrays (`Mips` + `CompMips`) | fitting exactly ONE | fitting >= 2 |
|-----------------------------------|------------------------------|---------------------|---|
| DX (S+T+M)                        |       5,057 (5,018 + **39**) |               3,695 | 1,362 |
| `LUM/Textures` — **tracked only** |           414 (384 + **30**) |                 412 | 2 |
| `LUM/Textures` — this machine     |           448 (418 + **30**) |                 446 | 2 |
| `uned/UED22`                      |               1,998 (+ **0**) |                 861 | 1,137 |
| Unreal Gold                       |              10,742 (+ **0**) |               4,916 | 5,826 |
| **total**                         |                   **18,245** |           **9,918** | **8,327 (45.6 %)** |

**The `CompMips` arrays counted on their own — the arrays this build adds:** **69** across the four
corpora (39 in DX `System`+`Textures`, 30 in the tracked `LUM_CoreTex.utx`, **0** in `uned/UED22`,
**0** in Unreal Gold; 207 over the whole `drive_c/DX` tree). **All 69 fit `bc8` uniquely**, so the
data alone decides every one of them, and **all 69 carry `CompFormat = 3`**, which corroborates
without being needed. They add zero ambiguity — which is why the ">= 2" column is identical in both
tables.

So the `Format`-code tiebreak is **not an edge case with two samples** — it is the deciding path for
nearly half the corpus. Every shape of it has a **git-tracked** offline sample:

| ambiguity                             | tracked sample |
|---------------------------------------|---|
| single mip, `linear1` vs `bc16`       | 1,137 in `uned/UED22` (any 4-aligned single-mip texture) |
| single mip, `linear1` vs `bc8`        | `uned/UED22/DeusExUI.u:HUDItemsBorder_Center` (64×2, 128 B), `:HealthButtonNormal_Center` (2×16, 32 B) |
| **truncated** multi-mip chain         | `uned/UED22/uwindow.u:WhiteTexture` and `:BlackTexture` — 32×32 → 16×16 → 8×8 → **4×4 and stops** (fits `linear1` **and** `bc16`) |
| decisive chain (control)              | any UED22 texture whose chain reaches 1×1 |
| gitignored real BC3 case              | `DmRiot.unr:SolModifié` (128×128), `:Flotte` (64×64), `DMBeyondTheSun.unr:Uebergang3` (256×128) — **three**, not two |

**And the tiebreaking code is almost always the implied 0, not a stored value** (§0d). Re-measured
2026-07-25 across all four corpora (per-texture unit):

| population                                              | count | how it resolves |
|---------------------------------------------------------|-------|---|
| chains fitting exactly one layout                        | 9,849 | data alone; no code consulted (§0d rule 1) |
| …of those, fitting a layout that is **not** `linear1`     |     8 | all eight store a code, and all eight name a layout in the map |
| chains fitting ≥ 2 layouts                                | 8,327 | needs the tiebreak (§0d rule 2) |
| …resolved by a **stored** code                            |     3 | `SolModifié`, `Flotte`, `Uebergang3` — all `Format=7` |
| …resolved by the **implied 0**                            | 8,324 | `linear1`/P8 is a fitted candidate in **all** of them |
| ambiguous chains where `linear1` is **not** a candidate and no code is stored | **0** | — the implied-0 tiebreak never comes up empty, so `ambiguous-layout` fires zero times |
| chains fitting **zero** layouts                           | **0** | — |
| exports storing a `Format` property at all                |    11 | §2c lists every one; every one is `3` or `7`, both in the map, so the veto rejects zero real textures |

Three consequences, all load-bearing:

1. **The tiebreak never comes up empty on real content**, because P8 is a candidate whenever no code
   is stored.
2. **Nothing in the corpus ever contradicted the data**, which is exactly why the
   `format-disagreement` case was deleted (D8): its only possible inputs were those 11 exports, and
   all 11 agree with their own chain's fit (§2c).
3. **Every stored-code path is gitignored.** All 11 live in the Unreal Gold install. Offline tests
   must therefore construct stored codes with `pkgfixture` (`fmt=…`) — including the **veto** test,
   whose input (`fmt=8`, a `TEXF_BC4` claim over a `bc8` chain) exists nowhere on this machine.

### 2c. The block formats that exist

Unreal Gold, re-counted: **10 × `Format=7`** and **1 × `Format=3`** — and those eleven are the only
texture exports in any corpus that store a `Format` property at all. Enumerated in full (2026-07-25),
with the layout their own mip chain fits, because this list is the *complete* real-world evidence
behind two of the design's claims: that the deleted `format-disagreement` had zero inputs (D8), and
that the veto rejects zero real files (every code here is `3` or `7`, both in §0d's map):

| export                              | code | mip 0 | fitted candidates |
|-------------------------------------|------|-------|---|
| `UnrealShare.u:TranslatorHUDHD`     | 7    | 2048×2048, 4,194,304 B | `bc16` only |
| `DmRiot.unr:Poster01`               | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Poster02`               | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Poster03`               | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Screenshot`             | 7    | 512×512, 262,144 B | `bc16` only |
| `DmRiot.unr:SolMurJonction`         | 7    | 256×256, 65,536 B | `bc16` only |
| `DmRiot.unr:Fenêtres`               | 7    | 256×128, 32,768 B | `bc16` only |
| `DmRiot.unr:SolModifié`             | 7    | 128×128, 16,384 B (**single mip**) | `linear1` + `bc16` |
| `DmRiot.unr:Flotte`                 | 7    | 64×64, 4,096 B (**single mip**) | `linear1` + `bc16` |
| `DMBeyondTheSun.unr:Uebergang3`     | 7    | 256×128, 32,768 B (**single mip**) | `linear1` + `bc16` |
| `DmExar.unr:Screenshot`             | 3    | 256×256, 32,768 B (**single mip**) | `bc8` only |

**Every one of the eleven is consistent with its own data** — the seven multi-mip `Format=7` chains
fit `bc16` and nothing else, the three single-mip ones name a *fitted* candidate, and the lone
`Format=3` fits `bc8` uniquely at 0.5 B/px (so BC1 **is** decidable from a single mip). That is the
measurement behind "the deleted `format-disagreement` had zero real inputs" (D8).

The multi-mip `Format=7` chains floor at **16 B** (`Poster01`: … 8×8 = 64, 4×4 = 16, 2×2 = **16**,
1×1 = **16**), and `Fenêtres` supplies the non-square partial-block case (4×2 = 16, 2×1 = 16).
`TranslatorHUDHD` is the 2048², 12-mip stress case.

The BC3 identification is corroborated exactly as claimed: **all 4,096** of `Poster01` mip 0's blocks
have the alpha half `0005ffffffffffff` — one distinct value across the whole mip. Decoded as **DXT5**
that block is uniformly opaque (`a0 = 0`, `a1 = 5`, `a0 ≤ a1` ⇒ the six-interpolant mode, and every
3-bit index is 7 ⇒ alpha 255); decoded as **DXT3** the same eight bytes are sixteen explicit 4-bit
values `0,0,0,5,15,15,…` ⇒ alpha 0 / 85 / 255 noise. That asymmetry is the identification.

The three `ETextureFormat` enum dumps reproduce verbatim through the **existing**
`uprops.enum_values` (re-run 2026-07-25) — Unreal Gold v69 8 slots `P8, RGB32, RGB64, DXT1, RGB24,
RGBA8, DXT3, DXT5`; UED22/227 v69 `P8, BGRA8_LM, R5G6B5, BC1, RGB8, BGRA8, BC2, BC3, BC4, BC4_S,
BC5, BC5_S, …` (**122** slots, not the 118 an earlier draft recorded); Deus Ex v68 5 slots `P8,
RGB32, RGB64, DXT1, RGB24`. **One of the three is offline** — `uned/UED22/Engine.u` is git-tracked;
the other two are integration. Their agreement on slots 0/3/6/7 is what §0d's code→layout map rests
on, and S6 pins it as such.

### 2d. The oracles, verified

- **Pillow 12.3.0** (uedcli's only third-party runtime dependency — `pyproject.toml:13`,
  `Pillow>=11`) decodes `DXT1`/`DXT3`/`DXT5` from a hand-built 128-byte DDS header at every edge
  shape this corpus contains — 4×4, 2×2, 1×1, 8×2, 4×1, 2×1, 512×128 — all to `RGBA`. Its
  RGB565→888 expansion is **bit-replication** (`(v<<3)|(v>>2)` and `(v<<2)|(v>>4)`, checked over all
  32 and all 64 values with **zero** mismatches, *not* `round(v·255/31)`), and its 1/3–2/3
  interpolants are the plain integer `(2a+b)/3` (white/black endpoints give 170 and 85). So
  **byte-exactness against Pillow is achievable**, not just a tolerance.
- **The `CompMips` pairs** agree with their P8 originals, but there is **no universal bound**.
  Re-measured mean absolute channel error, our P8 decode vs Pillow's DXT1 decode of the same
  texture's `CompMips`:

  | texture                          | mip 0 | mip 1 | mip 2 | mip 3 |
  |----------------------------------|-------|-------|-------|---|
  | `LUM_CoreTex:quadrocks_logo_02`  | 0.605 | 1.623 | 3.083 | 3.991 |
  | `LUM_CoreTex:ClenGreyWndow_C`    | 1.980 | 4.316 | 5.717 | **8.469** |

  (max channel delta 8 on `ClenGreyWndow_C` mip 0, 74 on mip 1.) Two conclusions the earlier draft
  got wrong: the bound **must be mip-0-only** (mip 3 already exceeds 8/255), and **a wrong decode
  does not necessarily score 60–80**. Four deliberately-wrong controls over the same two textures
  scored **20.3**, **35.9**, **39.3** and **62.0** mean error. So S4's `≤ 8/255 on mip 0` still
  separates right (≤ 1.98) from wrong (≥ 20.3) by roughly tenfold, but the discriminating power must
  be stated as "≥ 10× at mip 0", not "wrong decodes score 60–80".

---

## 3. Slices

### S1 — `CompMips`: parse both mip arrays, prefer `Mips`
*Fixes the live bug. 69 textures across Deus Ex + the project's own package become visible.*

`decode_texture` (`utexture.py:188`) reads `bHasComp` and `CompFormat` **from the tagged-property
list** (`_read_props` already returns them; a `BoolProperty` arrives as `(3, True)`, a `ByteProperty`
as `(1, 3)`), parses `Mips`, and — only when `bHasComp` is true — parses a second `FMipmap` array
with the identical reader, then applies the existing body-to-EOF guard across **both**. The
`WidthOffset` cursor check applies per-array unchanged. `TextureObj` grows `comp_mips` +
`comp_format`. `_decode_ref` selects its array by **S4's rule** — `Mips` if it *carries data* (the
array is non-empty and at least one mip has bytes), else `CompMips` if present and carrying data,
else the `no-mip-data` miss; "`Mips` is absent" is not a separate concept. The fallback is inert
until S4 lands BC1 — say so in the code comment, don't pretend otherwise. Delete `TEXF` (`:33`).

**S1 also owns the body-integrity REPORT, because S1 is where the guard is written.** The guard lives
at `utexture.py:217-219` and today raises *before* any other logic runs, so a later slice cannot put
anything in front of it without reopening it and its test. S1 changes what it produces:

- `decode_texture` records **two fields on every `TextureObj`, always**: `trailing_bytes = end - pos`
  after the mip array(s) — `0` for a clean body — and `no_mip_data` (true iff no mip in either array
  carries bytes). It **does not raise** for a non-EOF body.
- It still raises where it genuinely cannot continue: a `WidthOffset` cursor mismatch, a
  structurally impossible declared count. S2 maps those to `corrupt-body`.
- **S1's `_decode_ref` treats `trailing_bytes != 0` as a miss** (returning `None`, as the raise
  effectively did), so this slice changes no caller-visible outcome. S2 replaces both fields with
  typed cases: `no_mip_data` ⇒ `no-mip-data`, else `trailing_bytes != 0` ⇒ `corrupt-body`.

**This is deliberately NOT "weaken the guard so a fixture can produce `no-mip-data`."** An earlier
draft made the guard stop raising *only* when every mip was empty, which left every other
trailing-bytes shape unguarded on the v61 path — where body-to-EOF is the only integrity signal there
is. Reporting instead of raising keeps the signal for **every** body and adds information (how many
bytes were left over), while moving the *classification* to the layer whose job classification is.
It is also what makes `FireTexture` — zero-length mips *and* trailing `TArray<FSpark>` bytes —
classifiable as `no-mip-data` rather than `corrupt-body` for all 208 of them, without an ordering
rule buried in the parser.

**And S1 must not ship a black image.** Once the parser stops raising, a texture whose mips are all
empty reaches `_decode_ref`'s `if t.fmt != 0 or not t.mips` gate — which **passes**, because a list
of empty mips is truthy — and `mip0_to_rgb` then returns `w·h·3` zero bytes: a silent, plausible,
completely black picture. (Verified live 2026-07-25: `mip0_to_rgb(Mip(64, 64, b""), pal)` returns
12,288 zero bytes.) S1 adds an explicit **"no mip carries data ⇒ miss"** check *before* that gate, in
the same commit that stops the raising. It has its own Done-when below; do not fold it into the
`CompMips` assertions, because it is the one regression this slice can introduce.

Lands the two test enablers:

- **`uedcli/tests/pkgfixture.py`** — **promoted from the committed, self-verifying prototype**
  `dev/docs/spikes/2026-07-25-native-texture-formats/pkgfixture_proto.py` (§0e2). Drop its
  `sys.path` shim and its `main()` self-check; keep `texture_package()` and its keyword surface,
  which every offline Done-when below is written against.
- **`uedcli/tests/fixtures/LUM_CompMips.utx`** — a ~10 KB package whose single texture is
  `ClenGreyWndow_C`'s **real** payload (64×64 P8 chain to 1×1 + its 7-mip DXT1 `CompMips` + its
  256-entry palette) lifted out of the repo's own tracked `Textures/LUM_CoreTex.utx`.
  Project-authored content already in git — no third-party redistribution. The lift script goes into
  the commit (as a documented function in `pkgfixture.py`, or beside the spike); it must not live
  only in `_scratch/`.

**Done when**
- (offline) `LUM_CompMips.utx`'s texture decodes: `Mips` = 7 mips 64×64 → 1×1, `CompMips` = 7 mips
  ending 8 B, `comp_format == 3`, body parse reaches EOF.
- (offline) a `pkgfixture`-built synthetic `.utx` with `bHasComp` **false** consumes zero bytes after
  `Mips` and reaches EOF — i.e. `CompMips` is gated on the flag, not unconditionally present.
- (offline) **the body-integrity report, asserted here and not in S3:** a `pkgfixture` body built with
  `mips=[(64, 64, b"")], trailing=b"\x01"*24` decodes **without raising**, returning
  `no_mip_data is True` and `trailing_bytes == 24`; the same body with **real pixel data** plus the
  same 24 trailing bytes **also decodes without raising**, returning `no_mip_data is False` and
  `trailing_bytes == 24`. Both committed fixtures report `trailing_bytes == 0`. *(Today the
  second shape raises `texture body not at EOF … trailing 24 bytes unparsed`; that raise is what
  becomes a field. S2 turns the first into `no-mip-data` and the second into `corrupt-body`.)*
- (offline) **no black image (the regression this slice can introduce):** resolving a `pkgfixture`
  texture whose only mip is zero-length through `TextureResolver.resolve` is a **miss** — assert
  `is None` here, and assert *specifically* that the return value is not a `w·h·3` buffer of zeros,
  since that is precisely what the untouched `not t.mips` gate would produce. The same texture with
  24 trailing bytes (the `FireTexture` shape) is likewise a miss, not a picture. S2 restates both as
  the typed `no-mip-data` case.
- (offline) a `pkgfixture` texture with **real** pixel data and 24 trailing bytes resolves to a miss
  too — the integrity guard's effect survives the change from raise to field.
- (offline) `test_utexture.py:57 test_decode_all_mips_reach_eof` is **updated** to assert the
  two-array contract **and `trailing_bytes == 0`** on every texture in both fixtures — the guarantee
  the old raise gave, now stated positively — and still covers both existing fixtures; `test_decode_v69_pixel_exact` (`:39`)
  and `test_decode_v61_pixel_exact` (`:48`) digests are **unchanged** — this slice must not move a
  single decoded pixel.
- (offline) resolving `LUM_CompMips.ClenGreyWndow_C` through `TextureResolver` returns the **P8**
  image, not the DXT1 copy.
- (offline) **the motivating bug, pinned to a tracked FILE, not to a directory total:** the
  `Texture`-class parse-failure count over `conftest.repo_texture_root()/"LUM_CoreTex.utx"` (tracked,
  253 `Texture` exports) drops from **30 to 0**; the failure count over the whole
  `repo_texture_root()` directory is **0** as an invariant (no exact package/export total asserted —
  §0a's count-stability rule: 2 of the 6 packages there are untracked); and it stays **0** over
  `conftest.ued22_root()`, where the exact 34 packages / 1,998 exports **may** be asserted because
  that tree is fully tracked. **This is the offline criterion for the bug that motivates the whole
  build** — it must not be marked integration.
- (integration) the same count over `conftest.install_root()`'s `System` + `Textures` drops from
  **39 to 0**.
- `unrealed/package-format.md` §`Object body layouts (byte-exact) 🔬` gains the `UTexture` body (🔬),
  stating the property-gated `CompMips` explicitly, the empty-mips-beat-EOF rule, and citing the
  measured 207/207.

### S2 — typed decode results; the caller chooses the disposition
*D6. No new format is decoded here — only how failure travels.*

Introduce the error taxonomy as a **typed result from the decode layer**, and delete
`TextureResolver.resolve()`'s `None`-for-everything collapse (`utexture.py:299`, and `_decode_ref` at
`:362-402`, which has **seven** bare `return None`s — re-counted 2026-07-25, not the five an earlier
draft claimed — plus an eighth miss swallowed by `_package`'s `except`). The
resolver's public call returns either a decoded texture (width, height, RGB, mask, the detected
layout, the effective `Format` code, and the reported `bMasked`/`bAlphaTexture` flags) or a typed
error carrying its **case** and the offending ref. `resolve` and `resolve_masked` **merge into one
seam** — two caches and two near-identical lookups exist today only because the mask was bolted on,
and keeping both after the return type changes would be exactly the back-compat cruft §0b forbids.

**The case names are DEFINED here in full — in TWO layers — but S2 can only RAISE some of them.**
Defining the whole union up front keeps it stable; pretending S2 can produce all of it does not,
since three decode cases have no producer until layout detection exists.

**Decode-layer cases (8):**

| case                  | first slice that can raise it | why |
|-----------------------|-------------------------------|---|
| `corrupt-body`        | **S2** | S1's parser fields (`trailing_bytes != 0` with mip data present), the `WidthOffset` mismatch, an unparseable property list, the hostile-count caps |
| `missing-palette`     | **S2** | a dangling `Palette` object ref (`pkgfixture(palette_ref=…)`) or a palette body that will not decode |
| `size-mismatch`       | **S2** | on the surviving P8 path: a mip whose `DataCount != w·h` |
| `no-mip-data`         | **S2** | S1 already records the flag *and* already turns it into a miss; S2 gives it its name |
| `unverified-format`   | **S2** (interim) → re-pointed in **S3** | see the gate note below |
| `unrecognised-layout` | **S3** | needs the candidate-set computation |
| `ambiguous-alpha`     | **S3** | needs the candidate-set computation |
| `ambiguous-layout`    | **S3** | needs the candidate-set computation |

*(There is no `format-disagreement`. It was deleted by AD1 — see D8. If a build step finds a place
where it "would" fire, the answer is one of rows 2/5/7/8 of S3's table, not a new case.)*

**Ref-layer cases (4) — S2, and they are NOT the asset catalog's to define.** `_decode_ref` produces
these misses **today**, all as a bare `None`, and **four committed tests assert exactly that `None`**:
`test_utexture.py`'s `test_resolve_group_mismatch_is_miss` (`:95`), `test_resolve_bare_ref_is_miss`
(`:99`), `test_resolve_unknown_package_and_texture_are_misses` (`:105`) and
`test_resolve_corrupt_package_is_miss` (`:128`). Deferring them to a catalog that does not exist
would leave those four with no defined expectation the moment `resolve` stops returning `None`.

| case                 | today's producer in `utexture.py` | meaning |
|----------------------|-----------------------------------|---|
| `unqualified-ref`    | `return None` on a 1-part or > 3-part ref (`:369`) | a `Package[.Group].Name` qualifier is required; a bare name is refused rather than stem-scanned |
| `unknown-package`    | `pkg is None` after `_package(stem)` | no package of that stem on the composed search path |
| `package-unreadable` | `_package`'s `except (OSError, ValueError, struct.error, IndexError)` (`:294`) | the package IS on the path but will not open or parse. **A new distinction** — today it is indistinguishable from `unknown-package`, and the two need different fixes |
| `unknown-texture`    | the loop's final `return None` (`:402`) — name never matched, or matched with a different `Group` | no `Texture`-classed export of that name in that package; a group mismatch is this case and the message names the group asked for |

The remaining `_decode_ref` misses are decode-layer cases, not new ones: `decode_texture` raised ⇒
`corrupt-body`; palette ref out of range or `decode_palette` raised ⇒ `missing-palette`; the
`t.fmt != 0` gate ⇒ `unverified-format` (interim). Seven bare returns + one swallowed exception, all
accounted for.

**The asset catalog reuses these four verbatim** and mints only what is genuinely its own:
`ambiguous-ref` (a bare name matching several packages — unreachable here, since this layer refuses
bare refs with `unqualified-ref`) and `cache-unreadable`.

**The P8-only gate SURVIVES this slice — do not delete it.** `utexture.py:390`'s
`if t.fmt != 0 or not t.mips` is what stops a block-compressed chain reaching `mip0_to_rgb`, which
would read block bytes as palette indices and emit a **wrong image**. S3 is the first slice that can
safely replace it. What S2 changes is only its *return*: instead of a bare `None`, a chain the gate
rejects yields the typed `unverified-format` case naming the effective code and the measured
bytes/px. That is a truthful statement of what is known at this point in the build, and S3 narrows
it once detection can tell `unverified-format` from `unrecognised-layout` / `ambiguous-alpha` /
`ambiguous-layout` / `size-mismatch`.

Dispositions wired at the two live callers: `preview_native.py:300-304` keeps degrade-and-warn but
names the case; `dispatch.py`'s sprite path (grep `resolver.resolve_masked(bare)` and
`is not P8-decodable`) keeps the marker and names the case in its note. **No third disposition is
implementable in this plan** — see §7.3.

Fold in the standing hostile-input finding — `dev/docs/board/inbox.md`, grep
**`utexture` resolver can raise IndexError/MemoryError on hostile mip counts/sizes`** (item 5 of the
`preview_native` cold-review list; it was at `:1177` on 2026-07-25): cap the mip count and per-mip
dimensions and turn an over-large or self-inconsistent declaration into `corrupt-body`/
`size-mismatch`, never a `MemoryError`. *(Measured with the prototype: a `Mips` count of `1<<20`
today raises a bare `ValueError` out of the decoder.)*

**Done when**
- (offline) each of the **five S2-reachable decode cases** above is produced by a distinct
  constructed input and is distinguishable by its case field — one test per case, none reachable by
  accident from another. The other three are S3's Done-whens, not this slice's.
- (offline) each of the **four ref-layer cases** is asserted, by re-pointing the four tests that
  assert `None` today: `:99` → `unqualified-ref`; `:105` → `unknown-package` **and**
  `unknown-texture`; `:95` → `unknown-texture` with the requested group named in the message;
  `:128` → `package-unreadable`, plus a second assertion in the same test that an absent stem still
  gives `unknown-package` (the two are one value today, and splitting them is the point).
- (offline) the S1 no-mip-data miss becomes the typed `no-mip-data` case, and the assertion is on
  the case — it must **not** be satisfiable by a zero-filled RGB buffer (the black-image trap, §S1).
- (offline) a `pkgfixture` texture whose `Palette` ref points at a non-existent export
  (`palette_ref=99`) yields `missing-palette`, not `None`.
- (offline) a truncated or oversized declared mip count (`declared_mip_count=1<<20`) yields
  `corrupt-body` in bounded time and bounded memory; no `IndexError`/`MemoryError`/`struct.error`
  escapes.
- (offline) `preview_native` still renders a checkerboard and warns **once per distinct ref**, and
  the warning text contains the case name; `dispatch`'s sprite path still degrades to a marker.
  Neither exits non-zero.
- (offline) `resolve_masked` no longer exists anywhere (grep-verified); the nine `TextureResolver`
  tests in `test_utexture.py` (`:82` onward) assert on the result union — **including
  `test_resolve_caches_per_instance` (`:115`), whose `is first` object-identity assertion must still
  hold**: the merged seam caches and returns the *same* result object, not an equal rebuild.
- (offline) the two test modules the first draft's map missed are migrated and green:
  `test_actor_preview.py`'s `_FakeResolver` (`:352`) is rewritten onto the merged seam (it implements
  `resolve_masked`/`exists` today and is fed 4-tuples at `:374`/`:463`), and its `:405` assertion on
  the literal `"not P8-decodable"` now asserts the **`unverified-format`** case name;
  `test_ingest_validation.py:70`'s `assert r.resolve("Weird.RGBA7Tex") is None` asserts the case
  **`corrupt-body`** — name it, do not leave it as "the typed case". That fixture builds exports with
  `soff=0, ssize=0` over `buf=b""`, so the body has no property list at all and `decode_texture`
  raises `IndexError` (verified live 2026-07-25); despite the `RGBA7Tex` name there is no format miss
  in it, and asserting a format case would be asserting a fiction. `exists()`'s contract is unchanged
  and the rest of both modules stands.
- `docs/usage.md` (grep `or, for DT_Mesh/DT_None (or a missing/undecodable sprite)`) and the two
  `architecture.md` passages (grep `textures decode natively` and
  `utexture.TextureResolver.resolve_masked`) describe the new degrade text.

### S2b — the preview accessors (SCOPE ADDED 2026-07-26, owner ruling)

**Added after this plan was first reviewed**, so this plan **re-enters the plan-review round** before
building (`CLAUDE.md` "Review gates"). Requested by
[`../specs/2026-07-26-actor-preview-textured-faces.md`](../specs/2026-07-26-actor-preview-textured-faces.md)
§12: that spec needs two things from this decoder, and folding them in here means the texture API
changes **once** rather than twice.

Both ride S2's typed-result contract — they never return a bare `None`, and the caller chooses the
disposition.

1. **A mip-pyramid accessor.** Every mip of a ref as `(w, h, rgb, mask)`, not just mip 0. `actor
   preview --faces textured` picks a mip per face from screen density, so it needs the whole pyramid;
   `decode_texture` already decodes all mips and `mip0_to_rgb` is generic over any `Mip`, so this is
   an accessor, not new decoding. Note it must interact correctly with S1's `Mips`-preferred /
   `CompMips` rule — the pyramid handed out is the one S1 selected, and which array it came from is
   part of the typed result.
2. **`texture_has_bMasked(ref)`** — `"bMasked" in <the export's property block>`. A UE1 bool written
   **presence-only**, so present ⇒ masked, absent ⇒ not. Evidence and the corpus measurements are in
   [`../spikes/2026-07-26-texture-masked-property/findings.md`](../spikes/2026-07-26-texture-masked-property/findings.md)
   and `unrealed/quirks.md` "Surfaces / polys"; the decode needs no new parser (`_read_props` already
   handles `_PT_BOOL`).

**One contract note for this slice's builder.** S2 says a decoder error lets the caller choose, and
lists "preview degrades and warns" as an example disposition. That is true of `level preview
--native`'s frame, but **`actor preview --faces textured` REFUSES** — it exits 2 naming the ref (that
spec's decision 2.6). Do not assume every preview caller degrades; the typed result must carry enough
to let a caller write either message, including distinguishing a **bare (unqualified) ref** from a
package/name miss, since the refusing caller has to tell the user to qualify it.

### S3 — layout detection from the mip chain
*D1 — the governing idea, and the slice where the spec was most optimistic.*

**Detection and decodability are two separate questions, and conflating them is what made the first
draft of this slice self-contradictory.** Keep them apart:

- **`detect_layout(mips, *, code)` → a layout, or a detection failure.** Pure; knows nothing about
  which layouts have decoders. `code` is `int` (§0d's effective value: stored byte, else 0) or
  **`None`**, meaning *no code is available at all*. Production always passes an `int`; `None` is for
  a caller judging a bare mip array, and it is what makes "detect without consulting `Format`"
  something a test can actually express.
- **the decode step** then asks whether a decoder exists for the detected layout. If not, that is
  `unverified-format` — a *decode* failure over a *successful* detection.

The signature takes the code **explicitly, for the array being judged** — `Format` for `Mips`,
`CompFormat` for `CompMips`. It must never reach into the texture and read `Format`, because the two
arrays hold different layouts by construction: all 69 measured `CompMips` arrays are `bc8` while
their `Mips` are P8, so judging a `CompMips` array against a P8 code would send every one of the 69
textures this build exists to fix down an error branch (its code names `linear1`, which is not a
candidate) instead of decoding, and make S4's headline Pillow test unrunnable.

**Candidates.** A layout `L` is a candidate iff **every** mip in the chain satisfies its size rule:
`n == w·h·N` for `linear{N}`, `N ∈ {1, 2, 3, 4, 8}`; `n == ⌈w/4⌉·⌈h/4⌉·B` for `bc{B}`, `B ∈ {8, 16}`.

**The procedure, in order.** This is §0d's four-line rule spelled out. `code` is §0d's effective value
or `None`; the map is §0d's four-row table. **The rows are ordered and mutually exclusive by
construction**: row 2 is checked before anything looks at the data; rows 5/6 partition "exactly one
candidate" on whether it is `bc16`; rows 7/8 partition "two or more" on whether the code names one of
them. No input matches two rows — the old table's rows 4 and 5 both matched a single-`bc16`-candidate
chain with a contradicting stored code, which is one of the reasons the disagreement case is gone.

| # | condition | result |
|---|-----------|---|
| 0 | *(array selection, S4)* neither `Mips` nor `CompMips` carries data | `no-mip-data`; **detection is never invoked** (an empty chain would index mip 0 of an empty list). Otherwise the selected array and **its own** code are what every row below judges |
| 1 | every mip in the selected array is empty (S1's `no_mip_data`) | `no-mip-data` — `detect_layout` is callable on any array, so it holds this line itself |
| 2 | `code is not None` **and** `code` is not one of the map's four slots | **`unverified-format` — the VETO.** Names the code (and, for the message only, the candidates the data fitted). **No pixels even when exactly one layout fits.** This is what stops a 227 `TEXF_BC4` chain (`code=8`), which fits `bc8` uniquely and identically to BC1, from being drawn as BC1. **Checked before every fit row so nothing can reach around it.** Measured firing rate on real content: zero |
| 3 | no layout fits **mip 0** | `unrecognised-layout` — names the code and mip 0's measured bytes/px |
| 4 | mip 0 fits something but no layout fits the **whole** chain | `size-mismatch` — the chain is internally inconsistent; names the mip that breaks it |
| 5 | **exactly one** candidate, and it is `bc16` | code `6` → BC2, code `7` → BC3 (`layout_source: format-code`); **any other code — including the implied 0 and `None` — → `ambiguous-alpha`**, no pixels. The documented universality limit (D9) |
| 6 | **exactly one** candidate, otherwise | that layout, `layout_source: data`. **The code is not consulted** — this is what lets a foreign code-less **BC1** `.utx` decode (§0d), and it is where `bc8` is taken for BC1 by assumption |
| 7 | **≥ 2** candidates, and the code names one of them | that layout, `layout_source: format-code`; if that layout is `bc16` the same code (`6`/`7`) also names its alpha variant. **45.8 % of the corpus** (§2b) — a first-class branch with its own tests, and the implied 0 is what resolves 8,324 of the 8,327 ambiguous chains |
| 8 | **≥ 2** candidates, and no code names one of them — `code is None`, or the code names a layout that is not a candidate | `ambiguous-layout` — the data left a real choice and nothing legitimate breaks it, so we say so (§0d rule 3). Names the candidates and the code. Measured frequency on real content: **zero** |

Then, and only then, the decode step:

| # | condition | result |
|---|-----------|---|
| 9 | the detected layout has **no decoder** (`linear2`/`linear3`/`linear4`/`linear8`) | `unverified-format` — names the **detected layout**, the code, and the measured bytes/px. Never a decoded image |
| 10 | detected `linear1` and the `Palette` ref does not resolve | `missing-palette` |

**Row 9 is the case the first draft was missing, and it is what resolves its contradiction.** The
draft said both "a unique fit wins with `layout_source: data` even when the code names no implemented
layout" *and* "an unsampled slot whose chain fits `linear4` yields `unverified-format`". Both are now
true and not in conflict, because they answer different questions: **detection succeeds** (`linear4`,
`layout_source: data`) and **decoding fails** (`unverified-format`). The result carries the detected
layout either way, so a diagnostic can say *"this is a 4 bytes/pixel linear texture and we have no
verified decoder for it"* rather than *"unknown"*. (Rows 2 and 9 deliberately share a case name: both
mean "a layout we have not verified and will not guess at" — one learned from the code, one from the
data.)

**Two things that follow from §0d and are easy to get wrong:**

- The "code" is the **effective** value (stored byte, else 0) and there is **no provenance field**. A
  stored `Format=0` and an absent `Format` must produce identical results — if a branch needs to tell
  them apart, the design has drifted back to the deleted `format-disagreement` (D8).
- `layout_source` has exactly two values, `data` and `format-code`. On tracked material every
  `format-code` resolution comes from the implied 0; all 11 stored codes live in the gitignored
  Unreal Gold install (§2c), so every stored-code assertion below is integration or
  `pkgfixture`-constructed.

**Done when**
- (offline) `uned/UED22/uwindow.u:WhiteTexture` (32×32 → 4×4, truncated) is detected as **ambiguous**
  (`linear1` and `bc16` both fit) and resolved to `linear1` by its effective code, with
  `layout_source == "format-code"` (row 7).
- (offline) `uned/UED22/DeusExUI.u:HUDItemsBorder_Center` (64×2, 128 B) is ambiguous
  `linear1`/`bc8` and likewise resolved by the code.
- (offline) a UED22 texture whose chain reaches 1×1 is detected as `linear1` with
  `layout_source == "data"`, **and `detect_layout(chain, code=None)` returns the same layout as
  `detect_layout(chain, code=0)`** — that call *is* the "without consulting `Format`" criterion
  (row 6), and it is checkable because `None` is a real value of the parameter.
- (offline) a `pkgfixture` chain flooring at 8 B classifies `bc8` and one flooring at 16 B classifies
  `bc16` **with `code=None`**; the 16 B one then yields `ambiguous-alpha` (rows 6 and 5).
- (offline) **the veto pair — the reason this slice exists in this form** (row 2 vs row 6): a
  `pkgfixture` texture with **no stored `Format`** (`fmt=None`) whose chain fits `bc8` uniquely — a
  foreign 227/UT **BC1** file — detects as `bc8` with `layout_source == "data"` and **decodes**. The
  **same chain** with `fmt=8` stored (a `TEXF_BC4` claim) yields **`unverified-format` naming code 8
  and no pixels**, even though the data fits exactly one layout. One keyword on the fixture, two
  answers; without this pair the veto can be deleted without a red test, and a BC4 texture becomes a
  confident wrong image.
- (offline) `fmt=0` stored and `fmt=None` on the **same** chain produce **identical** results, in
  every branch tested — the assertion that no stored-vs-defaulted distinction crept back in (D8).
- (offline) a `FireTexture` body (`pkgfixture(mips=[(64, 64, b"")], trailing=…)`) yields
  `no-mip-data`, not `corrupt-body` — reading S1's fields, **without reopening the parser** (rows 0/1).
- (offline) a chain that fits `linear4` uniquely with **no** stored code: **detection succeeds**
  (`linear4`, `layout_source == "data"`) and the **decode** returns `unverified-format` naming
  `linear4` and 4 bytes/px (rows 6 then 9). Assert both halves — a test that only checks the error
  would not catch detection silently failing. *(Then one line for the contrast: the same chain with
  `fmt=5` stored is vetoed at row 2 instead, which is a different and also correct outcome.)*
- (offline) a chain whose mip 0 fits no layout at all yields `unrecognised-layout` (row 3), and one
  whose mip 0 fits `linear1` but whose mip 1 fits nothing yields `size-mismatch` (row 4) — the two
  are distinguishable, which is why the split is written down.
- (offline) an ambiguous chain judged with `code=None` yields `ambiguous-layout` (row 8) — distinct
  from `ambiguous-alpha`, which is one candidate with two decoders.
- (integration) `DmRiot.unr:SolModifié`, `:Flotte` and `DMBeyondTheSun.unr:Uebergang3` — the three
  real single-mip ambiguous samples, and the only real ones with a stored code — each resolve via the
  code, `layout_source == "format-code"`, layout `bc16` → BC3.
- (integration) the whole sweep produces **zero** `ambiguous-layout` rows and **zero**
  `unrecognised-layout` rows, matching §2b's measurement that every ambiguous chain is resolved by a
  code naming a fitted candidate.

### S4 — BC1 decode
*Makes the `CompMips` fallback real and gives the corpus its first non-P8 pixels.*

8-byte blocks: two RGB565 endpoints + 2-bit indices, with the `c0 ≤ c1` punch-through mode where
index 3 is transparent black. Row writes are clipped to the mip's real `w`/`h` — the partial-block
overrun case, live in the LUM `CompMips` chains at 8×2, 4×1 and 2×1. `mip0_to_rgb` (`:250`)
generalises to "decode this mip under this layout"; the P8 path keeps its exact current behaviour.
The mask S2's result carries is derived from the punch-through alpha for BC1 and stays "palette index
0 = transparent" for P8 (§5, decision D).

**S4 also fixes ARRAY SELECTION, and it is a defined procedure, not a preference.** S1 wires the
fallback inertly ("prefer `Mips`, fall back to `CompMips`"); BC1 is what makes the fallback real, so
S4 is where the ordering has to be exact. Detection is never run on an empty chain — it would index
mip 0 of an empty list and raise, against "no Python exception ever reaches the user":

1. **An array CARRIES DATA** iff it is non-empty *and* at least one of its mips has
   `len(data) > 0`. *("`Mips` is absent" is not a term this plan uses: a zero-length `Mips` array and
   a `Mips` array whose mips are all empty are treated identically, and both are simply "does not
   carry data".)*
2. **Selection runs FIRST**: `Mips` if it carries data; else `CompMips` if present and carrying data;
   else `no-mip-data`, with detection never invoked.
3. **Detection runs SECOND**, over the selected array, with **that array's** code (`Format` /
   `CompFormat`).
4. The result records which array it came from (`array: mips | comp-mips`), so a caller can see that
   a lossy copy was used.
5. **The fallback fires only on the selection rule — never because `Mips` failed to decode.** A
   `Mips` array that carries data and then errors reports **its** error. *(Rejected: falling back on
   any `Mips` failure. It would let a real corruption be papered over with a lossy copy and make the
   result's provenance unpredictable — the "no silent half-answers" shape. Measured cost of the
   strict rule: zero, since all 69 `bHasComp` textures have a perfectly decodable P8 `Mips`.)*

**Done when**
- (offline) **the `CompMips` array is judged against `CompFormat`, not `Format`** — the
  `LUM_CompMips.utx` texture's `CompMips` chain (64×64 → 1×1, flooring at 8 B) detects as `bc8`/BC1
  with `layout_source == "data"`, while the **same texture's** `Mips` chain detects as `linear1`/P8.
  One texture, two arrays, two layouts, and neither array's code interfering with the other's.
  *(Measured over all four corpora
  2026-07-25: all 69 `CompMips` arrays fit `bc8` **uniquely** and all 69 carry `CompFormat = 3`, so
  the data alone decides and the code corroborates.)*
- (offline) our BC1 decode is **byte-exact** against Pillow-DDS over the `LUM_CompMips.utx`
  `CompMips` chain, at every mip including 2×2 and 1×1. Pillow's conventions are pinned in §2d
  (bit-replication expansion, integer `(2a+b)/3` interpolants), so byte-exactness is the right bar;
  if a ±1 LSB divergence nonetheless appears, pin the convention actually observed and match it — do
  **not** loosen the assertion to a tolerance without recording why in the commit message.
- (offline) synthesized 8×2 / 4×1 / 2×1 BC1 blocks decode to exactly `w·h·3` bytes and match Pillow;
  a naive `bw*4` row write is caught (assert the buffer length, not just the pixels).
- (offline) the punch-through mode (`c0 ≤ c1`) yields a transparent index-3 pixel, matched against
  Pillow's alpha channel.
- (offline) the third-party agreement oracle: P8 `Mips` vs our BC1 `CompMips` on
  `LUM_CompMips.ClenGreyWndow_C` **mip 0** has mean absolute channel error **≤ 8/255** (measured
  1.98; four wrong-decode controls measured 20.3–62.0, so the bound discriminates by ~10×). Apply it
  at **mip 0 only** — mip 3 of the same texture measures 8.47 (§2d).
- (offline) **array selection, all four shapes** (the procedure above): a `pkgfixture` texture whose
  `Mips` array is **empty** and whose `CompMips` carries data decodes **through the fallback**, with
  the result reporting `array == "comp-mips"`; a texture whose `Mips` mips are all **zero-length**
  behaves identically (the two "absent" shapes are one rule); a texture where **neither** array
  carries data yields `no-mip-data` with **no exception** (detection is never invoked over the empty
  chain); and a texture whose `Mips` carries data but errors reports that error rather than silently
  returning the `CompMips` picture.
- (integration) every `bHasComp` texture in the install decodes **both** arrays and the two agree
  within the same mip-0 bound.

### S5 — BC2 / BC3 decode
*The last measured layouts (D3). Both share BC1's colour block at offset 8.*

BC2 = 16 explicit 4-bit alpha values; BC3 = two 8-bit endpoints + 3-bit indices (with the `a0 ≤ a1`
six-interpolant mode). The `Format` code selects between them via §0d's map (`6` → BC2, `7` → BC3);
any other code — including the **implied 0**, which names P8 and therefore names no 16-byte layout at
all — leaves it `ambiguous-alpha` from S3 (row 5), **never a coin flip**.

**This slice is where the universality limit at the top of this plan becomes real code, and the docs
it writes must say so plainly** (D9 / Andrzej's AD2): **a BC2 or BC3 file that stores no `Format`
does not decode.** It is not a corner the implementation "hasn't got to yet" and it must not be
described as one — there is no future measurement that fixes it, because the two layouts are
identical in size. Say it in the `unrealed/package-format.md` section this build writes, in the
`ambiguous-alpha` error text, and in the decoder's own comment. And say the other half in the same
breath, because it is what keeps the claim honest: **a code-less BC1 file DOES decode**, since 8-byte
blocks are unambiguous.

Three Done-whens (here, S3's, and S6's sweep census) depend on `ambiguous-alpha` being reachable.

**Done when**
- (offline) BC2 and BC3 decode byte-exact against Pillow-DDS over synthesized blocks covering: both
  alpha modes of BC3, a fully-opaque block, a graded-alpha block, and the 2×2 / 1×1 / 8×2 shapes.
- (offline) the same 16 bytes decoded as BC2 and as BC3 produce **different** alpha and **identical**
  RGB — the shared-colour-block claim, asserted rather than assumed.
- (offline) a 16-byte-block chain with no usable code still yields `ambiguous-alpha` and no pixels.
- (integration) `DmRiot.unr:Poster01` decodes as BC3 to a fully-opaque alpha channel, and all 4,096
  of its mip-0 alpha halves are `0005ffffffffffff` — the pinned identification (§2c), asserted where
  a future decoder change would break it.
- (integration) `UnrealShare.u:TranslatorHUDHD` (2048², 12 mips) decodes end to end without an
  exception and in bounded memory.

### S6 — the corpus sweep (offline + integration) and the engine-fact pins
*The test that would have caught both the fmt-7 gap and `CompMips`.*

**The sweep is TWO TIERS, and the offline one is the important half.** The first draft made the whole
sweep `-m integration`, which would have left the criterion for the live bug — 30 invisible textures
in `Textures/LUM_CoreTex.utx` — **deselected by default on the machine that has the bug**. Both
`Textures/*.utx` and `uned/UED22/` are git-tracked (§0a), so:

- **Offline tier — `uedcli/tests/test_utexture_corpus.py`, no marker.** Sweeps both reachable corpora,
  but **exact counts only where §0a's count-stability rule allows them**:
  - `conftest.ued22_root()` — **fully tracked**, so exact: **34** packages, **1,998** `Texture`
    exports, **1,998** mip arrays (this tree has **no** `CompMips` at all), **861** chains fitting one
    layout, **1,137** ambiguous, 0 parse failures, 0 `unrecognised-layout`, 0 `ambiguous-layout`,
    0 `ambiguous-alpha`. Say in the assertion which unit each number is in (exports vs arrays);
    they differ the moment a `CompMips` appears.
  - `conftest.repo_texture_root()` — **partly tracked and live** (4 of 6 packages here), so
    **invariants only**: every export decodes or names a case, 0 parse failures,
    0 `unrecognised-layout`, 0 `size-mismatch`, 0 `ambiguous-layout`, 0 `ambiguous-alpha`, no
    unhandled exception. **Do not assert a package or export total.** The one exact clause is pinned
    to a tracked *file*: `LUM_CoreTex.utx` goes from **30** `Texture`-class parse failures to **0**
    (it holds 253 `Texture` exports and all 30 of the failures; the other three tracked packages fail
    zero).

  Exact counts where they are legitimate are what turn a silent regression into a red test; a "no
  exceptions" sweep passes happily while everything degrades to a named error. An exact count over a
  directory that a fresh checkout populates differently is the opposite — it fails for the wrong
  reason and gets edited until it stops complaining.
- **Integration tier — `uedcli/tests/test_utexture_corpus_installs.py`, `-m integration`.** The Deus
  Ex install (via `conftest.install_root()`) and the Unreal Gold install (via a new
  `UEDCLI_TEST_UNREAL_INSTALL` env pointer, **skipped** when unset — there is no existing pointer for
  it, §0a).

Both tiers assert: **every** texture-classed export either decodes or produces a named case; zero
silent misses, zero exceptions. Both report the `(Format, CompFormat)` census and the
`layout_source` split (`data` vs `format-code`) so a regression shows up as a count change. **Every
reported number states its unit** — textures (one `Mips` chain each) or mip arrays (`Mips` plus each
`CompMips`); §2b gives both, and they differ by exactly the 69 `CompMips` arrays.

**The sweep needs its OWN export matcher, and must say so.** `utexture.textures()` matches
`class == "Texture"` **exactly** (`utexture.py:245`), so `FireTexture`/`WetTexture`/`ScriptedTexture`
are *never* enumerated through it — and widening it is explicitly out of scope (§6, it belongs to the
asset catalog). The first draft's "the procedural classes reporting `no-mip-data`" was therefore
unreachable through the shipped API. Fix: the sweep module defines a **test-local** matcher

```python
def _texture_like(pkg):     # test-only; deliberately NOT utexture.textures()
    return [i for i, _ in enumerate(pkg.exports)
            if (pkg.class_of_export(i) or "").endswith("Texture")]
```

and the `no-mip-data` criterion is asserted over *that*. Say in a comment that this is the sweep's
own widening, that production stays exact-match, and that the asset catalog is where the widening
would land for real.

The engine-fact pins land here per the "pin the finding" rule (§0b): the three `ETextureFormat` slot
lists (**the UED22/227 one is offline** — `uned/UED22/Engine.u` is tracked; the other two are
integration) and the BC3 alpha-block signature. These are **evidence, never a runtime dependency** —
assert that no production module imports them.

**S6 ALSO LANDS THE SPIKE MARKDOWN, and S7 is blocked on it.** S7 deletes this plan and the spec —
and the spike directory it keeps, `dev/docs/spikes/2026-07-25-native-texture-formats/`, contains
**exactly one file today: `pkgfixture_proto.py`. No markdown at all** (verified 2026-07-25). So on
deletion day the entire evidential basis of this design disappears: the fit census in both units and
the method behind it (§2b), the three `ETextureFormat` dumps (§0d/§2c), the eleven stored codes
(§2c), the `CompMips` measurements (§2a), the P8-vs-DXT1 mean-error table with its four wrong-decode
controls, and the pinned Pillow conventions (§2d). Some of it survives as test constants, which is
**not** the same thing: a constant records what we expect, never how it was measured or over which
corpus, so the next person cannot re-derive or challenge it.

S6 therefore writes `dev/docs/spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md`
(sibling of the existing prototype, matching the `NN-topic.md` convention of
`spikes/2026-06-27-decontainerize-uedcli/`) containing: the method (which roots, which parser, which
date, the script), the census in both units, the three enum dumps including Deus Ex's silence on 6/7
and 227's slot 8 `TEXF_BC4`, the eleven stored codes, the `CompMips` pairs and their error table, and
the Pillow convention pins. The **format facts** — the `UTexture`/`FMipmap` byte layout, the
property-gated `CompMips`, the arbitration rule — go where format facts live,
`dev/docs/unrealed/package-format.md`, with confidence markers; the **evidence** goes to the spike.

**Done when**
- (offline) the sweep is green with **zero** unhandled exceptions, zero `unrecognised-layout`, zero
  `ambiguous-layout`, zero `ambiguous-alpha`; the exact `uned/UED22` fit census above holds; and the
  `Texture`-class parse-failure count is **0** over both roots — including **0 for
  `LUM_CoreTex.utx`, down from 30**, the one exact clause allowed over `Textures/`.
- (offline) **the count-stability rule is respected in the test source itself**: no assertion in
  `test_utexture_corpus.py` compares a package or export **total** over `repo_texture_root()` (that
  directory holds untracked packages on this machine and unknown content on another). A reviewer
  should be able to check this by reading the file.
- (offline) **the spike markdown exists** at
  `dev/docs/spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md`, carries the census
  in both units, the three enum dumps, the eleven stored codes and the oracle tables, and is cited
  from `unrealed/package-format.md`. S7 must not delete anything until this is committed.
- (integration) the sweep is green over both installs with the same zero-exception /
  zero-`unrecognised-layout` bar, and records exactly the §2a failure profile: 0 `Texture` failures
  post-S1.
- (offline) using the sweep's own `_texture_like` matcher on a tracked package, every
  procedural-class export (`FireTexture` et al.) reports `no-mip-data` — **and** the shipped
  `utexture.textures()` still returns none of them, asserted in the same test so the widening cannot
  leak into production.
- (offline) **the §0d slot-map pin:** the UED22/227 enum dump asserts `{0: TEXF_P8, 3: TEXF_BC1,
  6: TEXF_BC2, 7: TEXF_BC3}` and 122 slots, with no install present — **and, in the same assertion,
  `8: TEXF_BC4`**, which is the evidence for the veto rather than for the map: it is the slot that
  proves an unknown code can collide byte-for-byte with a mapped layout (`bc8`). If a future
  substrate renames slot 8 to something we *can* decode, this test goes red and the veto's
  justification is re-examined. (integration) the Unreal Gold
  dump asserts `{0: TEXF_P8, 3: TEXF_DXT1, 6: TEXF_DXT3, 7: TEXF_DXT5}` and 8 slots, and the Deus Ex
  dump asserts `{0: TEXF_P8, 3: TEXF_DXT1}` and exactly **5** slots — i.e. that it *does not define*
  6 or 7, so its silence is pinned as silence rather than as agreement. **Together these three are
  the assertion that §0d's four-row map is justified**; if a future substrate breaks the agreement,
  this is the test that goes red. Each skips cleanly when its install is absent.
- (offline) `grep` proves no module under `uedcli/` outside the tests reads `ETextureFormat`.
- (offline) `bin/test` shows **no new skips** and **more deselected** versus the S1-measured baseline
  (§0) — the new integration module must be *deselected*, not skipped, in the default run, while the
  new offline module adds passed tests.

### S7 — docs, board, spec deletion
Cross-cutting only (per-slice docs already landed):
- **`decisions.md`** — the arbitration decision (AD1 + AD2) is **already in the ledger** as
  *"2026-07-25 17:45 UTC — Texture layout arbitration is a tiebreak-and-veto; `format-disagreement`
  is deleted and a code-less BC2/BC3 does not decode"*; do **not** re-record it. S7 appends only what
  the BUILD itself learns beyond it: the surviving builder-decided call of §5 (mask semantics ignore
  `bMasked`/`bAlphaTexture`), anything the implementation forces, and the outcome of the veto and
  `ambiguous-alpha` cases in practice. Append; never reword an existing entry.
- **`architecture.md`** — the four non-preview texture passages of §0f (grep
  `textures decode natively`, `utexture.TextureResolver.exists`, `the native` +
  `UTexture/UPalette decoder`, `utexture.TextureResolver.resolve_masked`).
- **`unrealed/package-format.md`** — finish the `UTexture`/`FMipmap`/`CompMips` body section under
  §`Object body layouts (byte-exact) 🔬` and the layout-detection rule, with confidence markers, and
  **state the `ambiguous-alpha` limit** beside the arbitration rule; cite S6's spike markdown.
- **`direction.md`** — the asset-catalog section's "**produces the picture** (decodes a texture,
  renders a mesh natively)" is where the compiled target claims universal decoding. Reconcile it with
  the limit: a code-less BC2/BC3 texture is reported undecodable rather than drawn. One clause, but
  the maintenance rule requires it because a decision landed.
- **`plans/2026-07-25-unified-asset-catalog-plan.md`** — mark its `P1` landed; correct its S1 note
  that "there is no UE1 package writer in the tree" (§0e2).
- **board** — the item is **already on `to-build.md`**, not `to-plan.md`: `to-plan.md`'s "Native
  texture decode" line is a **tombstone** ("PLANNED 2026-07-25, moved to `to-build.md`"), so **delete
  the tombstone** rather than moving anything, and tick/remove the `to-build.md` item under the
  heading `## Native texture decode for any UE1 package`. Also **fix the stale prerequisite note in
  the asset-catalog item further down the same file** — grep `Blocking prerequisite NOT yet on the
  board`, which still calls this work "an untriaged `inbox` item (`[spike/implement] p2`)" that needs
  triaging through `to-spec`/`to-plan`; it is neither untriaged nor `p2`. Leave `inbox.md`'s
  `[spike/implement] p1 The REMAINING UE1 texture layouts` item in place (it is D4's, not this
  build's) but point it at the `unverified-format` case that now exists; close the `utexture`
  sub-finding of the `preview_native` cold-review list in `inbox.md` (grep
  `utexture` resolver can raise IndexError/MemoryError`).
- delete `specs/2026-07-25-native-texture-formats.md` and this plan — **but only after S6's spike
  markdown is committed.** The spike dir holds no markdown today, so deleting first would take the
  census, the enum dumps, the stored-code list and the oracle tables with it. **Keep**
  `dev/docs/spikes/2026-07-25-native-texture-formats/` — spikes are durable evidence, not scratch.

**Done when:** no doc describes a P8-only decoder; **every doc that claims "any texture from any
engine" also states the `ambiguous-alpha` limit** (a code-less BC2/BC3 does not decode, a code-less
BC1 does); no board line calls this work untriaged or unplanned;
`dev/docs/spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md` exists and is cited
from `unrealed/package-format.md`; the spec and plan are gone and the spike dir remains; `bin/test`
green.

---

## 4. Risks

| risk | mitigation |
|-------------------------------------------------------------|---|
| The spec's original body layout was wrong (raw vs tagged `bHasComp`) | §0e1 states the measured layout; S1 builds against it and pins 207/207 |
| The `Format`-code tiebreak is 46 % of the corpus, not an edge case | §2b sizes it; S3 makes it a first-class branch with tracked offline samples and a `layout_source` field |
| Falling back to the `Format` code re-imports the portability problem D1 rejected | the fallback only ever breaks a tie between candidates the DATA already fitted, the source is recorded, and a code naming no fitted candidate errors rather than guessing |
| The tiebreak silently runs on a code nobody wrote              | §0d measures it (a `Format` property is present on 11/18,176) and states plainly that an absent property IS the byte 0 by UE1's own rule; S3 tests the `code=None` path separately from the implied-0 path |
| **A code-less foreign non-P8 file returns no pixels**          | §0d rule 1: a unique data fit decodes with the code unconsulted, so a code-less **BC1** file works. S3's veto pair asserts it (same chain, `fmt=None` decodes / `fmt=8` vetoed). The **known exception is BC2/BC3**, which is stated as a limit at the top of this plan rather than engineered away |
| **A stored code naming an undecodable layout is ignored, and the file is drawn wrong** | 227 slot 8 is `TEXF_BC4`, an 8-byte-block format that fits `bc8` identically to BC1. §0d's veto + S3 row 2, ordered ahead of every fit branch, with the `fmt=8` half of S3's veto pair as its red test |
| An **uncoded** `bc8` chain is really BC4, not BC1              | accepted and **recorded as an assumption** (§0d), sound because a real BC4 export must store `Format=8` (UE1 omits only class-default values) and the veto then catches it. A future BC4 sample is a test of the assumption |
| §0d's four-slot code→layout map quietly becomes the format table D1 rejected | it is used only to break a tie among candidates the DATA fitted and to name the codes we cannot decode — never to size a chain. S6 pins the three enums, incl. that Deus Ex is *silent* on 6/7 rather than agreeing |
| The `CompMips` array is judged against `Format` instead of `CompFormat` | the detector takes the code as an explicit argument per array (S3); S4 asserts one texture detecting `linear1` and `bc8` from its two arrays |
| S3 has to reopen S1's parser to put `no-mip-data` in front of the EOF check | S1 makes the parser **report** `trailing_bytes` + `no_mip_data` on every body instead of raising; S2 classifies, S3 only reads. The v61 integrity signal is preserved for every texture rather than weakened for one fixture shape |
| **S1 ships a silent black image** — the `not t.mips` gate passes a list of *empty* mips and `mip0_to_rgb` returns all zeros (verified live) | S1 adds an explicit "no mip carries data ⇒ miss" ahead of the gate, in the same commit that stops the raising, with its own Done-when that forbids a zero-buffer from satisfying it |
| Detection is invoked on an empty chain and raises `IndexError` | S4's array-selection procedure runs **before** detection and returns `no-mip-data` when neither array carries data |
| A census figure means textures in one place and mip arrays in another | §2b states both units explicitly and counts the 69 `CompMips` arrays separately; S6 requires every reported number to name its unit |
| **An "offline exact count" over `<repo>/Textures/` is wrong on a fresh checkout** — 2 of its 6 packages here are untracked, and it is live content | §0a's count-stability rule: exact counts only over `uned/UED22` + fixtures + the single tracked `LUM_CoreTex.utx` (30 → 0); invariants elsewhere. S6 has a Done-when a reviewer can check by reading the test source |
| The corpus criterion for the live bug is deselected by default | the sweep is two-tier (S6); both reachable corpora run offline, and S1's 30 → 0 clause is offline |
| No BC3 sample is committable (Epic content)                   | BC2/BC3 pixels are pinned against Pillow over synthesized blocks; the real samples are integration-only |
| A synthesized fixture would only test our own encoder          | the container comes from the in-tree writer, but every **expected pixel** comes from Pillow or from a real lifted payload — never from running our decoder once |
| The old "≤ 1/255" agreement bound is unmeetable                | measured per texture and per mip (§2d); S4 uses ≤ 8/255 at **mip 0 only**, which still separates right from wrong by ~10× |
| The ref-level misses have no typed case, leaving four committed tests with no expectation | S2 defines `unqualified-ref` / `unknown-package` / `package-unreadable` / `unknown-texture` here and re-points `test_utexture.py:95/:99/:105/:128` onto them; the asset catalog reuses them rather than inventing its own |
| The evidence dies with the deleted spec — the spike dir holds only a `.py` | S6 lands `01-texture-layout-census.md` in the spike dir and S7's deletion is explicitly gated on it |
| S1 silently moves a decoded pixel                              | the two frozen digests in `test_utexture.py:39`/`:48` are an explicit S1 Done-when |
| Later changing which array wins re-keys the catalog's frozen texture identity | this plan lands **before** the catalog's texture arm, so no shard exists yet; the risk is recorded there, not re-solved here |
| A new integration module is *skipped* rather than *deselected* | S6's last Done-when checks the baseline counts explicitly |
| Concurrent sessions edit board/docs                            | commit by explicit pathspec, never `git add .`/`-a` (§0b) |

---

## 5. One question this plan settles (builder-decided, reversible)

It was left open by the spec and it **blocks work**, so it is decided here rather than deferred. It
is chosen to fit the documents' own principles — *never a wrong pixel* and *no silent half-answers* —
and it is **builder-decided under Andrzej's "do whatever it takes" delegation and cheaply
reversible**, so overruling it costs one small change plus its test.

### C. *(withdrawn — Andrzej decided this one himself)*

This section defined `format-disagreement` as a named error, scoped by the stored-vs-defaulted
asymmetry. **Both are deleted by AD1** (see §0c D8): a code never contradicts the data, so there is
no disagreement to name, and with the contradiction gone the provenance axis distinguishes nothing.
The arbitration that replaces it is §0d's four lines and S3's ordered table; the rejected
alternatives — keeping the case as a fixture-only diagnostic, and keeping the provenance field —
are recorded in D8 and in the ledger. The heading is kept because other sections cite "§5-C"; nothing
here is design any more.

### D. Mask semantics: the decoder emits the mask the DATA carries and ignores `bMasked`

**Decision.** The transparency mask a decode returns comes **only from the pixel data**:

- **P8** — unchanged from today: palette index 0 = transparent, everything else opaque
  (`utexture.py:359`). P8 data carries no alpha, so this convention *is* its mask.
- **BC1** — the punch-through alpha: in the `c0 ≤ c1` mode index 3 is transparent, otherwise the
  block is fully opaque.
- **BC2 / BC3** — the block's own alpha values.

`bMasked` and `bAlphaTexture` are **read and reported as facts on the result**; the decoder never
applies them.

**Rationale.** uedcli's standing principle is that **the tool does not infer** — it reports what is
literally stored and produces the picture, and leaves meaning to the caller. The alpha bits inside a
BC1/BC2/BC3 block are literally in the data; `bMasked`/`bAlphaTexture` are *engine render policy*
owned by whoever is drawing. Folding them into the decoder would make identical bytes decode to two
different images depending on a flag the pixel layer does not own, and discarding real stored alpha
because a flag is unset is data loss the caller cannot undo. Keeping the P8 rule exactly as it is
also protects S1's invariant that the `CompMips` slice must not move a single decoded pixel.
*(Measured for this decision: `Engine.Texture`'s effective defaults state neither `bMasked` nor
`bAlphaTexture`, so both default to `False` — i.e. gating on them would silently turn the block
alpha OFF for essentially every texture in the corpus.)*

*Rejected: gate the block-format alpha on `bMasked`/`bAlphaTexture` inside the decoder.* An unflagged
BC3 texture would decode to a fully-opaque image that silently discards stored alpha; and the
decoder's output would depend on a property with nothing to do with how the bytes are laid out —
the beginning of exactly the per-game-semantics table D1 rejected.

---

## 6. Not in this plan

- **Encoding** textures. `pkgfixture` is test-only and never ships.
- **The unsampled linear slots** (Unreal Gold `RGB32`/`RGB64`/`RGB24`/`RGBA8`; 227
  `BGRA8_LM`/`R5G6B5`/`RGB8`/`BGRA8`, `BC4`+) — D4's `p1` board item owns them (grep
  `inbox.md` for `The REMAINING UE1 texture layouts`); they
  produce `unverified-format` until it lands.
- **Any per-game format table**, shipped or derived from a game's `Engine.u` (D1).
- **Widening `textures()` (`utexture.py:245`) to `Engine.Texture` descendants** — the asset catalog's.
  This plan makes procedural textures fail *honestly* when something else enumerates them.
- **`texture show` / catalog `undecodable` rows.** Neither exists (§7.3). Four dispositions of a
  typed decode error are conceivable — preview degrades to a checkerboard, the sprite path degrades
  to a marker, a per-ref request exits 2 naming the ref, and enumeration records an `undecodable`
  row and continues. Only the first two have a live caller today; the last two are the asset
  catalog's to wire onto the result type this plan defines.
- **Lightmap formats inside `Model`.**
- **Migrating `utexture` onto `upackage.py`** — a pre-existing separate board item (`architecture.md`,
  grep `migrate as a board follow-up`).

---

## 7. Where the spec and the code/corpus disagreed

Each of these was measured for this plan; the plan builds against the measurement, not the prose.
(The spec has since been rewritten to match, so these are recorded as the *reasons* the prose reads
the way it now does.)

1. **The body layout** — the spec's original §3 read as though `bHasComp`/`CompFormat` were raw
   trailing bytes. They are tagged properties; only `CompMips` is trailing data and it is gated on
   the flag. The raw reading fails on 39 of 39 DX `System`+`Textures` cases (20 skip-offset
   mismatches, 19 non-EOF); the property reading succeeds on 207 of 207 over the whole tree. *(§0e1)*
2. **"The tail of the chain separates them decisively"** — true only for chains that descend below
   one block. 8,327 of 18,176 texture exports (45.8 %) fit two or more layouts, so the `Format`-code
   fallback filed as an open question is the deciding path for nearly half the corpus. Three real
   single-mip block samples exist, not two. *(§2b)* And the code doing the deciding is, 99.94 % of
   the time, the class default rather than a stored value. *(§0d)*
3. **"`texture show` exits 2 … enumeration records an `undecodable` row"** — neither exists. The
   `texture` noun today is `sync|list|search|tags|classify` (`cli.py` — grep
   `sub.add_parser("texture"`, ~`:1455` → `_dispatch_texture` in `dispatch.py`, ~`:1226`); there is
   no `show` and no catalog enumeration until the
   asset catalog lands. "Asserted at both layers" is therefore **unbuildable here**; this plan
   defines the typed result and wires the two dispositions that do exist.
4. **"147/147"** — the count is corpus-dependent and was never pinned to a root. Measured: **39**
   (DX `System`+`Textures`+`Maps`), **30** (`LUM/Textures`), **69** (their union — very likely the
   draft's unattributed "69"), **207** (the whole `drive_c/DX` tree including the TNM mod). None is
   147. What is invariant, and what this plan asserts, is the **ratio**: `CompMips` explains 100 % of
   `Texture`-class parse failures on every root measured.
5. **"208 `FireTexture` failures in Deus Ex"** — 208 is the whole `drive_c/DX` tree; the
   `System`+`Textures` roots hold **40**, and Unreal Gold's 153 reproduces exactly. Same corpus
   caveat.
6. **"≤ ~1/255 mean error"** — holds for `quadrocks_logo_02` mip 0 (0.605) and not in general
   (`ClenGreyWndow_C` mip 0 = 1.98, mip 3 = 8.47). And a wrong decode does **not** reliably score
   60–80: controls measured 20.3–62.0. *(§2d)*
7. **"Enum dump as evidence (integration)"** — one of the three dumps is offline, because
   `uned/UED22/Engine.u` is git-tracked. Making it integration would needlessly weaken it. Also, the
   227 enum has **122** slots, not the 118 first recorded.
8. **`no-mip-data` vs "the body-to-EOF check remains the integrity guard"** — mutually exclusive for
   `FireTexture`, whose trailing `FSpark` array trips the EOF guard. Resolved by ordering:
   empty-pixel-data is decided first — and **implemented in S1**, where the guard is written
   (`utexture.py:217-219` raises before any layout logic runs, so a later slice cannot get in front
   of it without reopening it). An earlier draft filed this in S3, which was unbuildable as sliced.
9. **`utexture.py:33`'s `TEXF`** — the spec says no table is needed; the code already ships one, it
   is dead (no in-tree reader), and it is wrong on slots 1, 2 and 4 versus every enum measured.
   Deleted in S1.
10. **"no format table" vs a `{code → layout}` map** — the design makes the effective code the
    decider for 45.8 % of the corpus and the only possible BC2/BC3 selector, both of which require
    turning a number into a layout. The first draft left that map implicit, which read as a
    contradiction of D1. Resolved by writing it down in §0d as exactly four slots
    (`{0: P8, 3: BC1, 6: BC2, 7: BC3}`), naming it as THE one place slot semantics are assumed,
    justifying it from the three measured enums, pinning it in S6, and scoping it: it never sizes a
    chain, and decoding survives its absence. *(§0d)*
11. **A code out-voting the data at all** — a draft made the effective code able to *contradict* a
    unique data fit (`format-disagreement`), which meant a foreign code-less non-P8 `.utx` returned
    no pixels; a later draft rescued it with a stored-vs-defaulted asymmetry. **Both are now gone
    (AD1 / D8):** the code breaks ties and vetoes unknown layouts, and never contradicts. Measured
    justification: all 11 stored codes agree with their own chain's fit, so the disagreement fired on
    zero real files while manufacturing contradictions on non-P8 chains. *(§0d, S3 rows 2/6/7)*
    **Note for anyone rewriting this passage:** the worked example is **BC1**, not BC3 — a code-less
    BC3 file does *not* decode (`ambiguous-alpha`, AD2), so arguing the rule with a BC3 example
    would be arguing for a rescue the design does not perform.
12. **"data-decisive but unimplemented"** — the draft said both "a unique fit wins with
    `layout_source: data` even when the code names no implemented layout" and "an unsampled slot
    whose chain fits `linear4` yields `unverified-format`". Resolved by separating **detection** from
    **decodability**: detection succeeds and reports `linear4`; the decode step then returns
    `unverified-format` because no decoder exists. *(S3 rows 6 + 9)* And a *stored* unknown code no
    longer even reaches detection — it is vetoed at row 2.
13. **The corpus guard rail filed as integration-only** — `Textures/LUM_CoreTex.utx` and
    `uned/UED22/` are both git-tracked, so the criterion for the bug motivating the build was being
    deselected by default. Split into an offline tier over the reachable corpora and an integration
    tier over the two installs. *(§0a, S6)* A follow-up correction: the offline tier's **exact
    counts** over `<repo>/Textures/` were themselves wrong — that directory is only partly tracked
    (4 of 6 packages) and is live, so exact counts there are confined to the single tracked
    `LUM_CoreTex.utx` and everything else is an invariant. *(§0a's count-stability rule)*
14. **`textures()` cannot see a procedural texture** — it matches `class == "Texture"` exactly
    (`utexture.py:245`), so S6's "the procedural classes reporting `no-mip-data`" was unreachable
    through the shipped API, and widening `textures()` is out of scope. S6 defines its own test-local
    matcher instead and asserts that production stays exact-match. *(S6)*
15. **A stored code cannot be allowed to lose to the data** — 227's slot 8 is `TEXF_BC4`
    (re-dumped 2026-07-25 from the tracked `uned/UED22/Engine.u`), an **8-byte-block** format that
    fits `bc8` uniquely and identically to BC1. A "unique fit always wins" decoder draws it as BC1:
    a confident wrong image on a file that says it is not BC1. Hence the veto, ordered ahead of every
    fit branch, and the explicit note that an *uncoded* `bc8` chain is BC1 by assumption. *(§0d, S3
    row 2)*
16. **`_decode_ref` has SEVEN bare `return None`s, not five**, plus an eighth miss swallowed inside
    `_package`. Re-counted 2026-07-25. Four of them are asserted by committed tests
    (`test_utexture.py:95/:99/:105/:128`), which is why the **ref-layer** cases are defined in this
    plan instead of deferred to a catalog that does not exist. *(S2)*
17. **The `not t.mips` gate is not an emptiness check** — a list of *empty* mips is truthy, so once
    the parser stops raising, `mip0_to_rgb` returns an all-zero buffer: a silent black image
    (verified live 2026-07-25 — 12,288 zero bytes for a 64×64). S1 adds the real check ahead of the
    gate and owns the Done-when. *(S1)*
18. **The EOF guard was being weakened to make a fixture produce `no-mip-data`.** Reporting
    (`trailing_bytes` + `no_mip_data`, always, never raising for this condition) keeps the integrity
    signal for **every** body — including v61, where it is the only one — and moves the
    classification to the layer that classifies. *(S1, S2)*
19. **`<repo>/Textures/` is not fully tracked, and the spike directory has no markdown.** Two
    self-containment defects of the same kind: an offline expectation that depends on this machine
    (`CoreTexSky.utx`/`CoreTexWater.utx` are untracked, so "6 packages / 418 exports" is not a
    checkout's reality), and a durable record that is one `.py` file, so deleting the spec would
    delete the census, the enum dumps and the oracle tables. Fixed by §0a's count-stability rule and
    S6's spike markdown, with S7's deletion gated on the latter.

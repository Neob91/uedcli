+++
priority = "p1"
kind = "implement"
summary = "uscript: remaining construct + corpus work to reach 30 byte-exact packages"
depends-on = ["uedcli-unrealscript-compiler"]
+++

# uscript — the path from 4 to 30 byte-exact packages

The compiler compiles the full single/multi-class declaration surface + functions byte-exact vs UCC
(perm_gate), proven on **4 real brush-builder packages** (FrameBuilder, RahnemBrushBuilders,
ExtendedBuilders, DavesBrushBuilders). The remaining work to 30, in rough priority:

## Construct gaps (each blocks a class of real packages)
- **ProbeMask / IgnoreMask (UState/UClass).** A class overriding a probe event (Tick, Timer, Touch,
  …) sets a bit in the u64 `ProbeMask`; uedcli emits 0. MEASURED: `UnrealShare.UnrealTestInfo`
  overriding `Tick` → `ProbeMask = 0x1000000000` (bit 36). The bit is NOT the function's index in
  Actor's Children (Tick is #76 there) — it is a fixed engine `EProbe` enum. RE the probe-name→bit
  map (from `Engine.dll`, or by hierarchy-aware correlation over stock `.u`: a read-only scan of 1546
  stock classes found ProbeMask **ACCUMULATES through inheritance** — a subclass carries a probe bit
  without overriding the function, so bit-set ↔ own-function correlation fails; solve with the
  class-hierarchy closure `{classes where the class OR an ancestor defines f_b}`). Then per class
  ProbeMask = OR of bits for probe functions in its (inherited) set; `IgnoreMask` starts all-ones and
  clears `ignores`. Blocks nearly every gameplay class. UnrealShare becomes byte-exact once done.
- **states** (`state{...}` → UState exports + label tables + state code), **replication** blocks,
  **`#exec`** asset imports (TEXTURE/MESH/SOUND — the owner wants these in scope), and the
  **expected-type-directed operator overload** lowering residual (int-divide-into-int-field etc.;
  attempted+reverted twice as subtle — needs careful RE). See `test_uscript_lower.py` residuals.
- Parser edge: `mod`/other keyword operators inside array-dim expressions (TarquinExtrudeBuilder).

## UT99 substrate (2026-09-05) — the corpus source
A self-consistent UT99 (UnrealTournament GOTY) toolchain is stood up: `uscript/fetch_ut99.sh`
downloads the stock System (`.u`+`.dll`+`UCC.exe`, gitignored `uned/UT99/`) from archive.org
(`ut-goty/UT_GOTY_CD1.iso`); `uscript/reference_ut99.py` runs UT99's OWN UCC in a container (its
Core.u ≠ UED22's, so UED22's UCC must NOT be used for UT99 pkgs). Setup quirks RE'd: UCC needs a
`User.ini`; `EditPackages` must END at the target (else it cascade-rebuilds later pkgs and aborts).
Content packages (Botpack/relics/de/…) need `.uax`/`.utx` we don't fetch → not targets; **code-only
UT99 packages that round-trip under UT99-UCC are the corpus** (IpServer/UWeb/Fire round-trip; more
after the gaps below). Community mutators next (need Botpack+content → may need a content fetch).

First UT99 gaps surfaced (being fixed): inherited enum-name default (IpServer), Line/TextPos function
lookup (UWeb), non-scalar struct member (Fire) — all pre-existing uedcli gaps, help DeusEx corpus too.

## Corpus reality
- `native noexport` classes (ConSys, most of DeusEx, some of Engine/Extension) do NOT round-trip
  even under UCC — their `batchexport` sources don't recompile. Not valid targets.
- Stock pure-script packages are few (~the brush builders + a handful). **Reaching 30 needs
  community/Internet pure-script packages** (network works; download DeusEx/UT-tree script mods),
  most of which will exercise ProbeMask/states/replication above.
- Reference recipe stands: decompile `.u` → `.uc` (ucc batchexport), compile via UCC (fresh golden)
  AND uedcli, compare with `perm_gate`. Never use a shipped `.u` as the golden (editor-serialized).

## Done / not blocking
CLI verb `uedcli uscript compile` shipped. Adversarial Opus review done (critical export-Super hole
fixed; residuals in `uscript-pre-merge-hardening`). Merge gate: re-run the Opus review + close
hardening before squash-merge.

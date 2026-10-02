# The builder brush is `ULevel.Actors[1]` — a position, not a content heuristic

**Question.** `uedcli/normalize.py:is_builder_brush` currently identifies the transient "red
builder brush" (UnrealEd's live editing widget, not level content) by content: `Class=Brush` +
inner model name `Brush` (unnumbered) + no `CsgOper=`. It was just found WRONG on a real level
(`03_NYC_UNATCOHQ`): a genuine stray leftover builder brush, `Brush74`, has no `CsgOper` but its
inner model name is `Model`, same as every ordinary content brush in that level — so the
model-name half of the predicate can never fire on this real trunk, and the actor slips through
into the trunk as if it were content. How does UED22 *itself* decide which actor is "the" builder
brush, at MAP LOAD/SAVE time?

## Answer: it is `ULevel::Brush()`, which is `(ABrush*)Actors(1)` — pure array position

Two independent sources, agreeing exactly:

**1. Public UE1 engine source** (`Engine/Inc/UnLevel.h`, `stephank/surreal` — a source mirror of
the original Unreal Engine 1 codebase this project already treats as ground truth for UE1
architecture facts):

```cpp
ABrush* Brush()
{
    guardSlow(ULevel::Brush);
    check(Actors.Num()>=2);
    check(Actors(1)!=NULL);
    check(Actors(1)->Brush!=NULL);
    return (ABrush*)Actors(1);
    unguardSlow;
}
```

Contrast with the level-info accessor right next to it in the same header:

```cpp
ALevelInfo* GetLevelInfo()
{
    guardSlow(ULevel::GetLevelInfo);
    check(Actors(0));
    check(Actors(0)->IsA(ALevelInfo::StaticClass()));
    return (ALevelInfo*)Actors(0);
    unguardSlow;
}
```

`GetLevelInfo()` type-checks slot 0 (`IsA(ALevelInfo::StaticClass())`). `Brush()` does **not**
type-check slot 1 at all — it blindly casts `Actors(1)` to `ABrush*` and only asserts that its
(now-assumed-valid) `Brush` UModel field is non-null. There is no `Class=Brush` check, no
`CsgOper` check, no inner-model-name check anywhere in this function. The engine does not
"identify" the builder brush by inspecting an actor's properties at all — slot 1 of the Actors
array simply **is** the builder brush, by definition, and the editor's own brush-tool code is
responsible for always keeping a real `ABrush` there.

(`FStaticBrushIterator`, the general "walk every static/placed brush" iterator in the same file,
is the OTHER, content-based concept UE1 has — it walks the whole `Actors[]` array testing
`IsStaticBrush()` per actor, which is presumably what the `CsgOper != CSG_Active` distinction
actually feeds. That is a different question ("is this actor part of the built level") from "which
one actor is THE current builder brush" (`Level->Brush()`, always `Actors(1)`). uedcli's
`is_builder_brush` conflates the two — it tries to approximate the *first* question's answer using
signals that only really speak to the *second*.)

**2. This project's own byte-exact reverse engineering**, independently, from three separate
angles, none of which needed the public source above:

- `dev/docs/spikes/2026-07-15-native-materialize/sections/30-ulevel-paths-assembly.md` §1: the
  whole `ULevel` object body round-trips byte-exact across **100/100 real retail `.dx` maps**
  (`level_roundtrip.py`), and states plainly: *"`Actors[1]` = the level's Default Brush (the "red
  builder brush"): a `Brush` actor whose `Brush=` points to a small `UModel`... ✅"* — verified
  against real package bytes, not inferred.
- `dev/docs/spikes/2026-07-24-level-import-order/findings.md`: decoding the `Engine.Level`
  object's `Actors` array directly out of three more retail maps (`00_Intro.dx`, `00_Training.dx`,
  `02_NYC_Street.dx`) independently confirms *"`Actors[0]` is always `LevelInfo0`... `Actors[1]`
  the default/builder brush"* and cites the matching UE1 invariant
  (`ULevel::GetLevelInfo()` returns `Actors(0)`).
- `uedcli/mapimport.py` (production code, already merged) already encodes this as ground truth in
  its own docstrings: `actor_refs()` — *"`Actors[0]` is always the `LevelInfo`"* — and
  `native/level_write.py`'s `write_level_body` docstring — *"actor_refs is the Actors array in ITS
  load-bearing order (index 0 = LevelInfo, 1 = Default Brush)"*.
- `uedcli/native/materialize.py:369-372` (also already-merged production code, from the
  unrelated native-materialize campaign) had **already reached the same conclusion**, for a
  different reason: *"No is_builder_brush skip: UED22 excludes Actors[1] by POSITION... Content
  trunks carry no builder brush (**0 is_builder_brush hits on UNATCO**), so the heuristic was dead
  here"* (board: `ued22-world-bsp-differs-per-ingest-verb-paste`). That comment is an independent,
  prior confirmation — from a completely different subsystem, investigating a completely different
  bug — that `is_builder_brush`'s content check already does not fire on real UNATCO content.

So: **the ground-truth mechanism is array position, `Actors[1]`, full stop.** In T3D ingest terms
(`mapimport.import_map`'s `order` list, built directly from the package's own `Actors[]` array in
file order with nulls dropped — see `actor_refs`), this is: *the second actor in the decoded
order, immediately after the `LevelInfo` singleton at position 0, is the builder brush* —
unconditionally, regardless of its `Class`, `CsgOper`, or inner model name.

## Is "no explicit `CsgOper`" alone correct?

**No — it is a proxy that happens to hold on every real trunk checked, not the actual mechanism,
and it is not what makes the identification correct.** Concretely:

- The engine's own accessor performs **no property inspection whatsoever** — see above. Whatever
  correctness "no `CsgOper`" has is coincidental, not causal.
- The **inner-model-name half is definitively wrong**, independent of the `CsgOper` question: in
  all four real, full-size Deus Ex level trunks surveyed below, **every single** `Brush` actor —
  ordinary content and the stray leftover alike — uses the plain inner model name `Model`, never
  the reserved-singleton `Brush` the current predicate requires. The half-doc-comment claim this
  predicate was built on (`normalize.py:98`, `"...editor never assigns [inner model name Brush] to
  a second actor"`) traces to `dev/docs/spikes/2026-06-23-capability-gaps-round2.md` Spike 1, which
  verified it only against a **freshly-created, uedcli-driven editor session** (`Maps/Entry.dx` +
  `MAP IMPORTADD`) — never against real, long-lived, originally-Ion-Storm-authored retail content.
  That narrow verification generalized a fact that does not hold for real game levels.
- The `CsgOper`-less half is **empirically never wrong on the actual data available** — see the
  survey below — but "never wrong in four levels" is evidence of a correlation holding on this
  corpus, not a proof that it is the mechanism, and it offers no guarantee against a future/other
  level where a real, intentionally-authored, inert `CSG_Active` brush might exist for some other
  reason (nothing rules this out — the engine does not either).

## Survey: is there a false-positive risk for "no `CsgOper` alone" on real content?

Ran `harness/survey_csgoper_less_brushes.sh` against the four real, full-actor-count Deus Ex level
trunks this repo has for the `NATIVE-MATERIALIZE.md` lockstep levels that a trunk currently exists
for (`showcase_unatcohq` = `03_NYC_UNATCOHQ`, `showcase_island` = `01_NYC_UNATCOIsland`,
`showcase_bar` = `02_NYC_Bar`, `showcase_wanchai_market` = `06_HongKong_WanChai_Market`; no
OceanLab trunk exists in this repo to check). Results (raw output: `harness/survey_output.txt`):

| Trunk | Actors | `LevelInfo0` rank | CsgOper-less `Brush` actors found | Their rank |
|---|---:|---:|---|---:|
| `showcase_unatcohq` | 1437 | 0 | **`Brush74`** (the one the owner already found) | **1**, immediately after `LevelInfo0` |
| `showcase_island` | 901 | 0 | **`Brush296`** | **1**, immediately after `LevelInfo0` |
| `showcase_bar` | 487 | 0 | *(none)* | — |
| `showcase_wanchai_market` | 2288 | 0 | *(none)* | — |

Total actors surveyed: 5113. Findings:

1. **No false positive anywhere.** In no trunk does a CsgOper-less `Brush` actor occur at any rank
   OTHER than rank 1 (immediately after `LevelInfo0`). If one existed elsewhere, a naive
   `CsgOper`-only rule would wrongly treat it as the builder brush and drop real content; that case
   was not found in ~5100 real actors across two full retail levels' worth of ordinary numbered
   brushes (hundreds of `CsgOper`-bearing `Brush` actors, e.g. `showcase_island`'s `Brush570`,
   `Brush1104`, `Brush686`, `Brush1099`, all ranked immediately after `Brush296` and all carrying an
   explicit `CsgOper`).
2. **Exactly one hit per level, always at rank 1, when one exists at all.** `showcase_unatcohq` and
   `showcase_island` each have exactly one — matching the theory precisely (rank 0 = `LevelInfo0`,
   rank 1 = the stray builder brush, rank 2+ = real numbered content brushes, all with `CsgOper`).
3. **`showcase_bar` and `showcase_wanchai_market` have none at all**, and in both, the actor
   actually AT rank 1 today is not even a `Brush` (`Toilet0` in `showcase_bar`; `Brush3675` — an
   ORDINARY `CsgOper`-bearing content brush — in `showcase_wanchai_market`). This is NOT a
   counter-example to the mechanism: these trunks may simply never have carried a stray leftover
   builder brush in their source `.dx` (an accidental save with the builder-brush widget mid-edit
   is not guaranteed on every map), or their current on-disk rank order may have drifted from the
   moment of ingest through later edits to these long-lived spike/showcase trunks (LexoRank ranks
   are stable per-actor but a trunk this old has had many `actor add`/reorder commits layered on
   top). The `mapimport.import_map` code path only ever needs to be correct at the ONE moment of
   ingest, where `order[1]` is freshly derived, in the same function call, directly from the
   package's own `Actors[]` array — not from a possibly-edited trunk's current rank order. This
   survey is a spot-check against currently-committed trunk state, not a substitute for that
   stronger, direct, single-ingest-call guarantee.

## Proposed fix (not applied here — production code untouched per this task's scope)

Replace the content-sniffing predicate with the position rule, at the one place it is cheap and
exact: `mapimport.import_map` already builds `order: list[int]` directly from the package's own
`Actors[]` array (`actor_refs()`), with `order[0]` always `LevelInfo` and, per every source above,
`order[1]` always the builder brush. `drop_editor_scratch(level)` is called immediately afterward,
on the SAME freshly-decoded level, so the position is available for free, with no re-derivation.

Concretely: `is_builder_brush(actor)` (a pure per-actor predicate, no positional context) needs to
become something that also sees the order — e.g. `is_builder_brush(level, name)` checking
`level.order and level.order[1] == name` (with `level.order[0]` already known to be `LevelInfo`),
or a level-level `builder_brush_name(level) -> str | None`. This is a real, if small, API-shape
change, because `is_builder_brush` is called from more places than `mapimport.drop_editor_scratch`
alone, and NOT all of them obviously have `level.order` sitting right there today:

- `uedcli/mapimport.py:712` (`drop_editor_scratch`) — the primary fix target; `level.order` is
  available in the same scope.
- `uedcli/normalize.py:181` (`normalize_level`, called by `verify.py`/`store_export.py` on a
  freshly-decoded/exported level for the H3 post-verify compare and offline `.dx` export) — also
  operates on a level whose `.order` reflects a fresh decode, so the same rule should generalize,
  but this needs confirming case by case.
- `uedcli/preview_native.py:122,945` and `uedcli/preview_wire.py:84` — call `is_builder_brush`
  per-actor while iterating, generally over `level.order` already, so threading position through
  should be mechanical, but is a real touch to three files, not a one-line normalize.py patch.

Per `dev/docs/architecture.md`, `normalize_level`/`is_builder_brush` are already documented as
irrelevant to any trunk that went through `level import`'s `drop_editor_scratch` (a durable trunk
should never carry a builder brush at all — confirmed independently by
`uedcli/native/materialize.py`'s own "0 is_builder_brush hits on UNATCO" comment). So the highest-
value, lowest-risk fix is `mapimport.drop_editor_scratch` alone; the other three call sites are
defensive/belt-and-suspenders and can be revisited separately once the primary ingest path is
fixed and re-verified against real content (this is exactly the kind of design-shape decision that
should go through the owner, not be bundled silently into one patch).

The inner-model-name check (`BUILDER_BRUSH_MODEL_NAME = "Brush"`) should be dropped outright, not
kept as a redundant AND clause — it is proven dead on real content (never matches, per the survey
above) and its own justifying doc comment's premise is now known false.

## Harness + regression

- `harness/survey_csgoper_less_brushes.sh` — the survey script above; re-runnable against any T3D
  trunk directory.
- `harness/survey_output.txt` — the raw run this spike's table is drawn from.
- `harness/test_builder_brush_is_position_not_content.py` — a regression, run directly with
  pytest (`.venv/bin/python -m pytest harness/test_builder_brush_is_position_not_content.py -v`),
  not part of the `uedcli` package's own test suite (this is a research spike; production code and
  its test suite are untouched per this task's scope). Uses a SYNTHETIC actor reproducing the exact
  real-world shape this spike found (`Class=Engine.Brush`, no `CsgOper=`, inner model plainly named
  `Model`) rather than the real extracted `Brush74`/`Brush296` T3D bodies — `dev/games/` is
  gitignored copyrighted Deus Ex content and must never be committed (see the repo's own
  `.gitignore`); `harness/survey_output.txt` carries the real findings (actor names, classes,
  LexoRank positions only — no geometry/texture/tag content). It pins:
  1. the CURRENT `uedcli.normalize.is_builder_brush` returns `False` on the real-shaped stray brush
     (i.e. it demonstrably MISSES it, on real-shaped data — the bug, pinned so it cannot be "fixed"
     by accident and silently declared not-a-bug later without this test also being revisited);
  2. a pure reimplementation of the POSITIONAL rule (`order[1]`, no content inspection) correctly
     identifies the stray brush and correctly does NOT misidentify an ordinary `CsgOper`-bearing
     brush ranked immediately next to it.

+++
priority = "p2"
kind = "implement"
summary = "One catalog engine over texture, class, sound and music; spec re-gating after two rounds of structural findings."
depends-on = ["native-texture-decode"]
+++

# Unified asset catalog — one engine, four kinds

**NOT ON DECK.** A 3-reviewer spec round on 2026-07-26 returned structural findings; the owner's
rulings were folded and the spec re-entered the gate at round 1, which is where it is now. The plan
is **stale and needs re-cutting** (it carries its own `RE-CUT REQUIRED` banner listing what no slice
covers yet). **Two questions in `questions/` are unanswered.** A question does not move its item — owner
ruling — so this stays in the build queue with its blockers attached and `bin/board questions`
lists them. It is startable only when both are folded out, the spec passes a round, and the plan is
re-cut and reviewed.

Plan: board item `the-unified-asset-catalog-spec-revision`.
Spec: SPLIT 2026-07-26 into [`engine`](spec.md) + `class` (board item `the-asset-catalog-class-arm-needs-four-changes`) + [`texture`](spec-texture-arm.md) + `audio` (board item `sound-corpus-remeasure`).
Decisions: [`../../../direction/asset-catalog.md`](../../../direction/asset-catalog.md) (the owner's) and
`../../../rationale/` (the agent's) — **not** `decisions.md`, which is FROZEN.

**Governing principle:** the tool **lists, reports file facts, produces pictures, and stores the
classification it is handed — it never infers meaning.** The LLM works out what an asset is and
where it is used, and hands the answer back. The one deliberate exception is texture colours,
pre-filled from that texture's own pixels and ordered by importance, so colour search works before
any classification exists. *(This reframe, owner 2026-07-25, deleted a tool-computed stock-map
usage index, a class placement histogram, derived `placeable`, AND a whole build prerequisite.)*

**Sequencing** (value-first; each slice a commit, `usage.md` updated in the same commit, no new
test skips versus baseline):
`P0` schema_cache v2 (raw default tags — gates S2 onward) → `S1` engine core →
`S2` adapters → `S3` list/show (class, sound, music) → `S4` object-ref validation *(fixes a live
bug that silently ships broken levels)* → `S5` classification store → `S6` search + ranking →
`S7` class arm (mesh decoder → `uedcli/`, `class preview`, size facts) → `S8a` texture adapter
(library-level) → `S8b` repoint the noun + delete the legacy subsystem → `S9` `.umx` title sniffer
→ `S10` lifecycle → `S11` doc sweep.

**Blocking prerequisite:** board item `native-texture-decode` **gates `S8a` only** — everything else
proceeds without it. (It is now a real board item; it used to be an untriaged inbox entry.)

**Two things the builder must NOT decide alone:** (1) `S7` measures whether the existing Rust
rasterizer can render meshes — if it can, the ~300 ms/render figure underpinning decisions 7
(never render in `list`/`search`) and 11 (single `iso` angle) is a Python artifact, and any change
goes back to the owner as a ruling, not a mid-slice judgement call;
(2) the texture identity function `sha256(w,h,RGB)` is **frozen** and pinned by a committed golden
in `S8a` — it is every tracked shard's filename, so any decode change silently re-keys and orphans
authored classifications.

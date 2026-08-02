+++
priority = "p2"
kind = "implement"
summary = "One catalog engine over texture, class, sound and music; spec re-gating after two rounds of structural findings."
depends-on = ["native-texture-decode"]
+++

# Unified asset catalog — one engine, four kinds

**OWNER RULING 2026-08-01: SPLIT (not a third re-gate).** Build the near-clean CLASS arm now
(`the-asset-catalog-class-arm-needs-four-changes`); re-spec texture identity behind its own dedicated
gate. The four texture rulings (incl. the IRREVERSIBLE identity/mask one) were folded into
`direction/asset-catalog.md` on 2026-08-02 (commit 630b6cd); the one deferred piece — re-keying across
a pixel edit — split into board item `texture-classify-rekey-and-prune`. Re-measure the sound corpus
on the composed path before speccing audio (`sound-corpus-remeasure`).

**NOT ON DECK (engine/texture/audio).** A 3-reviewer spec round on 2026-07-26 returned structural findings; the owner's
rulings were folded and the spec re-entered the gate at round 1, which is where it is now. The plan
is **stale and needs re-cutting** (it carries its own `RE-CUT REQUIRED` banner listing what no slice
covers yet). The texture arm's `questions/` blockers are cleared (four-open folded 2026-08-02, rekey
split out), so it is startable once the spec passes a round and the plan is re-cut and reviewed.

Plan: board item `the-unified-asset-catalog-spec-revision`.
Spec: SPLIT 2026-07-26 into [`engine`](spec.md) + `class` (board item `the-asset-catalog-class-arm-needs-four-changes`) + [`texture`](spec-texture-arm.md) + `audio` (board item `sound-corpus-remeasure`).
Decisions: [`../../../direction/asset-catalog.md`](../../../direction/asset-catalog.md) (the owner's) and
`../../../rationale/` (the agent's) — **not** the retired decisions ledger.

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

**Prerequisite LANDED (2026-07-27):** board item `native-texture-decode` gated `S8a` only, and it is
done — the decoder now reads P8, BC1, BC2 and BC3 natively and returns a typed result naming its
failure case. Nothing here is blocked on it any more. Two things `S8a` inherits from it: the ref-level
error cases (`unqualified-ref`, `unknown-package`, `package-unreadable`, `unknown-texture`) are
**reused verbatim** rather than re-minted, and this catalog mints only what is genuinely its own
(`ambiguous-ref`, `cache-unreadable`).

**Two things the builder must NOT decide alone:** (1) `S7` measures whether the existing Rust
rasterizer can render meshes — if it can, the ~300 ms/render figure underpinning decisions 7
(never render in `list`/`search`) and 11 (single `iso` angle) is a Python artifact, and any change
goes back to the owner as a ruling, not a mid-slice judgement call;
(2) the texture identity function `sha256(w,h,RGB)` is **frozen** and pinned by a committed golden
in `S8a` — it is every tracked shard's filename, so any decode change silently re-keys and orphans
authored classifications.

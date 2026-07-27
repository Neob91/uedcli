+++
priority = "p?"
kind = "unknown"
summary = "GROUND-TRUTH byte-parity state PINNED 2026-07-18 (corrective — `sections/82b-ground-truth-byte-diff.md`, harness `ground_truth_bytediff.py` + `ground_truth_triage.py`)"
+++

# GROUND-TRUTH byte-parity state PINNED 2026-07-18 (corrective — `sections/82b-ground-truth-byte-diff.md`, harness `ground_truth_bytediff.py` + `ground_truth_triage.py`)

Raw on-disk parity of the level
`UModel` body is **0.005 % (12 / 249,287 B)** — only `NumZones` + trailing are byte-identical. **Prior
"byte-exact" reports were NORMALIZED-oracle results, NOT on-disk bytes.** The geometry *identity* is
already close (node plane SET 1156/1156, Vectors set 26/26, Surf texture+PolyFlags multisets, build-time
node_flags `{0:1145,5:11}` all match); the bytes diverge on **serialization ORDER, the light bake, and
the render/collision aux arrays**. Triaged REAL must-fix (by leverage): (1) ~~node~~/point/vert emit ORDER +
weld — **node emit ORDER DONE 2026-07-18 (§82 §10.17): RAW positional plane match `172/1156 → 1156/1156`,
first divergence NONE — the tree was already isomorphic, a tail-relabel of the Pass-D fragments fixed the
linearization.** Remaining sub-item is the point/vert pool (2035/1684, verts 16163/10407) — the §82
§10.13-10.16 vert-pool port below; (2) lighting bake — LightMap 484/480, LightBits 49513/48015, Lights
11392/3928 (§20; FP-determinism hazard §41); (3) Zone numbering swap + Vectors order (tiny bytes, big
iZone/vNormal cascade); ~~(4) LeafHulls 3866/4028; (5) Bounds 484/0~~ **(4)+(5) DONE 2026-07-18:
faithful `FilterBound` port (`passes.rs::bsp_build_bounds`) emits both — Bounds 484/484 & LeafHulls
3866/3866 (array lengths byte-EXACT; all 308 hull plane-ref sets byte-identical; residual is
≤0.005-unit FBox float drift inherited from the not-yet-parity Point pool (pBase), see §82c);
live-verified NativeCastle renders clean (no OccludeBsp crash)**; (6) trivia: ~~prefix
FBox.IsValid byte (native 1 vs editor 0 — 1-byte fix)~~ **DONE**, NumSharedSides 2739/2728, field_0x54 Polys ref.
Triaged **"and similar" EXCLUDABLE** (session/view, same category as GUID/timestamps): prefix name-index,
NodeFlags `0x08`/`0x10` occlusion bits (masking both makes editor build-flags == native exactly), raw
object-ref index VALUES (export/import renumbering). **@Andrzej:** the two big independent blocks are the
emit-order port (in flight) and the light bake; everything else is derived or trivia.

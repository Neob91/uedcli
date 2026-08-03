# UModel::Serialize binary format (Deus Ex `.dx`, package v68–v69)

**Status: COMPLETE (2026-06-27). The `0xa8` fix is applied and the parser reads the
level `Model` byte-exact to EOF on 12/12 real Deus Ex maps** (00_Intro/Training/…,
NYC set; largest = `01_NYC_UNATCOIsland` Model189, 7.1 MB, 13 226 nodes). Every array
(Vectors/Points/Nodes/Surfs/Verts/Zones/LightMesh/lightmap-bytes/FBox/INT/Leaves/INT +
the two trailing INTs) lands exactly at `serial_offset+serial_size`. So the full
`UModel` read format is decoded and validated — and the WRITE is the inverse, using the
same TArray/ci/raw primitives, so serializing a built `Model` into a `.dx` is mechanical.
This closes the de-containerization roadmap's "Model serialization is an incomplete
second port" risk (`spikes/2026-06-27-decontainerize-uedcli/03-native-package-write.md`):
the remaining long pole is the CSG/BSP *build* (D2) that GENERATES the data, not its
(de)serialization. One open *interpretation* detail (not a parse error): `FBspVert.iVertex`
ranges above the `Points` count (max 18932 vs 13493 points on 00_Intro), so it indexes a
larger pool than the bare `Points` array — to pin for the issue-detector, not for I/O.

(Original status — now historical — was "SPIKE IN PROGRESS"; the next-steps below are
done.)

## P0 feasibility-gate verdict (2026-08-03): GO

The board item `bsp-issue-detector` gates its located tier (`level doctor --built`) on one question:
can the six arrays be parsed from a BUILT `.dx` well enough to locate build-emergent BSP issues?
Re-verified this session on the retail built maps (in a sibling worktree's gitignored `Maps/`).

**P0-a: GO.** The read parser extracts all six required arrays from a built `.dx` — Vectors,
Points, Nodes (plane + `iVertPool` + `numVertices`), Surfs (incl. `PolyFlags`), Verts
(`iVertex`/`iSide`), Leaves — populated and correct. `01_NYC_UNATCOHQ` Model99: 575 / 9701 / 5174
/ 3570 / 82375 / 2293. Node polygons reconstruct from `Nodes[].iVertPool → Verts[].iVertex →
Points[]` and lie on the node's own plane to within float precision (max deviation 0.19 uu on
UNATCOHQ; exactly 0 on the 8.6 KB `99_Endgame4` Model1). Node area, node plane, and per-surf
`PolyFlags` are all available offline. This is the same read proven byte-exact to EOF (below) and
byte-exact on the write (`2026-06-28-…`).

**P0-b1 (located T-junction): confirmed negative, as the plan expected.** Geometry reconstructs
losslessly, but the built Model no longer carries the CSG-time T-junction event: the optimizer has
already resolved it (welded → gone, or left unlinked → already a D0 `T-points` count).
Reconstruction gives exact polygons, not a way to re-derive which welds the builder skipped. So HoM
stays a D0-count row, not a D1-located row.

**Two interpretation notes (pinned by `bspspike/test_umodel_p0_gate.py`):**
- `FBspVert.iVertex` exceeds the `Points` count on large maps (14096/82375 verts on UNATCOHQ), but
  every such vert is in the UNUSED tail of the Verts pool; every vert reachable from a node's
  `iVertPool` range indexes a real Point (0% out-of-bounds across 3 maps). Harmless for
  reconstruction.
- The harness constant `PF_PORTAL = 0x0080` (used only in `report_model`'s diagnostic) is wrong —
  real UE1 `PF_Portal = 0x04000000` (`uedcli/doctor.py`); `0x0080` is `PF_FakeBackdrop`. The raw
  `poly_flags` u32 parses correctly; only the convenience constant is wrong. Filed as a board
  finding; the promotion uses `doctor.py`'s constants.

**Viable D1 (`level doctor --built`) rows:**
- Invisible walls — near-zero-area nodes (compute node poly area; needs only P0-a).
- Fall-through — built floor surf with `PF_NotSolid`/`PF_SemiSolid`/`PF_Portal` (filter
  `Surfs[].poly_flags`; needs only P0-a).
- HoM (T-junction) — NOT a new located row; stays a D0 `T-points` count.

Pinned offline by `bspspike/test_umodel_p0_gate.py` against a committed 8.6 KB golden
(`bspspike/fixtures/endgame4_model1.bin`) — no install content needed. The retail-corpus sweep
(`test_umodel_serialize.py`) needs the gitignored maps and its hardcoded `_MAPS_DIR` is absent in
this checkout (filed).

**Next step:** gate is GO — board-plan steps 2–3 (`bsp/editorlog.py` promotion, `level doctor
--rebuilt`, and the `--built` arm routing to the D1-b located analyses) are unblocked. Building the
D1-b rows is its own plan.

---

This is a durable record of binary-format findings from disassembling `Engine.dll` and probing
real map files. The working harness lives in `_scratch/bspspike/` (`umodel_parser.py`,
`pe.py`). The goal is to parse the `UModel` section of a built `.dx` to support `level doctor
--rebuilt` (D1 tier of the BSP-issue detector).

---

## What is being parsed

A `.dx` map file is an Unreal package. Deus Ex uses **package file version 68–69**: the original
shipped maps are **v68** (and `Entry.dx` is older, v61), while any map re-saved in UnrealEd 2.2
(UT99-based, package v69 — the editor uedcli drives) comes out **v69**. The `UModel::Serialize`
binary layout documented here is **identical across that v68↔v69 bump** (which is why one parser
reads both byte-exact; the version differences are header-level — generation info, etc. — not in the
Model body). Each object is serialized by its class's `Serialize` method. The level geometry lives in
a `UModel` instance named `Model0`/`Model1` etc. `UModel::Serialize` encodes the BSP nodes, surfaces,
vertices, zone properties, and six auxiliary TArrays — all the data that describes what the editor
produced at `MAP REBUILD`.

---

## Serial order of UModel::Serialize (package v68–v69, identical)

Disassembled from `Engine.dll` (image base `0x10000000`):

```
UPrimitive prefix          — 42 bytes raw (fixed-size parent class)
Vectors TArray             — ci count + count × 12 raw bytes (FVector)
Points TArray              — ci count + count × 12 raw bytes (FVector)
Nodes TArray               — ci count + count × (element format TBD; large fixed-size blocks)
Surfs TArray               — ci count + count × (see "Surf element format" below)
Verts TArray               — ci count + count × (element format TBD)
NumSharedSides (i32)       — 4 raw bytes
NumZones (i32)             — 4 raw bytes
FZoneProperties[NumZones]  — each: 1 ci + 16 raw bytes
field_0x54 (ci)            — 1 ci (serialized at address 0x10170649 in Engine.dll)
[old-surfs Preload tag]    — present in file but contributes no stream bytes (verified live)
TArray at UModel+0xa8      — see "0xa8 element format" below (CURRENTLY PARKED HERE)
TArray at UModel+0xb4      — ci count + count × ? (format not yet verified)
TArray at UModel+0xc0      — ci count + count × ? (format not yet verified)
TArray at UModel+0xcc      — ci count + count × ? (format not yet verified)
TArray at UModel+0xd8      — BSP Leaves (format not yet verified)
TArray at UModel+0xe4      — ci count + count × ? (format not yet verified)
```

**Confidence:** UPrimitive prefix, Vectors, Points, Nodes, Surfs, Verts, NumSharedSides,
NumZones, FZoneProperties, and field_0x54 are verified by running `umodel_parser.py` against
`19_FMA.dx` (Model3) and observing correct downstream counts. The six-TArray sequence starting
at `0x10170820` in Engine.dll is confirmed by disassembly. The internal format of Nodes/Verts
and the six TArrays is partially verified (see below).

---

## Key finding: `0x1010c160` reads 3 × 4 raw bytes, NOT 1 ci

The original `_skip_array_0xa8` in `umodel_parser.py` assumed the call to `0x1010c160` was a
ci/object-ref serializer (1 FCompactIndex). **It is not.**

Full disassembly of `0x1010c160` (Engine.dll) shows it calls `FArchive::Serialize` (the raw
byte read at `0x101f90a8`) **three times in sequence**:

```
; at 0x1010c160: (the element struct starts at esi)
call dword ptr [0x101f90a8]   ; FArchive::Serialize(archive, esi+0x08, 4) → element+0x08
call dword ptr [0x101f90a8]   ; FArchive::Serialize(archive, esi+0x0c, 4) → element+0x0c
call dword ptr [0x101f90a8]   ; FArchive::Serialize(archive, esi+0x10, 4) → element+0x10
```

Total: **12 raw bytes** consumed from the stream. The old parser consumed only 1 ci (~1-2
bytes), causing a mis-alignment that propagated to all downstream TArrays and produced invalid
(negative) counts.

---

## 0xa8 element format (TArray<FLightMesh> — UModel+0xa8)

Corrected format, derived from disassembling the element serializer at `0x1016f9f0` and the
TArray handler at `0x1016eff0`:

```
offset  size  how
+0x00    4    raw (direct Serialize call)
+0x08   12    raw via 0x1010c160 (+0x08, +0x0c, +0x10)
+0x1c    ci   via 0x101f90ac (FCompactIndex serializer)
+0x20    ci   via 0x101f90ac
+0x14    4    raw
+0x18    4    raw
+0x04    4    raw
```

Total: **28 bytes raw + 2 ci per element** (old, wrong: 16 raw + 3 ci).

---

## Empirical verification on 19_FMA.dx (Model3, size = 536762 bytes)

With the old (wrong) element format:
- `0xa8` count = 1082 elements — parsed (count looked plausible)
- `0xb4` count = **−3** — invalid (negative count)
- `0xc0` count = **−8** — invalid

With the corrected element format (28 raw + 2 ci):
- `0xa8` count = 1082 elements — parsed
- `0xb4` count = **144328** — valid (plausible as raw lightmap byte data)
- `0xc0` count = **1010** — valid (plausible as FBox array)

The corrected format is clearly correct. 144328 is large but reasonable for built lightmap
data in a medium-sized map.

---

## Fix needed in `umodel_parser.py`

In `_skip_array_0xa8`, replace:

```python
# WRONG: assumes 0x1010c160 is a ci serializer
_, pos = _ci(data, pos)   # (the first ci call after the 4-byte raw)
```

with:

```python
# CORRECT: 0x1010c160 reads 3 × 4 = 12 raw bytes
pos += 12
```

One-line fix. The rest of the element loop (the two `_ci` calls and three `pos += 4` calls)
is correct.

---

## What remains (next steps)

**The spike is not complete. The parser is still blocked at the 0xa8 fix** — it has not been
applied yet, and no end-to-end parse has been run.

1. **Apply the fix** — one line in `_scratch/bspspike/umodel_parser.py`.
2. **Verify end-to-end** — run the parser on `19_FMA.dx` (and at least one other map). All
   six TArrays plus Leaves must be parsed cleanly with sane counts; the sanity checks in
   `sanity_check()` must pass.
3. **Verify the formats of the remaining TArrays** (0xb4, 0xc0, 0xcc, Leaves at 0xd8, 0xe4)
   — their element formats have not been verified by disassembly yet. They may have further
   format bugs.
4. **Write a go/no-go spike conclusion** — record whether the parser successfully handles
   real built maps and whether D1 (located-issue tier of `level doctor`) is feasible.

Once the spike is complete, the result feeds back into `board/to-build/` item #7.

---

## Tooling notes

The harness is committed in [`bspspike/`](bspspike/) alongside this document.

- **`bspspike/pe.py`** — `capstone` + `pefile` disassembly harness for `Engine.dll`. Image base
  `0x10000000`. Run with `python pe.py` after `pip install capstone pefile`.
- **`bspspike/umodel_parser.py`** — the in-progress `UModel` stream parser (the main artifact).
  **Note:** `_skip_array_0xa8` still contains the old buggy format — apply the one-line fix
  documented above before running it against a built `.dx`.
- **`bspspike/bsp_csg.py`, `bsp_port.py`, `bsp_editorlog.py`** — early BSP-port and D0 work.
- **Test file:** `19_FMA.dx` (one of the Deus Ex retail maps; in the gitignored install content).
- **Engine.dll key addresses:**
  - `0x1016eff0` — TArray handler for UModel+0xa8
  - `0x1016f9f0` — element serializer for 0xa8 elements
  - `0x1010c160` — reads 3 × 4 raw bytes (NOT a ci serializer)
  - `0x101f90ac` — `FCompactIndex` serializer (ci)
  - `0x101f90a8` — `FArchive::Serialize` vtable slot (raw byte read)
  - `0x10170649` — field_0x54 ci serialize (zone loop exit)
  - `0x10170820` — start of the six-TArray sequence

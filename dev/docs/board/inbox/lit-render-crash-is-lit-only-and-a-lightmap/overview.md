+++
priority = "p1"
kind = "unknown"
summary = "LIT-RENDER crash is LIT-ONLY and a LIGHTMAP-EMISSION bug — NOT Model completeness (side pool / Bounds RULED OUT)"
+++

# LIT-RENDER crash is LIT-ONLY and a LIGHTMAP-EMISSION bug — NOT Model completeness (side pool / Bounds RULED OUT)

p1. **Premise corrected 2026-07-16 (spike section 20 §12).** The earlier
framing ("needs node Bounds and/or the `bspOptGeom` side pool") is **WRONG**: a full `Render.dll`
disasm of the lit path proved it dereferences NEITHER `iSide`/`NumSharedSides` NOR node Bounds — so do
NOT port them for lighting (the `c0`/`cc` writer arrays are irrelevant here too). And a live re-test
shows the crash is **LIT-ONLY**: `NativeDark` (all-dark records, `iLightActors=-1`) now renders CLEAN
(0 singularities, player possessed) — the old "NativeDark crashes" was stale (pre-collision-fix). Only
LIT records (`iLightActors>=0`) crash `SetupNormalSurface`, so the fault is in the light-application
path (light loop `0x10b070c6` → `AddLight 0x10b08b30`, bit-plane ptr `LightBits+DataOffset+i*bytesPerLight`).
Our lightmap arrays are otherwise well-formed (grid matches `DXOnly` exactly; runs NULL-terminated;
offsets in-bounds; basis non-degenerate). **CORRECTED ROOT (live binary-patch capture, 2026-07-16 —
see spike `sections/20-lighting-bake.md` §13; this SUPERSEDES the earlier "bad `Model.Lights` pointer /
AV at `AddLight`" conclusion):** captured the runtime value live and it is **NOT** the `Model.Lights`
pointer — `Model.Lights.Data[iLightActors] = 0x07c9ce80`, a **valid MAPPED `AActor*`**. And **neutering
`AddLight`'s `[ebx+0x1e0]` read (binary-patched to store-and-return) does NOT stop the crash**: NativeLit
still logs `Anomalous singularity ... SetupNormalSurface → FLightManager::SetupForSurf`. So the fault is
a **runtime FP singularity in `SetupForSurf`** — `Render.dll 0x10b07696 fdiv st(1)` divides by
`|V|²`, `V=(0,0,0)` for one lumel ⇒ divide-by-zero. `V = M·g` (per-surface `FCoords` matrix `M`
`[ebp-0xe4]`, built from the surf lightmap basis + `Pan`/`UScale`/`VScale` + lumel grid). **Tested & ruled
out this session:** light position/symmetry (off-centre `(137,89,96)` light still crashes, 239
singularities); `Model.Lights`/`LightBits`/serialization/geometry (all byte-exact, §12). **THE OPEN STEP:
find which emitted per-surface lightmap input makes `M` degenerate for our surfaces but not for a real
lit map's — (i) capture `M`/`g` live at `0x10b07453` with the same store-to-scratch patch (9 floats →
`0x10b5c800..`, read back), OR (ii) field-diff our `iLA>=0` `FLightMapIndex`+surf basis vs `Entry.dx`'s 3
genuine lit records (`iLA` 22/27/32 — `DXOnly` is all-dark, NOT a valid control). Harness committed:
`harness/{game_capture_patch.py,game_capture2_travel.py,boot_watch_singularities.sh}`; capture/RE recipe
in `engine-internals/gotchas.md` §4 (INT3 is DEAD for `__except`-guarded faults; store-to-scratch works).
`game-entrypoint.sh` now RELAUNCHES until the link binds (beat the boot-deadlock). Fix is bake/emission
side, NEVER a BSP port. `run_materialize_native` stays `no_light=True` until it lands.
**FLAG for Andrzej:** this render crash has consumed ~2 context windows; the bake is byte-correct and
maps LOAD fine, but the FP-singularity fix needs deeper live RE. Decide: keep drilling (capture `M`
live / diff vs `Entry`), or ship lighting-bake-correct + render-off (`no_light=True`) and defer the
render fix as a known engine-render quirk? (My lean: one more capture pass at `M`/`g` — it's now a
narrow, well-instrumented target — then reassess.)

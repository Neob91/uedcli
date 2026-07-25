# Engine-runtime & RE-workflow gotchas

Hard-won traps from reverse-engineering + live-debugging the **Deus Ex game runtime** headless
under wine. **Append as you go.** Each entry: the trap, then how to avoid it. Confidence: ✅
live-verified this repo · 🔬 disasm/observed · 📖 inferred.

See [`README.md`](README.md) for how this relates to `unrealed/` (the *editor*). Dates are UTC.

---

## 1. Which DLLs, which base addresses (✅)

Two totally separate substrates — do **not** mix their addresses:

| Binary | Role | Path | Image base |
|---|---|---|---|
| Game `Render.dll` | **software renderer** (the one headless uses) | `DX/System/Render.dll` | `0x10b00000` |
| Game `Engine.dll` | game engine (collision, load, `UModel::Serialize`) | `DX/System/Engine.dll` | `0x10300000` |
| Editor `Engine.dll`/`Editor.dll` | **UnrealEd** (CSG, `LIGHT APPLY` bake) | `uned/UED22/*.dll` | `0x10000000` |

The game's `Render.dll` (software renderer) has **no editor counterpart**. When a fact is about
*rendering* a `.dx` in the game, it's `Render.dll @ 0x10b00000`. When it's about *building*
geometry/lighting, it's the editor DLLs @ `0x10000000`. `System.bak/`, `Ued2/`, `SystemOk/`,
`UED22/` under `DX/` are alternate copies — use `DX/System/` for the *game* runtime.

## 2. Disassembly harness (✅)

- Use `dev/docs/spikes/2026-07-15-native-materialize/harness/dishere.py`:
  `python dishere.py <dll-path> <start_va_hex> <len_hex>` → prints `addr: mnemonic op_str`.
  (For these DLLs, on-disk file offset == RVA, so reads are trivial.) `pe.py` has
  `pe.read_at_va`, `pe.image_base`, `pe.disasm`, `pe.exports`.
- ⚠️ **`adis.py` has an argv bug** and silently prints nothing — prefer `dishere.py`.
- **Finding a big function by its struct-offset refs:** scan `.text` for a window that
  references *many* distinct struct offsets (e.g. a `UModel::Serialize` touches Nodes `+0x58`,
  Verts `+0x68`, … Lights `+0xe4`). **Two traps:**
  1. A naive `'+ 0xNN]'` string match also catches **`[esp+0xNN]` / `[ebp+0xNN]` stack locals** —
     exclude `esp`/`ebp` to keep only real struct-field derefs.
  2. The **destructor / `Empty()`** also references *every* array offset. Distinguish it from
     `Serialize` by the **vtable store at the top** (`mov dword ptr [esi], <vtable>` = a ctor/dtor
     frame, not a serializer).

## 3. Wine live-debugging: `WINEDEBUG=+seh` (✅ — cost hours)

- `WINEDEBUG=+seh` logs first-chance exceptions. **THE filter gotcha:** wine writes
  `…dispatch_exception code=c0000005 flags=0 addr=<VA> ip=<VA>` — it uses **`ip=`, not `eip=`**,
  and the code token is **`code=c0000005`**. A filter matching only `c0000005|eip=` **catches
  `__regs_MSVCRT__setjmp` noise (which DOES contain `eip=`) and MISSES the real exception.** This
  sent a whole investigation down a wrong "FP singularity" path. **Use a broad filter:**
  `grep -iE 'code=c[0-9]|first chance|ip=0*10b0|addr=0*10b0'` (and `grep -v setjmp`).
- `+seh` is verbose → **cap it** (`| head -300`) and filter to the exception lines only; **host
  disk is chronically ~96% full** (see §5).
- **"Anomalous singularity in URender::DrawWorld" is a CATCH-ALL, not a math singularity.** ✅
  `URender::DrawWorld` wraps `DrawFrame` in `__try/__except`; the filter (logs the string, xref at
  `Render.dll 0x10b1ced0`) catches **any** SEH in the subtree and prints that one label. The
  `Critical: <fn>` lines above it are the **guard stack** at the fault — that's where it actually
  faulted. Most of the time it's a plain **`c0000005` access violation**, not FP. Confirm the
  real code with `+seh` (per above), don't infer from the message.

## 4. Reading a register at a game fault — the WORKING recipe + all the dead ends (✅🔬, 2026-07-16)

Reading a CPU register at a `Render.dll` fault in the headless game is HARD. What was learned, in
order of usefulness:

- **PREREQUISITE: `--cap-add=SYS_PTRACE`.** The default game container has `CapEff` **without**
  `SYS_PTRACE(19)` (check: `python3 -c "print(bool(int(open('/proc/self/status').read().split('CapEff:')[1].split()[0],16)>>19&1))"`),
  and `/proc/sys/kernel/yama/ptrace_scope=1`. Without this cap, `gdb` is absent AND `winedbg`/ptrace
  are **silent no-ops**. Add `--cap-add=SYS_PTRACE` to the `docker run` in
  `Tools/uplayctl/game/session-run.sh` (temp instrumentation — REVERT after; it was reverted).
- **`gdb` is absent. `winedbg` `attach` is BROKEN here** — `info process` works (lists DeusEx.exe's
  winpid), but `attach <winpid>; …; info reg` produces **zero output** even with SYS_PTRACE + stderr
  capture + stdin held open. Don't sink time into `winedbg attach`.
- **The guest AV does NOT surface as a Linux SIGSEGV.** `PTRACE_SEIZE`-ing all threads and running
  caught **zero signals** during a 60/s crash-loop — so you can't catch the fault by waiting for
  SIGSEGV. (Wine handles the guest page fault internally without a tracer-visible signal.)
- **INT3 breakpoint does NOT work for a fault inside an `__except` guard (❌ 2026-07-16).** Planting
  `0xCC` at the fault VA via `/proc/<pid>/mem` and `PTRACE_SEIZE`-ing all threads yielded **zero
  SIGTRAPs** even though the plant froze rendering — wine's structured-exception dispatch around
  `URender::DrawWorld` catches the guest `INT3` (as `EXCEPTION_BREAKPOINT`) **before** the host tracer
  sees a SIGTRAP. Any `Render.dll` render fault is inside that `__except` (it's why the game logs
  `Anomalous singularity` and survives), so INT3-via-ptrace is a dead end there.
  (`game_int3_catch_ebx.py` is kept as the harness but does NOT land hits for this class of fault.)
- **What ACTUALLY WORKS: binary-patch the faulting instruction to STORE a register to a scratch
  global, then early-return before the fault (✅ 2026-07-16).** No guest exception is raised (so
  `__except` never fires), and you read the captured value straight out of process memory. Recipe:
  1. Pick a scratch dword in the DLL's **writable `.data` BSS tail** (Render.dll `.data` VA
     `0x10b30000`, vsize `0x2cafc` ⇒ e.g. `0x10b5c800`); verify it reads 0.
  2. `PTRACE_SEIZE`+`PTRACE_INTERRUPT` every thread, then overwrite the faulting instruction with
     `mov [scratch], <reg>` (`89 1D <addr LE>` for `ebx`, 6 B) and neutralize the following
     dependent read (e.g. replace `test al,al` `84 C0` with `xor al,al` `30 C0` so the next `je`
     returns before a 2nd faulting deref). `/proc/mem` writes to `.text` bypass the r-x perms.
  3. `PTRACE_CONT`+`PTRACE_DETACH`; let the render run; read the scratch dword back via `/proc/mem`.
     Probe the captured pointer with a `read()` at `val+offset` (unmapped ⇒ bad pointer).
  Helper: **`harness/game_capture_patch.py`** + **`game_capture2_travel.py`** (patch on the clean boot
  map, then `TravelToLevel <litmap>` so the patched — non-faulting — code runs on the target map).
- **Burst timing / how to make the target render at all.** The headless game renders only a **short
  burst** after travel, then **double-faults** (`Exit: Double fault in object ShutdownAfterError`) and
  the console link dies — so you can't drive frames post-crash. Patch/attach **while on the clean boot
  map** (`DX_MAP=DX`, link alive), THEN travel to the lit map. Detect the crash by
  `grep -c "Anomalous singularity" DeusEx.log` (no screenshot needed). `boot_watch_singularities.sh`
  reproduces reliably in ~90 s.
- **Two pid/readiness gotchas:** (1) `pgrep -f DeusEx.exe` early in boot returns a **launcher** pid
  where Render.dll isn't mapped (reading `0x10b08b4a` → `EIO`); select the pid whose byte at the fault
  VA reads `0x8a`. (2) That render byte `0x8a` appears **before** `UPlayCtlLink` binds `:7777` — gate
  any console-travel capture on `:7777` listening too, or `create_connection` throws `ConnectionRefused`.

## 5. Boot & console-link infra (✅)

- **Boots are ~50% FLAKY due to an intermittent wine boot-DEADLOCK** (the root cause of "nl=0 /
  never reached the map" boots). `DeusEx.exe` wedges in early init with its **main thread blocked on
  `pipe_read` on the wineserver, using ZERO CPU** (`/proc/<pid>/wchan` = `pipe_read`; `utime+stime`
  stays 0). No log, no window, forever. The entrypoint has a partial fix (kill stale wineserver +
  esync/fsync) but it still fires intermittently. **Detect it FAST and retry** — don't wait 150s on a
  dead boot:
  - **Screenshot the Xvfb root every ~minute** (`docker exec <cn> sh -c 'DISPLAY=:99 import -window
    root /tmp/s.png'` → `docker cp` out): a live boot shows the DeusEx window; a deadlock shows only
    the fluxbox desktop (+ a harmless `fbsetbg` wallpaper `xmessage`). **No game window in ~1 min ⇒
    deadlocked ⇒ `docker rm -f` and reboot.**
  - Cheaper programmatic check: `wc -c < /work/dx/System/DeusEx.log` — a deadlocked boot leaves it
    **empty** (0 bytes) because the game never gets far enough to open its log; a live boot fills it
    within ~60–90s. Loop: boot → wait 90s → if log empty, kill+retry; else proceed.
- **`Tools/uplayctl/game/game-entrypoint.sh` (~line 66)** is the wine launch line. To inject
  `WINEDEBUG=…`, edit it and `bin/uplayctl session start` (which **rebuilds the image** from
  source, picking up the edit). **REVERT the entrypoint after** — it's a tracked file.
- **Boot sequence:** the game always boots to the custom **`DX.dx`** first (renders clean), *then*
  the entrypoint travels to `DX_MAP` via a console `open`. The console link **self-establishes**
  from `DeusEx.ini`'s `Console=` — **a manual `wine DeusEx.exe` relaunch does NOT re-establish the
  link** (it needs the entrypoint's whole `DeusEx.ini`/`User.ini` orchestration). So you can't just
  `pkill DeusEx; wine DeusEx.exe` to re-capture with different flags and expect the TCP link.
- **`uplayctl send "open <map>"` TIMES OUT when the game is crash-looping** (the wedged renderer
  starves the console thread). The command still *dispatches* (the travel happens) — don't read the
  `TimeoutError` as failure; check the log.
- **Hot-traveling a crash-looping game can hard-kill it** — `open`-ing another map on a game that's
  per-frame-faulting produced `Exit: Double fault in object ShutdownAfterError`. For a clean per-map
  test, **boot a fresh session** rather than hot-travel.
- **The log is BUFFERED** (see the `game-boot-log-buffered-poll-7777` memory): an empty
  `DeusEx.log` ≠ stuck boot. Readiness = **port 7777 up**, not log content.
- **Disk hygiene:** host `/` sits at ~96%. Between tests: `docker rm -f` the game containers,
  `docker container prune -f`, `docker image prune -f` (**never `-a`** — it deletes the `dx-lum-*`
  base images; rebuild is slow). ~20 GB free is enough for a boot or two, not many.

## 6. Verified game-runtime engine facts (🔬 `Render.dll` @ `0x10b00000`)

From the native-materialize lit-render investigation (spike `sections/20-lighting-bake.md` §12):

- **The software renderer RE-RAYTRACES lightmaps every frame — it does NOT read the baked
  `Model.LightBits`.** It computes `bytesPerLight = ceil(USize/8)*VSize` (`0x10b06ea2..0x10b06ed5`)
  and advances a bit-plane pointer it **never reads back**. So the on-disk `LightBits` *format* is
  irrelevant to *render* (it matters only if you ever feed a hardware path). This is *why* a
  lightmapped surface faults **per-frame** (it re-lights every frame).
- **The lit path never reads geometry-completeness fields.** `FLightManager::SetupForSurf`
  (`0x10b06c90`), `AddLight` (`0x10b08b30`), `Illuminate` (`0x10b05fa0`) read only the surf's
  texture basis (`Surf.{pBase,vNormal,vTextureU,vTextureV}` → `Points`/`Vectors`) and
  `Surf.iLightMap` → `Model.{LightMap, LightBits, Lights}`. They do **not** touch the `bspOptGeom`
  side pool (`iSide`/`NumSharedSides`) or node `Bounds` (`iCollisionBound`/`iRenderBound`). Do not
  port those "for lighting."
- **`Model` in-memory field offsets:** `Vectors +0x78`, `Points +0x88`, `Nodes +0x58`,
  `Surfs +0x98`, `Verts +0x68`, `LightMap +0xa8` (`Num +0xac`), `LightBits +0xb4`, `Bounds +0xc0`,
  `LeafHulls +0xcc`, `Lights +0xe4`. `FBspSurf.iLightMap` at surf `+0x18`. `FLightMapIndex` stride
  `0x28`, with `iLightActors` at `+0x04`, `USize`/`VSize` at `+0x1c`/`+0x20`.
- **A DARK lightmap record (`iLightActors=-1`) skips the whole light loop → renders fine.** Also, a
  **far-away light** produces dark records AND is excluded from the per-surface relevant-light list,
  so it is **never processed** — meaning a "NativeDark" repro built with a far light does **not**
  exercise `AddLight` at all. Don't treat "NativeDark renders" as proof that `AddLight(yourLight)`
  works — build the dark repro with an *in-range* light whose records you force dark another way.
- **Collision (`Engine.dll @ 0x10300000`):** `UModel::LineCheck`/`PointCheck` gate solidity on
  `FBspNode::IsCsg()` (`NodeFlags`/`NumVertices`), NOT on `iLeaf`; they read the FRONT child from
  `iChild[1]` (serial `+0x24`), BACK from `iChild[0]` (`+0x20`). `iZone[side]` is a **BYTE** at
  node `+0x34` (stride 1), `iLeaf[side]` an **i32** at `+0x38` (stride 4). (Full detail:
  `sections/60-leaf-solidity-collision.md`.)

## 7. Comparing a synthesized `.dx` to a real one (✅)

- The offline parser `native/umodel.py` is **lossy on a full re-serialize** (it drops the
  UPrimitive-prefix bbox and the `Bounds`/`LeafHulls` `c0`/`cc` arrays), so a
  parse→re-serialize→byte-compare of a *real* Model will NOT be byte-exact — that's a parser
  limitation, not a real difference. Compare **field-by-field** (counts, refs, flags) instead.
- **Good control maps:** `DX/Maps/DX.dx` / `Entry.dx` are small **lit** real maps (26 surfs, 3 lit
  records, 37 `Model.Lights`) that render clean headless — the ideal A/B target for a synthesized
  lit map. `DXOnly.dx` is a real **dark**-record single box (renders, but doesn't exercise the lit
  light loop). Decode any of them with `native/pkg_write.parse_package` + `native/umodel`.

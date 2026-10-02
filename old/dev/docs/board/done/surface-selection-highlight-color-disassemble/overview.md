+++
priority = "p1"
kind = "implement"
summary = "DONE -- UED22 draws a selected surface as a flat RGB(0,127,255) screen-space stipple (1 px in 16), no blend; replicated in SelectionHighlight.tsx and live-pixel-verified"
+++

# Surface (poly) selection highlight color -- RE and replicate

Closed 2026-09-18. Full finding, with the instruction traces and the live measurements:
`GUI-PARITY.md` "Surface selection highlight". Harness: the `harness-*.py` files beside this one
(kept flat because the board schema allows an item no subdirectory but `questions/`, and
`dev/docs/spikes/` needs the owner's yes per edit).

What it turned out to be, in one paragraph. UED22's four viewports are all pinned to
`SoftDrv.SoftwareRenderDevice` (`uned/UED22/UnrealEd.ini`), so the surface draw call is
`softdrv.dll`'s `USoftwareRenderDevice::DrawComplexSurface` (RVA `0xc3a0`). Its tail, gated on
`GIsEditor` and `PolyFlags & PF_Selected` (`0x02000000`, confirmed via `Editor.dll`'s
`polySelectReverse`'s `xor eax, 0x2000000`), loads the bytes `00 7f ff` and then re-walks the
surface's own span buffer doing a RAW framebuffer store of that value -- every second scanline, every
eighth pixel, phase alternating 0/4 per drawn row. So: flat RGB(0,127,255), one pixel in sixteen, no
blend of any kind, anchored to absolute screen coordinates. Channel order is settled by the 32bpp
path's own repack (`byte0<<16 | byte1<<8 | byte2` into a `0x00RRGGBB` surface), because byte-swapped
it would read orange. True of SoftDrv, which is what the editor runs; `OpenGLDrv`/`D3D9Drv` each do
something different (a ~50% blue blend, no stipple).

Replaced `SelectionHighlight.tsx`'s invented additive-white-0.25 overlay with that technique (a
fragment-shader stipple discard on the standard `MeshBasicMaterial` program, so masked-group
alpha clipping still works). One documented departure: the lattice is evaluated in CSS pixels rather
than device pixels, so a hi-DPI canvas shows UED22's own on-screen dot density instead of a
DPR-shrunk one.

Live-verified on real rendered pixels (headless Chromium, real WebGL, `showcase_bar` rebuilt, real
clicks): 99.5% / 97.7% of every changed pixel is exactly RGB(0,127,255), row gaps are 2 with no
exceptions, dot gaps are 8, and the first-dot phase is 0/4 split cleanly by drawn-row parity. A
review pass added deselect (0 changed pixels), two-surfaces-at-once, DPR 2, and a masked surface
(clipped to the texture's shape, not tinted by it). A live UED22 screenshot could not be taken in
that session -- the host's rootless docker daemon shares no filesystem with it, so the editor
container cannot start at all.

## Re-running the harness

`harness-exports.py <dll> [regex]` prints export RVAs; `harness-imports.py <dll> [va]` says which
import an IAT slot resolves to (this is what pinned `0x10030114` to `Core.dll`'s `GIsEditor`). For
the code itself, `objdump -d -M intel uned/UED22/softdrv.dll` and grep the VA.

`harness-stipple-verify.py <out-dir> [x y ...]` diffs the perspective pane's WebGL drawing buffer
before and after a real click on a surface and reports the changed pixels' colour and lattice. It
needs a backend whose build is SOLVED (`uedcli --project <games> serve <level> --port N`, then
`POST /api/level/<level>/rebuild` -- the textured mesh does not exist until then) and a vite dev
server proxying to it. It reads pixels via `canvas.toDataURL()` with `preserveDrawingBuffer` forced
on by an init script, never `page.screenshot()`: the app's canvases sit at fractional CSS offsets,
so the compositor resamples each one-pixel dot across two output pixels at ~50% and no exact colour
survives. `pixels-selected-zoom16x.png` is a magnified crop of the real dots.

`harness-chromium-stubs.py` exists because headless Chromium would not start on that host at all: it
hard-links `libatk-1.0`/`libatk-bridge-2.0`/`libatspi` through `DT_NEEDED` even though headless never
uses accessibility, and none are installed. The script generates no-op stubs exporting exactly the 89
symbols the binary references; the other missing libraries were copied out of the
`ued-x86-runtime:latest` image, which shares this host's Debian 12 base.

`harness-ued22-probe.py` drives a real UED22 container for the same comparison. It has never run --
see the docker note above. Kept for a host where bind mounts work.

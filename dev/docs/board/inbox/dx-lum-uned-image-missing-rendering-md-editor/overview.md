+++
priority = "p2"
kind = "debug"
summary = "dx-lum-uned:latest never baked rendering.md's editor-render fixes, so the GUI editor GPFs on any window-creating op; a real editor pixel render is unobtainable here."
+++

# dx-lum-uned image missing rendering.md's editor-render fixes; GUI GPFs

`dev/docs/unrealed/rendering.md` documents two "permanent fixes" for headless editor rendering:
drop `-log` from `entrypoint.sh`, and set `X=2000/Y=2000` on every `[* Browser]` ini section (plus
`Device=SoftDrv.SoftwareRenderDevice` on all viewports). **Neither was baked into
`dx-lum-uned:latest`:** the entrypoint still passes `-log` and the browser inis still sit at `X=516`.

Consequence (verified 2026-08-03, via the proper `ensure_editor` + `CAMERA OPEN REN=6` harness, NOT
a bare launch): the editor GPFs in `SyntaxHighlighting::AddQuote <- WCodeFrame::OnCreate <- WM_CREATE`
on **any** window-creating op — reproduced four ways: first console command (log window), boot without
`-log`, and browser/viewport init when a map is loaded as a launch arg. So a real editor **pixel**
render is unobtainable on this arm64/wine/Mesa host as shipped. The headless `Editor.ExecCommandlet`
path (no GUI, no `WCodeFrame`) works fine — that's how the byte-exact texture-frame parity was
obtained. GPF dialog was captured live via `import -window`.

Second reproduction (2026-08-05, `spikes/2026-08-04-sheer-bake-byte-parity`): the sheer-parity harness
hit the identical GPF on the first console command with **pids at 157/2048** (the old 512 cap lifted
to 2048, mem to 16 GiB) — so it is **not** resource-related, disproving that spike's earlier PID-cap
diagnosis. Relaunching **without `-log`** reproduces the same GPF, so the `WCodeFrame` is built at
startup regardless of the Log Window.

Fix candidate: rebuild the image with rendering.md's fixes actually baked in, then retry the harness.
UNTESTED whether that clears the GPF — the `SyntaxHighlighting`/`WCodeFrame` fault may be deeper in
this image's wine/Mesa build than the ini fixes reach. Either way, rendering.md's "permanent fix"
claims describe a setup the shipped image does not match — reconcile the doc and the image.

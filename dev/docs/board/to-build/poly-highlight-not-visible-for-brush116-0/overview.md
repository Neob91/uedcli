+++
priority = "p1"
kind = "debug"
summary = "selected poly highlight never shows for masked-texture surfaces (Brush100:0, Brush106:0, Brush111:0)"
+++

# poly highlight not visible for masked surfaces (Brush100:0 / Brush106:0 / Brush111:0)

**Reopened.** The originally-reported brushes (`Brush116`/`Brush111`, item first filed as
`poly-highlight-not-visible-for-brush116-0`) were misidentified by the owner — the real repro,
confirmed live, is **`Brush100:0`, `Brush106:0`, `Brush111:0`**. The landed fix (bumping
`SelectionHighlight.tsx`'s `polygonOffsetUnits` from 1 to 4, commit on `staging`) does not fix this —
the owner confirmed live it still doesn't show, and headless-browser verification this session
confirms the same for these three specific polys.

## The real lead: all three share `masked: true` and the same texture

Live scene data (`/api/level/showcase_bar/scene`) for these three polys:
```
Brush100 masked=True blend=opaque two_sided=False tex_index=29 flags=12582952
Brush106 masked=True blend=opaque two_sided=False tex_index=29 flags=12582952
Brush111 masked=True blend=opaque two_sided=False tex_index=29 flags=12582952
```
All three: same texture, same masked flag, same blend mode. This is very likely a
**masked-surface-specific bug** in the highlight overlay, not a depth-fighting/polygonOffset issue —
the landed fix doesn't touch masking at all and doesn't help.

`SelectionHighlight.tsx`'s own doc comment already describes special handling for a masked group:
the additive-white overlay samples the base material's own `map`/`alphaTest` so the highlight is
"clipped to the actual visible (alpha-tested) shape." That's the code path to scrutinize — something
in how the overlay samples/tests alpha for THIS texture (`tex_index` 29) likely fails the alpha test
everywhere, or uses the wrong UVs, so the highlight silently draws nothing.

## What's already confirmed (this session, via a real headless-Chromium harness — see below)

- Selecting these polys correctly updates React state and the Inspector (data plumbing is fine).
- The `SurfaceSelectionHighlight` mesh DOES mount, with the correct triangle count and correct
  real-world position for each poly (confirmed via direct Three.js object inspection, not guesswork).
- Forcing the material to `THREE.DoubleSide` live in the browser made no visual difference — this is
  NOT a backface-culling/viewing-angle issue.
- A real mouse click on a DIFFERENT (unmasked) poly (`Brush7:2`) DOES show a highlight correctly —
  the general mechanism works; the failure is specific to something about these three (very likely
  the shared masked texture).
- Caveat: automated selection triggered by directly calling the app's React callbacks (bypassing a
  real click) did not reliably reproduce a visible highlight even for a plain unmasked control poly
  in this session's test harness — so treat "zero pixels changed" from that specific automation path
  with some caution. The masked/tex_index-29 correlation across all three reported brushes, and the
  contrast with a real click working on an unmasked poly, are the trustworthy signals here.

## Verification tooling now available (use it — don't ship unverified again)

A real headless Chromium now works in this environment (previously blocked: no root/apt, ~40 missing
shared libraries). Setup + reusable scripts:
- Extracted `.deb` libraries (no root needed — `dpkg -x` into a plain directory + `LD_LIBRARY_PATH`):
  `/home/agent/.claude/jobs/08ed91b4/tmp/debs/extracted/{usr/lib,lib}/x86_64-linux-gnu/`
- Chromium binary: `/home/agent/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome` (the FULL
  chrome binary, not `chromium_headless_shell` — the shell variant is missing libglib and can't be
  fixed the same way). Launch via Python's `playwright.sync_api` with `executable_path` set to that
  binary and `LD_LIBRARY_PATH` including both extracted lib dirs.
- Example scripts (real click + pixel diff, and the React-fiber introspection technique for reading
  live Three.js object state): `/home/agent/.claude/jobs/08ed91b4/tmp/browser_verify_tools/`.
- **Prefer real synthetic mouse clicks/keyboard (`page.mouse.click`, `page.keyboard.press`) over
  calling React callbacks directly via fiber introspection** — this session found the latter doesn't
  reliably reproduce visible rendering even for known-working cases, for reasons not fully understood.
  A real click on the org-panel-selected, then-zoomed target (search box -> org panel button -> `F`
  to frame -> scroll-wheel zoom -> click) is slower to set up but trustworthy.
- The live `staging` preview (this session's setup, still running): backend `uedcli serve
  showcase_bar --project /workspace/uedcli/dev/games`, frontend `web/`'s vite dev server, both in
  `.claude/worktrees/staging-merge`.

## Repro

1. Serve `showcase_bar` (or any level — not level-specific, since all 3 examples are in this one).
2. Select poly `Brush100:0`, `Brush106:0`, or `Brush111:0` (a masked wall decal, `tex_index` 29).
3. Inspector shows it selected; viewport shows no highlight.
4. Contrast: select an unmasked poly (e.g. `Brush7:2`) — highlight shows correctly.

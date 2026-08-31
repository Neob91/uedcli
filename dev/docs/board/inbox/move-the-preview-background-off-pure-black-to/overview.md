+++
priority = "p2"
kind = "implement"
summary = "Preview background becomes #404040; CSG palette re-tune still outstanding."
+++

# Move the preview background off pure black to `#404040`

**Owner ruling, 2026-08-30.** `preview.py`'s `BG` goes from `0` (pure black) to `#404040`. This
supersedes the 2026-08-02 ruling that pinned it to black to match UnrealEd's viewport.

Flipping the constant is one line. The problem is everything tuned against it — the source says so
outright: "Colours (RGB), tuned for the BLACK background (see `BG`)", and the tint palette was "chosen
for contrast on the black bg (BG=0)".

**The facing cue partially inverts.** The CSG palette is `(front, back)` pairs where back = obscured =
dimmer, so the front/back cue reads as brighter/dimmer. At `BG = #404040` (luminance 64.0) two back
shades fall *below the background*:

| CSG op | front | back | vs bg 64.0 |
|---|---:|---:|---|
| `add` | 112.0 | **56.2** | below |
| `mover` | 110.6 | **56.0** | below |
| `semisolid` | 141.6 | 73.8 | +9.8 |
| `nonsolid` | 160.1 | 80.1 | +16.1 |
| `subtract` | 172.3 | 91.3 | +27.3 |

(Rec. 709 luminance.) So an obscured additive or mover face becomes a darker-than-background smudge
rather than a dimmer version of its front colour, and `semisolid`'s back is close behind.

**Also needs re-checking against the new background:**

- `_fade_dimmed` fades toward `BG`, so `--focus` de-emphasis now fades toward mid-grey, not black.
  `_DIM_FILL_ALPHA = 0.35` was picked by the owner from a ladder of real renders against black
  (`dev/docs/spikes/2026-07-27-preview-focus-dim/`, `dev/docs/rationale/preview.md`) — that measurement
  no longer describes what 0.35 looks like, and the rationale doc's reasoning has to be revisited.
- The neutral greys `BACK` (120), `DIVIDER` (130), `CAPTION` (170), `MARKER` (185) all still sit above
  the new bg, but their *separation* from it shrinks by 64 levels.
- The per-actor categorical tints, chosen for contrast on black.
- `dev/docs/unrealed/rendering.md` and `dev/docs/rationale/preview.md` both explain the palette in terms
  of the black background.

**Decided (owner, 2026-08-30): change it now, no ladder.** `BG = 64` (`#404040`). The CSG palette is
NOT re-tuned in the same change — see the caveat below — so this item ships the background move and
the grid colours that depend on it, and the palette re-tune is what remains open.

**Known consequence, accepted:** `add` and `mover` obscured shades (56.2 / 56.0) now sit just *below*
the background rather than above it. The front/back facing cue still holds — a back face is still
dimmer than its front partner — but an obscured additive face now reads as darker-than-surround
instead of lighter. Judged acceptable rather than blocking; revisit with real renders.

Blocks the grid greys in `add-visual-grid-for-2d-views-in-level-actor`, which must be chosen against
the final background.

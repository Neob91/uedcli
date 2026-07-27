+++
priority = "p?"
kind = "unknown"
summary = "#12 `brush build extrude` + `brush build revolve` — SHIPPED, but the build gate's ten findings were ALL deferred, unfixed, at Andrzej's explicit instruction (2026-07-25)"
+++

# #12 `brush build extrude` + `brush build revolve` — SHIPPED, but the build gate's ten findings were ALL deferred, unfixed, at Andrzej's explicit instruction (2026-07-25)

Built in a
feature worktree over seven commits (B1 `profile.py` → B2 extrude → B3 cap tiling → B4 revolve →
B5 advisories → B6 the UU units retrofit → B7 doc sweep), each landing green, then squash-merged.
Suite 2559 passed / 13 skipped, up 100 tests with no new skips. Round 1 of the build gate (1 cold
Opus, given `CLAUDE.md` + the spec + the plan, no priming) returned **ten findings, none
structural**; Andrzej directed in-session: *"Land what you have, fix the rest in another feature
branch."* Because nothing was fixed, the artifact did not change and **round 2 never fired** —
under `CLAUDE.md` "Review gates" that is the *form* of a passed gate but not the substance, since
findings 1 and 2 are in-scope defects and the file names deferring in-scope defects to dodge round
2 as gaming the gate. Recorded as Andrzej's ruling, a legitimate disposition, so the reason lives
outside chat. The shipped **geometry** was independently verified correct in that round (1400
fuzz cases + 75 configurations, zero faults) — every finding was docs or tests, none geometry.
**All ten findings were then fixed on the follow-up branch `profile-generator-fixes`**
(2026-07-25/26), along with the pre-existing `decimal.InvalidOperation` traceback filed beside
them. That branch was then reviewed TWICE, and each round found defects in the previous round's
own fixes — which is the pattern `CLAUDE.md` "Review gates" says to expect, at full strength:
- **Round 1 (8 findings)** — including one real defect in shipped `revolve` geometry (below) and
  one bookkeeping error: the coordinate `[debug]` item had TWO halves, only one was fixed, and
  the whole entry was deleted. The unfixed half (a degenerate-but-positive `--depth`/`--height`
  naming neither flag nor value) is **re-filed on `inbox.md`**.
- **Round 2 (13 findings), all in round 1's fixes.** The worst was a REGRESSION those fixes
  introduced: `emit.MAX_COORD` was hand-set to 1e21, a full decade below the real wall, so the
  new guard rejected coordinates `master` emitted fine (5e21 round-tripped before, exited 2
  after — enough to make an existing trunk unreadable to `actor show`/`level doctor`), while
  three places in the record claimed it narrowed nothing. The constant is gone: `_quantize6`
  asks Decimal where the limit is, so the accepted range equals the emittable range by
  construction. That also closed a hole where `clean` returned early for an integral value and
  never quantized, so `1e200` passed the "single front door" and failed later in `fmt_vertex`.
  Round 2 also caught `_denoise` being applied to only ONE of revolve's three hint families
  (the caps kept a residue-decided texture basis), a `level materialize --core coarse` flag
  written into three user docs that **does not exist** (the same not-runnable-example defect
  this batch set out to fix), spec §5.7 still carrying the superseded side-quad formula, and an
  "off by up to Δ/2" error magnitude overstated 10–20× in four places (the real supremum is
  `90° − 2·atan(√cos(Δ/2))` — 0.56° at the default 22.5° facet).
- **Round 3 (8 findings), run PAST `CLAUDE.md`'s two-round ceiling at Andrzej's explicit
  instruction** — recorded because the ceiling is a written rule and this is a deliberate
  one-item exception, not a precedent. It earned its slot: it caught the `fmt_loc` narrowing
  described above (a REGRESSION introduced by round 2's own fix, one decade out from the one
  round 2 had caught), the nonexistent `--core coarse` flag surviving in `builders.py` and
  `architecture.md` after the record claimed it removed, the superseded side-quad formula still
  standing in the PLAN doc after the spec was corrected, a `_tex_basis` docstring claiming the
  editor-blessed parity fixtures pin its tie-break when `builder_parity.json` carries no texture
  vectors at all, and this very entry contradicting itself on the coordinate guard.
  **Every round found real defects in the previous round's fixes — three for three.** Round 3's
  own fixes ship unreviewed. Two pre-existing defects found while probing are logged on `inbox.md` rather than
fixed: `brush vertex move` escaping as a bare `ValueError` traceback, and a 1-uu revolve
building a non-manifold brush at exit 0 (identical on `master`). Note also that the
"State the profile-sweep caveats…" commit additionally rewrote `--rotate`'s help on
`brush intersect`/`deintersect`, which its subject does not mention. What the fixes added
beyond the literal findings, and why:
- `_hint_disagreements` in `test_profile_generators.py`. Finding 8 was that the 90° revolve case
  pinned nothing, and the reason turned out to be sharper than "thin coverage": at 90° an
  unrotated far-cap hint is exactly perpendicular to the true normal, so `_face`'s flip test
  (`_dot(nw, out) < 0`) is a no-op and the winding comes out right by accident. `doctor` can
  never see that. But `_face` also uses the hint for the emitted `Normal` and as the seed for
  `_tex_basis` — and the editor PRESERVES TextureU/V while recomputing `Normal`, so the surviving
  defect is a mis-projected texture, not a bad solid. The new oracle asserts every face's stored
  hint agrees with its own winding-derived normal and that both texture axes lie in the face
  plane. Measured on the same mutation matrix: 90° far-cap-unrotated goes 0 doctor findings → 2
  hint disagreements, sides-unrotated 0 → 32, control clean at every angle.
- A signed-volume assertion on the extrude oracles (finding 3), since a vertex set is
  orientation-blind and `check_watertight` only catches winding that is INCONSISTENT between
  neighbours, not a uniform inversion.
- `model.CoordinateError`, replacing a `decimal.InvalidOperation` traceback (finding 7). It
  lives in `model` because `emit` may not import `geometry` — `geometry` already imports `emit`.
  **Where the check goes took three tries, and the first two were regressions** — the durable
  lesson: a magnitude guard in the SHARED front door narrows whatever the WIDEST emitter could
  write. `emit.MAX_COORD = 1e21` (round 1) rejected vertices master emitted; moving it to the
  real 1e22 wall and probing the quantize from `_guard` (round 2) still rejected **Locations**,
  because `fmt_loc` formats with `f"{d:.6f}"` and has no precision wall at all while
  `fmt_vertex` rounds through `quantize(_SIX_DP)` and does. Either way an existing trunk became
  unreadable to `actor show`/`level doctor`. Final shape: no magnitude constant anywhere;
  `_guard` rejects only NON-FINITE (unwritable by either emitter) and `emit.quantize6` turns the
  precision failure into a named error at each quantize site. `rotation.py` quantizes at three
  sites of its own that `clean` never sees, so those route through `quantize6` too — `emit`'s
  "single write path" docstring was false for a rotated actor until they did.
- **A real defect in shipped `revolve`, found by the round-2 review** (`builders.py`, the
  side-quad loop). The outward hint was the 2D edge normal `(dv, −du)` turned by the facet's
  mid-angle, and an in-code comment asserted that IS the quad's true normal. It is not:
  de-rotated, the true normal is proportional to `(dv, −du·cos(Δ/2))`, so the two agree only
  when `du == 0` or `dv == 0` — i.e. only for an axis-parallel profile edge. Every profile in
  the test suite was a rectangle, so nothing caught it. On a slanted edge (a tapered turned
  column, a chamfered arch ring) the hint was off by `90° − 2·atan(√cos(Δ/2))` — 0.56° at the
  default 22.5° facet, 2.27° at 45°, 9.88° at 90°, nearing Δ/2 only as Δ→180°. It never
  mis-wound a face
  (`_dot(nw, shortcut) = dv² + du²·cos(Δ/2) > 0` always), which is why `doctor` and the new
  signed-volume check were both silent — but `_face` also seeds `_tex_basis` from the hint, and
  the editor PRESERVES TextureU/V while recomputing `Normal`, so the error shipped into the
  built map as a texture basis tilted out of the face plane (measured: 20 faces at 90°/4, 32 at
  360°/8, worst axis ≈1° out). The hint is now the quad's own Newell normal, oriented outward by
  the mid-angle direction (whose sign is all that was ever needed), and `_denoise` snaps its
  float noise so `_tex_basis`'s `argmin` seed cannot flip on rounding — without that, two faces
  of the committed golden changed texture basis by 90°. `test_a_slanted_profile_revolve_has_an
  _exact_outward_hint` covers the case `CORRIDOR` structurally could not.
**Remnant:** the spec and plan are **deliberately NOT deleted** (the usual fate of ephemeral docs
once work lands) — delete them once the follow-up branch has merged and settled.

# D2 — fully-offline BSP issue detector (FOR LATER) — scoping spec

**Status:** scoping spec (ephemeral). Marked FOR LATER — this is not a commitment to build now, only
a scope of what remains and the decisions the owner must make first.
**Sibling:** `bsp-issue-ground-truth-detector-d0-d1` (D0/D1 — the near-term detector). D2 is the tier
that also catches *silent-absence* holes, the one class D0/D1 do not.

## Goal

Catch the build-emergent issues that leave NO editor trace — a **silent-absence hole** (an authored
face that should survive CSG but is dropped, with no drop-warning) — with **no editor at any point**.
This is the only detector tier that must re-run CSG itself so it *knows what should exist*, then diff
should-vs-did.

## Current state

The premise in this item's `overview.md` — "a pure-Python reimplementation, slices prototyped in
`_scratch/bspspike/`, remaining work is SplitPolyList + CSG filter" — is **stale**. The offline
engine substrate now exists in **Rust**, and `_scratch/bspspike/` is gone.

- The CSG→BSP build is ported and runs offline, no editor: `uedcli-native/src/bspcsg.rs` (incremental
  `bspBrushCSG`), `build.rs` (bspBuild / SplitPolyList / FindBestSplit), `csg.rs`, `passes.rs`
  (bspOptGeom, merge-coplanars), `fpoly.rs`, `f32.rs` (float32-faithful), `zones.rs` (leaves/zones).
  Exposed to Python at `uedcli-native/src/lib.rs:503-504` (`build_geometry`,
  `build_geometry_bspcsg`), consumed by `uedcli/preview_native.py:320`.
- Collision is built: `uedcli-native/src/linecheck.rs:62` (`line_clear`, a LineCheck/PointCheck
  port), validated against the editor in `uedcli/tests/test_native_collision.py` (castle floor
  box-drop lands where UnrealEd's does).
- The built `UModel` is readable/writable: `uedcli/native/umodel.py` (reader),
  `uedcli-native/src/model_write.rs` (writer). This closes the D0/D1 spec's P0-a feasibility gate.
- Parity is measured, not assumed: `uedcli/tests/test_csg_native_differential.py` asserts full
  Tier-S surf-set parity vs frozen editor goldens on subtract / add-in-subtract / annihilation /
  semisolid / portal cases (incl. leaf/zone counts). One off-grid case (Balance=50 split
  distribution + bspOptGeom) is a tracked xfail.

So the engine — the expensive, multi-week part this spec was written to justify — is largely done.
What D2 still lacks is the **detector layer on top of it**: run the native build, compute the set of
authored faces that *should* produce a surf, diff against the surfs the build actually emitted, and
report each unexplained absence as a located finding. Nothing wires that today; the only shipped
detector is the static `uedcli/doctor.py` (`level doctor`), which predicts per-brush issues without
building.

Why D2 is still a *later* upgrade, not near-term: D0/D1 (the sibling item) cover every issue class
**except** silent-absence on a build the editor or the native engine already makes. D2's sole added
value is that last class plus "never run the editor at all." Given the native build now backs the
D0/D1 detector too, the marginal capability D2 adds is narrow — hence FOR LATER, pending the owner's
priority call.

## Design (FOR LATER — high level)

The detector diff, over the existing native build:

1. Build the level's Model with the native CSG core (`build_geometry_bspcsg`).
2. For each authored brush face, decide whether CSG *should* leave a visible/collidable surf (an
   interior/shared/buried face legitimately leaves none — this is the hard part, see risks).
3. Diff the should-set against the built Surf set (Tier-S key: plane + signed-normal winding +
   cleaned vertex set; texture vectors excluded — the D0/D1 spec §5 defines this key).
4. Report each face that should exist but has no matching built surf as a located silent-absence
   finding (brush, poly, coord), in the existing `doctor.Finding` shape.

Big risks / unknowns:

- **"Should this face survive?" is the whole difficulty.** CSG splits, merges, reverses and
  annihilates faces; a missing surf is usually correct. Distinguishing a legitimate absence from a
  silent bug is exactly what has no editor oracle — the reason this class is "silent." The diff is
  only as trustworthy as the native build's own fidelity, so D2 inherits every native-parity gap
  (the off-grid xfail above) as a potential false positive.
- **No ground-truth oracle for silent-absence.** By construction the editor emits nothing, so D2's
  own findings cannot be blessed against the editor the way surf-set parity is. Confidence has to
  come from constructed known-answer cases, not a corpus diff.
- **Native-build maturity gates it.** D2 is only sound where the native build is faithful; today
  that excludes the off-grid / Balance=50 distribution case and anything the differential suite
  hasn't frozen. A D2 finding on an unfaithful build is noise.

## Open questions (owner)

1. **Is D2 wanted at all, given the engine already exists?** The distinctive capability (silent-
   absence) is narrow and has no editor oracle. Options: build the diff layer; fold it into the
   D0/D1 detector as one native-build tier; or drop silent-absence as out of scope. (This mirrors
   the D1/D2-boundary question filed on the sibling item.)
2. **If wanted, when?** It is now a diff/report layer, not a multi-week engine — small enough to
   pull forward, or still deferrable on priority. Owner's call.
3. **What clears it to ship, with no editor oracle for its target class?** Propose: known-answer
   constructed cases only, plus a per-finding confidence label, and refuse to run on maps where the
   native build isn't at frozen parity. Owner confirms the bar.

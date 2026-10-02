+++
priority = "p3"
kind = "debug"
summary = "FPoly rotation-matrix ULP gap confirmed real (NYC747 Brush562), not shipped"
+++

# FPoly rotation-matrix ULP gap confirmed real (NYC747 Brush562), not shipped

`uedcli/rotation.py`'s module header flags a theoretical, previously unmeasured gap: a genuine
non-cardinal multi-axis FRotator (arbitrary angle on 2+ axes) composes its rotation matrix in Python
double (`euler_to_matrix_uu`), while the real editor composes in float32 `FCoords` — proven bit-exact
only for single-axis and cardinal (90°-multiple) multi-axis rotations.

Testing that hypothesis against NYC 747's open node/leaf-count residual
(`dev/docs/spikes/2026-09-02-nyc747-rotated-transform/`) found the level's one genuine non-cardinal
multi-axis brush, `Brush562` (Pitch=32768, Yaw=32768, Roll=59392 — Roll not a multiple of 16384).
Measured directly against a live self-built golden: the theoretical gap IS real — a 2-ULP divergence
in one rotation-matrix entry, propagating to 1–6 ULP differences in 3 of the brush's 8 transformed
node planes (the other 5, untouched by the tilt, are byte-identical). This is the first live
confirmation of the gap anywhere in the codebase.

It does NOT explain NYC 747's residual (Brush562's own node ownership already matches exactly,
native=8=editor=8), so no fix was shipped as part of that investigation — see
`dev/docs/native-materialize-findings.md`, "NYC 747 rotated-brush transform cross-validation"
(2026-09-02), for the full write-up.

Worth a look on its own terms: this is a genuine CONTENT-exactness gap (would show as a
`parity_report.py` field diff even on a level that's already node/surf/leaf-count-exact), relevant to
the standing full-byte-parity goal. No known DX level is currently blocked on it — fixing it means
porting a float32 `FCoords`-style compose into `rotation.py`/`fpoly.rs` for the non-cardinal
multi-axis case specifically, with no live case yet to validate the fix against. Low priority: real,
but unblocking nothing today.

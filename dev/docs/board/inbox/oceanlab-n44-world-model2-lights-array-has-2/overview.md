+++
priority = "p2"
kind = "debug"
summary = "OceanLab N44 FAILS: world Model2's per-surf Lights run has 2 extra light refs native shouldn't emit, plus a downstream LightBits byte diff."
+++

# OceanLab N44 world Model2 Lights array has 2 extra entries

Found 2026-09-06 pushing the ladder with `ladder_run.py` after the texture-resolver fix
(`2d223ce`) and the `BoundVisible` port (`4239ed6`) landed. N=1..43 PASS; N=44 (adding `Brush1419`,
a plain brush — no new light or zone actor) FAILS.

## The divergence

`body_token_diff.py native_N44.dx ref_N44.dx model2`:

    token COUNT differs: native=11953 ued=11951
    token[11509] literal span: first differing byte at +6676 of 128650/128518
          nat=00001818f5a68541f5a68541ffffffffc48b0100002048c3b9c787c400000000
          ued=00001818f5a68541f5a68541ffffffff408b0100002048c3b9c787c400000000
    token[11946] O: nat=('light light111',) ued=('light light106',)
    token[11947] O: nat=('light light121',) ued=('None',)
    token[11948] O: nat=('light light106',) ued=('None',)
    token[11950] O: nat=('None',) ued=(b'\x00\x00\x00\x00\x00\x00\x00\x00',)

`Model.Lights` (`_model_tail`'s final `e4` array, written by `light.rs::bake` as flattened
per-surf `[light_idx, ..., -1]` runs, then patched to object refs) has native's list running
`..., light111, light121, light106, -1(None)` where the editor's stops after `light106` two slots
earlier — native emits an extra `light121` AND a duplicate/extra `light106` some OTHER surf's run
does not have in the editor's build. Two tokens longer overall (11953 vs 11951), consistent with
one extra 2-entry run (`[light_idx, -1]`) or one run gaining 2 extra members.

The literal-span diff at token 11509 (`c48b0100` vs `408b0100`, a 4-byte LE int `0x00018bc4` vs
`0x00018b40`, differing by `0x84` = 132) sits in the SAME tail region just before the Lights array
(after LightMap/LightBits/Bounds/LeafHulls/Leaves per `_model_tail`'s consumption order) — likely
the packed shadow-plane `LightBits` data, and likely a DOWNSTREAM symptom of the same root cause
(a surf lit by a different light set bakes different shadow bits), not a second independent bug.

## What's NOT yet known

- WHICH surf(s) gained the extra `light121`/`light106` entries, and why Brush1419 (a plain brush,
  not a light or zone actor) changes any surf's light-relevance set.
- Whether this is a light-to-surf VISIBILITY/reachability test difference (same family as the
  `BoundVisible`/`OccludeBsp` work just landed — a light reaching a surf it shouldn't, or vice
  versa) or a light-BAKE-ORDER difference (a surf's run built in a different pass/order gets
  different membership).
- Whether the `port-occludebsp-frustum-cone-subtree-reject` residual (native box-tests 51 extra
  subtrees per build, filed same session) is related — plausible given both are about which
  node/surf a light's visibility test reaches, but NOT measured here.

## Repro

    ladder_run.py --dx <…>/Maps/14_OceanLab_Lab.dx --from 44 --to 44 --keep-native
    body_token_diff.py <…>/native_N44.dx <…>/ref_N44.dx model2

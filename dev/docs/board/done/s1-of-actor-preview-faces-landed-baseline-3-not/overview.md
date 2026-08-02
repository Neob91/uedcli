+++
priority = "p3"
kind = "unknown"
summary = "S1 of actor preview --faces landed baseline +3, not the planned +1"
+++

# S1 of actor preview --faces landed baseline +3, not the planned +1

A recorded DEVIATION from the plan in board item `actor-preview-faces-plan-cites-dev-docs`, §3/S1.
It lived only in commit `ee4b205`'s message, which a squash-merge buries, so it is filed here.

**What the plan said.** S1 is "a pure move … no new test beyond the import-hygiene one", and its
Done-when asks for a pass count of "the re-measured baseline **+1**".

**What landed.** `uedcli/tests/test_texframe.py` holds 7 tests: the 3 UV-frame pins S1 re-homes out
of `test_preview_native.py` (one rewritten — the original asserted nothing, because both fallback
arms produced the same basis on its fixture), the one budgeted import-hygiene test, and 3 more:

| test                                                        | why |
|-------------------------------------------------------------|---|
| `..._zero_axes_seed_from_THE_WINDING_when_normal_is_absent` | the fallback's other arm. S1's Done-when does ask for that pin — pinning both arms takes two tests |
| `test_poly_flags_int_parses_or_falls_back_to_zero`          | **the deviation proper** — below |
| `test_texframe_use_loads_no_native_or_texture_module`       | a round-1 review finding: the AST-based hygiene test guarantees nothing transitive, so a `from .utexture import …` added to `builders.py` leaves it green |

**Why the `poly_flags_int` test.** `poly_flags_int` moved into `texframe`, the resolver-free tier
that exists to work with no `cargo` and no game install. Its only other exercise is through
`preview_native.build_scene`, behind `test_preview_native.py`'s module-level
`importorskip("uedcli_native")` — so on a no-cargo machine the symbol had ZERO assertions, which is
the exact defect S1 exists to fix for the UV tests.

**The counts, `bin/test` on the no-cargo dev box.** The two S1 commits were measured against each
other in one session: `44531c6` **9366 passed**, `ee4b205` **9369 passed** — **+3**. 1 failed / 74
skipped / 76 deselected at both; the failure is the pre-existing, separately boarded
`test_native_materialize.test_class_names_are_unique_across_the_deusex_package_set`. The pre-S1 leg
was measured in an earlier session, whose absolute figures do not line up with those two: 9360
without the new module, 9364 with it.

**"+1" was also not measurable as written on this machine.** The plan's arithmetic assumes a box
with the native extension, where the 3 re-homed tests already ran. Here they were skipped before S1
and run after it, so re-homing alone moves the pass count — and it does **not** drop the skip count
by 3 in exchange, because a module-level `importorskip` reports as ONE skip for the whole module.

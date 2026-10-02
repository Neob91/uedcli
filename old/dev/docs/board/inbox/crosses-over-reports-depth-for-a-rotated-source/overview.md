+++
priority = "p2"
kind = "debug"
summary = "Two rotated cubes that only touch are reported as crossing by their full 100uu depth."
+++

# crosses over-reports depth for a rotated source

`actor_survey.penetration_depth`'s own docstring records this as an unexercised limit and asks for
it to be reported rather than patched around if a rotated case ever turned up: "A source or a face
at an arbitrary (non-axis-aligned) angle could in principle have its single deepest point fall
outside the actual overlap region, over-reporting the depth; nothing in this plan's fixtures
exercises that, and it is not solved here — if a rotated case turns up, report it."

One has. Two 100-cubes butted face to face over a full 100x100 square, the whole pair turned about
the shared face's centre (`survey_scenarios.two_cubes_face_to_face`):

```
  0 deg   crosses = []                                    touches = [('PrismA', 'PrismB')]
 17 deg   crosses = [('PrismA', 'PrismB', 100.0)]         touches = []
 30 deg   crosses = [('PrismA','PrismB',100.0), ('PrismB','PrismA',100.0)]   touches = []
 45 deg   crosses = []                                    touches = [('PrismA', 'PrismB')]
```

Nothing interpenetrates at any angle — the reported 100uu is the cube's own full width. The axis
aligned angles (0 and 45) come out right only because the deepest point of an axis-aligned
cross-section lies inside the overlap region; at 17 and 30 degrees it does not.

Two consequences, both live:

- A rotated pair that merely touches is reported as crossing, with a depth equal to the source's own
  size.
- `touches` is then suppressed for that pair by the mutual-exclusivity rule, so a rotated flush
  contact is reported by neither relation. `test_two_rotated_cubes_face_to_face_do_touch` asserts
  `pair_touches` directly for exactly this reason and records why.

Rotated brushes are ordinary in shipped content, so this is not an exotic case. The `touches` side
needs no change: its own region test is exact at every angle (the contrasting
`test_two_cubes_meeting_at_one_edge_never_touch` passes at all four angles).

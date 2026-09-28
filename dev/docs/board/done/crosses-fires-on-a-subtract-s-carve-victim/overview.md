+++
priority = "p1"
kind = "debug"
summary = "FIXED — `_source_cells` filtered to resolved matter (convex-piece partition against later Subtracts), not authored cells."
+++

# crosses fires on a Subtract's carve victim

Fixed: `_source_cells` (`uedcli/actor_survey.py`) now partitions each source's authored cells by
every Subtract later than it in trunk order (`_partition_by_brushes`) and keeps only the pieces
whose `resolved_matter_of` still holds at their centroid. Covers all four cases this item named:
`blind_pocket_in_a_wall`, `two_rooms_side_by_side`, `a_doorway_through_a_wall_seam`, and the
Add-to-Add case on `an_oversized_corridor_past_its_room`. Regression tests in
`uedcli/tests/test_actor_survey.py`.

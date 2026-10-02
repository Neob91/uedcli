+++
priority = "p1"
kind = "debug"
summary = "FIXED — carves moved to an exact ordered-volume measure (`_carves_volume`), replacing the face-area `removed_by`."
+++

# csg carves misses a carve entirely interior to its victim's volume

Fixed: `carves_facts_for` (`uedcli/actor_survey.py`) now uses `_carves_volume`, an exact boolean-CSG
volume measure (`victim INTERSECT s INTERSECT {victim's own matter, just before s}`), replacing the
retired face-area `removed_by`. Catches a Subtract wholly interior to an Add's volume, which the old
face-area comparison missed entirely. Regression fixture
`a_subtract_buried_inside_an_adds_interior` in `uedcli/tests/survey_scenarios.py`.

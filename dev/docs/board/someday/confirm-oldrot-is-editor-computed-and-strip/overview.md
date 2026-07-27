+++
priority = "p3"
kind = "implement"
summary = "Confirm `OldRot` is editor-computed and strip it"
+++

# Confirm `OldRot` is editor-computed and strip it

`normalize.COMPUTED_PROPS`
strips `BasePos`/`BaseRot`/`OldLocation` but NOT `OldRot` (not spike-confirmed). The mover
integration test (`test_mover_integration.py`) checks whether a re-exported mover carries `OldRot`;
if it does, add it to `COMPUTED_PROPS` (decisions.md 2026-06-25, Task 3 note).

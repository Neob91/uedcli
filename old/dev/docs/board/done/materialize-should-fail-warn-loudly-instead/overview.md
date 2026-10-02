+++
priority = "p3"
kind = "implement"
summary = "Materialize fails loudly (exit 2, complete set) on a referenced package absent from the path; 0-package composed path is advisory only"
+++

# Materialize fails loudly on a missing referenced package

Done: `apply.run_materialize` gates on the level's referenced packages before the editor is created —
exit 2 naming the complete missing set, verify-independent. A composed path resolving 0 packages when
the level references none prints one advisory line and still builds (owner 2026-08-02). Dead
`run_materialize(packages=…)` param and `MaterializeResources.load_set` removed.

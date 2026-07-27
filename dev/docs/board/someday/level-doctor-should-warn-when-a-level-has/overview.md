+++
priority = "p2"
kind = "implement"
summary = "`level doctor` should WARN when a level has no `LevelInfo` (materialize will fail), and materialize's error should name that cause"
+++

# `level doctor` should WARN when a level has no `LevelInfo` (materialize will fail), and materialize's error should name that cause

p2. `level create` now bakes an `Engine.LevelInfo`
(fixes the common/new-level case), but a PRE-EXISTING trunk without one still fails materialize
opaquely (`MAP NEW`'s default LevelInfo survives → re-export carries an actor the trunk lacks →
mismatch). A doctor warn + a named materialize error close the gap for older levels.

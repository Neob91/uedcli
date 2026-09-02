+++
priority = "p2"
kind = "debug"
summary = "HIGH: `actor delete`/`actor find` glob missed a `LevelInfo`-class actor"
+++

# HIGH: `actor delete`/`actor find` glob missed a `LevelInfo`-class actor

p2. `actor
find --class LevelInfo` + `--name 'LevelInfo*'` fed to `actor delete` did NOT remove it → a later
`actor build Engine.LevelInfo` produced two → materialize precondition trip "found 2". Check
`actor find`'s `--class`/`--name` handling for `Engine.LevelInfo`-class actors.

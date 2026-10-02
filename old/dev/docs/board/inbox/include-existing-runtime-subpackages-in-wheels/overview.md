+++
priority = "p2"
kind = "implement"
summary = "Include existing runtime subpackages in wheels"
+++

# Include existing runtime subpackages in wheels

`pyproject.toml` lists only `uedcli`, so built wheels omit the production `uedcli.native` package.
The command-layer reorganization will validate its new `uedcli.cli` packages without widening that
behavior-preserving change. Add all runtime packages and an installed-wheel regression separately.

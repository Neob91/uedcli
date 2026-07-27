+++
priority = "p?"
kind = "unknown"
summary = "`help=` enforcement test (board #9)"
+++

# `help=` enforcement test (board #9)

— BUILT 2026-07-19. New `test_help_completeness.py` walks
the real argparse tree from `cli.build_parser()` and asserts every subcommand + argument has a help
that (a) exists, (b) doesn't echo the flag/command name, (c) clears a 10-char minimum — plus a
classifier self-test so a future gap fails CI. Filled the 6 gaps it surfaced (the terse `brush build`
`X/Y/Z extent` dimension helps → descriptive units/axis). Commit `18d96bfca`.

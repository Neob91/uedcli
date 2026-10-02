+++
priority = "p3"
kind = "chore"
summary = "Fixed — `brush clip` now prints `clipped {name}: {before}→{after} faces` on stderr for a real clip"
+++

# `brush clip` prints nothing on success

Fixed in `uedcli/cli/commands/brush/edit.py:clip()` — a genuinely clipped actor now gets a stderr
confirmation matching the existing "whole"/unchanged note's style.

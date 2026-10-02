+++
priority = "p2"
kind = "debug"
summary = "`doctor` `fallthrough` warns on EVERY upward-facing semisolid poly — trains you to ignore the category"
+++

# `doctor` `fallthrough` warns on EVERY upward-facing semisolid poly — trains you to ignore the category

A detailed space emitted 17 `fallthrough` warns, all benign (ceiling beams at
Z=220 nobody can walk on), because the check flags any up-facing semisolid regardless of
reachability. Noise this dense hides a real fall-through. Needs a reachability/height gate so the
warning means something. (Agent C.)

+++
priority = "p3"
kind = "chore"
summary = "`brush clip` prints nothing on success"
+++

# `brush clip` prints nothing on success

A successful clip emits only the "editing level"
banner — no confirmation — so a blind builder can't tell it did anything without re-inspecting. Print
e.g. `clipped <name>: 6→7 faces`. (Blind-build test, 2026-07-25.)

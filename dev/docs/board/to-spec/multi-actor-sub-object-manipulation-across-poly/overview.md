+++
priority = "p3"
kind = "implement"
summary = "Multi-actor sub-object manipulation across `poly`/`vertex`/`clip`"
+++

# Multi-actor sub-object manipulation across `poly`/`vertex`/`clip`

Make
the `BRUSH:SELECTOR` target token (from `poly set`, e.g. `poly set Wall1:3,5 Wall2:all`) the
consistent pattern for the other sub-object tools: `brush vertex move` (currently single-brush
`--at`), `brush clip` (currently single-brush), future `poly` ops. Generalize the target-token
parser into a shared helper.

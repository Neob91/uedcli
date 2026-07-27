+++
priority = "p2"
kind = "chore"
summary = "Lit-render first-person VISUAL is intro/menu-blocked for custom maps"
+++

# Lit-render first-person VISUAL is intro/menu-blocked for custom maps

p2. The lighting
crash is FIXED (below), and a `uplayctl session start --map NativeLit` confirms `link up on NativeLit`
with 0 singularities + a possessed player — but DeusEx composites its **intro/menu overlay** over the
render, and there's no menu path to true first-person for a *custom* map (only an in-game console
`open` gives it), so `uplayctl shot` / an X grab shows the intro logo, not the lit room (the world
renders clean BEHIND it). To screenshot a native map first-person, drive: boot → skip intro → New
Game/Training (real first-person) → in-game console `open <map>` → shot (cf. `game/dxplay.sh enter`).
Nice-to-have for visual verification; the render itself is proven by metrics.

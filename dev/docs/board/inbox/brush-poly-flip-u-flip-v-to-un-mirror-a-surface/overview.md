+++
priority = "p2"
kind = "implement"
summary = "Add brush poly flip-u/flip-v to mirror a surface's texture mapping; document the sheet facing/un-mirror rule."
+++

# brush poly flip-u/flip-v to un-mirror a surface texture

Source: `dev/docs/spikes/levelbuild-friction/` owner finding #4 + §6b. No verb mirrors a surface's
texture mapping today (`grep flip uedcli/` → none), so an agent that hit a mirrored or backwards
texture had no fix.

Two deliverables:
- **Verb:** `brush poly flip-u` / `flip-v` — negate the surface's `TextureU` / `TextureV` to mirror the
  mapping in place. Fits the existing `brush poly {pan,rotate,scale}` family.
- **Doc:** document the sheet facing / un-mirror rule (the "+Y side reads correct" convention agents
  kept guessing) in `docs/leveldesign` textures guidance.

Relation to [[generator-texture-basis-mirrors-lettered]]: if that basis fix lands, flip is no longer
needed for *correctness*, but stays useful for deliberate mirroring. Keep both.

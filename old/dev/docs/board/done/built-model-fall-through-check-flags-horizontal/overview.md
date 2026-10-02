+++
priority = "p3"
kind = "owner-question"
summary = "Fall-through check flags any floor-facing PF_Portal surf; a horizontal zone portal is a false positive"
+++

# Built-model fall-through check flags horizontal zone portals as PF_Portal floors

Resolved: the owner removed the fall-through check entirely (2026-08-03), so the false positive is
gone. The built-model check now locates only invisible walls (near-zero-area BSP nodes).

"""Task: widen a WanChai Market corridor -- see ../spec_format.py for the
entry-kind vocabulary this file uses.
"""

TASK = dict(
 id="wanchai_corridor", level="wanchai",
 title="Widen the upper corridor",
 req="&ldquo;The corridor Brush1159 feels cramped. Widen it by 48 units &mdash; push the south wall out.&rdquo;",
 base_trunk="wanchai_gt",
 photo_camera=dict(at=[-640,384,184], pitch=0),
 before=dict(
   quad="before_quad",
   note="Middle segment of a 3-part hallway (Brush1157 west, Brush1159 here, Brush1156 east). Brush1159's east wall is exactly coplanar with Brush1156's west wall (0 unit gap) -- moving only the south face's corners keeps that seam intact; translating the whole brush would break it.",
   photos=[f"pan_before_{i}" for i in range(8)]),
 entries=[
   dict(kind="update", actor="Brush1159", target="corners",
        at=[[-840,280,128],[-440,280,128],[-440,280,240],[-840,280,240]], delta=[0,-48,0],
        what="the corridor's own south wall; the task's widen target"),
   dict(kind="update", actor="Brush1156", target="unchanged",
        what="hallway segment continuing east; its west wall is coplanar with Brush1159's east wall at the seam -- must stay exactly where it is"),
   dict(kind="update", actor="Brush1157", target="unchanged",
        what="hallway segment continuing west; floor coplanar with Brush1159's -- must stay unchanged"),
 ])

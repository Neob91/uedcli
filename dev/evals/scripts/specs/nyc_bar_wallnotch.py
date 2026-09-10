"""Task: push out NYC_Bar's back nook -- see ../spec_format.py for the
entry-kind vocabulary this file uses.
"""

TASK = dict(
 id="nyc_bar_wallnotch", level="bar",
 title="Push out the back nook",
 req="&ldquo;The nook Brush15 feels cramped. Push its south wall out by 64 units.&rdquo;",
 base_trunk="nyc_bar_gt",
 photo_camera=dict(at=[-640,-550,150], pitch=0),
 before=dict(
   quad="before_quad",
   note="The back nook (Brush15) is a separate room from the main hall (Brush1), connected through a gap in the shared wall at y=-384 -- not one stepped brush. Its own far wall (y=-640) has two recess pockets (Brush16, Brush73) carved flush against it, plus counter/shelf fixtures (Brush71, Brush72) reaching into them.",
   photos=[f"pan_before_{i}" for i in range(8)]),
 entries=[
   dict(kind="update", actor="Brush15", target="corners",
        at=[[-1024,-704,0],[-256,-704,0],[-256,-704,256],[-1024,-704,256]], delta=[0,-64,0],
        what="the nook's far wall; the task's own push-out target"),

   dict(kind="anchor", actor="Brush16", to="Brush15", what="recess pocket carved flush against the far wall's west half"),
   dict(kind="anchor", actor="Brush73", to="Brush15", what="recess pocket carved flush against the far wall's east half"),
   dict(kind="anchor", actor="Brush71", to="Brush15", what="counter support reaching flush to the far wall"),
   dict(kind="anchor", actor="Brush72", to="Brush15", what="counter shelf back panel reaching flush to (and just past) the far wall"),

   dict(kind="update", actor="Brush631", target="unchanged",
        what="small subtract niche sitting just clear of the moving wall -- close enough to tempt a naive move, not actually attached"),
 ])

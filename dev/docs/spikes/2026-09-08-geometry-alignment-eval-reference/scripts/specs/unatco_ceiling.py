"""Task: raise Manderley's office ceiling (UNATCO HQ) -- see
../spec_format.py for the entry-kind vocabulary this file uses.
"""

TASK = dict(
 id="unatco_ceiling", level="unatco",
 title="Task 2 — Raise the ceiling",
 req="&ldquo;Manderley&rsquo;s office feels cramped. Raise its ceiling by 48 units.&rdquo;",
 base_trunk="unatco_gt",
 frame="59,-360,200,620,140,500",
 before=dict(
   diags=[("before_side","Side view (elevation) of the office before any change — the ceiling is flat at z=416, spanning both wall volumes (Brush418 south, Brush420 north)."),
          ("before_top","Top-down plan of the same office, for footprint context.")],
   photos=[f"pan_before_{i}" for i in range(8)]),
 entries=[
   dict(kind="update", actor="Brush418", target="corners", at=[[128,-288,416],[448,-288,416],[448,64,416],[128,64,416]], delta=[0,0,48],
        why="south wall's ceiling face; the task's own raise-ceiling target"),
   dict(kind="update", actor="Brush420", target="corners", at=[[-96,64,416],[448,64,416],[448,304,416],[-96,304,416]], delta=[0,0,48],
        why="north wall's ceiling face, shares the ceiling with Brush418 at the y=64 seam -- must rise the same amount or the ceiling steps"),

   dict(kind="anchor", actor="Brush285", to="Brush418", why="recessed ceiling light panel over the south half"),
   dict(kind="anchor", actor="Brush295", to="Brush418", why="recessed ceiling light panel over the south half"),
   dict(kind="anchor", actor="Brush132", to="Brush418", why="ceiling trim cap over the south half"),
   dict(kind="anchor", actor="Brush74", to="Brush418", why="ceiling trim cap over the south half"),
   dict(kind="anchor", actor="Brush284", to="Brush420", why="recessed ceiling light panel over the north half"),

   dict(kind="update", actor="Brush663", target="unchanged",
        why="the niche is its own separate room with its own ceiling -- expected to keep its own height, not match the office's new one"),
   dict(kind="update", actor="Light156", target="unchanged",
        why="room light -- every light sits a fixed distance below its ceiling room-wide, not mounted to the surface"),
   dict(kind="update", actor="Light103", target="unchanged", why="room light, same fixed-height convention"),
   dict(kind="update", actor="Light318", target="unchanged", why="room light, same fixed-height convention"),
   dict(kind="update", actor="Light86", target="unchanged", why="room light, same fixed-height convention"),
   dict(kind="update", actor="Light120", target="unchanged", why="room light, same fixed-height convention"),
 ],
 scenarios={
   "ceil": dict(title="Ceiling (both halves of the room)", view="side",
     note="Like the east wall, the ceiling spans two wall volumes sharing one surface. Both must rise together, or the ceiling gets a step in it.",
     members=["Brush418","Brush420"]),
   "fixtures": dict(title="Ceiling-mounted fixtures (light panels, trim)", view="side",
     note="Three recessed light panels and two corner trim caps are set into the ceiling, split across both wall volumes: most sit over the south half (Brush418), one panel sits over the north half (Brush420). Each rises with its own half.",
     members=["Brush285","Brush295","Brush284","Brush132","Brush74"],
     extra_photos=[("pan_after_0","Photo, camera tilted upward, showing the raised ceiling with one of the light panels visible.")]),
   "niche": dict(title="Niche ceiling", view="side",
     note="The niche is its own separate room with its own ceiling. It's expected to keep its own height and not match the office's new one.",
     members=["Brush663"],
     extra_photos=[("pan_after_0","Photo, camera tilted upward — the height step at the boundary with the niche is visible in the top-right.")]),
   "lights": dict(title="Overhead room lights", view="side",
     note="Every light sits the same distance below its ceiling, room-wide — a fixed convention, not a mount to the ceiling surface. They must stay put.",
     members=["Light156","Light103","Light318","Light86","Light120"]),
 })

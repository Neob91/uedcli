"""Single source of truth: which actors are ANCHORS (the task pins an exact
delta on these), which are DEPENDENTS (must match a SPECIFIC anchor's actual
delta -- verified per-actor by geometry, not assumed uniform), and which must
stay UNCHANGED. Scenario grouping (for the human page) is layered on top and
does not affect grading, which always walks this flat per-actor structure.

Every entry carries a `why` -- what the entry is actually FOR, in plain
language. Grading cares about the RESULT, not how an agent got there:
`why` isn't consumed by the mechanical check, it's for a human (or a
follow-up review) reading a FAILURE, to judge whether the underlying intent
was satisfied some other way the mechanical check didn't anticipate (e.g. a
different but equally valid construction), rather than auto-failing it.

`op` on anchors/dependents is deliberately narrow today (only `move` exists,
since both current tasks are pure translations) but is a real field, not an
assumption -- a future task needing `rotate`/`duplicate`/`resize`/`delete`
adds a new op kind and a corresponding check in check_trunk.py, without
restructuring this file's shape.
"""

TASKS = {
 "t1": dict(
   base_trunk="unatco_gt",
   anchors=[
     dict(actor="Brush418", op="move", kind="brush_vertex_move",
          at=[[448,-288,416],[448,64,416],[448,64,240],[448,-288,240]], task_delta=[48,0,0],
          why="south wall of Manderley's office; the task's own east-widen target"),
     dict(actor="Brush420", op="move", kind="brush_vertex_move",
          at=[[448,64,416],[448,304,416],[448,304,240],[448,64,240]], task_delta=[48,0,0],
          why="north wall of Manderley's office, shares the east wall with Brush418 at the y=64 seam -- must widen the same amount or the wall steps"),
   ],
   # anchor verified from real geometry (which wall volume's y-range the
   # actor actually sits in), not assumed uniform across a scenario.
   dependents=[
     dict(actor="Brush670", anchor="Brush418", op="move", why="switch recess, cut into the south wall"),
     dict(actor="Brush161", anchor="Brush418", op="move", why="south wall trim board"),
     dict(actor="Brush132", anchor="Brush418", op="move", why="south wall trim board"),
     dict(actor="Brush203", anchor="Brush418", op="move", why="south wall trim board"),
     dict(actor="Brush74", anchor="Brush418", op="move", why="south wall trim board"),
     dict(actor="Brush152", anchor="Brush418", op="move", why="south wall fixture"),
     dict(actor="Switch6", anchor="Brush418", op="move", why="the wall light switch itself, mounted in Brush670's recess"),
     dict(actor="Brush869", anchor="Brush420", op="move", why="decorative pilaster on the north wall"),
     dict(actor="Light14", anchor="Brush420", op="move", why="the pilaster's own light"),
     dict(actor="Brush766", anchor="Brush420", op="move", why="wall cavity holding the trophy shelf + hidden safe, cut into the north wall"),
     dict(actor="Brush364", anchor="Brush420", op="move", why="the safe's own interior geometry inside the cavity"),
     dict(actor="Brush873", anchor="Brush420", op="move", why="the safe's own back panel inside the cavity -- moving the cavity without this orphans it mid-room (the original bug this eval caught)"),
     dict(actor="Brush592", anchor="Brush420", op="move", why="the display shelf inside the cavity"),
     dict(actor="Light149", anchor="Brush420", op="move", why="the shelf's own light"),
     dict(actor="Vase3", anchor="Brush420", op="move", why="display item on the shelf"),
     dict(actor="Vase4", anchor="Brush420", op="move", why="display item on the shelf"),
     dict(actor="BookClosed1", anchor="Brush420", op="move", why="display item on the shelf"),
     dict(actor="NanoKey0", anchor="Brush420", op="move", why="display item on the shelf"),
     dict(actor="WeaponModRecoil0", anchor="Brush420", op="move", why="display item on the shelf"),
     dict(actor="FlagPole3", anchor="Brush420", op="move", why="ceremonial flagpole anchored to the north wall's corner (~48u off two adjacent walls, not flush-mounted)"),
     dict(actor="FlagPole4", anchor="Brush418", op="move", why="ceremonial flagpole anchored to the south wall's corner"),
     dict(actor="Brush663", anchor="Brush418", op="move", why="the display niche -- a genuinely separate small room built against the south wall, must stay flush against it"),
     dict(actor="Brush1", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush138", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush140", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush148", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush164", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush168", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush1158", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush1550", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="Brush1551", anchor="Brush418", op="move", why="niche interior detail brush"),
     dict(actor="OrdersTrigger5", anchor="Brush418", op="move", why="scripted trigger inside the niche"),
     dict(actor="Light6", anchor="Brush418", op="move", why="the niche's own light"),
   ],
   unchanged=[],
   # scenario grouping for the human-readable page -- display only
   scenarios={
     "t1_wall": dict(title="East wall (both halves of the room)", view="top",
       note="The office is built from two wall volumes sharing one wall. Both must move out together, or the wall gets a step in it.",
       members=["Brush418","Brush420"]),
     "t1_fixtures": dict(title="Wall-mounted fixtures (switch, trim, pilaster)", view="top",
       note="The wall's own hardware is split across both wall volumes: the switch/recess/most trims sit on the south half (Brush418), the pilaster and its light sit on the north half (Brush420). Each moves with its OWN wall, not a single shared delta.",
       members=["Brush670","Brush161","Brush132","Brush203","Brush74","Brush152","Switch6","Brush869","Light14"]),
     "t1_safe": dict(title="Trophy shelf with a hidden wall safe", view="top",
       note="A wall-mounted display shelf has a real hidden safe built into its back, entirely on the north wall volume (Brush420). The whole unit and its contents must move together with it.",
       members=["Brush766","Brush364","Brush873","Brush592","Light149","Vase3","Vase4","BookClosed1","NanoKey0","WeaponModRecoil0"]),
     "t1_flags": dict(title="Corner flagpoles", view="top",
       note="Two flagpoles stand in opposite corners of the room, anchored to DIFFERENT wall volumes: FlagPole3 to the north wall (Brush420), FlagPole4 to the south wall (Brush418). Each must move with its own corner's wall.",
       members=["FlagPole3","FlagPole4"]),
     "t1_niche": dict(title="Display niche (a separate small room)", view="top",
       note="This niche is a genuinely separate small room built against the south wall volume (Brush418), not part of the wall itself. It must move so it stays flush against it.",
       members=["Brush663","Brush1","Brush138","Brush140","Brush148","Brush164","Brush168","Brush1158","Brush1550","Brush1551","OrdersTrigger5","Light6"]),
   }),
 "t2": dict(
   base_trunk="unatco_gt",
   anchors=[
     dict(actor="Brush418", op="move", kind="brush_vertex_move",
          at=[[128,-288,416],[448,-288,416],[448,64,416],[128,64,416]], task_delta=[0,0,48],
          why="south wall's ceiling face; the task's own raise-ceiling target"),
     dict(actor="Brush420", op="move", kind="brush_vertex_move",
          at=[[-96,64,416],[448,64,416],[448,304,416],[-96,304,416]], task_delta=[0,0,48],
          why="north wall's ceiling face, shares the ceiling with Brush418 at the y=64 seam -- must rise the same amount or the ceiling steps"),
   ],
   dependents=[
     dict(actor="Brush285", anchor="Brush418", op="move", why="recessed ceiling light panel over the south half"),
     dict(actor="Brush295", anchor="Brush418", op="move", why="recessed ceiling light panel over the south half"),
     dict(actor="Brush132", anchor="Brush418", op="move", why="ceiling trim cap over the south half"),
     dict(actor="Brush74", anchor="Brush418", op="move", why="ceiling trim cap over the south half"),
     dict(actor="Brush284", anchor="Brush420", op="move", why="recessed ceiling light panel over the north half"),
   ],
   unchanged=[
     dict(actor="Brush663", why="the niche is its own separate room with its own ceiling -- expected to keep its own height, not match the office's new one"),
     dict(actor="Light156", why="room light -- every light sits a fixed distance below its ceiling room-wide, not mounted to the surface"),
     dict(actor="Light103", why="room light, same fixed-height convention"),
     dict(actor="Light318", why="room light, same fixed-height convention"),
     dict(actor="Light86", why="room light, same fixed-height convention"),
     dict(actor="Light120", why="room light, same fixed-height convention"),
   ],
   scenarios={
     "t2_ceil": dict(title="Ceiling (both halves of the room)", view="side",
       note="Like the east wall, the ceiling spans two wall volumes sharing one surface. Both must rise together, or the ceiling gets a step in it.",
       members=["Brush418","Brush420"]),
     "t2_fixtures": dict(title="Ceiling-mounted fixtures (light panels, trim)", view="side",
       note="Three recessed light panels and two corner trim caps are set into the ceiling, split across both wall volumes: most sit over the south half (Brush418), one panel sits over the north half (Brush420). Each rises with its own half.",
       members=["Brush285","Brush295","Brush284","Brush132","Brush74"]),
     "t2_niche": dict(title="Niche ceiling", view="side",
       note="The niche is its own separate room with its own ceiling. It's expected to keep its own height and not match the office's new one.",
       members=["Brush663"]),
     "t2_lights": dict(title="Overhead room lights", view="side",
       note="Every light sits the same distance below its ceiling, room-wide — a fixed convention, not a mount to the ceiling surface. They must stay put.",
       members=["Light156","Light103","Light318","Light86","Light120"]),
   }),
}

"""Single source of truth: which actors are ANCHORS (the task pins an exact
delta on these), which are DEPENDENTS (must match a SPECIFIC anchor's actual
delta -- verified per-actor by geometry, not assumed uniform), and which must
stay UNCHANGED. Scenario grouping (for the human page) is layered on top and
does not affect grading, which always walks this flat per-actor structure.
"""

TASKS = {
 "t1": dict(
   base_trunk="unatco_gt",
   anchors=[
     dict(actor="Brush418", kind="brush_vertex_move",
          at=[[448,-288,416],[448,64,416],[448,64,240],[448,-288,240]], task_delta=[48,0,0]),
     dict(actor="Brush420", kind="brush_vertex_move",
          at=[[448,64,416],[448,304,416],[448,304,240],[448,64,240]], task_delta=[48,0,0]),
   ],
   # (actor, anchor) -- anchor verified from real geometry (which subtract's
   # y-range the actor actually sits in), not assumed uniform across a scenario.
   dependents=[
     ("Brush670","Brush418"), ("Brush161","Brush418"), ("Brush132","Brush418"),
     ("Brush203","Brush418"), ("Brush74","Brush418"), ("Brush152","Brush418"),
     ("Switch6","Brush418"),
     ("Brush869","Brush420"), ("Light14","Brush420"),
     ("Brush766","Brush420"), ("Brush364","Brush420"), ("Brush873","Brush420"),
     ("Brush592","Brush420"), ("Light149","Brush420"), ("Vase3","Brush420"),
     ("Vase4","Brush420"), ("BookClosed1","Brush420"), ("NanoKey0","Brush420"),
     ("WeaponModRecoil0","Brush420"),
     ("FlagPole3","Brush420"), ("FlagPole4","Brush418"),
     ("Brush663","Brush418"), ("Brush1","Brush418"), ("Brush138","Brush418"),
     ("Brush140","Brush418"), ("Brush148","Brush418"), ("Brush164","Brush418"),
     ("Brush168","Brush418"), ("Brush1158","Brush418"), ("Brush1550","Brush418"),
     ("Brush1551","Brush418"), ("OrdersTrigger5","Brush418"), ("Light6","Brush418"),
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
     dict(actor="Brush418", kind="brush_vertex_move",
          at=[[128,-288,416],[448,-288,416],[448,64,416],[128,64,416]], task_delta=[0,0,48]),
     dict(actor="Brush420", kind="brush_vertex_move",
          at=[[-96,64,416],[448,64,416],[448,304,416],[-96,304,416]], task_delta=[0,0,48]),
   ],
   dependents=[
     ("Brush285","Brush418"), ("Brush295","Brush418"), ("Brush132","Brush418"), ("Brush74","Brush418"),
     ("Brush284","Brush420"),
   ],
   unchanged=["Brush663","Light156","Light103","Light318","Light86","Light120"],
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

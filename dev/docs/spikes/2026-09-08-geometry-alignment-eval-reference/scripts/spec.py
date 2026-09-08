"""Single source of truth: for each task, a flat list of ENTRIES, each an
acceptance criterion in one of four kinds -- the closed vocabulary every
uedcli geometry verb's RESULT reduces to (move/resize/clip/scale/rotate all
just produce some final property/shape value; only existence is different):

  anchor  X to Y [, props]   -- X's delta on `props` (default Location, or a
                                 brush's named corners) must equal Y's ACTUAL
                                 delta in the trunk being graded -- not a
                                 hardcoded number, so "the flagpole is
                                 broken" stays distinguishable from "the wall
                                 itself moved by the wrong amount."
  update  X with props Y=Z   -- X's `props` must equal an ABSOLUTE target:
                                 a task-pinned value (e.g. "+48 east" on
                                 specific corners), "= baseline" (unchanged),
                                 or a full resulting shape for a non-delta
                                 change (clip, scale, resize) -- stored as
                                 the real T3D `Begin Brush...End Brush` block
                                 (what `actor show` already dumps and
                                 `brush replace` already consumes), not a
                                 parallel vertex/poly format.
  create  X: class Y, props Z=U [, geometry] -- a NEW actor must exist,
                                 not present in the baseline, of class Y with
                                 matching props (and full geometry for a
                                 brush). Graded by SEARCH (no fixed name to
                                 look up), not a lookup -- the one kind that
                                 genuinely differs in mechanism from the rest.
  delete  X                  -- X must no longer exist. Trivial.

Grading cares about the RESULT, not how an agent got there -- every entry
carries a `why`: plain language, not consumed by the mechanical check, but
surfaced by check_trunk.py under every FAILURE, so a mechanical fail is a
prompt to check whether the intent was satisfied some other way, not an
automatic hard fail.

`create`/`delete` and `update`'s full-geometry form are DOCUMENTED here as
the agreed vocabulary; neither current task exercises them (both are pure
corner translations, fully covered by `update`'s at+delta form and `anchor`'s
relative-delta form) -- implemented in check_trunk.py only when a real task
needs one, not speculatively.
"""

TASKS = {
 "t1": dict(
   base_trunk="unatco_gt",
   entries=[
     dict(kind="update", actor="Brush418", target="corners", at=[[448,-288,416],[448,64,416],[448,64,240],[448,-288,240]], delta=[48,0,0],
          why="south wall of Manderley's office; the task's own east-widen target"),
     dict(kind="update", actor="Brush420", target="corners", at=[[448,64,416],[448,304,416],[448,304,240],[448,64,240]], delta=[48,0,0],
          why="north wall of Manderley's office, shares the east wall with Brush418 at the y=64 seam -- must widen the same amount or the wall steps"),

     dict(kind="anchor", actor="Brush670", to="Brush418", why="switch recess, cut into the south wall"),
     dict(kind="anchor", actor="Brush161", to="Brush418", why="south wall trim board"),
     dict(kind="anchor", actor="Brush132", to="Brush418", why="south wall trim board"),
     dict(kind="anchor", actor="Brush203", to="Brush418", why="south wall trim board"),
     dict(kind="anchor", actor="Brush74", to="Brush418", why="south wall trim board"),
     dict(kind="anchor", actor="Brush152", to="Brush418", why="south wall fixture"),
     dict(kind="anchor", actor="Switch6", to="Brush418", why="the wall light switch itself, mounted in Brush670's recess"),
     dict(kind="anchor", actor="Brush869", to="Brush420", why="decorative pilaster on the north wall"),
     dict(kind="anchor", actor="Light14", to="Brush420", why="the pilaster's own light"),
     dict(kind="anchor", actor="Brush766", to="Brush420", why="wall cavity holding the trophy shelf + hidden safe, cut into the north wall"),
     dict(kind="anchor", actor="Brush364", to="Brush420", why="the safe's own interior geometry inside the cavity"),
     dict(kind="anchor", actor="Brush873", to="Brush420", why="the safe's own back panel inside the cavity -- moving the cavity without this orphans it mid-room (the original bug this eval caught)"),
     dict(kind="anchor", actor="Brush592", to="Brush420", why="the display shelf inside the cavity"),
     dict(kind="anchor", actor="Light149", to="Brush420", why="the shelf's own light"),
     dict(kind="anchor", actor="Vase3", to="Brush420", why="display item on the shelf"),
     dict(kind="anchor", actor="Vase4", to="Brush420", why="display item on the shelf"),
     dict(kind="anchor", actor="BookClosed1", to="Brush420", why="display item on the shelf"),
     dict(kind="anchor", actor="NanoKey0", to="Brush420", why="display item on the shelf"),
     dict(kind="anchor", actor="WeaponModRecoil0", to="Brush420", why="display item on the shelf"),
     dict(kind="anchor", actor="FlagPole3", to="Brush420", why="ceremonial flagpole anchored to the north wall's corner (~48u off two adjacent walls, not flush-mounted)"),
     dict(kind="anchor", actor="FlagPole4", to="Brush418", why="ceremonial flagpole anchored to the south wall's corner"),
     dict(kind="anchor", actor="Brush663", to="Brush418", why="the display niche -- a genuinely separate small room built against the south wall, must stay flush against it"),
     dict(kind="anchor", actor="Brush1", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush138", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush140", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush148", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush164", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush168", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush1158", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush1550", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="Brush1551", to="Brush418", why="niche interior detail brush"),
     dict(kind="anchor", actor="OrdersTrigger5", to="Brush418", why="scripted trigger inside the niche"),
     dict(kind="anchor", actor="Light6", to="Brush418", why="the niche's own light"),
   ],
   # scenario grouping for the human-readable page -- display only, does not affect grading
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

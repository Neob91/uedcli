"""Defines and writes every aspect diff JSON under ../diffs/. This is the
single source of truth for what "correct" means, per aspect, for the UNATCO
widen/ceiling tasks -- edit here, then re-run scripts/render_from_diff.py to
regenerate every picture from the new diffs. Never hand-edit a diffs/*.json
or a picture directly.
"""
import json, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "diffs"
OUT.mkdir(parents=True, exist_ok=True)

ASPECTS = [
 dict(id="t1_wall", task="t1", title="East wall (both halves of the room)", view="top",
   note="The office is built from two wall volumes sharing one wall. Both must move out together, or the wall gets a step in it.",
   ops=[
    dict(kind="brush_vertex_move", actor="Brush418",
         at=[[448,-288,416],[448,64,416],[448,64,240],[448,-288,240]], by=[48,0,0]),
    dict(kind="brush_vertex_move", actor="Brush420",
         at=[[448,64,416],[448,304,416],[448,304,240],[448,64,240]], by=[48,0,0]),
   ]),
 dict(id="t1_fixtures", task="t1", title="Wall-mounted fixtures (switch, trim, pilaster)", view="top",
   note="The wall's own hardware — a light switch, its recessed panel, corner trim boards, and a decorative pilaster — are physically part of the wall.",
   ops=[dict(kind="actor_move",
             actors=["Brush670","Brush161","Brush132","Brush203","Brush74","Brush152","Brush869","Light14","Switch6"],
             by=[48,0,0])]),
 dict(id="t1_safe", task="t1", title="Trophy shelf with a hidden wall safe", view="top",
   note="A wall-mounted display shelf has a real hidden safe built into its back. The whole unit and its contents must move together.",
   ops=[dict(kind="actor_move",
             actors=["Brush766","Brush364","Brush873","Brush592","Light149","Vase3","Vase4","BookClosed1","NanoKey0","WeaponModRecoil0"],
             by=[48,0,0])]),
 dict(id="t1_flags", task="t1", title="Corner flagpoles", view="top",
   note="Two ceremonial flagpoles each stand a fixed distance from two adjacent walls, planted in the room's corners. Both must move to stay in their corners.",
   ops=[dict(kind="actor_move", actors=["FlagPole3","FlagPole4"], by=[48,0,0])]),
 dict(id="t1_niche", task="t1", title="Display niche (a separate small room)", view="top",
   note="This niche is a genuinely separate small room, not part of the wall itself. It must move so it stays flush against the wall.",
   ops=[dict(kind="actor_move",
             actors=["Brush663","Brush1","Brush138","Brush140","Brush148","Brush164","Brush168","Brush1158","Brush1550","Brush1551","OrdersTrigger5","Light6"],
             by=[48,0,0])]),

 dict(id="t2_ceil", task="t2", title="Ceiling (both halves of the room)", view="side",
   note="Like the east wall, the ceiling spans two wall volumes sharing one surface. Both must rise together, or the ceiling gets a step in it.",
   ops=[
    dict(kind="brush_vertex_move", actor="Brush418",
         at=[[128,-288,416],[448,-288,416],[448,64,416],[128,64,416]], by=[0,0,48]),
    dict(kind="brush_vertex_move", actor="Brush420",
         at=[[-96,64,416],[448,64,416],[448,304,416],[-96,304,416]], by=[0,0,48]),
   ]),
 dict(id="t2_fixtures", task="t2", title="Ceiling-mounted fixtures (light panels, trim)", view="side",
   note="Three recessed light panels and two corner trim caps are physically set into the ceiling surface. They must rise with it.",
   ops=[dict(kind="actor_move", actors=["Brush285","Brush295","Brush284","Brush132","Brush74"], by=[0,0,48])]),
 dict(id="t2_niche", task="t2", title="Niche ceiling", view="side",
   note="The niche is its own separate room with its own ceiling. It's expected to keep its own height and not match the office's new one.",
   ops=[dict(kind="assert_unchanged", actors=["Brush663"])]),
 dict(id="t2_lights", task="t2", title="Overhead room lights", view="side",
   note="Every light sits the same distance below its ceiling, room-wide — a fixed convention, not a mount to the ceiling surface. They must stay put.",
   ops=[dict(kind="assert_unchanged", actors=["Light156","Light103","Light318","Light86","Light120"])]),
]

FULL_BASE_TRUNK = "unatco_gt"
FULLS = {
 "t1_full": [a for a in ASPECTS if a["task"] == "t1"],
 "t2_full": [a for a in ASPECTS if a["task"] == "t2"],
}

if __name__ == "__main__":
    for aspect_id, aspects in FULLS.items():
        ops = [op for a in aspects for op in a["ops"] if op["kind"] != "assert_unchanged"]
        (OUT / f"{aspect_id}.json").write_text(json.dumps(
            dict(id=aspect_id, base_trunk=FULL_BASE_TRUNK, ops=ops), indent=2) + "\n")
        print("wrote", aspect_id, "(full) ->", len(ops), "ops")

    for a in ASPECTS:
        a["base_trunk"] = FULL_BASE_TRUNK
        a["render_from"] = f"{a['task']}_full"
        a["highlight"] = [n for op in a["ops"] for n in op.get("actors", [op.get("actor")])]
        (OUT / f"{a['id']}.json").write_text(json.dumps(a, indent=2) + "\n")
        print("wrote", a["id"], "->", len(a["highlight"]), "actors, renders from", a["render_from"])

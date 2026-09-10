"""Task: raise the bar's ceiling (NYC_Bar) -- see ../spec_format.py for the
entry-kind vocabulary this file uses.
"""

TASK = dict(
 id="nyc_bar_ceiling", level="bar",
 title="Raise the bar's ceiling",
 req="&ldquo;This bar (Brush1) feels cramped. Raise its ceiling by 48 units.&rdquo;",
 base_trunk="nyc_bar_gt",
 photo_camera=dict(at=[-1024,0,100], pitch=4096),
 before=dict(
   quad="before_quad",
   note="Built from two volumes sharing one ceiling: the main hall (Brush1) and a side alcove (Brush15), coplanar at z=256 across their shared y=-384 seam. 13 hanging DeusEx.HKMarketLight lanterns sit below it at two fixed offsets, not recessed into it.",
   photos=[f"pan_before_{i}" for i in range(8)]),
 entries=[
   dict(kind="update", actor="Brush1", target="corners",
        at=[[-2048,-384,304],[0,-384,304],[0,384,304],[-2048,384,304]], delta=[0,0,48],
        what="main hall's ceiling face; the task's own raise-ceiling target"),
   dict(kind="update", actor="Brush15", target="corners",
        at=[[-1024,-640,304],[-256,-640,304],[-256,-384,304],[-1024,-384,304]], delta=[0,0,48],
        what="alcove's ceiling face, coplanar with Brush1's at the y=-384 seam -- must rise the same amount or the ceiling steps"),

   dict(kind="anchor", actor="HKMarketLight2", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight3", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight4", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight5", to="Brush1", what="hanging lantern, fixed ~8u below ceiling (shorter cord)"),
   dict(kind="anchor", actor="HKMarketLight15", to="Brush1", what="hanging lantern, fixed ~8u below ceiling (shorter cord)"),
   dict(kind="anchor", actor="HKMarketLight17", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight18", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight20", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight21", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight24", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight25", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight13", to="Brush1", what="hanging lantern, fixed ~24u below ceiling"),
   dict(kind="anchor", actor="HKMarketLight8", to="Brush15", what="hanging lantern over the alcove, fixed ~24u below its own ceiling"),
 ])

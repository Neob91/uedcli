"""Task: add a sixth bar stool to NYC_Bar's counter -- see ../spec_format.py
for the entry-kind vocabulary this file uses.
"""

TASK = dict(
 id="nyc_bar_stool", level="bar",
 title="One more stool",
 req="&ldquo;The bar counter Brush70 could use one more stool at its west end. Extend the counter westward and add a matching stool to continue the row.&rdquo;",
 dx_map="02_NYC_Bar",
 photo_camera=dict(at=[-700,-300,60], pitch=0),
 before=dict(
   quad="before_quad",
   note="The counter (Brush70) runs X[-896,-384], already carrying 5 evenly-spaced stools (112 units apart) with no gap -- the row is full; extending the counter is the only way to add a sixth.",
   photos=[f"pan_before_{i}" for i in range(8)]),
 entries=[
   dict(kind="update", actor="Brush70", target="corners",
        at=[[-1008,-512,16],[-1008,-448,16],[-1008,-448,48],[-1008,-512,48]], delta=[-112,0,0],
        what="bar counter's west face; must extend 112 units west to make room, without disturbing its top or east end"),
 ])

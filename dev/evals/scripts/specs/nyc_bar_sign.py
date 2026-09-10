"""Task: hang a second matching bar sign in NYC_Bar -- see ../spec_format.py
for the entry-kind vocabulary this file uses.
"""

TASK = dict(
 id="nyc_bar_sign", level="bar",
 title="Hang a matching bar sign",
 req="&ldquo;There&rsquo;s a sign, Brush111, on the wall. Put a matching one further down that same wall.&rdquo;",
 dx_map="02_NYC_Bar",
 photo_camera=dict(at=[-800,-500,150], pitch=0),
 before=dict(
   quad="before_quad",
   note="The existing bar sign (Brush109/110/111) hangs on the alcove's (Brush15) west wall, the x=-1024 plane, near its south corner.",
   photos=[f"pan_before_{i}" for i in range(8)]),
 entries=[
   dict(kind="create", actor="Brush111",
        what="a second matching bar sign (mount bracket + niche + sign board, same NYCBar.Misc.BarSign_Bb texture) further down the same wall, away from the existing one near the south corner"),
 ])

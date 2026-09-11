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
 # No update/anchor entries -- this task is pure creation, nothing for build_gold.py to apply.
 # Brush111 here is only a frame anchor for the "before" whole-room shot (render_before has no
 # touched-actor diff to frame around yet, since there's no execution); it's also shown as a
 # `what` label if a diffed execution happens to touch Brush111 itself.
 entries=[dict(actor="Brush111", what="the existing bar sign, for reference/orientation")])

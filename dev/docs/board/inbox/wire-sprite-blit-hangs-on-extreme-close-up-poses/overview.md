+++
priority = "p2"
kind = "debug"
summary = "level photo --faces wire: a point-actor sprite very close to the camera blits pw×ph in pure Python and appears to hang."
+++

# Wire sprite blit hangs on extreme close-up poses

`preview_wire._render_frame` sizes a point-actor billboard as `pw = sprite_world * focal / depth`
(perspective). As the camera nears a point actor, `depth → NEAR` (4 uu), so `pw`/`ph` grow without
bound. `preview._blit` then runs a pure-Python `pw × ph` nested loop, `_px`-clipping most pixels.

Example: a 256×256 sprite at `DrawScale` 1 → `sprite_world` 256 uu; at 1280 wide / fov 75 the focal
is ~834 px; at depth 4 that is `pw ≈ 53000`, so `pw × ph ≈ 2.8e9` iterations — minutes of CPU, which
reads as a crash. Output stays correct (the on-screen pixels are right); only runtime is the problem.

New with the wire path: the Rust textured tier draws no point actors, and ortho `actor diagram` is
bounded by auto-fit framing, so neither hits this. Only reachable when a shot is authored a few uu
from a point actor with a large sprite (`at:`/`orbit:radius:` very small).

Fix candidate (cheap): clamp `pw`/`ph` to a small multiple of the frame size before `_blit` — every
pixel beyond the frame is `_px`-clipped anyway, so the visible result is unchanged. Confirm the clamp
keeps the sprite centred and does not distort aspect. See code in `uedcli/preview_wire.py`
(`_render_frame`) and `uedcli/preview.py` (`_blit`).

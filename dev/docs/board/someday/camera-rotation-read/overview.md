+++
priority = "p?"
kind = "implement"
summary = "Camera rotation READ (`camera get-rotation`-style verb)"
+++

# Camera rotation READ (`camera get-rotation`-style verb)

SET is done
(`level preview --rotate`). This is the remaining piece: report the live camera's current rotation
without the caller already knowing it. Known avenue: parse the camera `Rotation` out of a `MAP
SAVE`'d binary `.dx` (verified parser: `dev/docs/spikes/camera-rotation/parse_dx_camera.py`). NOTE: `JUMPTO
X,Y,Z` centers viewports on a coordinate — a direct camera-position verb is cheap to retest.

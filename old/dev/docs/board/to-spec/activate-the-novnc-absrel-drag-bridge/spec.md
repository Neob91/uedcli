# Spec — activate the noVNC abs→rel drag bridge on the standing editor

## Goal

Make the (already-built) abs→rel drag bridge actually run on the standing `dx-lum-uned` editor, so a
browser RMB-drag rotates the viewport at a sane rate instead of slamming the camera.

## Current state

- Bridge code is done and in the image: `uned/vnc_input_bridge.py`, wired at `uned/entrypoint.sh:56`
  as `x11vnc -pipeinput "python3 /opt/uned/vnc_input_bridge.py"`.
- It is gated at `uned/entrypoint.sh:46` on `VNC_VIEW_ONLY != 1`; the default is `1` (viewonly), which
  omits `-pipeinput` entirely.
- A running container only reflects the entrypoint/image it last started with. `dx-lum-uned` was not
  recreated after the 2026-06-22 image rebuild, so it is not injecting through the bridge.

## Approach

No code change — operational only. When no session is mid-drive, recreate the standing editor with the
bridge active:

- `docker compose up -d --force-recreate` for the `dx-lum-uned` service, with `VNC_VIEW_ONLY=0` so the
  `-pipeinput` branch is taken.
- Re-confirm in a real browser that an RMB-drag rotates smoothly (no unbounded over-rotation).

## Test

None — manual browser verification; the bridge itself already has its findings doc
(`dev/docs/specs/2026-06-18-uedcli-viewport-drag-sensitivity-findings.md`).

## Open questions

None.

+++
priority = "p3"
kind = "debug"
summary = "After the zone-retire + frustum-cone ports, native's gather runs exactly the editor's 1218 box tests on OceanLab N=48, but 45 keys differ on each side and 49 of 1173 shared tests disagree -- every one native=hidden, editor=visible."
spikes = ["dev/docs/spikes/2026-09-07-oceanlab-n48-lightbits/"]
+++

# The gather still over-occludes against the live editor

`compare_box_tests.py` on an OceanLab N=48 golden build, native's `UEDCLI_VISGATE_TRACE_BOX` trace
against the live `BoundVisible` capture
(`dev/docs/spikes/2026-09-07-oceanlab-n48-lightbits/logs/frame-probe-n48.log`):

    native 1218 tests / 1218 keys; editor 1218 / 1218 keys
    matched keys 1173, agreeing 1124, native-only 45, editor-only 45

The counts now match (they were 1458 vs 1218 before the zone-retire port), and the resulting
`NF_BoxOccluded` set matches the live editor exactly on this build — so nothing OceanLab N=48
depends on is wrong. But 49 shared tests still disagree, **every one `native = hidden,
editor = visible`**, and each side reaches 45 nodes the other does not.

The direction is uniform, so the suspect is span-buffer content: native's rasterizer claims more
screen area than the editor's, which makes `FSpanBuffer::BoxIsVisible` answer "hidden" earlier and
shifts which subtrees the traversal reaches. That is the same family as
`wanchai-n45-spotlight22-light-runs-differ-on-4` (the `ClipBspSurf` / fixed-point scanline port),
and the OceanLab capture is a much smaller reproducer for it than WanChai's.

## Repro

    RAYON_NUM_THREADS=1 UEDCLI_VISGATE_TRACE_BOX=1 <native build of OceanLab N=48>  2> trace.log
    dev/docs/spikes/2026-09-06-boundvisible-port/harness/parse_frame_probe.py \
        dev/docs/spikes/2026-09-07-oceanlab-n48-lightbits/logs/frame-probe-n48.log --json bv.json
    dev/docs/spikes/2026-09-06-boundvisible-port/harness/compare_box_tests.py trace.log bv.json

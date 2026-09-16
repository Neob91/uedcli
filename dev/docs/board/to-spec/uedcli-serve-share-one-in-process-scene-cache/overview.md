+++
priority = "p1"
kind = "implement"
summary = "uedcli serve: share one in-process scene cache across /scene, /atlas, /lightmap"
+++

# uedcli serve: share one in-process scene cache across /scene, /atlas, /lightmap

Fixed a real production failure (2026-09-14): loading the GUI against the WanChai level (2288
actors) via a cloudflared tunnel failed with a tunnel timeout on `/api/level/WanChai/atlas` —
measured at **2m44s** for that one request. Cloudflare's free quick tunnels cut off at ~100s, so
this is a real, user-facing outage on any level of meaningful size, not just a slowness complaint.

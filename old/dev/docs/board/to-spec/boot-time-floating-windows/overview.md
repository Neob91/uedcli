+++
priority = "p3"
kind = "chore"
summary = "Boot-time floating windows (Log Window / Textures browser / boot-time `xmessage`) still cover the panes"
+++

# Boot-time floating windows (Log Window / Textures browser / boot-time `xmessage`) still cover the panes

Apply the fix in `unrealed/rendering.md`: drop `-log` from
`entrypoint.sh` + set `X=2000`/`Y=2000` on every `[* Browser]` ini section.

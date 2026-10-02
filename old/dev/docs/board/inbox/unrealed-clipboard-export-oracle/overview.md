+++
priority = "p2"
kind = "implement"
summary = "The second export oracle - UnrealEd plus SELECT ALL and EDIT COPY - has not been run; it is a different engine code path."
+++

# The second oracle the owner asked for — UnrealEd + `SELECT ALL` + `EDIT COPY` — has NOT been run

The first one has: `UCC batchexport` from the v69 UED22 substrate now works on this
machine (an amd64 image built under emulation on aarch64 — `docker build --platform linux/amd64` of
`uned/Dockerfile`; wine and UCC run fine), and it settled the `Actors`-array question decisively
(`unrealed/package-format.md` "The `Actors` array is the AUTHORITY"). The clipboard route is a
DIFFERENT code path in the engine and may differ from `MAP EXPORT` — it needs the GUI editor driven
live (Xvfb + `xdotool`/`wine_ctl.py` + `xclip`), which was not attempted. Worth doing: it is the
path `EDIT PASTE`-based materialize actually round-trips through.

*Carried over from the `installer-url` branch, whose `inbox.md` addition the board migration had already deleted.*

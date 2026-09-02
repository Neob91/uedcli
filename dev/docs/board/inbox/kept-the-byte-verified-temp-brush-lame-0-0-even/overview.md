+++
priority = "p3"
kind = "owner-question"
summary = "Kept the byte-verified temp-brush `LAME/0/0` even though it doesn't fix N=33"
+++

# Kept the byte-verified temp-brush `LAME/0/0` even though it doesn't fix N=33

`build_brush_temp_bsp` now builds with `Opt=LAME, Balance=0, PortalBias=0` (the value the binary
actually pushes — `findbestsplit-params-decode.md §4`), replacing the historical `OPTIMAL/50/70`.
It is **exactly soup-neutral** (full-castle `onlyN=21/onlyE=15`, nodes `1171`, surfs `485` — same
as before; verified by flipping the config). I kept it because it matches the binary and the repo
rule says code should reflect verified engine facts; the task had said "revert if the hypothesis is
wrong." If you'd rather this session touch no functional param, revert the three `bspcsg.rs` hunks
(`TEMP_BALANCE`/`TEMP_PORTAL_BIAS` → `50/70`, `Opt::Lame` → the old stride-1) — it changes no output.

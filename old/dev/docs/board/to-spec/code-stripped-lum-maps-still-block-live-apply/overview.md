+++
priority = "p3"
kind = "implement"
summary = "Code-stripped LUM maps still block live `apply`"
+++

# Code-stripped LUM maps still block live `apply`

Base-content maps run
(DONE 2026-06-20), but code-stripped maps stay blocked — LUM mission maps need a recompiled
`LUM_Core.u`; `20_Lenz` + the 5 retail cinematics need un-stripped
`Engine.CameraPoint`/`DeusEx.DeusExDecoration.BeginPlay`. (Package stubbing covers v68 code deps;
the cinematics' stripped *engine* symbols and first-party `LUM_Core.u` remain out of scope.)

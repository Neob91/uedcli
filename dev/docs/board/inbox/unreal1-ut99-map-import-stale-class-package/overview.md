+++
priority = "p3"
kind = "debug"
summary = "Unreal1/UT99 map import: stale class-package hints (UnrealI vs UnrealShare)"
+++

# Unreal1/UT99 map import: stale class-package hints (UnrealI vs UnrealShare)

`level import` on an original (1998/Gold) Unreal `.unr` fails every map tried (8/8: `Bluff`,
`DmDeck16`, `DmCurse`, `DmMorbias`, `DmTundra`, `Dig`, `Dark`, `DasaPass`) with `SchemaError: ...
the Level Actors array names <Actor>, whose class UnrealI.<Class> does not descend from
Engine.Actor`. Whether a UT99 map hits the same thing is UNTESTED (no UT99 `.unr` files pulled this
session) — UT99's own `UnrealI.u`/`UnrealShare.u` were re-exported at some point and no longer carry
the sibling `RemapAnimVerts` issue this was found alongside, so its map import tables may equally
have been re-qualified and not need this fallback at all.

Root cause: the map's own import table states the class's home package as `UnrealI`, but the
shipped System files actually define the class in `UnrealShare.u` (`Eightball`, `ASMD`, `Barrel`,
`Tentacle`, `NaliFruit`, `TriggerLight`, ... — a different class every map). This is genuine
content, not corruption — every map on the authoritative archive.org Unreal Gold ISO hits it, so
the real engine must resolve it leniently (an import whose stated package doesn't have the class
falls back to a global by-name lookup, matching how UE1 registers native classes).

`mapimport.py::_is_actor_export` (the pre-render validation gate) does the exact-package check
only; it has no fallback. `ClassIndex.bare_to_fqcn()` already builds the whole-index by-name lookup
`qualify_and_validate`/`_qualify_bare` uses for T3D's own bare `Class=` lines, so the fix is
probably: on an exact-match miss, fall back to `bare_to_fqcn()`, preferring a match in
`UnrealShare` on an ambiguous collision (observed: `TriggerLight` exists in both `Engine` and
`UnrealShare`; every real redirect found so far lands in `UnrealShare`) before raising.

Verified as a real, working fallback in a throwaway script (not committed) — monkeypatching
`_is_actor_export` this way got `Bluff.unr` past the actor-descent gate. Not implemented in
production code: it's a change to a validation function shared by every substrate (DX/UT99/
Unreal1), so it needs its own scoped change + tests + review, not folded into the mesh-parsing fix
(`RemapAnimVerts`/`OldFrameVerts`, `uedcli/umesh.py`) this was found alongside.

Scope note: getting past this gate is necessary but likely not sufficient for a full level
screenshot — `brush_of`'s model/BSP decode (`uedcli/native/umodel.py`, docstring says "Serial order
(ver > 61)") has never been extended to package v61 (Unreal Gold's map version, older than DX's
v69/UT99's v6x), so `level import` still won't produce brush geometry for these maps even once
class resolution is fixed. That is a separate, larger RE gap (older BSP/model struct layout),
not scoped here.

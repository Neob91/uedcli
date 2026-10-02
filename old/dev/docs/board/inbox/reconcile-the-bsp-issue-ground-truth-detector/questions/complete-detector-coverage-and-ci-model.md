# What must the "complete detector" cover, and is its output a CI tripwire or located findings?

## Context

The spec's coverage claim is "every issue class EXCEPT silent-absence, on the real editor build,"
hedged throughout. Two things changed that pin: the native offline build now exists, so re-running
CSG and diffing authored faces against built surfs (silent-absence detection) is reachable offline
— the one class the spec pushed out of D0/D1. And the static `level doctor` (`doctor.py`) already
emits located per-finding output (severity, brush, poly, coord).

Decisions for the owner:
- Coverage: is silent-absence (should-vs-did) IN scope for this detector item, or explicitly the
  boundary with the D2 item (`d2-fully-offline-bsp-csg-collision-engine`)?
- Output shape: a counts-only CI tripwire (exit non-zero on a regression, no locations), or located
  findings with coord/brush like the static doctor? The spec proposes counts-only for the editor
  tier and located for the built tier; the native build can now give located findings for both.
- Verb surface: one `level doctor` with mode flags, or distinct verbs per tier.

Recommendation: located findings over the native build, unified under `level doctor` with a mode
flag; silent-absence named as the explicit boundary handed to the D2 item, not silently absorbed.

## Answer

<!-- Empty = open. -->

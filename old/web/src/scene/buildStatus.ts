// The `buildSolved` signal Task 18's `isModeAvailable` gates on (quad-layout Part 4, Task 19).
//
// Deviation from the plan (flagged, not silent): the plan wrote this as a stub --
// `useBuildStatus(level): boolean` hardcoded to `true`, pending the separate
// gui-explicit-rebuild-pinned-build-state-mode item's real signal, which hadn't landed when the
// plan was written. That item HAS since landed on master: `App.tsx` already fetches/polls
// `GET /api/level/{level}/status` (`StatusPayload.geometry_pinned`) for the Load/Rebuild toolbar --
// this is the literal, already-real "buildSolved" signal (app.py's own `/status` route comment:
// "geometry_pinned is the literal mode-gate condition"). So this is a pure DERIVATION of App.tsx's
// existing status state, not a second independent fetch/hook -- naming it `useBuildStatus` (a hook
// with its own fetching) would have been actively wrong now that the real data already exists one
// render up.
import type { StatusPayload } from '../api'

/** Whether shading modes beyond wireframe are unlocked for the current level. */
export function resolveBuildSolved(status: StatusPayload | null): boolean {
  return status?.geometry_pinned ?? false
}

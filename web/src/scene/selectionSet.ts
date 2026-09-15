// Pure multi-select membership logic (quad-layout Part 3, Task 12, spec §9): a plain tap REPLACES
// the selection; Ctrl+tap TOGGLES one actor's membership; Esc is the only way to clear it entirely.

/** `additive=false`: REPLACE the set with exactly `{name}` (a plain tap's semantics), regardless of
 * what was previously selected -- including a re-tap of the sole already-selected actor (a no-op
 * reselect, not a toggle-off). `additive=true`: toggle `name`'s membership in `current` (add if
 * absent, remove if present -- Ctrl+tap's "multi-selects" semantics). */
export function toggleSelection(current: ReadonlySet<string>, name: string, additive: boolean): Set<string> {
  if (!additive) return new Set([name])
  const next = new Set(current)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  return next
}

/** `Esc`'s semantics: always an empty set. Named so callers read as intent rather than inlining
 * `new Set()` at each call site. */
export function clearSelection(): Set<string> {
  return new Set()
}

/** The "primary" (most-recently-selected) actor, or undefined for an empty selection --
 * UED22's real pivot widget drops onto whichever actor a human click lands on (one widget per
 * SELECTION, never one per actor; `dev/docs/spikes/2026-06-19-multiactor-rotate-groundtruth.md`
 * "Pivot caveat"). A `Set`'s iteration order is insertion order, and `toggleSelection` always
 * appends a freshly-added name at the end, so the last element stands in for "last clicked." */
export function primarySelection(selectedNames: ReadonlySet<string>): string | undefined {
  return [...selectedNames].at(-1)
}

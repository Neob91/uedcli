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

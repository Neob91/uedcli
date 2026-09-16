// Pure quad-layout maximize/restore state (quad-layout Part 1, Task 7). The grid RENDERING itself
// is pure layout CSS (QuadLayout.tsx) -- this is the one piece of logic worth pinning with a test.
export type PaneId = 'perspective' | 'top' | 'front' | 'side'

/** Double-click toggle: double-clicking the currently-maximized pane restores the 2x2 grid (`null`);
 * double-clicking a DIFFERENT pane while one is maximized switches the maximized pane to the clicked
 * one (a judgment call -- the spec doesn't say, flagged in the plan's Open Questions); double-
 * clicking any pane when none is maximized maximizes it. */
export function toggleMaximize(current: PaneId | null, clicked: PaneId): PaneId | null {
  if (current === clicked) return null
  return clicked
}

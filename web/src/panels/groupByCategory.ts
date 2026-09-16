// Split out of Inspector.tsx (which also exports the Inspector COMPONENT) so that file exports only
// components -- Vite's react-refresh plugin can't Fast Refresh a file that mixes a component export
// with a plain function export ("X export is incompatible"), which silently wedges a pane on the
// next HMR update until a full page reload (the same failure class that broke point-actor rendering
// this session -- see viewportRender.ts's module comment).

// Groups props[i] under categories[i], preserving first-occurrence category order and
// within-category prop order (both already stored/T3D order). A length mismatch is a boundary
// invariant violation (the backend guarantees props.length === categories.length), not a
// recoverable UI state.
export function groupByCategory(
  props: [string, string][],
  categories: string[],
): Map<string, [string, string][]> {
  if (props.length !== categories.length) {
    throw new Error(`groupByCategory: props.length (${props.length}) !== categories.length (${categories.length})`)
  }
  const groups = new Map<string, [string, string][]>()
  props.forEach((prop, i) => {
    const category = categories[i]
    const rows = groups.get(category)
    if (rows) {
      rows.push(prop)
    } else {
      groups.set(category, [prop])
    }
  })
  return groups
}

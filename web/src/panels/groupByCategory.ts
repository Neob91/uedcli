// Split out of Inspector.tsx (which also exports the Inspector COMPONENT) so that file exports only
// components -- Vite's react-refresh plugin can't Fast Refresh a file that mixes a component export
// with a plain function export ("X export is incompatible"), which silently wedges a pane on the
// next HMR update until a full page reload (the same failure class that broke point-actor rendering
// this session -- see viewportRender.ts's module comment).
import type { EffectiveProp } from '../api'

// Groups props by each prop's own `.category` field, preserving first-occurrence category order
// and within-category prop order (both already stored/T3D order).
export function groupByCategory(props: EffectiveProp[]): Map<string, EffectiveProp[]> {
  const groups = new Map<string, EffectiveProp[]>()
  for (const prop of props) {
    const rows = groups.get(prop.category)
    if (rows) {
      rows.push(prop)
    } else {
      groups.set(prop.category, [prop])
    }
  }
  return groups
}

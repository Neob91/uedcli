// Read-only property inspector (spec, "Selection & inspector"): name/class/transform/folder/
// labels/order_value, then the full raw T3D property set grouped into UnrealEd-style categories
// as collapsible sections (SceneActor.categories, parallel to .props). Draws only what it's
// handed -- no model/diff logic here.
import type { SceneActor } from '../api'

export interface InspectorProps {
  actor: SceneActor | null
}

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

export function Inspector({ actor }: InspectorProps) {
  if (!actor) {
    return (
      <div className="inspector inspector-empty" data-testid="inspector-empty">
        No selection
      </div>
    )
  }

  return (
    <div className="inspector" data-testid="inspector">
      <h2>{actor.name}</h2>
      <dl>
        <dt>Class</dt>
        <dd>{actor.cls}</dd>
        <dt>Location</dt>
        <dd>{actor.location.map((c) => c.toFixed(2)).join(', ')}</dd>
        <dt>Rotation</dt>
        <dd>{actor.rotation.join(', ')}</dd>
        <dt>Folder</dt>
        <dd>{actor.folder ?? '(no folder)'}</dd>
        <dt>Labels</dt>
        <dd>{actor.labels.length > 0 ? actor.labels.join(', ') : '(no label)'}</dd>
        <dt>Order</dt>
        <dd>{actor.order_value}</dd>
      </dl>
      {Array.from(groupByCategory(actor.props, actor.categories)).map(([category, rows]) => (
        <details key={category}>
          <summary>{category} ({rows.length})</summary>
          <table>
            <tbody>
              {rows.map(([key, value], i) => (
                <tr key={`${key}-${i}`}>
                  <td>{key}</td>
                  <td>{value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
    </div>
  )
}

// Read-only property inspector (spec, "Selection & inspector"): name/class/transform/folder/
// labels/order_value, then the full raw T3D property set grouped into UnrealEd-style categories
// as collapsible sections (SceneActor.categories, parallel to .props). Draws only what it's
// handed -- no model/diff logic here.
import type { SceneActor } from '../api'

export interface InspectorProps {
  // 0 selected -> "No selection" (unchanged); exactly 1 -> the full detail view below (unchanged,
  // same markup/testids); 2+ -> a lightweight multi-select summary (Part 3, Task 16). Neither
  // settled main-spec paragraph defines the N-selected view -- this is the simplest thing that
  // satisfies "highlighted ... + inspector" without guessing at a richer multi-actor rollup.
  selected: SceneActor[]
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

export function Inspector({ selected }: InspectorProps) {
  if (selected.length === 0) {
    return (
      <div className="inspector inspector-empty" data-testid="inspector-empty">
        No selection
      </div>
    )
  }

  if (selected.length > 1) {
    return (
      <div className="inspector inspector-multi" data-testid="inspector-multi">
        <h2>{selected.length} actors selected</h2>
        <ul>
          {selected.map((a) => (
            <li key={a.name}>{a.name}</li>
          ))}
        </ul>
      </div>
    )
  }

  const actor = selected[0]
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

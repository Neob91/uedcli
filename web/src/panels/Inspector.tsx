// Read-only property inspector (spec, "Selection & inspector"): name/class/transform/folder/
// labels/order_value, then the full raw T3D property set (collapsible). Draws only what it's
// handed -- no model/diff logic here.
import type { SceneActor } from '../api'

export interface InspectorProps {
  actor: SceneActor | null
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
      <details>
        <summary>Raw properties ({actor.props.length})</summary>
        <table>
          <tbody>
            {actor.props.map(([key, value], i) => (
              <tr key={`${key}-${i}`}>
                <td>{key}</td>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  )
}

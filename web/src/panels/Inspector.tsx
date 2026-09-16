// Read-only property inspector (spec, "Selection & inspector"): name/class/transform/folder/
// labels/csg_rank (the actor's 1-based CSG-order position -- a human-readable stand-in for the
// opaque order_value LexoRank string, which stays off-screen), then the full raw T3D property set
// grouped into UnrealEd-style categories as collapsible sections (SceneActor.categories, parallel
// to .props). Draws only what it's handed -- no model/diff logic here.
import type { ScenePoly, SceneActor } from '../api'
import { surfaceKey } from '../scene/selectionSet'
import { groupByCategory } from './groupByCategory'

/** One selected SURFACE (single polygon) -- GUI.md "Selection & the Inspector": a distinct
 * selection kind from a whole-actor selection (`SceneActor`), owner-answered as "highlight + inspect
 * only," no editing action. `poly` is a representative `ScenePoly` the backend sent for rendering --
 * possibly one of SEVERAL solved fragments sharing this `polyIndex` (CSG can split one authored
 * polygon), any of which carries the same texture/UV/blend data, so any one stands in for the whole
 * authored poly. `polyIndex` is `ScenePoly.i_brush_poly` (`BRUSH:IDX` addressing, `uedcli/surface.py`)
 * -- displayed as `actorName:polyIndex`, the literal CLI-paste form. The Inspector draws `poly`'s
 * fields directly, same "no model logic of its own" convention this component already follows for
 * `SceneActor.props`. */
export interface SurfaceSelection {
  actorName: string
  polyIndex: number
  poly: ScenePoly
}

export interface InspectorProps {
  // 0 selected -> "No selection" (unchanged); exactly 1 -> the full detail view below (unchanged,
  // same markup/testids); 2+ -> a lightweight multi-select summary (Part 3, Task 16). Neither
  // settled main-spec paragraph defines the N-selected view -- this is the simplest thing that
  // satisfies "highlighted ... + inspector" without guessing at a richer multi-actor rollup.
  selected: SceneActor[]
  // The surface-selection counterpart of `selected` above. The two are mutually exclusive at any
  // moment (App.tsx clears one kind's set whenever the other is selected), so at most one of these
  // two props is ever non-empty; `selected` takes rendering priority if both somehow are. Defaults
  // to empty so every existing actor-only call site (tests included) is unaffected.
  selectedSurfaces?: SurfaceSelection[]
}

/** One surface's raw `ScenePoly` fields, in the same "draw what the backend sends" spirit as the
 * actor detail view's own raw-props table below -- no derived texture NAME (the client has no
 * texture-catalog lookup), just what's already on the payload. */
function SurfaceDetail({ actorName, polyIndex, poly }: SurfaceSelection) {
  return (
    <div className="inspector inspector-surface" data-testid="inspector-surface">
      <h2>{actorName}:{polyIndex}</h2>
      <dl>
        <dt>Texture</dt>
        <dd>{poly.tex_index >= 0 ? `#${poly.tex_index}` : '(untextured)'}</dd>
        <dt>Pan</dt>
        <dd>{poly.pan.join(', ')}</dd>
        <dt>Blend</dt>
        <dd>{poly.blend}</dd>
        <dt>Masked</dt>
        <dd>{poly.masked ? 'yes' : 'no'}</dd>
        <dt>Two-sided</dt>
        <dd>{poly.two_sided ? 'yes' : 'no'}</dd>
        <dt>Lit</dt>
        <dd>{poly.lightmap ? 'yes' : 'no'}</dd>
      </dl>
    </div>
  )
}

export function Inspector({ selected, selectedSurfaces = [] }: InspectorProps) {
  if (selected.length === 0 && selectedSurfaces.length === 1) {
    return <SurfaceDetail {...selectedSurfaces[0]} />
  }

  if (selected.length === 0 && selectedSurfaces.length > 1) {
    return (
      <div className="inspector inspector-multi" data-testid="inspector-multi-surfaces">
        <h2>{selectedSurfaces.length} surfaces selected</h2>
        <ul>
          {selectedSurfaces.map(({ actorName, polyIndex }) => (
            <li key={surfaceKey(actorName, polyIndex)}>{actorName}:{polyIndex}</li>
          ))}
        </ul>
      </div>
    )
  }

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
        <dd>{actor.csg_rank}</dd>
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

// Read-only property inspector (spec, "Selection & inspector"): name/class/transform/folder/
// labels/csg_rank (the actor's 1-based CSG-order position -- a human-readable stand-in for the
// opaque order_value LexoRank string, which stays off-screen), then the resolved property set --
// `resolveClass` gives this actor's class shape+defaults (classResolver.ts), `buildDisplayProps`
// walks it against the actor's own sparse `SceneActor.props` (resolveDisplayProps.ts) into the same
// EffectiveProp[] tree grouped into UnrealEd-style categories as collapsible sections, with a
// name-substring search box and an overrides-only/show-all toggle over the same list. Struct/
// array-kind props expand into nested rows (one `<details>` level per struct/array, recursively for
// a struct-of-structs or array-of-structs); `bool` renders a disabled (read-only) checkbox and
// `enum` renders its resolved value as plain text -- the backend already canonicalizes it to the
// tag's own name, so there's no ordinal to look up.
import { useState } from 'react'
import type { AtlasRect, EffectiveProp, ScenePoly, SceneActor } from '../api'
import type { ClassResolveResult } from '../scene/classResolver'
import { surfaceKey } from '../scene/selectionSet'
import { filterOverridesOnly, isExplicit, searchMatch, shownValue } from './effectiveProps'
import { groupByCategory } from './groupByCategory'
import { buildDisplayProps } from './resolveDisplayProps'

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
  // The surface-selection counterpart of `selected` above. Both can be non-empty at once (a Ctrl+tap
  // that crossed kinds -- GUI-PARITY.md "Actor + surface selection coexist"), and then both sections
  // render, actors first. Defaults to empty so every existing actor-only call site is unaffected.
  selectedSurfaces?: SurfaceSelection[]
  // Resolves one actor's class shape+defaults (gui-inspector-props-payload-redesign spec §4) --
  // synchronous, cache-first, 'pending' until the owning package has loaded, an `{error}` for a
  // genuinely unresolvable class. Defaults to a permanently-pending stub so a call site that
  // doesn't care about props content (this file's own multi-select/folder/labels tests) needs no
  // change.
  resolveClass?: (fqcn: string) => ClassResolveResult
  // ScenePayload's companion `/atlas` manifest (AtlasPayload.manifest, keyed by `String(tex_index)`,
  // the SAME lookup convention `geometry.ts`'s `polyUVs` already uses) -- `SurfaceDetail` needs it to
  // resolve a real texture GROUP name instead of a bare `#index`. Reused, not re-fetched: App.tsx
  // already fetches `/atlas` once (for the viewports) and holds it in its own `atlas` state; this
  // prop threads that same object down. Optional/defaulted to `{}` so an existing surface-less or
  // atlas-less call site (this file's own actor-only tests) is unaffected.
  atlasManifest?: Record<string, AtlasRect>
}

/** The texture cell's text: the real texture group name from the atlas manifest, falling back to a
 * bare `#index` when either the poly is untextured (`tex_index === -1`, the existing convention --
 * kept as `(untextured)` rather than `#-1`) or the atlas has no NAME for this index (a mesh-skin
 * entry -- `AtlasRect.name` is `null` there, Task 7). The manifest is keyed by `String(tex_index)`,
 * the same convention `geometry.ts`'s `polyUVs` already uses. */
function textureLabel(poly: ScenePoly, atlasManifest: Record<string, AtlasRect>): string {
  if (poly.tex_index < 0) return '(untextured)'
  return atlasManifest[String(poly.tex_index)]?.name ?? `#${poly.tex_index}`
}

/** One surface's raw `ScenePoly` fields, in the same "draw what the backend sends" spirit as the
 * actor detail view's own raw-props table below. `Texture` resolves a real name via `atlasManifest`
 * (see `textureLabel`); `Area`/`Normal` are floats (unlike `Pan`/`Rotation`, which are integer UU/
 * rotation-unit fields) and are formatted with `.toFixed(2)`, matching `actor.location`'s own
 * convention below and in `ConflictResolver.tsx` -- not shown at their raw ~14-significant-digit
 * precision. */
function SurfaceDetail({ actorName, polyIndex, poly, atlasManifest }: SurfaceSelection & { atlasManifest: Record<string, AtlasRect> }) {
  return (
    <div className="inspector inspector-surface" data-testid="inspector-surface">
      <h2>{actorName}:{polyIndex}</h2>
      <dl>
        <dt>Texture</dt>
        <dd>{textureLabel(poly, atlasManifest)}</dd>
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
        <dt>Area</dt>
        <dd>{poly.area.toFixed(2)}</dd>
        <dt>Normal</dt>
        <dd>{poly.normal.map((c) => c.toFixed(2)).join(', ')}</dd>
      </dl>
    </div>
  )
}

/** The surface half of the inspector: one surface's detail, or a list summary for 2+. Never called
 * with an empty list. */
function SurfaceSection({ surfaces, atlasManifest }: { surfaces: SurfaceSelection[]; atlasManifest: Record<string, AtlasRect> }) {
  if (surfaces.length === 1) return <SurfaceDetail {...surfaces[0]} atlasManifest={atlasManifest} />
  return (
    <div className="inspector inspector-multi" data-testid="inspector-multi-surfaces">
      <h2>{surfaces.length} surfaces selected</h2>
      <ul>
        {surfaces.map(({ actorName, polyIndex }) => (
          <li key={surfaceKey(actorName, polyIndex)}>{actorName}:{polyIndex}</li>
        ))}
      </ul>
    </div>
  )
}

/** `stored_value`/`default_value` (via `shownValue`, same fallback every other kind uses) as a bool
 * checkbox's checked state -- the backend sends 'True'/'False' (propedit's own casing), matched
 * case-insensitively rather than assuming one exact spelling. */
function isBoolChecked(p: EffectiveProp): boolean {
  return (shownValue(p) ?? '').toLowerCase() === 'true'
}

/** One property row -- a plain name/value `<tr>` for a scalar kind (typed: a disabled checkbox for
 * `bool`, plain resolved text for everything else including `enum`), or a `<details>`-wrapped
 * summary row nesting a member table for `struct`/`array`. Recurses for a struct member or array
 * element that is itself a struct/array. `displayName` overrides the prop's own `name` for display
 * only -- `isExplicit`/`shownValue`/`searchMatch` all key off the real `prop`, unaffected by this
 * override. An array element's row reads "`<ArrayName>.<i>`", where `i` is the element's POSITION
 * in the `elements` array, not `el.name`: the backend resolves every element by recursing on the
 * array's own `Prop` object, never rewriting `.name` per element, so all N elements of e.g.
 * `AmmoCount[3]` carry `.name == "AmmoCount"` and only the index distinguishes them for display.
 * `expandOnSearch` mirrors the category-level `<details
 * open={query !== ''}>` one level deeper, threaded through every recursive call so a struct-of-
 * structs/array-of-arrays auto-expands fully while a search term is active, not just its top level. */
function PropRow({ prop, displayName, expandOnSearch = false }:
    { prop: EffectiveProp; displayName?: string; expandOnSearch?: boolean }) {
  const name = displayName ?? prop.name
  const explicit = isExplicit(prop)

  if (prop.kind === 'struct') {
    return (
      <tr data-default={!explicit ? true : undefined}>
        <td colSpan={2}>
          <details open={expandOnSearch}>
            <summary>
              {name}
              {!explicit && <span className="inspector-default-tag">default</span>}
            </summary>
            <table>
              <tbody>
                {prop.members.map((m, i) => (
                  <PropRow key={`${m.name}-${i}`} prop={m} expandOnSearch={expandOnSearch} />
                ))}
              </tbody>
            </table>
          </details>
        </td>
      </tr>
    )
  }

  if (prop.kind === 'array') {
    return (
      <tr data-default={!explicit ? true : undefined}>
        <td colSpan={2}>
          <details open={expandOnSearch}>
            <summary>
              {name} ({prop.elements.length})
              {!explicit && <span className="inspector-default-tag">default</span>}
            </summary>
            <table>
              <tbody>
                {prop.elements.map((el, i) => (
                  <PropRow key={`${el.name}-${i}`} prop={el} displayName={`${name}.${i}`}
                    expandOnSearch={expandOnSearch} />
                ))}
              </tbody>
            </table>
          </details>
        </td>
      </tr>
    )
  }

  return (
    <tr data-default={!explicit ? true : undefined}>
      <td>{name}</td>
      <td>
        {prop.kind === 'bool' ? (
          <input type="checkbox" checked={isBoolChecked(prop)} disabled />
        ) : (
          shownValue(prop) ?? ''
        )}
        {!explicit && <span className="inspector-default-tag">default</span>}
      </td>
    </tr>
  )
}

/** The actor half: one actor's full detail, or a name-list summary for 2+. Never called empty.
 * `search`/`showAll` are lifted into the parent `Inspector` (not local state here): `Inspector`
 * renders `ActorSection` at a DIFFERENT tree position depending on whether a surface selection
 * coexists (bare vs. nested inside `.inspector-sections`, see `Inspector` below) -- React remounts
 * a component whose tree position changes, which used to silently wipe local search/show-all state
 * the instant a Ctrl+click added or removed a surface selection alongside an actor one. Lifting the
 * state up survives that remount since the parent (whose own position never moves) keeps holding it. */
function ActorSection({ actors, search, onSearchChange, showAll, onShowAllChange, resolveClass }: {
  actors: SceneActor[]
  search: string
  onSearchChange: (value: string) => void
  showAll: boolean
  onShowAllChange: (value: boolean) => void
  resolveClass: (fqcn: string) => ClassResolveResult
}) {
  if (actors.length > 1) {
    return (
      <div className="inspector inspector-multi" data-testid="inspector-multi">
        <h2>{actors.length} actors selected</h2>
        <ul>
          {actors.map((a) => (
            <li key={a.name}>{a.name}</li>
          ))}
        </ul>
      </div>
    )
  }

  const actor = actors[0]
  const query = search.trim()
  const resolved = resolveClass(actor.cls)
  // spec §4: an ordinary async-data race for the Load-time closure, self-resolving within the
  // render cycle after it completes -- no loading spinner. A genuinely unresolvable class (a
  // package missing from the search path entirely) is the one new user-facing error surface this
  // redesign adds -- a clear, named error inline, never a silently empty props table. Either way,
  // the REST of the actor's own metadata (name/class/location/folder/labels/order) still renders
  // unconditionally below -- only the props section itself switches on `resolved`.
  const displayProps = resolved === 'pending' || 'error' in resolved
    ? null
    : buildDisplayProps(resolved, actor.props)
  const overridesFiltered = displayProps === null
    ? null
    : (showAll ? displayProps : filterOverridesOnly(displayProps))
  const visibleProps = overridesFiltered === null
    ? null
    : (query === '' ? overridesFiltered : overridesFiltered.filter((p) => searchMatch(p, query)))
  const groups = visibleProps === null ? null : groupByCategory(visibleProps)

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
        <dd>{actor.folder ?? '—'}</dd>
        <dt>Labels</dt>
        <dd>
          {actor.labels.length > 0 ? (
            <span className="inspector-labels">
              {actor.labels.map((label) => (
                <span key={label} className="inspector-label-chip">
                  {label}
                </span>
              ))}
            </span>
          ) : (
            '—'
          )}
        </dd>
        <dt>Order</dt>
        <dd>{actor.csg_rank}</dd>
      </dl>
      <div className="inspector-prop-controls">
        <input
          type="text"
          placeholder="Search properties"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
        <label>
          <input type="checkbox" checked={showAll} onChange={(e) => onShowAllChange(e.target.checked)} />
          Show all
        </label>
      </div>
      <div className="inspector-props" data-testid="inspector-props">
        {resolved === 'pending' && (
          <p data-testid="inspector-props-pending">Loading properties…</p>
        )}
        {resolved !== 'pending' && 'error' in resolved && (
          <p data-testid="inspector-props-error">{resolved.error}</p>
        )}
        {groups !== null && Array.from(groups).map(([category, rows]) => (
          <details open={query !== ''} key={category}>
            <summary>{category} ({rows.length})</summary>
            <table>
              <tbody>
                {rows.map((p, i) => (
                  <PropRow key={`${p.name}-${i}`} prop={p} expandOnSearch={query !== ''} />
                ))}
              </tbody>
            </table>
          </details>
        ))}
      </div>
    </div>
  )
}

export function Inspector({ selected, selectedSurfaces = [], atlasManifest = {},
    resolveClass = () => 'pending' }: InspectorProps) {
  // Lifted out of ActorSection (Inspector review finding): ActorSection renders at a different tree
  // position depending on whether a surface selection coexists (bare below vs. nested inside
  // .inspector-sections further down), and React remounts a component whose position moves -- state
  // that lived IN ActorSection was silently wiped by that remount. Holding it here, in the component
  // whose own position never moves, survives it.
  const [search, setSearch] = useState('')
  const [showAll, setShowAll] = useState(false)

  if (selected.length === 0 && selectedSurfaces.length === 0) {
    return (
      <div className="inspector inspector-empty" data-testid="inspector-empty">
        No selection
      </div>
    )
  }

  if (selected.length === 0) return <SurfaceSection surfaces={selectedSurfaces} atlasManifest={atlasManifest} />
  if (selectedSurfaces.length === 0) {
    return (
      <ActorSection actors={selected} search={search} onSearchChange={setSearch}
        showAll={showAll} onShowAllChange={setShowAll} resolveClass={resolveClass} />
    )
  }

  // Both kinds at once -- a Ctrl+tap that crossed kinds, or Shift+tap on a surface while surfaces
  // were selected (see InspectorProps above). Show both sections, actors first.
  return (
    <div className="inspector-sections" data-testid="inspector-sections">
      <ActorSection actors={selected} search={search} onSearchChange={setSearch}
        showAll={showAll} onShowAllChange={setShowAll} resolveClass={resolveClass} />
      <SurfaceSection surfaces={selectedSurfaces} atlasManifest={atlasManifest} />
    </div>
  )
}

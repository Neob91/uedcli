import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import type { AtlasRect, EffectiveProp, ScenePoly, SceneActor } from '../api'
import { Inspector } from './Inspector'
import type { SurfaceSelection } from './Inspector'

function fixturePoly(overrides: Partial<ScenePoly> = {}): ScenePoly {
  return {
    verts: [0, 0, 0, 1, 0, 0, 1, 1, 0],
    base: [0, 0, 0],
    tu: [1, 0, 0],
    tv: [0, 1, 0],
    pan: [4, 8],
    normal: [0, 0, 1],
    area: 100,
    tex_index: 12,
    masked: false,
    two_sided: false,
    blend: 'opaque',
    flags: 0,
    lightmap: null,
    owner: 'Room',
    i_brush_poly: 4,
    ...overrides,
  }
}

// A `poly.tex_index -> AtlasRect` manifest fixture, keyed the same way the real `/atlas` payload is
// (`String(tex_index)`, `geometry.ts`'s `polyUVs` convention) -- each entry only needs to state the
// fields a given test cares about, the rest are filled with harmless placeholders.
function atlasManifest(entries: Record<number, Partial<AtlasRect>>): Record<string, AtlasRect> {
  const out: Record<string, AtlasRect> = {}
  for (const [index, rect] of Object.entries(entries)) {
    out[index] = { x: 0, y: 0, w: 8, h: 8, name: null, ...rect }
  }
  return out
}

// A single-surface `SurfaceSelection` fixture, optionally paired with an atlas manifest for the
// texture-name lookup tests below.
function makeSurfaceWith(overrides: Partial<ScenePoly>, manifest?: Record<string, AtlasRect>): { surface: SurfaceSelection; atlasManifest: Record<string, AtlasRect> } {
  return {
    surface: { actorName: 'Room', polyIndex: 4, poly: fixturePoly(overrides) },
    atlasManifest: manifest ?? {},
  }
}

afterEach(cleanup)

function fixtureActor(overrides: Partial<SceneActor> = {}): SceneActor {
  return {
    name: 'Room',
    cls: 'Engine.Brush',
    bbox_lo: [-256, -256, -128],
    bbox_hi: [256, 256, 128],
    location: [10, 20, 30],
    rotation: [0, 16384, 0],
    folder: 'geo/rooms',
    labels: ['lighting'],
    order_value: 'm',
    csg_rank: 3,
    props: effectiveProps([
      // real live-verified category mapping for both (see scene.py's plan)
      { kind: 'string', name: 'CsgOper', category: 'Brush', stored_value: 'CSG_Subtract', default_value: '' },
      { kind: 'int', name: 'PolyFlags', category: 'Brush', stored_value: '2', default_value: '0' },
    ]),
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
    ...overrides,
  }
}

// Typed identity helper -- lets a test spell out an EffectiveProp[] literal (kind-discriminated
// union) without every call site needing its own `as const`/explicit annotation.
function effectiveProps(props: EffectiveProp[]): EffectiveProp[] {
  return props
}

// A one-actor SceneActor fixture carrying exactly the given props -- everything else defaulted from
// fixtureActor().
function makeActorWith(props: EffectiveProp[]): SceneActor {
  return fixtureActor({ props })
}

describe('Inspector', () => {
  it('renders "no selection" when nothing is selected (regression pin: prop-shape-only change)', () => {
    render(<Inspector selected={[]} />)
    expect(screen.getByTestId('inspector-empty').textContent).toBe('No selection')
  })

  it("renders a fixture actor's property rows for exactly one selected actor (regression pin)", () => {
    render(<Inspector selected={[fixtureActor()]} />)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()
    expect(screen.getByText('Engine.Brush')).toBeTruthy()
    expect(screen.getByText('10.00, 20.00, 30.00')).toBeTruthy() // location
    expect(screen.getByText('0, 16384, 0')).toBeTruthy() // rotation
    expect(screen.getByText('geo/rooms')).toBeTruthy()
    expect(screen.getByText('lighting')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy() // csg_rank, not the raw order_value string
    expect(screen.queryByText('m')).toBeNull()
    expect(screen.getByText('CsgOper')).toBeTruthy()
    expect(screen.getByText('CSG_Subtract')).toBeTruthy()
  })

  it('empty folder/labels show a dash, not a sentence', () => {
    render(<Inspector selected={[fixtureActor({ folder: null, labels: [] })]} />)
    expect(screen.queryByText('(no folder)')).toBeNull()
    expect(screen.queryByText('(no label)')).toBeNull()
    expect(screen.getAllByText('—')).toHaveLength(2)
  })

  it('labels render as individual chip elements, not a joined string', () => {
    const { container } = render(<Inspector selected={[fixtureActor({ labels: ['lit', 'indoor'] })]} />)
    expect(screen.getByText('lit')).toBeTruthy()
    expect(screen.getByText('indoor')).toBeTruthy()
    // A comma-joined string would put both names in one text node ("lit, indoor"), which the exact
    // getByText('lit') above would then fail to find -- this assertion is belt-and-suspenders.
    expect(screen.queryByText('lit, indoor')).toBeNull()
    expect(container.querySelectorAll('.inspector-label-chip')).toHaveLength(2)
  })

  it('folder keeps its raw dotted path, no breadcrumb rendering', () => {
    render(<Inspector selected={[fixtureActor({ folder: 'castle.tower.roof' })]} />)
    expect(screen.getByText('castle.tower.roof')).toBeTruthy()
  })

  it('re-renders for a newly selected actor (selection swap)', () => {
    const { rerender } = render(<Inspector selected={[fixtureActor({ name: 'Room' })]} />)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()

    rerender(<Inspector selected={[fixtureActor({ name: 'Door', cls: 'Engine.Mover' })]} />)
    expect(screen.getByRole('heading', { name: 'Door' })).toBeTruthy()
    expect(screen.getByText('Engine.Mover')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Room' })).toBeNull()
  })

  it('renders one collapsible section per distinct category', () => {
    render(
      <Inspector
        selected={[
          fixtureActor({
            props: effectiveProps([
              { kind: 'string', name: 'CsgOper', category: 'Brush', stored_value: 'CSG_Subtract', default_value: '' },
              { kind: 'float', name: 'Mass', category: 'Movement', stored_value: '100', default_value: '0' },
            ]),
          }),
        ]}
      />,
    )
    expect(screen.getByText('Brush (1)')).toBeTruthy()
    expect(screen.getByText('Movement (1)')).toBeTruthy()
    expect(screen.getByText('CsgOper')).toBeTruthy()
    expect(screen.getByText('Mass')).toBeTruthy()
    // Both fixtures are explicit (a real stored_value) -- neither should carry the defaulted-row
    // marker or its "default" tag (mutation-tested: catches an unconditional data-default={true}).
    expect(screen.getByText('CsgOper').closest('[data-default]')).toBeNull()
    expect(screen.queryByText('default')).toBeNull()
  })

  it('renders a single "Uncategorized" section when every prop falls back', () => {
    render(
      <Inspector
        selected={[
          fixtureActor({
            props: effectiveProps([
              { kind: 'string', name: 'Brush', category: 'Uncategorized', stored_value: "Model'MyLevel.Model_Room'", default_value: '' },
            ]),
          }),
        ]}
      />,
    )
    expect(screen.getByText('Uncategorized (1)')).toBeTruthy()
    expect(screen.getByText('Brush')).toBeTruthy()
  })

  // Task 10a: search box + overrides-only/show-all toggle over the props list.
  it('filters props by name substring', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'float', name: 'LightRadius', category: 'Lighting', stored_value: '8', default_value: '0' },
      // Explicit (real stored_value), so it survives the overrides-only filter and reaches the
      // search filter -- only the search term itself can exclude it. A null stored_value here would
      // already be dropped by overrides-only, making the search assertion below vacuous (mutation-
      // tested: deleting the search filter entirely left this test passing until this fixture was
      // made explicit).
      { kind: 'string', name: 'Tag', category: 'Object', stored_value: 'X', default_value: '' },
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    fireEvent.change(screen.getByPlaceholderText('Search properties'), { target: { value: 'light' } })
    expect(screen.getByText('LightRadius')).toBeTruthy()
    expect(screen.queryByText('Tag')).toBeNull()
  })

  it('auto-expands every category while a search term is active', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'float', name: 'LightRadius', category: 'Lighting', stored_value: '8', default_value: '0' },
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    const details = screen.getByText('Lighting (1)').closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false) // collapsed by default, no search term yet
    fireEvent.change(screen.getByPlaceholderText('Search properties'), { target: { value: 'light' } })
    expect(details.open).toBe(true)
  })

  it('overrides-only is the default; show-all reveals a defaulted row, tagged', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'float', name: 'LightRadius', category: 'Lighting', stored_value: null, default_value: '0' },
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    expect(screen.queryByText('LightRadius')).toBeNull()
    fireEvent.click(screen.getByLabelText('Show all'))
    expect(screen.getByText('LightRadius')).toBeTruthy()
    expect(screen.getByText('LightRadius').closest('[data-default]')).not.toBeNull()
    // Fix 3: a defaulted row also carries the small "default" tag (mutation-tested: hardcoding
    // data-default={true} unconditionally left the old assertion above passing with no tag check).
    expect(screen.getByText('default')).toBeTruthy()
  })

  // Part 3, Task 16: 2+ selected -> a lightweight summary, not the full single-actor detail view.
  it('renders a lightweight "N actors selected" summary for 2+ selected actors', () => {
    render(<Inspector selected={[fixtureActor({ name: 'A' }), fixtureActor({ name: 'B' }), fixtureActor({ name: 'C' })]} />)
    expect(screen.getByTestId('inspector-multi')).toBeTruthy()
    expect(screen.getByText('3 actors selected')).toBeTruthy()
    expect(screen.getByText('A')).toBeTruthy()
    expect(screen.getByText('B')).toBeTruthy()
    expect(screen.getByText('C')).toBeTruthy()
    // Not the single-actor detail view's own markup.
    expect(screen.queryByTestId('inspector')).toBeNull()
  })

  // Surface (single-polygon texture) selection -- a DISTINCT selection kind from a whole-actor
  // selection (GUI.md "Selection & the Inspector"), owner-answered as highlight+inspect only.
  it('renders a single surface\'s detail view when exactly one texture is selected and no actor is', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: fixturePoly() }
    render(<Inspector selected={[]} selectedSurfaces={[surface]} />)
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Room:4' })).toBeTruthy()
    expect(screen.getByText('#12')).toBeTruthy() // tex_index
    expect(screen.getByText('4, 8')).toBeTruthy() // pan
    expect(screen.queryByTestId('inspector-empty')).toBeNull()
  })

  it('renders "(untextured)" for a surface with no texture', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 0, poly: fixturePoly({ tex_index: -1 }) }
    render(<Inspector selected={[]} selectedSurfaces={[surface]} />)
    expect(screen.getByText('(untextured)')).toBeTruthy()
  })

  // Task 11: real texture group name (from the atlas manifest) instead of a bare #index.
  it('shows the real texture name instead of a bare index', () => {
    const { surface, atlasManifest: manifest } = makeSurfaceWith(
      { tex_index: 3 },
      atlasManifest({ 3: { name: 'CoreTexMetal.Metal.Area51Wall_A' } }),
    )
    render(<Inspector selected={[]} selectedSurfaces={[surface]} enums={{}} atlasManifest={manifest} />)
    expect(screen.getByText('CoreTexMetal.Metal.Area51Wall_A')).toBeTruthy()
    // Mutation check: the raw index must NOT also render as its own text node.
    expect(screen.queryByText('#3')).toBeNull()
  })

  it('falls back to #index when the atlas name is null (mesh-skin entry)', () => {
    const { surface, atlasManifest: manifest } = makeSurfaceWith(
      { tex_index: 5 },
      atlasManifest({ 5: { name: null } }),
    )
    render(<Inspector selected={[]} selectedSurfaces={[surface]} enums={{}} atlasManifest={manifest} />)
    expect(screen.getByText('#5')).toBeTruthy()
  })

  it('shows area and normal formatted to 2 decimal places (they are floats, not the integer Pan/Rotation kind)', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: fixturePoly({ area: 42.5, normal: [0, 0, 1] }) }
    render(<Inspector selected={[]} selectedSurfaces={[surface]} enums={{}} />)
    expect(screen.getByText('42.50')).toBeTruthy()
    expect(screen.getByText('0.00, 0.00, 1.00')).toBeTruthy()
  })

  it('rounds a high-precision float area/normal instead of rendering it raw (e.g. a real 45° wall)', () => {
    const surface: SurfaceSelection = {
      actorName: 'Room',
      polyIndex: 4,
      poly: fixturePoly({ area: 12799.999999999998, normal: [0.7071067811865475, -0.7071067811865476, 0] }),
    }
    render(<Inspector selected={[]} selectedSurfaces={[surface]} enums={{}} />)
    expect(screen.getByText('12800.00')).toBeTruthy()
    expect(screen.getByText('0.71, -0.71, 0.00')).toBeTruthy()
    expect(screen.queryByText('12799.999999999998')).toBeNull()
  })

  it('renders a lightweight "N surfaces selected" summary for 2+ selected surfaces', () => {
    const surfaces: SurfaceSelection[] = [
      { actorName: 'Room', polyIndex: 1, poly: fixturePoly() },
      { actorName: 'Room', polyIndex: 2, poly: fixturePoly() },
    ]
    render(<Inspector selected={[]} selectedSurfaces={surfaces} />)
    expect(screen.getByTestId('inspector-multi-surfaces')).toBeTruthy()
    expect(screen.getByText('2 surfaces selected')).toBeTruthy()
    expect(screen.queryByTestId('inspector-surface')).toBeNull()
  })

  it('defaults selectedSurfaces to empty -- an actor-only call site is unaffected', () => {
    render(<Inspector selected={[]} />)
    expect(screen.getByTestId('inspector-empty')).toBeTruthy()
  })

  // The two kinds COEXIST -- UED22 keeps `AActor.bSelected` and `PF_Selected` as independent state
  // (GUI-PARITY.md "Actor + surface selection coexist; only a plain click clears both"), so both
  // props can be non-empty at once and BOTH sections must render. Replaces an earlier test that
  // asserted the actor selection "takes priority over a (should-be-empty) stale surface selection".
  it('renders BOTH an actor section and a surface section when both kinds are selected', () => {
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: fixturePoly() }
    render(<Inspector selected={[fixtureActor()]} selectedSurfaces={[surface]} />)
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
    expect(screen.getByTestId('inspector')).toBeTruthy()
    expect(screen.getByTestId('inspector-surface')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Room:4' })).toBeTruthy()
    expect(screen.queryByTestId('inspector-empty')).toBeNull()
  })

  // Regression: ActorSection used to hold search/show-all as its OWN local state, and Inspector
  // renders it at a different tree position depending on whether a surface selection coexists
  // (bare vs. nested inside .inspector-sections) -- React remounts a component whose position moves,
  // which wiped the typed search term the instant a Ctrl+click added a surface selection alongside
  // an actor one (or removed one, leaving just the actor). Fails on the old code (ActorSection's own
  // useState re-initializes to '' on remount); passes once search/show-all are lifted into Inspector,
  // which never itself remounts across this prop change.
  it('search term survives a surface selection being added alongside an actor selection', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'float', name: 'LightRadius', category: 'Lighting', stored_value: '8', default_value: '0' },
    ]))
    const surface: SurfaceSelection = { actorName: 'Room', polyIndex: 4, poly: fixturePoly() }
    const { rerender } = render(<Inspector selected={[actor]} selectedSurfaces={[]} enums={{}} />)
    fireEvent.change(screen.getByPlaceholderText('Search properties'), { target: { value: 'light' } })
    expect((screen.getByPlaceholderText('Search properties') as HTMLInputElement).value).toBe('light')

    // Ctrl+click adds a surface selection -- ActorSection now renders inside .inspector-sections.
    rerender(<Inspector selected={[actor]} selectedSurfaces={[surface]} enums={{}} />)
    expect(screen.getByTestId('inspector-sections')).toBeTruthy()
    expect((screen.getByPlaceholderText('Search properties') as HTMLInputElement).value).toBe('light')
    expect(screen.getByText('LightRadius')).toBeTruthy()

    // Removing the surface selection again -- ActorSection moves back to the bare position.
    rerender(<Inspector selected={[actor]} selectedSurfaces={[]} enums={{}} />)
    expect((screen.getByPlaceholderText('Search properties') as HTMLInputElement).value).toBe('light')
  })

  it('renders both MULTI summaries when 2+ actors and 2+ surfaces are selected together', () => {
    const actors = [fixtureActor(), fixtureActor({ name: 'Hall' })]
    const surfaces: SurfaceSelection[] = [
      { actorName: 'Room', polyIndex: 1, poly: fixturePoly() },
      { actorName: 'Room', polyIndex: 2, poly: fixturePoly() },
    ]
    render(<Inspector selected={actors} selectedSurfaces={surfaces} />)
    expect(screen.getByTestId('inspector-multi')).toBeTruthy()
    expect(screen.getByTestId('inspector-multi-surfaces')).toBeTruthy()
    expect(screen.getByText('2 actors selected')).toBeTruthy()
    expect(screen.getByText('2 surfaces selected')).toBeTruthy()
  })

  it('renders only the actor section when no surface is selected (no stray wrapper)', () => {
    render(<Inspector selected={[fixtureActor()]} selectedSurfaces={[]} />)
    expect(screen.getByTestId('inspector')).toBeTruthy()
    expect(screen.queryByTestId('inspector-sections')).toBeNull()
    expect(screen.queryByTestId('inspector-surface')).toBeNull()
  })

  // Task 10b: struct/array expansion + typed display (checkbox/enum text).
  //
  // The actor-header block above already renders a `<dt>Rotation</dt>` row (and `<dt>Location</dt>`)
  // -- a bare `screen.getByText('Rotation')` would match BOTH that header row and a struct prop named
  // "Rotation", throwing "Found multiple elements". Every query below is scoped with `within(...)` to
  // `data-testid="inspector-props"` (the props-list container, below the header `<dl>`) so it can
  // never collide with the header's own fixed dt/dd rows. No `@testing-library/jest-dom` matchers
  // (`toBeInTheDocument`/`toBeDisabled`/`toBeChecked`) are installed in this project -- assertions use
  // the same `.toBeTruthy()`/raw-DOM-property style every existing Inspector test already uses.
  it('renders a struct as nested rows, one per member, genuinely toggled and genuinely nested', () => {
    // Fix 3: prove the click really toggles the struct's own <details> (not just that "Yaw" appears
    // somewhere in the document) and that "Yaw" is genuinely INSIDE that <details>, not a flat
    // sibling row rendered elsewhere. Mutation-tested against this exact file: breaking the
    // click-to-expand handler, and moving struct members outside their own <details> as flat
    // siblings, both left the old (presence-only) assertions green.
    const actor = makeActorWith(effectiveProps([
      { kind: 'struct', name: 'Rotation', category: 'Movement', members: [
        { kind: 'int', name: 'Yaw', category: 'Movement', stored_value: '8192', default_value: '0' },
      ]},
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    const props = within(screen.getByTestId('inspector-props'))
    const summary = props.getByText('Rotation')
    const details = summary.closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false) // collapsed by default, no search term
    fireEvent.click(summary) // expand
    expect(details.open).toBe(true)
    expect(within(details).getByText('Yaw')).toBeTruthy()
  })

  it('renders a static array as a summary row, expandable to elements, genuinely toggled and nested', () => {
    // Fix 1 + Fix 3 combined: the fixture's element `.name` fields match what the REAL backend
    // actually sends -- the backend resolves each array element by recursing on the array's own
    // `Prop` object, never rewriting `.name` per element, so every element of a real array
    // keeps the ARRAY's own declared name (`MultiSkins`), never `'0'`/`'1'`. The display name is
    // therefore built from the element's POSITION in `elements`, not from `el.name` (which would
    // render three indistinguishable "MultiSkins.MultiSkins" rows against the real payload shape).
    const actor = makeActorWith(effectiveProps([
      { kind: 'array', name: 'MultiSkins', category: 'Display', element_kind: 'string',
        elements: [
          { kind: 'string', name: 'MultiSkins', category: 'Display', stored_value: 'A', default_value: '' },
          { kind: 'string', name: 'MultiSkins', category: 'Display', stored_value: null, default_value: '' },
        ]},
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    const props = within(screen.getByTestId('inspector-props'))
    const summary = props.getByText('MultiSkins (2)')
    const details = summary.closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false) // collapsed by default, no search term
    fireEvent.click(summary)
    expect(details.open).toBe(true)
    const withinArray = within(details)
    expect(withinArray.getByText('MultiSkins.0')).toBeTruthy()
    expect(withinArray.getByText('MultiSkins.1')).toBeTruthy()
  })

  it('an enum shows the canonical name directly, no ordinal', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'enum', name: 'LightType', category: 'Lighting', enum_type: 'Engine.Light.ELightType', stored_value: 'LT_Steady', default_value: 'LT_None' },
    ]))
    render(<Inspector selected={[actor]} enums={{ 'Engine.Light.ELightType': ['LT_None', 'LT_Steady'] }} />)
    const props = within(screen.getByTestId('inspector-props'))
    expect(props.getByText('LT_Steady')).toBeTruthy()
  })

  it('a bool shows a disabled checkbox, checked when stored True', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'bool', name: 'bHidden', category: 'Display', stored_value: 'True', default_value: 'False' },
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    const props = within(screen.getByTestId('inspector-props'))
    const checkbox = props.getByRole('checkbox') as HTMLInputElement
    expect(checkbox.disabled).toBe(true)
    expect(checkbox.checked).toBe(true)
  })

  it('a bool shows an unchecked checkbox when stored False (Fix 2: discriminates checked=false)', () => {
    // The True-only test above would pass even with `checked={true}` hardcoded unconditionally.
    // This fixture pins the other value so that mutation is caught.
    const actor = makeActorWith(effectiveProps([
      { kind: 'bool', name: 'bHidden', category: 'Display', stored_value: 'False', default_value: 'False' },
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    const props = within(screen.getByTestId('inspector-props'))
    const checkbox = props.getByRole('checkbox') as HTMLInputElement
    expect(checkbox.disabled).toBe(true)
    expect(checkbox.checked).toBe(false)
  })

  // Fix 4: a fully-defaulted struct/array row gets the same "default" tag scalar rows already have
  // (Task 10a), not just the dimming `data-default` attribute.
  it('a fully-defaulted struct carries the "default" tag on its summary', () => {
    // A fully-defaulted struct (every member's stored_value is null) is excluded by the
    // overrides-only default filter, same as a defaulted scalar -- toggle "Show all" first, same as
    // the existing "overrides-only is the default; show-all reveals a defaulted row" test above.
    const actor = makeActorWith(effectiveProps([
      { kind: 'struct', name: 'Rotation', category: 'Movement', members: [
        { kind: 'int', name: 'Yaw', category: 'Movement', stored_value: null, default_value: '0' },
      ]},
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    fireEvent.click(screen.getByLabelText('Show all'))
    const props = within(screen.getByTestId('inspector-props'))
    const summary = props.getByText('Rotation')
    expect(summary.closest('[data-default]')).not.toBeNull()
    // Scoped to the summary itself, not the whole <details>: the member/element row underneath is
    // also defaulted and carries its own "default" tag, so a details-wide query would find two.
    expect(within(summary).getByText('default')).toBeTruthy()
  })

  it('a fully-defaulted array carries the "default" tag on its summary', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'array', name: 'MultiSkins', category: 'Display', element_kind: 'string',
        elements: [
          { kind: 'string', name: 'MultiSkins', category: 'Display', stored_value: null, default_value: '' },
        ]},
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    fireEvent.click(screen.getByLabelText('Show all'))
    const props = within(screen.getByTestId('inspector-props'))
    const summary = props.getByText('MultiSkins (1)')
    expect(summary.closest('[data-default]')).not.toBeNull()
    // Scoped to the summary itself, not the whole <details>: the member/element row underneath is
    // also defaulted and carries its own "default" tag, so a details-wide query would find two.
    expect(within(summary).getByText('default')).toBeTruthy()
  })

  // Fix 5: a nested struct/array <details> auto-expands while a search term is active, the same way
  // Task 10a's category-level <details> already does (see "auto-expands every category..." above).
  it('auto-expands a matched struct\'s own <details> while a search term is active', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'struct', name: 'Rotation', category: 'Movement', members: [
        { kind: 'int', name: 'Yaw', category: 'Movement', stored_value: '8192', default_value: '0' },
      ]},
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    const props = within(screen.getByTestId('inspector-props'))
    const details = props.getByText('Rotation').closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    fireEvent.change(screen.getByPlaceholderText('Search properties'), { target: { value: 'rotation' } })
    expect(details.open).toBe(true)
  })

  it('auto-expands a matched array\'s own <details> while a search term is active', () => {
    const actor = makeActorWith(effectiveProps([
      { kind: 'array', name: 'MultiSkins', category: 'Display', element_kind: 'string',
        elements: [
          { kind: 'string', name: 'MultiSkins', category: 'Display', stored_value: 'A', default_value: '' },
        ]},
    ]))
    render(<Inspector selected={[actor]} enums={{}} />)
    const props = within(screen.getByTestId('inspector-props'))
    const details = props.getByText('MultiSkins (1)').closest('details') as HTMLDetailsElement
    expect(details.open).toBe(false)
    fireEvent.change(screen.getByPlaceholderText('Search properties'), { target: { value: 'multiskins' } })
    expect(details.open).toBe(true)
  })
})

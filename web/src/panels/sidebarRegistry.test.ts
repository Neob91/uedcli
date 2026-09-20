import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SceneActor } from '../api'
import { buildSidebarPanels } from './sidebarRegistry'

afterEach(cleanup)

function actor(name: string, folder: string | null = null): SceneActor {
  return {
    name,
    cls: 'Engine.Light',
    bbox_lo: [0, 0, 0],
    bbox_hi: [1, 1, 1],
    location: [0, 0, 0],
    rotation: [0, 0, 0],
    folder,
    labels: [],
    order_value: 'm',
    csg_rank: 1,
    props: [],
    categories: [],
    brush: null,
    sprite: null,
    radii: null,
    is_mover: false,
    directional_arrow: null,
  }
}

describe('buildSidebarPanels', () => {
  it('builds "selection" then "org", with the mockup\'s placeholder icons/titles', () => {
    const panels = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(panels.map((p) => p.id)).toEqual(['selection', 'org'])
    expect(panels[0].icon).toBe('▣')
    expect(panels[0].title).toBe('Selection')
    expect(panels[1].icon).toBe('☰')
    expect(panels[1].title).toBe('Org / Search')
  })

  it('the "selection" entry\'s content renders the Inspector with the given actor selection', () => {
    const [selectionPanel] = buildSidebarPanels({
      selectedActors: [actor('Room')],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    render(selectionPanel.content)
    expect(screen.getByRole('heading', { name: 'Room' })).toBeTruthy()
  })

  it('the "org" entry\'s content renders the OrgPanel with the given actors', () => {
    const [, orgPanel] = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [actor('Torch1')],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    render(orgPanel.content)
    expect(screen.getByTestId('org-panel')).toBeTruthy()
  })

  it('forwards onSelectOrgBatch to OrgPanel exactly as OrgPanel calls it', () => {
    const onSelectOrgBatch = vi.fn()
    const [, orgPanel] = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [actor('Loose1')],
      selectedNames: new Set(),
      onSelectOrgBatch,
    })
    render(orgPanel.content)
    screen.getByTestId('org-folder-no-folder').click()
    expect(onSelectOrgBatch).toHaveBeenCalledWith(['Loose1'], false)
  })

  it('the "selection" entry\'s hasIndicator mirrors hasUnseenSelection', () => {
    const withDot = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: true,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(withDot[0].hasIndicator).toBe(true)

    const withoutDot = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: false,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(withoutDot[0].hasIndicator).toBe(false)
  })

  it('the "org" entry\'s hasIndicator is always false -- Org has no discoverability signal', () => {
    const panels = buildSidebarPanels({
      selectedActors: [],
      selectedSurfaces: [],
      hasUnseenSelection: true,
      orgActors: [],
      selectedNames: new Set(),
      onSelectOrgBatch: vi.fn(),
    })
    expect(panels[1].hasIndicator).toBe(false)
  })
})

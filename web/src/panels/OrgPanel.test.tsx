import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { SceneActor } from '../api'
import { OrgPanel } from './OrgPanel'

afterEach(cleanup)

function actor(name: string, folder: string | null): SceneActor {
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
    props: [],
    categories: [],
    brush: null,
    sprite: null,
  }
}

const ACTORS: SceneActor[] = [
  actor('Torch1', 'castle.tower'),
  actor('Torch2', 'castle.tower'),
  actor('Gate1', 'castle.gate'),
  actor('Loose1', null),
]

describe('OrgPanel folder-node selection', () => {
  it('clicking a folder node calls onSelectActor with every actor name under that folder, additive=false', () => {
    const onSelectActor = vi.fn()
    render(<OrgPanel actors={ACTORS} selectedNames={new Set()} onSelectActor={onSelectActor} />)

    fireEvent.click(screen.getByTestId('org-folder-castle.tower'))

    expect(onSelectActor).toHaveBeenCalledWith(['Torch1', 'Torch2'], false)
  })

  it('Ctrl-clicking a folder node calls onSelectActor with additive=true', () => {
    const onSelectActor = vi.fn()
    render(<OrgPanel actors={ACTORS} selectedNames={new Set()} onSelectActor={onSelectActor} />)

    fireEvent.click(screen.getByTestId('org-folder-castle.tower'), { ctrlKey: true })

    expect(onSelectActor).toHaveBeenCalledWith(['Torch1', 'Torch2'], true)
  })

  it('the "(no folder)" bucket selects every folder===null actor', () => {
    const onSelectActor = vi.fn()
    render(<OrgPanel actors={ACTORS} selectedNames={new Set()} onSelectActor={onSelectActor} />)

    fireEvent.click(screen.getByTestId('org-folder-no-folder'))

    expect(onSelectActor).toHaveBeenCalledWith(['Loose1'], false)
  })
})

describe('OrgPanel focus-search keybinding', () => {
  it("pressing '/' with nothing focused focuses the find input", () => {
    render(<OrgPanel actors={ACTORS} selectedNames={new Set()} onSelectActor={vi.fn()} />)
    const findInput = screen.getByTestId('org-find')
    expect(document.activeElement).not.toBe(findInput)

    fireEvent.keyDown(window, { key: '/' })

    expect(document.activeElement).toBe(findInput)
  })

  it('pressing Ctrl+F focuses the find input and calls preventDefault', () => {
    render(<OrgPanel actors={ACTORS} selectedNames={new Set()} onSelectActor={vi.fn()} />)
    const findInput = screen.getByTestId('org-find')

    const notCancelled = fireEvent.keyDown(window, { key: 'f', ctrlKey: true })

    expect(document.activeElement).toBe(findInput)
    expect(notCancelled).toBe(false) // dispatchEvent returns false when preventDefault was called
  })

  it("pressing '/' while a DIFFERENT text input already has focus does not move focus (keeps typing '/' there)", () => {
    render(
      <div>
        <input data-testid="other-input" />
        <OrgPanel actors={ACTORS} selectedNames={new Set()} onSelectActor={vi.fn()} />
      </div>,
    )
    const other = screen.getByTestId('other-input')
    other.focus()

    fireEvent.keyDown(other, { key: '/' })

    expect(document.activeElement).toBe(other)
  })
})

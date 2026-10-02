import { describe, expect, it } from 'vitest'

import { toggleMaximize } from './paneLayout'

describe('toggleMaximize', () => {
  it('maximizes the clicked pane when none is currently maximized', () => {
    expect(toggleMaximize(null, 'top')).toBe('top')
  })

  it('restores the grid when double-clicking the currently-maximized pane', () => {
    expect(toggleMaximize('top', 'top')).toBeNull()
  })

  it('switches the maximized pane to the newly double-clicked one', () => {
    expect(toggleMaximize('top', 'front')).toBe('front')
  })
})

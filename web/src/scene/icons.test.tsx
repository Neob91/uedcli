import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import {
  FlyIcon,
  FullbrightIcon,
  GridIcon,
  LitIcon,
  MiscIcon,
  MoversIcon,
  PanIcon,
  RadiiIcon,
  WireframeIcon,
} from './icons'

afterEach(cleanup)

const ICONS = {
  FlyIcon,
  PanIcon,
  WireframeIcon,
  FullbrightIcon,
  LitIcon,
  MiscIcon,
  MoversIcon,
  RadiiIcon,
  GridIcon,
}

describe('cluster icons', () => {
  it('every icon renders exactly one svg element', () => {
    for (const [name, Icon] of Object.entries(ICONS)) {
      const { container, unmount } = render(<Icon />)
      expect(container.querySelectorAll('svg').length, name).toBe(1)
      unmount()
    }
  })
})

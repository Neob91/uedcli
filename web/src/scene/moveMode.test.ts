import { describe, expect, it } from 'vitest'

import { cycleMoveMode } from './moveMode'

describe('cycleMoveMode', () => {
  it('fly cycles to pan', () => {
    expect(cycleMoveMode('fly')).toBe('pan')
  })

  it('pan cycles back to fly', () => {
    expect(cycleMoveMode('pan')).toBe('fly')
  })
})

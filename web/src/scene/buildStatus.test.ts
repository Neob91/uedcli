import { describe, expect, it } from 'vitest'

import type { StatusPayload } from '../api'
import { resolveBuildSolved } from './buildStatus'

function status(overrides: Partial<StatusPayload> = {}): StatusPayload {
  return { changes_available: false, geometry_pinned: false, build_status: 'no_build', ...overrides }
}

describe('resolveBuildSolved', () => {
  it('is true when geometry_pinned', () => {
    expect(resolveBuildSolved(status({ geometry_pinned: true, build_status: 'built' }))).toBe(true)
  })

  it('is false when not pinned', () => {
    expect(resolveBuildSolved(status({ geometry_pinned: false }))).toBe(false)
  })

  it('is false when no status has loaded yet (null)', () => {
    expect(resolveBuildSolved(null)).toBe(false)
  })
})

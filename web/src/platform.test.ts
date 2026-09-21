import { afterEach, describe, expect, it, vi } from 'vitest'

import { isAdditiveModifier, isMac } from './platform'

function mockNavigator(overrides: { platform?: string; userAgent?: string; userAgentDataPlatform?: string }) {
  vi.stubGlobal('navigator', {
    platform: overrides.platform ?? '',
    userAgent: overrides.userAgent ?? '',
    ...(overrides.userAgentDataPlatform !== undefined
      ? { userAgentData: { platform: overrides.userAgentDataPlatform } }
      : {}),
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('isMac', () => {
  it('true for a real macOS navigator.platform value', () => {
    mockNavigator({ platform: 'MacIntel' })
    expect(isMac()).toBe(true)
  })

  it('false for Linux (jsdom\'s own default -- the existing test suite\'s baseline)', () => {
    mockNavigator({ platform: '', userAgent: 'Mozilla/5.0 (linux) AppleWebKit/537.36 jsdom' })
    expect(isMac()).toBe(false)
  })

  it('false for Windows', () => {
    mockNavigator({ platform: 'Win32' })
    expect(isMac()).toBe(false)
  })

  it('prefers userAgentData.platform when present, over navigator.platform', () => {
    mockNavigator({ platform: 'Win32', userAgentDataPlatform: 'macOS' })
    expect(isMac()).toBe(true)
  })

  it('falls back to userAgent when both platform and userAgentData are empty', () => {
    mockNavigator({ platform: '', userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)' })
    expect(isMac()).toBe(true)
  })
})

describe('isAdditiveModifier', () => {
  it('on Mac: only metaKey (Cmd) counts, ctrlKey alone does not', () => {
    mockNavigator({ platform: 'MacIntel' })
    expect(isAdditiveModifier({ ctrlKey: false, metaKey: true })).toBe(true)
    expect(isAdditiveModifier({ ctrlKey: true, metaKey: false })).toBe(false)
    expect(isAdditiveModifier({ ctrlKey: false, metaKey: false })).toBe(false)
  })

  it('elsewhere: only ctrlKey counts, metaKey alone does not', () => {
    mockNavigator({ platform: 'Win32' })
    expect(isAdditiveModifier({ ctrlKey: true, metaKey: false })).toBe(true)
    expect(isAdditiveModifier({ ctrlKey: false, metaKey: true })).toBe(false)
    expect(isAdditiveModifier({ ctrlKey: false, metaKey: false })).toBe(false)
  })
})

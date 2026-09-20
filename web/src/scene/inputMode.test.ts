import { describe, expect, it } from 'vitest'

import { nextInputMode } from './inputMode'

describe('nextInputMode', () => {
  it('a touch pointer switches to touch mode from desktop', () => {
    expect(nextInputMode('desktop', { kind: 'pointerdown', pointerType: 'touch' })).toBe('touch')
  })

  it('a touch pointer stays in touch mode', () => {
    expect(nextInputMode('touch', { kind: 'pointerdown', pointerType: 'touch' })).toBe('touch')
  })

  it('a mouse pointer switches to desktop mode from touch', () => {
    expect(nextInputMode('touch', { kind: 'pointerdown', pointerType: 'mouse' })).toBe('desktop')
  })

  it('a mouse pointer stays in desktop mode', () => {
    expect(nextInputMode('desktop', { kind: 'pointerdown', pointerType: 'mouse' })).toBe('desktop')
  })

  it('a keypress switches to desktop mode from touch', () => {
    expect(nextInputMode('touch', { kind: 'keydown' })).toBe('desktop')
  })

  it('a keypress stays in desktop mode', () => {
    expect(nextInputMode('desktop', { kind: 'keydown' })).toBe('desktop')
  })

  it('a pen pointer is a no-op in touch mode (does not hide the joystick)', () => {
    expect(nextInputMode('touch', { kind: 'pointerdown', pointerType: 'pen' })).toBe('touch')
  })

  it('a pen pointer is a no-op in desktop mode (does not show the joystick)', () => {
    expect(nextInputMode('desktop', { kind: 'pointerdown', pointerType: 'pen' })).toBe('desktop')
  })

  it('an unrecognized pointerType is a no-op', () => {
    expect(nextInputMode('touch', { kind: 'pointerdown', pointerType: 'unknown' })).toBe('touch')
    expect(nextInputMode('desktop', { kind: 'pointerdown', pointerType: 'unknown' })).toBe('desktop')
  })
})

/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

// jsdom (this suite's DOM environment) never lays out CSS, so no test here can measure real pixel
// positions/overlap. These assertions instead pin the specific rules the two toolbar layout bugs
// hinge on -- a regression to either shape would reintroduce the bug even though nothing else in
// the suite would notice (CSS is real for a browser and inert for jsdom).
const CSS = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'index.css'), 'utf8')

/** The declaration block for one CSS selector, or null if the selector isn't found. */
function ruleBody(selector: string): string | null {
  const escaped = selector.replace(/[.[\]]/g, '\\$&')
  const match = new RegExp(`(?<![\\w-])${escaped}\\s*\\{([^}]*)\\}`).exec(CSS)
  return match ? match[1] : null
}

describe('toolbar layout CSS (dev/docs/GUI.md toolbar bug fixes)', () => {
  it('.misc-options (Movers/Radii/Grid, viewport-control-redesign-icon-cluster-replaces) is positioned relative to the quad, not left in document flow', () => {
    const body = ruleBody('.misc-options')
    expect(body).not.toBeNull()
    expect(body).toMatch(/position:\s*absolute/)
    expect(body).toMatch(/(bottom|left):\s*\d/)
  })

  it('.mover-solid-toggle/.radii-toggle have no standalone rule of their own anymore -- replaced by .misc-options-toggle (viewport-control-redesign-icon-cluster-replaces)', () => {
    expect(ruleBody('.mover-solid-toggle')).toBeNull()
    expect(ruleBody('.radii-toggle')).toBeNull()
  })

  it('.grid-control (the old Grid checkbox+dropdown container) has no rule of its own anymore -- replaced by .misc-options-select-wrap', () => {
    expect(ruleBody('.grid-control')).toBeNull()
  })

  it('.toolbar-row is a normal flex-column sibling, not an absolute overlay on top of the quad', () => {
    const body = ruleBody('.toolbar-row')
    expect(body).not.toBeNull()
    expect(body).not.toMatch(/position:\s*absolute/)
  })

  it('.viewport-pane stacks the toolbar above .viewport-content in a flex column', () => {
    const body = ruleBody('.viewport-pane')
    expect(body).not.toBeNull()
    expect(body).toMatch(/flex-direction:\s*column/)
  })
})

/** All declaration blocks for one selector (a plain `ruleBody` only finds the first — some
 * selectors here, like `.misc-options-flyout`, have a second block layered on top). */
function allRuleBodies(selector: string): string[] {
  const escaped = selector.replace(/[.[\]]/g, '\\$&')
  const re = new RegExp(`(?<![\\w-])${escaped}\\s*\\{([^}]*)\\}`, 'g')
  return [...CSS.matchAll(re)].map((m) => m[1])
}

describe('control-cluster/misc-options live bugs found after ship (owner report)', () => {
  it('.misc-options-flyout never wraps onto a second row -- it broke the "stays the trigger\'s own height" requirement outright, not just in the narrow-pane case', () => {
    const bodies = allRuleBodies('.misc-options-flyout')
    const combined = bodies.join('\n')
    expect(combined).toMatch(/flex-wrap:\s*nowrap/)
    expect(combined).not.toMatch(/flex-wrap:\s*wrap\b/)
  })

  it('.misc-options-flyout allows horizontal scroll instead, for the genuine narrow-pane case', () => {
    const combined = allRuleBodies('.misc-options-flyout').join('\n')
    expect(combined).toMatch(/overflow-x:\s*auto/)
  })

  it('.misc-options paints above .control-cluster (a rising tooltip must never render underneath it)', () => {
    const misc = ruleBody('.misc-options')
    const cluster = ruleBody('.control-cluster')
    expect(misc).not.toBeNull()
    expect(cluster).not.toBeNull()
    const miscZ = Number(/z-index:\s*(\d+)/.exec(misc!)?.[1])
    const clusterZ = Number(/z-index:\s*(\d+)/.exec(cluster!)?.[1])
    expect(Number.isNaN(miscZ)).toBe(false)
    expect(Number.isNaN(clusterZ)).toBe(false)
    expect(miscZ).toBeGreaterThan(clusterZ)
  })

  it('[data-tip]::after is left-aligned to its button, not centered -- every button this applies to sits within 8px of the pane edge, and a centered tooltip pushes off-screen', () => {
    const body = ruleBody('[data-tip]::after')
    expect(body).not.toBeNull()
    expect(body).toMatch(/left:\s*0\b/)
    expect(body).not.toMatch(/left:\s*50%/)
    expect(body).not.toMatch(/transform:\s*translateX/)
  })
})

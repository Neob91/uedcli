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
  it('.quad-toolbar (Movers/Radii/Grid) is positioned relative to the quad, not left in document flow', () => {
    const body = ruleBody('.quad-toolbar')
    expect(body).not.toBeNull()
    expect(body).toMatch(/position:\s*absolute/)
    expect(body).toMatch(/(top|right):\s*\d/)
  })

  it('.mover-solid-toggle/.radii-toggle have no standalone rule of their own anymore -- they lay out via .quad-toolbar\'s flex row, not a hardcoded per-button `right` offset (bug fix: anchored to .quad-layout-root, which also spans the org-panel sidebar, a small offset landed the button INSIDE the sidebar)', () => {
    expect(ruleBody('.mover-solid-toggle')).toBeNull()
    expect(ruleBody('.radii-toggle')).toBeNull()
  })

  it('.grid-control (the consolidated Grid checkbox+dropdown) is not independently absolute-positioned', () => {
    const body = ruleBody('.grid-control')
    expect(body).not.toBeNull()
    expect(body).not.toMatch(/position:\s*absolute/)
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

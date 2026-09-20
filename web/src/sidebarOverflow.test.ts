/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

// jsdom (this suite's DOM environment) never lays out CSS, so no test here can measure real pixel
// overflow -- same limitation toolbarLayout.test.ts already documents, and confirmed again for this
// bug fix: no runnable headless browser is available in this sandbox (chrome-headless-shell is
// missing shared libraries with no root to install them, the same gap GUI-PARITY.md records). These
// assertions instead pin the specific rules the sidebar-overflow bug hinges on -- a regression to
// either shape would let the page need horizontal scroll again even though nothing else in the
// suite would notice.
const CSS = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'index.css'), 'utf8')

/** The declaration block for one CSS selector, or null if the selector isn't found. */
function ruleBody(selector: string): string | null {
  const escaped = selector.replace(/[.[\]]/g, '\\$&')
  const match = new RegExp(`(?<![\\w-])${escaped}\\s*\\{([^}]*)\\}`).exec(CSS)
  return match ? match[1] : null
}

describe('sidebar overflow CSS (board item sidebar-can-overflow-viewport-needs-scroll)', () => {
  it('the page root chain clips horizontal overflow instead of letting the whole page scroll', () => {
    // `.sidebar` is a non-shrinking flex child (flex: 0 0 auto) of #app-root, same role
    // `.org-panel-wrapper`/`.inspector-pane-wrapper` used to have (unified-sidebar spec) -- without
    // overflow-x: hidden somewhere in this chain, a narrow viewport (or a manually-reopened sidebar
    // below the responsive breakpoint) forces the whole page wider than the viewport and the PAGE
    // scrolls, instead of the sidebar handling its own overflow internally.
    const body = ruleBody('html,\nbody,\n#root,\n#app-root')
    expect(body).not.toBeNull()
    expect(body).toMatch(/overflow-x:\s*hidden/)
  })

  it('.sidebar stays a non-shrinking flex child, same as the old per-panel wrappers', () => {
    const body = ruleBody('.sidebar')
    expect(body).not.toBeNull()
    expect(body).toMatch(/flex:\s*0 0 auto/)
  })

  it('.sidebar-panel-body scrolls its own horizontal overflow (long folder/actor names, wide inspector values) instead of escaping the sidebar', () => {
    const panel = ruleBody('.sidebar-panel')
    expect(panel).not.toBeNull()
    expect(panel).toMatch(/min-width:\s*0/)
    const panelBody = ruleBody('.sidebar-panel-body')
    expect(panelBody).not.toBeNull()
    expect(panelBody).toMatch(/overflow-x:\s*auto/)
  })

  it('the flex chain down to the sidebar allows shrinking below content size (min-width: 0), so overflow is handled by the sidebar itself, not by growing an ancestor', () => {
    for (const selector of ['.viewport-pane', '.viewport-content', '.quad-layout-root', '.quad-layout']) {
      const body = ruleBody(selector)
      expect(body, `${selector} rule should exist`).not.toBeNull()
      expect(body, `${selector} should have min-width: 0`).toMatch(/min-width:\s*0/)
    }
  })
})

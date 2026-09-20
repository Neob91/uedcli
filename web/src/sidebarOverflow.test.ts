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
    // .org-panel-wrapper/.inspector-pane-wrapper are non-shrinking flex children (flex: 0 0 auto) of
    // #app-root/.quad-layout-root -- without overflow-x: hidden somewhere in this chain, a narrow
    // viewport (or a manually-reopened sidebar below the responsive breakpoint) forces the whole
    // page wider than the viewport and the PAGE scrolls, instead of each sidebar handling its own
    // overflow internally.
    const body = ruleBody('html,\nbody,\n#root,\n#app-root')
    expect(body).not.toBeNull()
    expect(body).toMatch(/overflow-x:\s*hidden/)
  })

  it('.org-panel scrolls its own horizontal overflow (long folder/actor names) instead of escaping the sidebar', () => {
    const body = ruleBody('.org-panel')
    expect(body).not.toBeNull()
    expect(body).toMatch(/min-width:\s*0/)
    expect(body).toMatch(/overflow-x:\s*auto/)
  })

  it('.inspector-pane scrolls its own horizontal overflow (wide inspector values/tables) instead of escaping the sidebar', () => {
    const body = ruleBody('.inspector-pane')
    expect(body).not.toBeNull()
    expect(body).toMatch(/min-width:\s*0/)
    expect(body).toMatch(/overflow-x:\s*auto/)
  })

  it('the flex chain down to each sidebar allows shrinking below content size (min-width: 0), so overflow is handled by the sidebar itself, not by growing an ancestor', () => {
    for (const selector of ['.viewport-pane', '.viewport-content', '.quad-layout-root', '.quad-layout']) {
      const body = ruleBody(selector)
      expect(body, `${selector} rule should exist`).not.toBeNull()
      expect(body, `${selector} should have min-width: 0`).toMatch(/min-width:\s*0/)
    }
  })
})

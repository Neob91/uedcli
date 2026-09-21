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
  // Bug fix: this used to escape only `.[]`, so a selector with parens (e.g. `:not(...)`) left them
  // as regex GROUPING syntax -- the group's own closing `)` doesn't consume the CSS text's literal
  // `)`, so the match silently failed. Escape every regex metacharacter, not a hand-picked subset.
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
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

describe('sidebar fixed-width CSS (bug: sidebar width changed with the selected name\'s length)', () => {
  it('.selection-strip allows shrinking below its (unclamped) text content width', () => {
    // Without this, a long actor/surface name's natural width set this flex item's automatic
    // minimum width, and `.sidebar` (an auto-width flex column) grew to fit it -- the sidebar's
    // rendered WIDTH changed depending on which item was selected, instead of staying the fixed
    // ~280px `.sidebar-panel` (below) already establishes.
    const body = ruleBody('.selection-strip')
    expect(body).not.toBeNull()
    expect(body).toMatch(/min-width:\s*0/)
  })

  it('.selection-strip-text truncates instead of overflowing or silently clipping', () => {
    const body = ruleBody('.selection-strip-text')
    expect(body).not.toBeNull()
    expect(body).toMatch(/min-width:\s*0/)
    expect(body).toMatch(/overflow:\s*hidden/)
    expect(body).toMatch(/white-space:\s*nowrap/)
    expect(body).toMatch(/text-overflow:\s*ellipsis/)
  })
})

describe('sidebar fixed-width CSS, part 2 (bug: a "separate desktop jump" survived the fix above)', () => {
  // The fix above constrains `.selection-strip` so it CAN shrink -- but `.sidebar` itself
  // (flex: 0 0 auto, flex-shrink: 0) never had anything forcing it to use that shrunk size: with no
  // `width` of its own, its flex-basis fell back to its own max-content (content-based) size, which
  // still includes a descendant's unwrapped text even when that descendant has min-width: 0. Giving
  // `.sidebar` an explicit `width` removes content from its sizing equation entirely.
  it('.sidebar has a fixed, non-content-derived width for the collapsed (rail-only) case', () => {
    const body = ruleBody('.sidebar')
    expect(body).not.toBeNull()
    expect(body).toMatch(/width:\s*var\(--sidebar-rail-width\)/)
  })

  it('.sidebar widens to rail + panel only when NOT collapsed, keyed off data-collapsed (not content)', () => {
    const body = ruleBody(".sidebar:not([data-collapsed='true'])")
    expect(body).not.toBeNull()
    expect(body).toMatch(/width:\s*calc\(var\(--sidebar-rail-width\)\s*\+\s*var\(--sidebar-panel-max-width\)\)/)
  })

  it('.sidebar-panel and the expanded .sidebar width share the SAME --sidebar-panel-max-width token (one source of truth)', () => {
    const panel = ruleBody('.sidebar-panel')
    expect(panel).not.toBeNull()
    expect(panel).toMatch(/flex:\s*0 0 var\(--sidebar-panel-max-width\)/)
  })
})

describe('sidebar mobile width CSS (bug: sidebar super wide on mobile for any tab)', () => {
  it('--sidebar-panel-max-width caps the panel to a fraction of the viewport width, not just a fixed px', () => {
    const root = ruleBody(':root')
    expect(root).not.toBeNull()
    expect(root).toMatch(/--sidebar-panel-max-width:\s*min\(var\(--sidebar-panel-width\),\s*calc\(80vw - var\(--sidebar-rail-width\)\)\)/)
  })
})

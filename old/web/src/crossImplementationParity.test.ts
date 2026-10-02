/// <reference types="node" />
import { readFileSync } from 'node:fs'

import { expect, test } from 'vitest'

import init, { WasmResolutionContext } from './wasm/resolve_wasm.js'
import { buildDisplayProps } from './panels/resolveDisplayProps'
import type { EffectiveProp } from './api'

const golden = JSON.parse(readFileSync('../uedcli/tests/fixtures/resolve_golden/nyc_bar.json', 'utf-8'))

/** Flattens an EffectiveProp[] tree back down to its own stated leaves, the same dotted-path
 * convention resolve_actor_props_json/build_golden.py both use -- the inverse of
 * buildDisplayProps's own walk, so this test can compare against golden.actors[name].sparse
 * directly rather than re-deriving a second comparison shape. */
function statedLeaves(props: EffectiveProp[]): Record<string, string> {
  const out: Record<string, string> = {}
  function walk(prefix: string, p: EffectiveProp): void {
    if (p.kind === 'struct') {
      for (const m of p.members) walk(`${prefix ? `${prefix}.` : ''}${m.name}`, m)
    } else if (p.kind === 'array') {
      p.elements.forEach((el, i) => walk(`${prefix}.${i}`, el))
    } else if (p.stored_value !== null) {
      out[prefix] = p.stored_value
    }
  }
  for (const p of props) walk(p.name, p)
  return out
}

test('the frontend WASM walk agrees byte-for-byte with the native /scene sparse map', async () => {
  const wasmBytes = readFileSync('src/wasm/resolve_wasm_bg.wasm')
  await init({ module_or_path: wasmBytes })

  const ctx = new WasmResolutionContext()
  ctx.add_package('DeusEx', readFileSync('../uned/UED22/DeusEx.u'))
  ctx.add_package('Engine', readFileSync('../uned/UED22/Engine.u'))
  ctx.add_package('Core', readFileSync('../uned/UED22/core.u'))

  type ActorEntry = { cls: string; sparse: Record<string, string>; note: string | null }
  const actors = Object.values(golden.actors) as ActorEntry[]

  for (const [fqcn, classGolden] of Object.entries(golden.classes) as [string, unknown][]) {
    const cr = JSON.parse(ctx.resolveClass(fqcn))
    expect(cr).toEqual(classGolden)

    // Round-trip every REAL stated leaf a REAL instance of this class carries, through
    // buildDisplayProps, and confirm the rendered stored_value matches byte-for-byte -- unconditionally
    // (no path-presence gate: a stated golden leaf that buildDisplayProps fails to reproduce, whether
    // through a wrong dotted-path convention or a dropped value, must fail this test, not be silently
    // treated as an orphan).
    const instancesOfThisClass = actors.filter((a) => a.cls === fqcn && a.note === null)
    for (const { sparse } of instancesOfThisClass) {
      const rendered = statedLeaves(buildDisplayProps(cr, sparse))
      for (const [path, value] of Object.entries(sparse)) {
        expect(rendered).toHaveProperty(path, value)
      }
    }
  }
})

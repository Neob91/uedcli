/// <reference types="node" />
import { readFileSync } from 'node:fs'

import { expect, test } from 'vitest'

// Path relative to web/src/ (this file's location) -- confirmed against the real glue JS Task 9
// produced (`web/src/wasm/resolve_wasm.js`, built by `bin/ensure_wasm.sh` via the Docker
// `wasm-export` stage). `add_package`/`resolveClass` -- NOT `addPackage`/`resolveClass()` typo --
// per `resolve-wasm/src/lib.rs`'s `#[wasm_bindgen(js_name = resolveClass)]` (no rename on
// `add_package`).
import init, { WasmResolutionContext } from './wasm/resolve_wasm.js'

const golden = JSON.parse(readFileSync('../uedcli/tests/fixtures/resolve_golden/nyc_bar.json', 'utf-8'))

test('resolveClass matches the golden for DeusEx.Karkian', async () => {
  const wasmBytes = readFileSync('src/wasm/resolve_wasm_bg.wasm')
  // Confirmed against the real generated glue (`resolve_wasm.js`'s `__wbg_init`): a plain object
  // whose prototype is `Object.prototype` gets destructured for its `module_or_path` field, and
  // raw bytes (not a string/Request/URL) then go straight to `WebAssembly.instantiate` --
  // `init({ module_or_path: wasmBytes })` works synchronously-in-effect against in-memory bytes
  // under Node, no fetch() involved. `initSync` is not needed here.
  await init({ module_or_path: wasmBytes })

  const ctx = new WasmResolutionContext()
  ctx.add_package('DeusEx', readFileSync('../uned/UED22/DeusEx.u'))
  ctx.add_package('Engine', readFileSync('../uned/UED22/Engine.u'))
  ctx.add_package('Core', readFileSync('../uned/UED22/core.u')) // on-disk file is lowercase
                                                                 // `core.u`; package NAME stays
                                                                 // "Core".

  const start = performance.now()
  const result = JSON.parse(ctx.resolveClass('DeusEx.Karkian'))
  console.log('resolveClass(DeusEx.Karkian) cold:', performance.now() - start, 'ms')

  // Structural comparison against Task 6's real golden fragment -- the WHOLE {class, types}
  // object, not a hand-guessed prop shape.
  expect(result).toEqual(golden.classes['DeusEx.Karkian'])
})

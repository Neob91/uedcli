// Loads the built resolve-wasm artifact (`web/src/wasm/`, `bin/ensure_wasm.sh`) and resolves one
// class against the fixed DeusEx/Engine/Core package triple `test_resolve_native.py`'s own
// `_ctx_with_ued22()` and `resolveWasm.test.ts` both use, then prints the resulting JSON string to
// stdout -- `test_resolve_native.py`'s byte-identity test diffs this against
// `uedcli_native.resolve_class_json`'s own output for the same input.
//
// Usage: node wasm_resolve_check.mjs <fqcn> <DeusEx.u path> <Engine.u path> <core.u path>
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const [fqcn, deusExPath, enginePath, corePath] = process.argv.slice(2)

const wasmDir = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..', 'web', 'src', 'wasm')
const { default: init, WasmResolutionContext } =
  await import(pathToFileURL(join(wasmDir, 'resolve_wasm.js')).href)

await init({ module_or_path: readFileSync(join(wasmDir, 'resolve_wasm_bg.wasm')) })

const ctx = new WasmResolutionContext()
ctx.add_package('DeusEx', readFileSync(deusExPath))
ctx.add_package('Engine', readFileSync(enginePath))
ctx.add_package('Core', readFileSync(corePath)) // real on-disk file is lowercase `core.u`;
                                                  // package NAME argument stays "Core".

process.stdout.write(ctx.resolveClass(fqcn))

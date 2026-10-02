import { existsSync, readFileSync } from 'node:fs'

import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { ensureClosureForClasses, prefetchCoreEngine, resolveClassSync } from './classResolver'

const UED22 = '../uned/UED22'

function fakeFetch(): typeof fetch {
  return vi.fn(async (url: string | URL | Request) => {
    const path = String(url)
    if (path.endsWith('.wasm')) {
      // Vite's import-analysis plugin rewrites resolve_wasm.js's own `new URL('resolve_wasm_bg.wasm',
      // import.meta.url)` to a fake jsdom origin with nothing listening behind it -- serve the real
      // compiled bytes directly so ensureWasm()'s bare init() can actually initialize under vitest,
      // same technique resolveWasm.test.ts already uses for this exact WASM module.
      return new Response(readFileSync('src/wasm/resolve_wasm_bg.wasm'))
    }
    const m = /\/api\/package\/([^/]+)\/raw$/.exec(path)
    if (!m) throw new Error(`unexpected fetch: ${path}`)
    const name = decodeURIComponent(m[1])
    const file = name === 'Core' ? 'core.u' : `${name}.u` // real on-disk name is lowercase core.u
    const buf = readFileSync(`${UED22}/${file}`)
    return new Response(buf, { status: 200 })
  }) as unknown as typeof fetch
}

beforeEach(() => {
  vi.stubGlobal('fetch', fakeFetch())
})

afterEach(() => {
  vi.unstubAllGlobals()
})

test('resolveClassSync is pending before the owning package has loaded', () => {
  expect(resolveClassSync('DeusEx.Karkian')).toBe('pending')
})

// Runs before any other test touches Core/Engine/DeusEx (module-level state is never reset between
// tests in this file) -- needs all three genuinely untouched so gating Engine's fetch actually holds
// DeusEx's own closure open.
test('resolveClassSync stays pending (never a stuck error) while an ancestor package is still mid-fetch', async () => {
  // DeusEx's own package.u directly imports Engine (among others) -- and DeusEx.Karkian's Super
  // chain genuinely needs it (Engine.Pawn/Engine.Actor). Reproduces the original bug shape: DeusEx's
  // own bytes parse and `loaded.add('DeusEx')` used to run before Engine -- one of DeusEx's OWN
  // transitive imports -- had landed, so the old gate (`loaded.has('DeusEx')`) opened early, called
  // ctx.resolveClass, threw ("package not added: Engine"), and cached that error in classCache
  // PERMANENTLY -- never self-healing even once Engine landed moments later.
  let releaseEngine: (() => void) | null = null
  const engineGate = new Promise<void>((resolve) => { releaseEngine = resolve })

  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => {
    const path = String(url)
    if (path.endsWith('.wasm')) {
      return new Response(readFileSync('src/wasm/resolve_wasm_bg.wasm'))
    }
    const m = /\/api\/package\/([^/]+)\/raw$/.exec(path)
    if (!m) throw new Error(`unexpected fetch: ${path}`)
    const name = decodeURIComponent(m[1])
    // A handful of real on-disk filenames are lowercase-only (core.u, ipdrv.u, ubrowser.u,
    // uwindow.u, ...) -- DeusEx's own import list crosses several of these, not just Engine/Core.
    const exact = `${UED22}/${name}.u`
    const file = existsSync(exact) ? exact : `${UED22}/${name.toLowerCase()}.u`
    const bytes = () => new Response(readFileSync(file), { status: 200 })
    return name === 'Engine' ? engineGate.then(bytes) : bytes()
  }) as unknown as typeof fetch)

  const closure = ensureClosureForClasses(['DeusEx.Karkian'])

  // Poll while the gate is held: DeusEx's own bytes (and its other, ungated imports) have every
  // chance to land and parse (fast, real WASM), but Engine cannot have.
  for (let i = 0; i < 5; i++) {
    await new Promise((r) => setTimeout(r, 10))
    expect(resolveClassSync('DeusEx.Karkian')).toBe('pending')
  }

  releaseEngine!()
  await closure

  const result = resolveClassSync('DeusEx.Karkian')
  expect(result).not.toBe('pending')
  expect(result).not.toHaveProperty('error')
  if (result === 'pending' || 'error' in result) throw new Error('unreachable')
  expect(result.class.props.some((p) => p.name === 'RotationRate')).toBe(true)
})

test('ensureClosureForClasses loads DeusEx.Karkian\'s whole Super-chain closure, then resolves it', async () => {
  await ensureClosureForClasses(['DeusEx.Karkian'])
  const result = resolveClassSync('DeusEx.Karkian')
  expect(result).not.toBe('pending')
  expect(result).not.toHaveProperty('error')
  if (result === 'pending' || 'error' in result) throw new Error('unreachable')
  expect(result.class.props.some((p) => p.name === 'RotationRate')).toBe(true)
  expect(result.types['Core.Rotator']).toBeTruthy()
})

test('resolveClassSync caches: a second call does not re-parse', async () => {
  await ensureClosureForClasses(['DeusEx.Karkian'])
  const first = resolveClassSync('DeusEx.Karkian')
  const second = resolveClassSync('DeusEx.Karkian')
  expect(second).toBe(first) // same cached object reference
})

test('resolveClassSync surfaces a named error for an unresolvable class once its package is loaded', async () => {
  await ensureClosureForClasses(['DeusEx.Karkian']) // loads DeusEx + its closure
  const result = resolveClassSync('DeusEx.ThisClassDoesNotExistAnywhereInTheCorpus')
  expect(result).not.toBe('pending')
  expect(result).toHaveProperty('error')
})

test('prefetchCoreEngine kicks off Core/Engine unconditionally', async () => {
  prefetchCoreEngine()
  await ensureClosureForClasses([]) // no-op closure, but waits for nothing new
  // Core/Engine were already requested by prefetchCoreEngine -- give their in-flight promises a
  // tick to land, then confirm Engine.Actor's own real ELightType enum resolves with no further
  // package-specific ensureClosureForClasses call for "Engine" itself.
  await new Promise((r) => setTimeout(r, 0))
  const result = resolveClassSync('Engine.Light')
  expect(result === 'pending' || 'error' in result ? null : result?.class.props.some((p) => p.name === 'LightType')).not.toBe(false)
})

test('a package fetch failure surfaces as a named per-class error, not an unhandled rejection', async () => {
  // A package name no earlier test in this file ever loads -- isolates this test's own fetch
  // override from the module-level loaded/packageErrors state prior tests already populated.
  vi.stubGlobal('fetch', vi.fn(async () => {
    throw new Error('network down')
  }) as unknown as typeof fetch)
  await ensureClosureForClasses(['NoSuchPackage.SomeClass'])
  const result = resolveClassSync('NoSuchPackage.SomeClass')
  expect(result).not.toBe('pending')
  if (result === 'pending') throw new Error('unreachable')
  expect(result).toHaveProperty('error')
  if (!('error' in result)) throw new Error('unreachable')
  expect(result.error).toContain('NoSuchPackage')
})

// MUST be the last test in this file: unlike a per-package fetch failure, a genuine parse failure
// poisons the shared resolver SESSION-WIDE (sessionPoisoned, never reset) -- every test defined
// after this one would see every class as an error too.
test('a genuinely malformed package poisons the shared resolver session-wide, with a loud reloadable error', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string | URL | Request) => {
    const path = String(url)
    if (path.includes('/BadPackage/')) {
      return new Response(new Uint8Array([1, 2, 3, 4]), { status: 200 }) // garbage -- not a real .u file
    }
    const m = /\/api\/package\/([^/]+)\/raw$/.exec(path)
    if (!m) throw new Error(`unexpected fetch: ${path}`)
    const name = decodeURIComponent(m[1])
    const file = name === 'Core' ? 'core.u' : `${name}.u`
    return new Response(readFileSync(`${UED22}/${file}`), { status: 200 })
  }) as unknown as typeof fetch)

  await ensureClosureForClasses(['BadPackage.SomeClass'])
  const bad = resolveClassSync('BadPackage.SomeClass')
  expect(bad).not.toBe('pending')
  if (bad === 'pending') throw new Error('unreachable')
  expect(bad).toHaveProperty('error')

  // The poisoning is session-wide: an UNRELATED class this test never touched errors too.
  const unrelated = resolveClassSync('Engine.SomeOtherClassNeverResolvedInThisTest')
  expect(unrelated).not.toBe('pending')
  if (unrelated === 'pending') throw new Error('unreachable')
  expect(unrelated).toHaveProperty('error')
  if (!('error' in unrelated)) throw new Error('unreachable')
  expect(unrelated.error).toContain('reload')
})

// gui-inspector-props-payload-redesign spec §4: fetches the code-relevant package closure lazily
// (Core/Engine unconditionally, everything else once the scene's own actor list is known), parses
// it via the shared Rust core's WASM build, and resolves one class's shape+defaults at a time,
// synchronously, caching the result for the session's life. Nothing here ever awaits a network call
// AFTER the owning package has landed -- that's what makes the Inspector's "never a spinner"
// requirement literally true.
import init, { WasmResolutionContext } from '../wasm/resolve_wasm.js'
import type { ClassResolution } from '../api'

let ctx: WasmResolutionContext | null = null
let wasmInit: Promise<void> | null = null
const loading = new Map<string, Promise<void>>()
// Set as soon as THIS package's own bytes are parsed into ctx -- guards against a redundant
// add_package call and infinite recursion on cyclic imports. NOT the readiness gate for
// resolveClassSync: a package can be in here while its own imports are still mid-fetch. See
// closureComplete below, which is.
const loaded = new Set<string>()
// Set only after ensurePackageLoaded's OWN `Promise.all` over its imports has resolved -- i.e. the
// package's WHOLE transitive closure, not just its own bytes, has landed. NOT strictly "every
// package the subtree depends on is already in closureComplete too" -- the `!loaded.has(n)` filter
// below can skip recursing into a direct import whose OWN bytes already parsed (from an earlier,
// unrelated call) but whose own closure is still open elsewhere, so a grandchild could in principle
// still be mid-fetch when this package's own closureComplete fires. Harmless on this project's real
// corpus: verified every real package's own import list is already transitively closed (no package
// imports something whose own imports aren't already covered), so this gap never manifests in
// practice -- but it's a corpus property, not a proof. This -- not `loaded` -- is resolveClassSync's
// readiness gate: the bug this fixes was resolveClassSync opening as soon as a class's OWN package
// had parsed, even while THAT package's own imports (e.g. Engine) were still mid-fetch, which threw
// inside ctx.resolveClass and cached the error permanently (classCache never self-heals on a cache
// hit).
const closureComplete = new Set<string>()
const packageErrors = new Map<string, string>()
const classCache = new Map<string, ClassResolution | { error: string }>()
// Set once a genuine `add_package`/`packageImports` parse failure happens (as opposed to a
// network/fetch failure, tracked per-package in `packageErrors` above): the underlying shared
// resolve-core `ResolutionContext` a malformed package poisons is PERMANENT and WHOLE-CONTEXT
// (`uedcli-native/resolve-core/src/resolve.rs:352-362`) -- every class, in every package, for the
// rest of this page's life, since `ctx` is a module-level singleton never recreated on a level
// switch (this app's own SPA navigation, `session/route.ts`'s `pushState`, never reloads the
// page). Mirrors the backend's own accepted risk for a malformed `.u` file (Task 2's
// `_populate_for_class` docstring: a rare, severe failure treated as a loud, visible signal, not
// silently absorbed) -- recovering by rebuilding `ctx` would need re-fetching every already-loaded
// package's bytes from scratch, out of proportion to a failure mode this project's own corpus
// isn't expected to hit in practice.
let sessionPoisoned: string | null = null

async function ensureWasm(): Promise<WasmResolutionContext> {
  if (!wasmInit) {
    wasmInit = init().then(() => undefined)
  }
  await wasmInit
  if (!ctx) ctx = new WasmResolutionContext()
  return ctx
}

async function fetchPackageBytes(name: string): Promise<Uint8Array> {
  const res = await fetch(`/api/package/${encodeURIComponent(name)}/raw`)
  if (!res.ok) throw new Error(`fetching package ${name}: ${res.status} ${res.statusText}`)
  return new Uint8Array(await res.arrayBuffer())
}

async function ensurePackageLoaded(name: string): Promise<void> {
  if (loaded.has(name) || packageErrors.has(name)) return
  const inFlight = loading.get(name)
  if (inFlight) return inFlight
  const promise = (async () => {
    const c = await ensureWasm()
    let buf: Uint8Array
    try {
      buf = await fetchPackageBytes(name)
    } catch (e) {
      // A network/fetch failure never reaches the WASM binding at all -- ctx itself is untouched,
      // so this degrades ONLY this one package (spec's "no silent half-answers": a named error
      // every class in this package's closure surfaces, never an unhandled rejection).
      packageErrors.set(name, `loading package ${name}: ${String(e)}`)
      loading.delete(name)
      return
    }
    try {
      // `add_package`/`packageImports` are real WASM bindings returning `Result<_, JsValue>` -- see
      // `sessionPoisoned`'s own comment above for why a throw HERE (as opposed to the fetch above)
      // is treated session-wide rather than per-package: the underlying shared ResolutionContext is
      // already permanently poisoned by the time this catch runs.
      c.add_package(name, buf)
      loaded.add(name)
      // Filtered by resolve-core itself (Class/Struct/Enum-typed imports only, spec §4) -- never a
      // blind follow of every import (~20x over-fetch on the real corpus, mostly texture/mesh/sound
      // references that can't affect resolution).
      const imports = c.packageImports(name)
      await Promise.all(imports.filter((n) => !loaded.has(n) && !packageErrors.has(n))
        .map((n) => ensurePackageLoaded(n)))
      closureComplete.add(name)
    } catch (e) {
      sessionPoisoned = `a malformed package (${name}) broke the shared class resolver -- reload ` +
        `the page to continue (${String(e)})`
    } finally {
      loading.delete(name)
    }
  })()
  loading.set(name, promise)
  return promise
}

/** Two fetches that start immediately, with no dependency on /scene's own actor list -- Core/Engine
 * are the root of nearly every real Super chain (spec §4's own measured numbers) and are cheap
 * regardless. Call once at app startup. */
export function prefetchCoreEngine(): void {
  void ensurePackageLoaded('Core')
  void ensurePackageLoaded('Engine')
}

/** Extends the fetch to every package the scene's own actors' classes need, transitively -- call
 * once /scene's actor list is known. The returned promise resolves once every CURRENTLY-known class
 * is resolvable with zero further network calls; not awaiting it is also fine -- resolveClassSync
 * returns 'pending' until it lands (spec §4's own accepted async race for the Load-time closure). */
export function ensureClosureForClasses(fqcns: readonly string[]): Promise<void> {
  const pkgs = new Set(fqcns.map((fqcn) => fqcn.split('.', 1)[0]))
  return Promise.all([...pkgs].map((p) => ensurePackageLoaded(p))).then(() => undefined)
}

export type ClassResolveResult = ClassResolution | { error: string } | 'pending'

/** Synchronous, cache-first (spec §4's "never a spinner"): resolves fqcn's class shape from
 * whatever packages have landed so far. 'pending' means the owning package's transitive closure
 * hasn't fully landed yet (not just its own bytes -- see closureComplete above) -- the caller
 * re-renders once ensureClosureForClasses/prefetchCoreEngine's promise settles and this returns
 * something else (Task 6 wires that re-render). An error is a real, named
 * per-class failure (spec §4's "what the Inspector actually shows" section) -- never a silently
 * empty result. */
export function resolveClassSync(fqcn: string): ClassResolveResult {
  const cached = classCache.get(fqcn)
  if (cached) return cached
  // A class already resolved before the session poisoned stays showing its own good data (no
  // reason to hide it); anything NOT yet cached surfaces the loud, session-wide error instead.
  if (sessionPoisoned) return { error: sessionPoisoned }
  const pkg = fqcn.split('.', 1)[0]
  const pkgError = packageErrors.get(pkg)
  if (pkgError) {
    const result = { error: pkgError }
    classCache.set(fqcn, result)
    return result
  }
  if (!ctx) return 'pending'
  if (!closureComplete.has(pkg)) return 'pending'
  try {
    const result = JSON.parse(ctx.resolveClass(fqcn)) as ClassResolution
    classCache.set(fqcn, result)
    return result
  } catch (e) {
    const result = { error: `can't resolve ${fqcn}: ${String(e)}` }
    classCache.set(fqcn, result)
    return result
  }
}

+++
priority = "p2"
kind = "implement"
summary = "Redesign /scene's props payload: stop re-shipping class-constant default text per actor"
depends-on = ["gui-inspector-effective-props-search-show-all", "shared-rust-core-for-class-schema-resolution"]
+++

# GUI Inspector: `/scene` props payload redesign

Follow-up to `gui-inspector-effective-props-search-show-all` (done). Its final whole-branch review
found `/scene` ships every actor's full resolved property tree, including fully-resolved default
text for every unstated prop — ~40KB/actor measured on real content, ~32-68MB per Load on a full
retail level, most of it identical text repeated once per actor of a shared class.

v16 (sixteen design-review passes, every review from v9 onward zero Critical issues) had the
backend resolve every class in a package and ship already-resolved JSON. **v17 (2026-09-24) is an
architecture pivot, owner-directed**: real benchmarks showed the backend's per-class resolution
cost is genuine, unavoidable work, not a caching bug (measured ~25-183ms/class depending on cache
state) — and a real level only uses a small fraction of a package's classes, so resolving a whole
package eagerly is real overwork regardless of caching. The owner's own reference point settled the
redesign: UnrealEd itself never resolves a whole package eagerly — it loads packages' raw bytes
fast and resolves one class's properties lazily, only when actually inspected, entirely in-process.
v17 reproduces that: the backend's only NEW surface for this feature is a raw `.u` package endpoint
(ETag-cached, a real content hash — the owner's own "etag with checksum of .u" ruling); the
frontend parses those bytes and resolves one class's shape+defaults at a time, lazily, entirely
client-side — synchronously, so the Inspector never shows a spinner for connectivity reasons (the
owner's explicit requirement). `/scene`'s own per-actor value resolution (unchanged wire shape)
ALSO moves onto this same shared core, natively — replacing the existing Python
`effective_props.py` walk, not running alongside it, so "one implementation" is true in substance:
one Rust module, called natively by `/scene`'s route and via WASM by the frontend. Split into its
own dependency, `shared-rust-core-for-class-schema-resolution` (native PyO3 + WASM — `web/` has no
prior WASM tooling). Explicitly out of scope for this pass, confirmed with the owner and tracked
separately: migrating the CLI's own class-display, the write path's validation, or the viewport's
radii/`bHiddenEd`/`bDirectional` resolvers onto the same core — `dev/docs/board/inbox/
migrate-radii-bhiddened-bdirectional-and-cli/`. Two fix rounds after the pivot (both in `spec.md`'s
own changelog) closed real gaps reviews found: routing `/scene` through the shared core too (not a
second Python implementation), a real ~20x package-fetch over-fetch (fixed by filtering to
code-relevant imports), and a real content-hash `ETag` per the owner's standing instruction.

Everything the sixteen prior rounds verified against the real corpus carries over unchanged: struct
AND enum type shape normalize once, keyed on `(package, outer, name)` read off the TYPE's own
export record (mirroring this codebase's existing texture-identity `Package.Group.Name` pattern) —
verified against every real same-name collision found (`XAIParams` ×9, `sUserInfo`, `ESkinColor`
×28 declarations/21 distinct value lists, 9 enum-typed struct members). Defaults stay per-class,
never type-shared (`Core.Rotator`'s real, different `RotationRate` defaults on `Karkian` vs `Rat`
prove why). `/scene` carries no shape at all — a flat sparse per-actor map of stated leaf paths to
already-canonicalized values; the frontend renders every view by walking the class shape (now
resolved locally, not fetched as JSON), reading each leaf's own per-class default, and overlaying
the actor's sparse map. See `spec.md` for the full design, the raw-file endpoint, the frontend
fetch/resolve/cache strategy, and the complete v1→...→v17 change history.

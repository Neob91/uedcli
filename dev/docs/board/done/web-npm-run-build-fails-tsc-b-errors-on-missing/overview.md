+++
priority = "p2"
kind = "debug"
summary = "web npm run build fails: tsc -b errors on missing @types/node in test files"
+++

# web npm run build fails: tsc -b errors on missing @types/node in test files

Fixed (commit `b8d82ae1`): `@types/node` was already a devDependency, but `tsconfig.app.json`'s
`"types": ["vite/client"]` is an explicit allowlist that excludes it — added `"node"` to that array.
A second, separate pre-existing error then surfaced (`BrushOutlines.test.tsx`'s unsafe `as` cast
between unrelated types) — fixed with a proper type-predicate `filter`. `npm run build` now succeeds
end to end; full `vitest run` (48 files, 433 tests) still green.

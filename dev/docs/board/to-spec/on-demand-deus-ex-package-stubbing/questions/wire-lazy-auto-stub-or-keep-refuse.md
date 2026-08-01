# Should `level materialize`/`preview` auto-stub a referenced v68 package, or keep refusing?

## Context

`direction/containers.md` ("What we want") says stubbing is **automatic and lazy, triggered at
package resolution rather than by a verb the user must remember**. But the code does not do this:
`stub_missing_packages` (the auto-trigger core, `stub.py:322`) has **no production caller**. Today
`level materialize`/`level preview` instead hit `packages.unloadable_v68_packages` and **refuse** the
build with a named error telling the user to run `substrate stub <pkg>` first.

So the tool ships the opposite of the stated intent. Two coherent resolutions:

- **Wire the auto-trigger (recommended).** Call `stub_missing_packages` on the unstubbed-v68 set at
  the materialize/preview resolution pre-pass, before the refuse check. A referenced v68 code package
  is stubbed on demand; the build proceeds. Machinery already exists and is tested — only the call
  site is missing. Cost: a first materialize of a level with a new v68 dep now runs a multi-second
  container stub build inline.
- **Keep refuse-and-tell, and revise the direction doc.** Treat the explicit `substrate stub` verb +
  the named refusal as the intended UX. Then `direction/containers.md` "automatic and lazy" is stale
  and needs an owner-approved edit.

Either way a `direction/` doc changes (wiring makes architecture match it; keeping refuse means
editing it), so this is the owner's call.

## Answer

<!-- Empty = open. -->

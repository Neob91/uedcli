# `actor folder rename OLD NEW` where no actor is filed under OLD — error or no-op?

## Context

`OLD` is an exact literal folder path, not a glob. If nothing is filed under it:

- **Exit 2 naming OLD (recommended).** Conventions: "an exact name matching nothing is an error; an
  empty GLOB or set result is not." A typo'd source folder (`rename castle.twoer keep`) should fail
  loudly rather than silently do nothing and report success.
- **Clean no-op, exit 0.** Treats a folder rename like a set operation over an empty selection.
  Simpler to script in bulk, but hides typos.

Recommendation: exit 2. The source path is exact and user-typed; a silent success on a mistyped
source is exactly the failure the "exact match ⇒ error" rule guards against. (Note: this differs
from `actor folder set --to X -` reading empty stdin, which is a clean no-op — there the empty set
came from an upstream query, here the path is typed directly.)

## Answer

<!-- Empty = open. -->

+++
priority = "p1"
kind = "implement"
summary = "upackage.load_package has zero caching -- 3404 reparse calls rendering one photo"
+++

# upackage.load_package has zero caching

Companion finding to `port-ue1-package-primitive-decode-to-rust-61m` (same profiling pass,
2026-09-11) -- filed separately because the fix here is caching, not a Rust port, and might be
cheaper and higher-leverage than either Rust-conversion item: `uedcli/upackage.py:177
load_package` has no memoization at all (checked: no `lru_cache`, no manual dict keyed by path) --
every call re-opens and re-parses the file from disk (`_parse_package.py:201`'s own docstring
context notwithstanding). Rendering ONE `level photo --native` shot of `IsvKran32.unr` (1439 mesh
actor instances, only 108 distinct meshes) called `load_package`/`_parse_package` 3,404 times.

`uprops/values.py:507 resolve_class_defaults`'s own comment says packages load "once (shared with
the render cache)" -- implying a cache exists somewhere in that chain-walk, but it isn't preventing
the 3,404-call count seen here across repeated actor instances of the same handful of classes.

Not sized or root-caused beyond the call count above -- worth a look at whether a simple
path-keyed cache on `load_package` (or a level of caching in whatever "render cache" the comment
refers to) collapses most of these 3,404 calls into a much smaller distinct-package count, before
committing to the larger Rust-port work in the two companion items.

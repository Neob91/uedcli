+++
priority = "p2"
kind = "implement"
summary = "uscript: cross-package struct type not resolved (var IpAddr X)"
+++

# uscript: cross-package struct type not resolved (var IpAddr X)

Found compiling the real UT99 `IpServer` package (after the `byte -> string` conversion and
`P.static.Foo()` fixes, both closed). `UdpServerUplink` has `var IpAddr MasterServerIpAddr;` — `IpAddr`
is a struct declared in `Engine` (a native engine struct), not in the compiling package.

`compile.py`'s `_resolve_var_type` only resolves a struct type through `b.local_structs` (structs
declared in the CURRENTLY-COMPILING package); anything else falls through to `env.resolve_class(base)`,
which only knows CLASSES, not structs from another package — raising `NotImplementedError: var
'MasterServerIpAddr': unknown type 'IpAddr' (not scalar/local/class)`.

Not fixed here — this is a different, bigger gap than the two just closed: it needs a way to resolve a
struct DECLARATION (fields, types, layout — needed for `PT_STRUCT` defaults) from an already-compiled
package, not just a class or enum. Likely needs `ClassGraph`/`InstallEnv` extended with a struct lookup
that decodes a struct export from another package's `.u`, mirroring how enum tags already resolve
cross-package (`ClassGraph.enum_ordinal`). Scoped out per this session's instructions (report, don't
chain a third fix). Blocks `IpServer` from a corpus win. Decompiled sources + a fresh UT99-UCC golden
are saved offline (not committed — scratch) at `_scratch/uscript_survey/IpServer/` in this worktree.

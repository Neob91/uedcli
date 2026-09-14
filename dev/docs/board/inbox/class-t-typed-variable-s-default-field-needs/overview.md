+++
priority = "p3"
kind = "debug"
summary = "class<T>-typed variable's .default.Field needs meta-class type tracking"
+++

# class<T>-typed variable's .default.Field needs meta-class type tracking

Found chasing the real UT99 stock package `UTServerAdmin` (`UTImageServer.uc`,
`UTServerAdmin.uc`) as a corpus candidate — not pursued further; `ASPMutator` landed as the corpus
win instead (`USCRIPT-COMPILER.md`). Left open for whoever picks up `UTServerAdmin` next.

`class'X'.default.Field` (a CLASS LITERAL's default) is fixed and pinned
(`test_uscript_package.py::test_class_literal_default_field_access`, `pkg_UscDefProbe`) — see
`USCRIPT-COMPILER.md`'s ASPMutator entry for the `ClassContext`(0x12)/`DefaultVariable`(0x02)
mechanism. `UTServerAdmin.LoadGameTypes` hits a DIFFERENT, unfixed shape:
`TempClass.Default.GameName` where `TempClass` is a LOCAL of declared type `class<GameInfo>` (via
`DynamicLoadObject(...)`), not a literal. `lower.type_label()` collapses EVERY `class<T>` declaration
to the bare string `"class"` — the meta-class `T` is discarded, so `Scope`/`Symbol` has no way to
recover `GameInfo` when resolving `GameName`'s type/owner at the `.default.` access.

`UTServerAdmin.uc` has MANY such occurrences, and not all are simple locals — some are `class<T>(x)`
METACLASS CASTS used inline (`class<DeathMatchPlus>(GameClass).Default.MaxPlayers`), and at least one
NESTED chain (`GameClass.Default.MapListType.Default.Maps[i]`, where `MapListType` is itself a
`class<T>`-typed FIELD read off another class's default). A real fix needs a general mechanism to
track the meta-class through: local/param/member declarations, metaclass casts, and reading a
`class<T>`-typed field off a `.default` access — not a narrow patch for one shape. Likely design:
thread a parallel `meta` string alongside the existing "class" type label (a new `Symbol.meta`/
`Scope` lookup, populated from `TypeRef.meta_class` at declaration sites and from a metaclass cast's
own AST node), read only by `lower._ex_member`'s `.default` branch — leaving every existing "class"-
typed equality check (casts, value-size, `_CONV`) untouched.

Not attempted — larger than the ASPMutator-path fixes and not needed for that win.

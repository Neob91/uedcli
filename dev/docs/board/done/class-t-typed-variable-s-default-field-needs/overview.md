+++
priority = "p3"
kind = "debug"
summary = "class<T>-typed variable's .default.Field needs meta-class type tracking"
spikes = ["dev/docs/spikes/2026-09-14-utserveradmin-class-ref-gaps/"]
+++

# class<T>-typed variable's .default.Field needs meta-class type tracking

FIXED 2026-09-14 (`lower._meta_class_of` + `natives.ClassSig.member_meta`) — see
`USCRIPT-COMPILER.md`'s `UTServerAdmin` entry and the spike above. `UTServerAdmin` (4 classes) is
now a real corpus win at `perm_gate`, `fixtures/uscript/ut99/UTServerAdmin/`.

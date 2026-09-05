+++
priority = "p2"
kind = "debug"
summary = "native/saveorder.py msvc_qsort may be the classic-variant mis-port (latent within-tie order bug)"
+++

# `native/saveorder.py` msvc_qsort — verify it's the faithful MSVC variant

Found during the uscript ordering RE (2026-09-05): UED22's `SavePackage` sorts the name/import/export
tables with the **modern MSVC `qsort`** (`core.dll` `appQsort`@0x315c0 → CRT qsort@0x77cb0:
median-kept-in-place, equal-run-skipping Hoare partition, `shortsort` for runs ≤8). `uscript/
ordering.py` originally had the CLASSIC K&R median-of-3 quicksort, which produces a DIFFERENT unstable
permutation of equal-key runs — and that permutation is part of the byte-exact output. Fixed in
uscript (`fc8c539`).

`uedcli/native/saveorder.py` (the native-materialize map path) has its OWN `msvc_qsort` copy. If it's
the same classic mis-port, the map campaign has a latent within-tie ordering bug. It hasn't surfaced
because `parity_gate.py` is identity/permutation-based (table ORDER is an excluded permutation there),
so a wrong tie order passes that gate — but it would break any move toward RAW byte parity on maps.

Action: diff `native/saveorder.py`'s qsort against the faithful port now in `uscript/ordering.py`
(the modern MSVC variant); if it differs, port the faithful one. Owner of the native campaign to
confirm whether raw-byte table order matters there.

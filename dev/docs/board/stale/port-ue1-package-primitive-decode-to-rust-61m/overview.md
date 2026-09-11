+++
priority = "p1"
kind = "implement"
summary = "Port UE1 package primitive decode (read_compact_index/read_name/read_fstring/_parse_package) to Rust -- 61M-call hot loop"
+++

# Port UE1 package primitive decode to Rust

Superseded by `unify-ue1-package-read-primitives-into-one-rust`, which does this Rust port plus
consolidates 5 other files (7 duplicate decoders total, one file carries two) onto the same core.

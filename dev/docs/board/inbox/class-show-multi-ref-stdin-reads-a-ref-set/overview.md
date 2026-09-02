+++
priority = "p3"
kind = "implement"
summary = "class show: multi-ref + stdin (- reads a ref set) deferred from C1"
+++

# class show: multi-ref + stdin (`-`) deferred from C1

The class-arm spec's verb table lists `class show <ref>… | -` (multiple refs, or `-` to read a ref
set from stdin, empty stdin a clean exit-0 no-op). C1 shipped `class show <Package.Class>` as a
single positional (the pre-existing shape) plus the Facts block and `--json`, matching C1's "Done
when" wording (singular `<mesh-class>`). Multi-ref + stdin was **deliberately not built** — it is a
larger parser/dispatch change (stdin reading, JSONL-per-ref `--json` output) and not required by C1's
stated deliverable.

When picked up: `--json` over multiple refs should emit one object per line (JSONL). Keep the
single-ref behaviour identical.

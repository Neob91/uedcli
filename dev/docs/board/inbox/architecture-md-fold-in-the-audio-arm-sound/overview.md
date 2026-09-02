+++
priority = "p2"
kind = "owner-question"
summary = "OWNER-GATED doc fold-back: add the audio arm (sound + music) to architecture.md."
+++

# [OWNER] architecture.md: fold in the audio arm (sound + music)

The `sound-corpus-remeasure` build shipped the audio arm (phase a). Per `rules/documentation.md`
specs are ephemeral and fold into `architecture.md` on merge, but `dev/docs/` is owner-gated. Proposed
text below — please confirm or edit, then it lands in `architecture.md` (audio arm).

## Proposed text

> ### Asset catalog — the audio arms (sound + music)
>
> Two nouns, `sound` and `music`, catalog the substrate's audio, mirroring the class arm. Modules:
>
> - `audioindex.py` — offline enumeration over the composed package path (header-only, via
>   `upackage.load_package`): the exports of class `Sound` (kind `sound`) or `Music` (kind `music`),
>   each carrying its dotted `object_path`, Outer group, and package file path. A single unparseable
>   package is skipped with a stderr note. Identity follows the texture arm's collision rule:
>   `Package.Name` when the bare name is unique in its package, else the full dotted
>   `Package.Group.Name`. `AudioIndex.resolve` reduces either spelling to the one stored identity; an
>   ambiguous 2-part (collided bare name) or unknown ref exits 2.
> - `audio_catalog.py` — the classification store: one git-tracked shard per object under
>   `<catalog>/classified/<kind>/<identity-segments>.json`, payload `{kind, ref, tags, description}`.
>   A private copy of the class arm's shard/flock/atomic-write shape, with two divergences: a
>   variable-arity ref parser (≥2 components), and the **refuse-then-`--force`** write rule (a `set`
>   over an existing shard refuses; `--force` replaces wholesale — no union, no per-field merge).
> - `umxtitle.py` — sniffs a `.umx`'s embedded tracker-module title by magic (IT/S3M/XM), reporting
>   an unrecognised container as `(None, "unknown")`.
> - `cli/commands/audio.py` — one kind-parametrised handler behind `cli/parsers/{sound,music}.py`;
>   `resources.audio_index(project, kind)` is the mockable enumeration seam.
>
> Phase (b) — sample decoding (`sound preview` spectrograms, duration/rate/channels, `sound export`)
> — is deferred behind a separate `.uax`-decode spike and is absent from the phase-(a) parser.

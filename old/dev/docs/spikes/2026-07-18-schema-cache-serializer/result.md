# Spike: schema-cache serializer format (JSON vs compact binary)

**Question (spec §4.4/§9):** does `json.loads` on the ACTUAL v1 `PackageSchema` bundle stay well
under the `load_package` table parse it replaces, or does it "approach the ~13 ms pickle number"?
If the latter, pick a compact stdlib binary format up front (before any cache entry is written, to
avoid burning a `SCHEMA_CACHE_VERSION` on a later swap).

**Harness:** `spike.py` (committed here). Builds the real v1 bundle — class list, cmap, super-ref
FQCN strings, abstract flags, own-property schema (with local enum names) — for the install
`DeusEx.u` (§9's reference package, the largest realistic code package), serializes it, and times the
median decode over 30 runs, host-native in the dev venv.

## Result (DeusEx.u — 5.39 MB, 1158 classes, 4295 own props)

| format | blob size | median decode | vs the 135 ms parse it replaces |
|---|---|---|---|
| **JSON** (`json.loads`) | 1017.9 KB | **16.69 ms** | 12% |
| **marshal** (`marshal.loads`) | 507.6 KB | **5.71 ms** | 4% |
| `load_package` (the parse we skip) | — | 135.71 ms | 100% |

## Decision: marshal (compact stdlib binary)

§9's expectation was that v1's small bundle would make JSON decode negligible (≪ 13 ms). It did
NOT: **JSON came out at 16.69 ms — ABOVE the ~13 ms pickle baseline** the trigger names, and its
blob is 2× the size. Per §9's explicit rule ("if JSON parse approaches the ~13 ms pickle number …
pick a compact stdlib binary format up front"), the trigger fired, so v1 locks **marshal**:

- **Fast + compact:** 5.71 ms / 508 KB — a third of JSON's time, half its size.
- **No pickle RCE:** `marshal` only reconstructs basic containers/scalars (dict/list/tuple/str/int/
  bool/None); it does NOT execute arbitrary code on load, so §4.4's safety objection to `pickle`
  does not apply. (`marshal` can raise on malformed input — handled: a corrupt/unloadable entry is a
  MISS, re-decoded, never an abort; entries land via atomic tmp+`os.replace`, so no torn read.)
- **Version fragility is contained.** `marshal`'s wire format is tied to the CPython minor version.
  The tool pins Python 3.12 (`bin/_venv.sh`), whose `marshal` format is stable across all 3.12.x
  patch releases. A Python-minor change (or any decoder/shape change) makes an old blob fail to load
  → treated as a MISS → re-decode. Belt-and-braces: `SCHEMA_CACHE_VERSION` is folded into the key +
  `v<N>/` path, and a `"v"` field inside the blob is version-checked on load. So a format drift can
  never serve a wrongly-shaped entry — it only forces a re-decode.
- **Nuitka:** the release binary bundles its own CPython; `marshal` is self-consistent within a
  build, and cross-build format drift again degrades to a re-decode of a derivable cache, never a
  crash.

Trade-off accepted: the blob is not human-inspectable by eye (JSON's debugging nicety), and the
committed frozen-golden blob (§11 version guard) is Python-minor-specific — a Python upgrade trips
it, which is the DESIRED signal (the on-disk format genuinely changed → refresh the golden or bump
the version).

## Reproduce

```
.venv/bin/python dev/docs/spikes/2026-07-18-schema-cache-serializer/spike.py [PKG.u]
```

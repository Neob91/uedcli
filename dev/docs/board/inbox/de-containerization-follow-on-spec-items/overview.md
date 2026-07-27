+++
priority = "p2"
kind = "unknown"
summary = "De-containerization follow-on spec items"
+++

# De-containerization follow-on spec items

(surfaced by the 2026-06-27 spike series;
all gated on Andrzej's scope decision Q0 in the roadmap spec). Each is its own future
`[spec]`/`[spike]`:
- `[spec]` p2 — **Native package WRITER module** (`package_writer.py`): from-scratch
  serializer from the proven primitives (`package_rw` encoders + `prop_writer` + StateFrame),
  incl. offset back-patch, GUID/generation + version policy, `ULevel` body, and patching
  internal absolute offsets (FMipmap/lazy-array/Model) when a body is relocated. (Phase B.)
- `[spec]` p2 — **Native `texture sync`** wired to `utexture` decode (drop the UCC/PCX/
  container seam). (Phase A; lowest-risk immediate win.)
- `[chore]` p3 — **Fold `umodel_serialize.detect_prefix` back into `umodel_parser.py`** so
  the READ parser handles the 57-byte UPrimitive-prefix variant (243 models; one,
  `00_TrainingCombat.dx Model413`, has real geometry the fixed-42 assumption mis-reads).
  The serializer already auto-detects; the parser doesn't. Mind its callers
  (`native_render.py` etc.). Surfaced by `spikes/2026-06-28-umodel-serialize-byte-exact.md`.
- `[spike]` p2 — **Native `Model` GAME-load gate** (the cheap D2 de-risk, now unblocked):
  hand-author a minimal carved-room `Model`'s arrays, emit natively via `umodel_serialize`
  + the package writer, load in `dx-game`, confirm player spawns. Serialization is proven
  byte-exact (`decisions.md` 2026-06-28); this tests a *natively-emitted* (vs editor-built)
  Model end-to-end. Gates Q0's D2 commitment.
- `[spec]` p2 — **Native qualification** in `qualify.py` (import-table read + manifest
  name→package index w/ load-order collision policy), replacing OBJ DEPENDENCIES/OBJ LIST.
- ~~`[spike]` p3 — **Native mesh DECODER**~~ — **DONE 2026-07-25**
  (`spikes/2026-07-25-native-mesh-decode/`): full `UMesh`/`ULodMesh` body decodes byte-exact on
  902 meshes (466 retail v68 + 436 UED22 v69), vertex stride self-detects, textured render
  proven. `umodel.exe` is no longer needed for a mesh READ — it survives only inside the stub
  pipeline. Remaining: productise the harness into `uedcli/` (rides the asset-catalog build).
- `[spike]` p3 — **Native textured preview** — **superseded: specced as `level preview --native`
  (Andrzej 2026-07-16)**; see `specs/2026-07-16-native-preview-design.md` + the `to-plan.md` entry.
- `[spec]` p3 — **Native lighting baker** (2nd long pole): per-lumel raytrace producing the
  `FLightMesh` + lumel bytes (~1.7MB/small map); downstream of D2. Plus native pathnode
  reachspec build (moderate).
- `[spike]` p3 — **Native sound/music decode** (`.uax`/`.umx`): DeusEx `.uax` has NO RIFF
  (raw PCM or other encoding — storage TBD); off the de-containerization path (external
  refs), for a future sound catalog.

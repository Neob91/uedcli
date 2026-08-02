# Four asset-catalog decisions still open from gate round 1

## Context

Round 1 of the asset-catalog spec gate (3 cold Opus reviewers, 2026-07-26, ~58 findings, all three
verdicts "not ready to build on") raised five decisions only you can make. **Ruling 5 is in** —
`asset-catalog/` as the directory name, `direction/projects-and-config.md` updated. Four remain.

Terms used below: **identity** is the string that names a texture's stored description on disk, so
changing it orphans every classification already written. A **shard** is one such stored
description. A **procedural** texture is one the game generates at runtime (fire, water) rather than
storing pixels for.

**1. Does texture identity cover the TRANSPARENCY MASK, and is the preview image addressed by the
identity or by its own digest?** (all 3 reviewers.) §3b freezes identity as `sha256(w, h, RGB)`;
§3a says the preview PNG is content-addressed by "the bare hex sha256 of its pixels" AND that "for
textures the preview hash IS the identity — no second digest". Those cannot both hold, because the
decode path already returns a mask and the gated native-texture-decode spec pins the mask as derived
from pixel data. If the preview carries the mask, its digest ≠ identity and two textures with
identical RGB but different masks **share one preview file** — an agent classifying a masked grille
is handed the opaque twin's image, the misattribution decision 14 bans the contact sheet to prevent.
If the preview drops the mask, every masked texture is shown OPAQUE — exactly the defect §4d was
added to surface. **Identity is frozen and is every shard's path, so this is not revisitable after
shards exist.**

**2. Are procedural textures name-keyed?** (2 of 3; one called it structural.) §4a widens
enumeration to `Engine.Texture` descendants, and every `FireTexture`/`WetTexture`/`WaveTexture`/
`IceTexture`/`ScriptedTexture` stores mips with `DataCount == 0`. No pixels ⇒ no pixel-hash key ⇒
§3a's "cannot be classified". So water and fire are enumerable, referenceable and **permanently
unclassifiable**; `texture list --unclassified` never empties and `classify status` never reaches
done. **`direction/asset-catalog.md` may already answer this**: "Identity: content hash where
content exists, **name where it does not**" — a procedural texture has no content, so your own rule
arguably prescribes the name fallback the spec omits.

**3. Is `classify set -`'s JSONL an approved THIRD stdin convention?** (all 3.) `conventions.md`
says "Exactly TWO stdin conventions … never add a third"; `direction/asset-catalog.md` blesses
"`classify set -` reads JSONL". Two of your protected docs conflict, and inside one noun `-` means a
name list for `show`/`preview` and JSONL for `classify set`. Needs a carve-out in `conventions.md`
or the feature dropped.

**4. How are editor-icon sprites detected?** §6 marks them via an "icon **group**" pattern set, but
measured against tracked `uned/UED22/Engine.u`: 28 of its 32 texture exports are **groupless** —
`S_Weapon`, `S_Camera`, `S_ZoneInfo`, `S_Ambient`, … — and the only groups present are fonts. A
group pattern matches NOTHING, so every sprite class would report `preview_state: ok` and `prewarm`
would count hundreds of lightbulb glyphs as covered — inverting the honest reporting §6 exists to
guarantee. The only signal that exists is the `S_` NAME prefix, which `conventions.md` rejects for
class questions and §0 forbids as inference. Needs a ruling or an explicit config of icon **refs**.

**Also escalated, because it is authored-work-destroying and half design:** `classify set` has no
defined behaviour over an existing shard (replace / merge / refuse), against `direction/safety.md`
"a destination that already exists is never written over silently"; **pixel-hash dedup defeats §3b's
own conflict-free-merge premise** (two agents classifying two differently-NAMED refs with identical
pixels write the SAME shard, the second silently overwriting the first, while the write-once `ref`
still names the first); and **no re-key path exists across a pixel edit**, so
`classify prune --outdated` deletes descriptions that are still accurate — on a project that edits
its own `LUM_CoreTex.utx`.

The remaining ~45 findings need no ruling and are the agent's to fix once these land.

## Options

These are four independent rulings rather than a menu; 2 and the `classify set` case each have a
default your own protected docs arguably already imply:

- **2** — take `direction/asset-catalog.md` at its word: name-key a texture that has no pixels.
- **`classify set` over an existing shard** — take `direction/safety.md` at its word: refuse rather
  than overwrite.
- **1, 3 and 4** have no implied default and genuinely need you.

## Recommendation

Answer 1 first and separately: it is the only one that is **irreversible** once shards exist, and 2
depends on how you resolve it.

## Answer

*(Owner ruled 2026-08-02 via AskUserQuestion. Fold into the texture-arm re-spec and, with owner-approved
text, `direction/asset-catalog.md`.)*

**1. Identity + the TWO-LAYER model (REVISED 2026-08-02, supersedes the earlier same-day
mask-in-identity answer — safe, no shards exist):** texture data splits into two layers.
- **Layer 1 — bitmap/content (the classification layer):** identity = `sha256(w, h, RGB)`, pixel content
  ONLY. The mask is NOT in identity. The stored classification (tags/description) attaches to this
  identity; identical pixels are deliberately one classifiable thing; the preview is this bitmap.
- **Layer 2 — per-`Package.Name` facts:** `masked` (the import flag) and `group` are read LIVE from the
  package for a given ref, shown by `show`, filterable (`--masked`/`--group`), cached for speed — NOT part
  of identity, NOT stored in the classification.
So a masked grille and its opaque-pixel twin share ONE classification (Layer 1); their masked-ness is
Layer-2 ref info shown alongside, not baked into identity.

**2. Procedural textures:** name-keyed — a texture with no pixel content (`DataCount==0`:
Fire/Wet/Wave/Ice/ScriptedTexture) uses its NAME as identity, per `asset-catalog.md` "content hash where
content exists, name where it does not". This also resolves `scriptedtexture-s-identity-is-unresolved`
(each `ScriptedTexture` keys on its name — no collapse).

**3. `classify set -` JSONL (third stdin convention):** already resolved — the `conventions.md` carve-out
landed with the class-arm build.

**4. Editor-icon sprites:** NOT special-cased — sprites are ordinary textures; §6's icon-group detection
is dropped. Coverage/`prewarm` honestly counts them as unclassified.

**`classify set` over an existing shard:** REFUSE, exit 2 naming it; `--force` to replace — never a silent
overwrite (`direction/safety.md`).

Remaining for the texture-arm re-spec to fold: the pixel-hash-dedup / no-re-key-across-edit cluster.

**Related direction/doc approvals (2026-08-02, via AskUserQuestion) — ready to fold with `Confirmed:`
trailers, then close each item:**
- `texture-group-is-a-first-class-fact` — proposed text APPROVED as written (a Layer-2 package-read fact;
  `--group` filter; not identity).
- `texture-masked-is-a-stored-fact` — proposed text APPROVED as written (Layer-2; the `masked` flag is
  read from the export, `--masked` filter, not identity — consistent with the two-layer model above).
- `direction-asset-catalog-md-reword-the-class` — line-34 no-override reword APPROVED as proposed.
- `asset-catalog-says-the-tool-produces-the` — the `packages.md` "a code-less BC1 file decodes"
  correction APPROVED (a code-less compressed chain is ambiguous BC1-vs-P8 → named error, never a wrong
  pixel).

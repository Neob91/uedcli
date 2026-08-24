+++
priority = "p2"
kind = "debug"
summary = "class_catalog/texture_catalog shard loaders leak KeyError/JSONDecodeError to user"
+++

# class_catalog / texture_catalog shard loaders leak raw tracebacks

Both `shard_from_json` do required-key access with no guard, and `load_shard` calls `json.loads`
with no try/except:

- `class_catalog.py:114-123` — `ClassShard(ref=d["ref"], …)`; reached from `class show` /
  `class list --json` / `class preview` via `_classification_of` → `load_shard`, with no wrapping
  try/except up through `run()`. Its sibling `audio_catalog.load_shard` WAS hardened
  (`except (ValueError, KeyError, OSError): raise AudioCatalogError(...)`); this one never got it.
- `texture_catalog.py:95-104` — `d["identity"]`, `d["ref"]`. `texture.py` `run()` catches
  `ValueError` (so `JSONDecodeError`, a subclass, is caught) but NOT `KeyError`.

Trigger: a classified shard file with valid JSON missing `"ref"` (older schema, hand-edit, or a git
merge conflict on the tracked catalog), then `class show Engine.Actor` → raw `KeyError` /
`json.JSONDecodeError` traceback. Texture variant: shard missing `identity`/`ref`, then
`texture show <ref>`.

Violates "never let a Python exception reach the user." Untested.

Fix: wrap both loaders to raise the catalog's own error type naming the offending file/key
(mirror `audio_catalog`). Regression test per path.

Confirmed by direct read.

# Texture classification has no re-key path across a pixel edit

## Context

The two-layer identity ruling (2026-08-02, `direction/asset-catalog.md` "Two layers" / "Identity")
keys a texture's classification on `sha256(w,h,RGB)` — the pixels. It leaves one part of the cluster
unfolded: the re-key-across-edit case. The dedup half is now covered (identical pixels are one shard;
`classify set` over an existing shard refuses, `--force` replaces). The re-key half is not, and it is
not an implementer's call.

The problem: edit a texture's pixels (repaint the project's own `LUM_CoreTex.utx`) and its identity
changes. The old shard's identity now resolves to nothing on the path, so it becomes an **outdated
entry** — and `classify prune --outdated` deletes it. The description was still accurate; the only
thing that changed is a few pixels. On a project that edits its own `.utx`, prune throws away authored
classification that is still correct, with no migration path.

The shard stores a write-once `ref` (`Package[.Group].Name`) for exactly the outdated-tracking case,
so the *information* to reattach exists — but no verb moves a classification from an orphaned identity
to the ref's new identity, and nothing warns before `prune` deletes it.

This is the same tension the direction doc names ("repaint a texture and its new pixels are a new
identity that simply reads unclassified, while the old classification becomes an outdated entry") but
it stops before saying what happens to the *description* when the repaint was a small edit, not a new
asset.

Options the owner may want to choose among (not exhaustive):

- **Re-key verb.** A `classify rekey <ref>` (or `prune` prompting one) that moves an outdated shard
  onto the ref's current identity, so a re-painted texture keeps its description.
- **Prune stays destructive; the ref is the record.** Accept that a pixel edit orphans the
  classification; the write-once `ref` in the deleted shard is the only trail. Cheap, lossy.
- **Never auto-delete.** `prune --outdated` only *reports*; removal is always explicit per shard, so
  an accidental repaint can never silently drop a description.
- **Something else.**

`prune`/`list-outdated` are a deferred engine board item, so this ruling is not blocking the first
texture slices; it is blocking the lifecycle slice.

## Answer

*(empty — owner to rule)*

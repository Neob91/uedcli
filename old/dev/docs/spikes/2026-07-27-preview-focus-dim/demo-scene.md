# Rebuilding the demo scene and its reference renders

**Why this is written down.** The demo project and the `golden-master/` reference renders that
`actor preview --faces` was checked against live in a scratchpad on **tmpfs** — they are gone the moment
the container dies. The repo's committed goldens (`uedcli/tests/fixtures/preview_*_golden_*.png`) are the
real regression guard and they survive; this is the recipe for rebuilding the EXTERNAL check, and the
scenes the `--focus` findings were measured on. Verified 2026-07-29.

## 1. Game packages — curate them, do NOT point at the editor install

`~/.uedcli/config.toml`:

```toml
[games.deusex]
paths = "<dir>"
```

**`paths` is a COLON-SEPARATED STRING, not a TOML list** — a list is a clean error.

`<dir>` holds symlinks to the thirteen game-only packages from `/workspace/uedcli/uned/UED22/`:

```
core Engine DeusEx DeusExCharacters DeusExConversations DeusExDeco DeusExItems
DeusExSounds DeusExUI UnrealShare fire ConSys Extension
```

**Why curated, and this is the trap:** `uned/UED22/` is the **UnrealEd 2.2 editor install**, not a game
package directory. Pointing `paths` at it directly puts editor-only packages and the **`UED2_FIXM_p1` fix
pack** on the search path; that pack re-declares `AllHongKongDeco`, and
`test_native_materialize.test_class_names_are_unique_across_the_deusex_package_set` then fails on a
duplicate class. That failure was briefly mis-filed as a resolver defect. Curating to the thirteen above
makes it disappear. The residual `{'none': ['core','fire']}` failure of that same test is a **different**
and genuine scan defect, boarded separately.

## 2. Project

A directory containing `uedcli.toml` with one line:

```toml
game = "deusex"
```

then `bin/uedcli level create demo` and `export UEDCLI_LEVEL=demo`.

## 3. The scene — a subtracted room with two adds inside it

```sh
brush build cube --width 1024 --breadth 1024 --height 384 --at 0,0,0      --csg subtract --base-name Room   | actor add -
brush build cube --width 128  --breadth 128  --height 384 --at -256,-256,0 --csg add      --base-name Pillar | actor add -
brush build cube --width 256  --breadth 128  --height 96  --at 200,100,-144 --csg add     --base-name Crate  | actor add -
```

**`actor add` allocates names with a RANDOM SUFFIX** — `Room_ehuj9o`, `Pillar_n4txud`, `Crate_g86z9y` in
the original run. Read them back with `actor find`; do not hardcode them. Every render command in
[`findings.md`](findings.md) names those three, so they must be substituted. (`brush build` alone emits a
snippet and allocates nothing, which is why §5's `--from-t3d` names are exactly as given.)

## 4. The reference renders

Captured from `master` **before any `--faces` code existed**, and used as the external byte-identity check
that `--faces wire` — with and without the flag spelled out — still renders the historical wireframe:

```sh
actor preview <the three names> --size 700 --layout single --view iso     # single-iso.png
actor preview <the three names> --size 700 --layout quad                  # quad.png
actor preview <the three names> --size 700 --layout single --view top     # single-top.png
```

## 5. The coplanar repro — the structural `--focus` finding

Kept because it is not obvious to re-derive: a subtracted room spanning `z ∈ [-128, 128]` and an added
slab whose **top cap is flush at `z = -128`** with the room's floor.

```sh
brush build cube --width 1024 --breadth 1024 --height 256 --at 0,0,0    --csg subtract --base-name CopRoom >  cop.t3d
brush build cube --width 1024 --breadth 1024 --height 128 --at 0,0,-192 --csg add      --base-name CopSlab >> cop.t3d
actor preview --from-t3d cop.t3d --layout single --view top --size 200 --faces flat --annotate none [--focus CopRoom|CopSlab]
```

Probe the **centre pixel**. `CopRoom` is first in the file, so scene order gives its floor the coplanar
tie, and `--focus` may change only its BRIGHTNESS:

| run              | centre pixel      | what it is
|------------------|-------------------|---
| unfocused        | `(205, 180, 110)` | the room's floor
| `--focus CopRoom`| `(205, 180, 110)` | the room's floor, still — it is the focus, so undimmed
| `--focus CopSlab`| `(217, 209, 184)` | the room's floor, dimmed as context

**What the defect looked like:** `--focus CopRoom` gave `(146, 146, 216)` — the SLAB, at context
brightness, with the focused room's own floor gone. De-emphasised faces were resolved in a pass of their
own and so rasterized first, and the depth test is strictly `<`, so the tie went to whichever pass a face
was in instead of to scene order. `--focus` was deciding what was VISIBLE. `--layout breakdown` focuses
every brush pane in turn, which made it the common case rather than a corner. Pinned by
`test_focus_never_changes_which_flush_surface_is_visible_through_the_cli`.

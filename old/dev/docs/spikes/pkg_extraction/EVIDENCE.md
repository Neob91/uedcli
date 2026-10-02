# Package-extraction spike — raw evidence (2026-06-18)

Environment: ephemeral editor container `uned-pkgspike`
(`docker compose run -d --name uned-pkgspike -v uned-wp-pkgspike:/wineprefix
--entrypoint bash uned`), UCC assembled at `/opt/UED22` (symlink farm from
`/repo/Tools/uedcli/uned/UED22`, writable `.ini` copies). Real maps under
`/home/human/src/dx_lum/Maps/`.

## 1. Package header is version 69, magic 0x9E2A83C1

    dx.dx        tag=9e2a83c1 ver=69 names=82@64   exports=20@5306    imports=14@5191
    20_Hexagon   tag=9e2a83c1 ver=69 names=2120@64 exports=1799@...   imports=188@2237821

## 2. Import table of dx.dx (authoritative dependency list)

    ClassPkg=Core  Class=Package  PkgIdx=0   Obj=Engine
    ClassPkg=Core  Class=Class    PkgIdx=-1  Obj=Camera        # PkgIdx -1 -> import[0] = Engine
    ClassPkg=Core  Class=Class    PkgIdx=-1  Obj=PlayerStart
    ClassPkg=Core  Class=Class    PkgIdx=-1  Obj=Teleporter
    ...
    ClassPkg=Core  Class=Package  PkgIdx=0   Obj=Core
    ClassPkg=Core  Class=Class    PkgIdx=-11 Obj=TextBuffer    # -> Core
    ClassPkg=Core  Class=Package  PkgIdx=0   Obj=DeusExDeco
    ClassPkg=Engine Class=LodMesh PkgIdx=-13 Obj=AcousticSensor # -> DeusExDeco

dx.dx DIRECT packages = {Core, DeusExDeco, Engine}.

## 3. The actor-class packages T3D scanning MISSES

Each imported Class and its resolved source package (dx.dx):

    class Camera        <= Engine
    class PlayerStart   <= Engine
    class Teleporter    <= Engine
    class LevelInfo     <= Engine
    class TextBuffer    <= Core
    ...

In the T3D export these actors are written UNQUALIFIED (`Begin Actor
Class=PlayerStart`, `Class=Teleporter`), so a `Class'Pkg.Obj'` regex scan
attributes NONE of them to a package. Only the import table maps
`PlayerStart -> Engine`. For a DeusEx gameplay map the same applies to
`DeusExMover`, gameplay actors, etc. -> `DeusEx`/`UNATCO`/...

## 4. Transitivity: UCC demands packages NOT in the level's own tables

    $ wine UCC.exe batchexport ../Maps/dx.dx Level T3D <out>
    Loading package ../Maps/dx.dx...
    Failed loading package: Can't find file for package 'Effects'

`Effects` is NOT in dx.dx's Names or Import tables. It is a dependency of
`DeusExDeco.u`:

    DeusExDeco.u -> {Core, DeusExItems, Effects, Engine}

So the engine loads dependencies transitively; the manifest must be the
TRANSITIVE CLOSURE. closure.py computes it offline:

    dx.dx closure (5): Core, DeusExDeco, DeusExItems, Effects, Engine
        MISSING from substrate: Effects   <-- matches UCC's runtime complaint exactly

## 5. Fail-fast message names the missing package (one at a time)

    20_Lenz.dx -> Failed loading package: Can't find file for package 'NewYorkCity'
    19_FMA.dx  -> Failed loading package: Can't find file for package 'CoreTexMetal'

Both `NewYorkCity` and `CoreTexMetal` are members of the offline closure for
their maps. UCC reports only the FIRST missing package, so ensure-load must
check ALL closure members up front to produce the complete missing list.

## 6. Blocker: base-game content not present in this environment

`Effects.u`, `NewYorkCity`, the `.utx/.uax/.umx` content packages, etc. do
not exist anywhere in the repo (it's a LUM mod tree, not a full Deus Ex
install). So end-to-end "materialize with no missing-class errors" could NOT
be demonstrated here. What IS demonstrated: offline extraction enumerates the
closure, and UCC's runtime demand falls within that closure every time.

## 7. Unicode (negative-length) names — parser robustness

`20_AireGardens.dx` initially crashed the parser at name 90. Cause: DeusEx
ver-69 packages store some FNames (long comma-joined Group strings) as
UTF-16LE with a NEGATIVE compact-index length (`-N` => N wide chars).
dxpkg.read_name now branches on the sign. Full sweep after the fix — all 12
maps parse with zero garbage package names:

    19_FMA            imports=123  pkgs=25
    19_Multiport      imports=208  pkgs=35
    20_AireGardens    imports=223  pkgs=38   <- was crashing
    20_Downtown       imports=824  pkgs=58
    20_Hexagon        imports=188  pkgs=29
    20_Lenz           imports=58   pkgs=16
    20_Northgate      imports=144  pkgs=25
    20_Nuradyne       imports=174  pkgs=25
    20_Train          imports=90   pkgs=20
    Entry / dx        imports=14   pkgs=3

## 8. Name table has NO dotted Pkg.Obj entries

For 20_Lenz, scanning the 247 Names for `Pkg.Obj`-shaped strings yields []
— every reference is a package INDEX into the import table, not a qualified
string. The import table is the only complete source; a T3D qualified-ref
scan is a reconstruction (floor), not the ground truth.

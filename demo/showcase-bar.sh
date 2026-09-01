#!/usr/bin/env bash
# ================================================================
# NEON STRATA — a cyberpunk VIP club for UnrealEngine 1.0 (Deus Ex). uedcli-authored, BSP-safe.
# Dark reflective floor + cool tech walls so the neon carries every hue. Three read-apart zones:
# a sunken CYAN dance floor (front-left), a MAGENTA lounge pit (front-right), a warm AMBER bar
# along the +Y wall with a mirrored black back-bar (lit bottles) + a "Lucky Money" neon sign above.
# Booths, entrance couches, 4 columns, a ceiling-beam grid, LED-strip fixtures. Empty (no NPCs).
# Interior X[-768,768]  Y[-576,576]  Z[0,512]   (1536 x 1152 x 512, floor Z=0, ceiling Z=512).
# Reads $UEDCLI_LEVEL as {LEVEL}; needs a clean $UEDCLI_HOME (paths only, no ignore_props).
# ================================================================
set -euo pipefail
: "${UEDCLI_HOME:?set UEDCLI_HOME to a clean config dir (paths only)}"
: "${UEDCLI_LEVEL:?set UEDCLI_LEVEL to the target level}"
cd /workspace/uedcli/.claude/worktrees/megagrant-demo
U=bin/uedcli

# ---------------- palette (dark cool tech; neon carries the colour; fabric only on seats) --------
WALL=CoreTexMetal.ClenGrayMetal_B     # dark navy mottled metal (quiet; neon carries the colour)
CEIL=CoreTexMetal.PitdSilvMetal_B     # smooth grey ceiling (distinct + recessive)
COL=CoreTexMetal.ClenMetlPanel_A      # clean framed panel  (columns, pit walls)
FLOOR=CoreTexStone.ShnyBlacMarbl_A    # glossy black marble (main floor) — reflective
LOUNGEFLR=CoreTexStone.ClenViltMarble0 # pale veined marble (lounge-pit floor) — lighter than FLOOR so the magenta wash actually shows, not just black-on-black
DANCE=HK_Interior.HexagonTile         # near-black hex tech tile (sunken dance floor, edge-neon pops)
TRIM=CoreTexMetal.ClenIronWOriv_A     # brushed steel       (all trim: lips, kicks, nosings, footrail, mullions, floor inlay)
BARBODY=CoreTexMetal.ClenMetlPatrn_A  # dark inset-diamond panel (bar counter body)
BARTOP=CoreTexStone.DarkBrwnMarbl_A   # gold-veined emperador (warm luxe bar top + table caps)
SEAT=NYCBar.WornCouchFab_A            # diamond-quilt fabric — SEATING ONLY (benches, booths, couches)
BOOTHWOOD=CoreTexWood.ClenWoodPanel_C # warm mahogany raised panel — booth backs (was riveted metal, read as a locker)
QUILT=Airfield.tanleatherseat          # tufted diamond-quilt leather atlas — cropped (top-left 96x96 of 256) to its tufted square for booth cushion caps
MIRROR=CoreTexGlass.Mirror_Highligh   # near-black glass — reads glossy under the back-bar lights
BOTL1=DeusExItems.LiquorBottleTex1    # dark liquor bottle skin
BOTL2=DeusExItems.WineBottleTex1      # red wine bottles
BOTL3=DeusExItems.Liquor40ozTex1      # amber bottle
GLASS=DeusExDeco.FlaskTex1            # clear glass (drinks on bar/tables)
SIGN=NeonStrata.Neon.Strata           # our own NEON STRATA logo (.utx via make-utx.sh), Unlit
SIGN2=V_Com_Center.ClenBlueLight_A    # vertical neon tube bank (wall accent — un-branded)
SIGN3=V_Com_Center.ClenBlueLight_A    # abstract white-cyan neon (blade over the pit)
# emissive LED-strip fixtures (thin Unlit brushes = visible light sources)
LED_CY=HK_MJ12Lab.Lights_A            # twin cyan-white tubes (ceiling-beam runs)
LED_BL=HK_MJ12Lab.Lights_A            # twin-tube glow       (under-bar + dance-floor edges)
LED_VT=V_Com_Center.ClenBlueLight_A   # white-cyan vertical tube (column accents)
LED_MG=Rocket.ClenRedLight_B          # red bar, tinted magenta by its colocated light (pit edges)

# ---------------- helpers ----------------
add(){  $U brush build cube --csg add --width $1 --breadth $2 --height $3 --at $4,$5,$6 \
        --texture $7 --base-name $8 | $U actor add - >/dev/null; snap; }                  # solid cube
ss(){   $U brush build cube --csg add --solidity semisolid --width $1 --breadth $2 --height $3 \
        --at $4,$5,$6 --texture $7 --base-name $8 | $U actor add - >/dev/null; snap; }     # semisolid cube
non(){  $U brush build cube --csg add --solidity nonsolid --width $1 --breadth $2 --height $3 \
        --at $4,$5,$6 --texture $7 --base-name $8 | $U actor add - >/dev/null; snap; }     # nonsolid decoration
cyl(){  $U brush build cylinder --csg add --solidity ${8:-semisolid} --sides ${9:-12} --radius $1 \
        --height $2 --at $3,$4,$5 --rotate ${10:-0,0,0} --texture $6 --base-name $7 | $U actor add - >/dev/null; snap; }
light(){ $U actor build Engine.Light --at $1,$2,$3 --prop LightHue=$4 --prop LightSaturation=$5 \
        --prop LightBrightness=$6 --prop LightRadius=$7 --base-name $8 | $U actor add - >/dev/null; snap; }
# unlit emissive sign: build nonsolid, capture name, flag all faces Unlit so it self-glows
sign(){ local n; n=$($U brush build cube --csg add --solidity nonsolid --width $1 --breadth $2 \
        --height $3 --at $4,$5,$6 --texture $7 --base-name $8 | $U actor add -)
        $U brush poly set "$n":all --add-flag unlit >/dev/null; snap; }
npc(){  $U actor build DeusEx.$1 --at $2,$3,$4 --rotate 0,$5,0 --prop Orders=$6 --base-name $7 \
        | $U actor add - >/dev/null; }   # args: CLASS X Y Z YAW ORDERS NAME
# ring($outerW $outerB $innerW $innerB $cx $cy $z $height $texture $name): a closed rectangular
# frame as ONE welded brush (CSG intersect: outer solid minus inner void), replacing 4 separate
# abutting strips that never actually met cleanly at the corners — this file used to build pit
# lips that way and kept them apart at the corners to dodge a semisolid-touching-semisolid CSG
# issue, which read as visibly broken/gapped trim. One welded brush has no seam to get wrong.
ring(){
  { $U brush build cube --csg add      --width $1 --breadth $2 --height $8 --at $5,$6,$7 --texture $9
    $U brush build cube --csg subtract --width $3 --breadth $4 --height $8 --at $5,$6,$7 --texture $9
  } | $U brush intersect - --solidity semisolid --texture $9 --base-name ${10} | $U actor add -
  snap
}
# miter($actorA $actorB $cx $cy $z $nx $ny): clip A and B on the SAME 45-degree plane through
# ($cx,$cy,$z) with normal ($nx,$ny,0), on OPPOSITE sides -- A keeps below (its outer edge reaches
# the true corner tip, its inner edge tapers to a point), B keeps above (the complementary taper).
# Keeping the SAME side for both (an earlier bug here) makes them overlap in one triangle of the
# corner square and gap in the other -- coplanar/coincident on the CUT FACES alone doesn't catch
# that, since it doesn't know which side is solid; check by bbox/vertices instead (each piece's
# outer edge should run the full extent, inner edge should taper to a single point) or just look
# at a top-down `actor diagram`. For an OPEN run (3 sides, unlike ring()'s closed frame) where a
# plain rectangular overlap read as sloppy. Both actors must already extend past the corner.
miter(){
  local a=$1 b=$2
  $U actor show "$a" | $U brush clip - --plane $3,$4,$5 $6,$7,0 --keep below | $U brush replace "$a" -
  $U actor show "$b" | $U brush clip - --plane $3,$4,$5 $6,$7,0 --keep above | $U brush replace "$b" -
  snap
}
# flush($target $obj [$want]): nudge $obj by the EXACT gap `brush measure relation` reports
# against $target, instead of trusting a hand-typed Z constant — this is what used to leave
# bottles floating above shelves and glasses buried in tables (see git log). $want (default 0)
# is the intended final distance: 0 = touching exactly, -1 = a 1uu embed to kill Z-fighting
# (the convention already used throughout this file). Fails loudly if the two share no facing
# plane at all — a silently-wrong flush is worse than no flush.
declare -A TABLECAP
flush(){
  local target=$1 obj=$2 want=${3:-0} out delta
  out=$($U brush measure relation "$target" "$obj") || { echo "$out" >&2; return 1; }
  delta=$(python3 -c '
import re, sys
text, want = sys.stdin.read(), float(sys.argv[1])
m = re.search(r"distance:\s*(-?[0-9.]+)uu", text)
n = re.search(r"normals:.*?\(([^)]+)\)", text, re.S)
if not (m and n):
    sys.exit(1)
dist = float(m.group(1))
nx, ny, nz = (float(v) for v in n.group(1).split(","))
k = want - dist
print(f"{k*nx:.3f},{k*ny:.3f},{k*nz:.3f}")
' "$want" <<<"$out") || { echo "flush: no facing relation between $target and $obj:" >&2
                          echo "$out" >&2; return 1; }
  [ "$delta" = "0.000,0.000,0.000" ] || $U actor move "$obj" --by "$delta" >/dev/null
  snap
}
# TIMELAPSE=1 → one wireframe frame per added element (called from each geometry helper), so the
# build-up plays like an agent placing pieces one at a time. Dedup on actor count so the section
# `snap` calls and light-only steps don't emit duplicate frames. `snap force` bypasses the dedup —
# for a move/retexture correction, where the actor count doesn't change but the frame should differ.
_snap=0; _lastn=-1
snap(){ [ -n "${TIMELAPSE:-}" ] || return 0
  local n=$($U actor find 2>/dev/null | grep -v LevelInfo | wc -l)
  [ "$n" -gt 0 ] || return 0
  [ "${1:-}" = force ] || { [ "$n" != "$_lastn" ] || return 0; }
  _lastn=$n; mkdir -p demo/out/timelapse; local f=demo/out/timelapse/$(printf '%03d' $_snap).png
  $U actor find | grep -v LevelInfo | $U actor diagram - --layout single --view iso \
     --faces wire --annotate none --size 1080 --out "$f" >/dev/null 2>&1 || return 0
  # mark both this frame and the one before it .hold, so the MP4 assembler pauses on a
  # correction long enough to actually see it (the mistake, then the fix), not just flash by
  if [ "${1:-}" = force ]; then
    : > "$f.hold"
    [ "$_snap" -gt 0 ] && : > "demo/out/timelapse/$(printf '%03d' $((_snap-1))).png.hold"
  fi
  _snap=$((_snap+1)); }

snap
# ========================= SHELL =========================
ROOM=$($U brush build cube --csg subtract --width 1536 --breadth 1152 --height 512 \
   --at 0,0,256 --texture $WALL --base-name Room | $U actor add -)
$U brush poly find "$ROOM" --facing +Z | $U brush poly set - --texture $FLOOR >/dev/null
$U brush poly find "$ROOM" --facing -Z | $U brush poly set - --texture $CEIL  >/dev/null
# finer floor tiling (default tile reads oversized/stretched on a 1536-wide room)
$U brush poly find "$ROOM" --facing +Z | $U brush poly scale - --by 0.5,0.5 >/dev/null
$U actor prop set LevelInfo AmbientBrightness=10 >/dev/null

snap
# ========================= FLOOR INLAY (breaks up the flat marble slab) =========================
# thin steel strips 1uu above the floor (nonsolid — never touches the shell's solid face, no
# Z-fight, free to run over/through pits and furniture since nonsolid never enters CSG).
# Perimeter border on 3 walls (North skipped: that's the bar counter, a border there would hide).
# Built a half-thickness LONGER than the room edge on each mitered end, so adjacent runs actually
# overlap at the corner square (not just touch it) -- miter() needs real overlap to produce a
# clean bevel; an edge-exact overlap only clips a corner wedge off one side, leaving a pentagon.
FIS=$($U brush build cube --csg add --solidity nonsolid --width 1462 --breadth 6 --height 3 \
      --at 0,-536,1 --texture $TRIM --base-name FloorInlayS | $U actor add -)
FIW=$($U brush build cube --csg add --solidity nonsolid --width 6 --breadth 1078 --height 3 \
      --at -728,0,1 --texture $TRIM --base-name FloorInlayW | $U actor add -)
FIE=$($U brush build cube --csg add --solidity nonsolid --width 6 --breadth 1078 --height 3 \
      --at 728,0,1 --texture $TRIM --base-name FloorInlayE | $U actor add -)
miter "$FIW" "$FIS" -728 -536 1 1 -1
miter "$FIS" "$FIE" 728 -536 1 1 1
# entrance-to-bar runway, straight down the walkway between the two pits (matches the PlayerStart line)
non 16 940 3 -96 -50 1 $TRIM FloorInlayRunway

snap
# ========================= WALL TRIM RAIL (breaks up the flat wall plane) =========================
# thin steel band a few uu off each wall face, floating clear of the shell (no coincident faces).
# North (+Y) skipped: that wall is already the back-bar/mirror/sign, a rail there would coincide.
# Same miter() construction as the floor inlay above, but these original dimensions already
# overlap generously at the corners (unlike the floor inlay's edge-exact original sizing), so no
# extension needed here for a clean bevel.
WRS=$($U brush build cube --csg add --solidity nonsolid --width 1536 --breadth 4 --height 8 \
      --at 0,-572,140 --texture $TRIM --base-name WallRailS | $U actor add -)
WRW=$($U brush build cube --csg add --solidity nonsolid --width 4 --breadth 1152 --height 8 \
      --at -764,0,140 --texture $TRIM --base-name WallRailW | $U actor add -)
WRE=$($U brush build cube --csg add --solidity nonsolid --width 4 --breadth 1152 --height 8 \
      --at 764,0,140 --texture $TRIM --base-name WallRailE | $U actor add -)
miter "$WRW" "$WRS" -764 -572 140 1 -1
miter "$WRS" "$WRE" 764 -572 140 1 1

snap
# ========================= SUNKEN DANCE FLOOR (front-left, cyan) =========================
DANCEPIT=$($U brush build cube --csg subtract --width 512 --breadth 512 --height 96 \
   --at -480,-160,0 --texture $COL --base-name DancePit | $U actor add -)   # floor Z=-48, walls=COL
$U brush poly find "$DANCEPIT" --facing +Z | $U brush poly set - --texture $DANCE >/dev/null
$U brush poly find "$DANCEPIT" --facing +Z | $U brush poly scale - --by 0.5,0.5 >/dev/null
ss 32 448 24 -240 -160 -36 $TRIM DanceStep          # one step down on the entry (east) edge
# pit-lip trim: one closed frame flush with the pit mouth, 8uu wide, sitting on the main floor
ring 528 528 512 512 -480 -160 4 8 $TRIM DanceLip

snap
# ========================= LOUNGE PIT (front-right, magenta) =========================
LOUNGE=$($U brush build cube --csg subtract --width 448 --breadth 448 --height 96 \
   --at 256,-160,0 --texture $COL --base-name LoungePit | $U actor add -)   # floor Z=-48
$U brush poly find "$LOUNGE" --facing +Z | $U brush poly set - --texture $LOUNGEFLR >/dev/null
$U brush poly find "$LOUNGE" --facing +Z | $U brush poly scale - --by 0.5,0.5 >/dev/null
ring 464 464 448 448 256 -160 4 8 $TRIM LoungeLip
# bench ring (fabric, seat top Z=-8), each inset 8 from its pit wall (no coincident face)
add 432 40 40 256 68   -28 $SEAT LoungeBenchN
add 432 40 40 256 -356 -28 $SEAT LoungeBenchS
add 40 336 40 60  -160 -28 $SEAT LoungeBenchW
add 40 336 40 452 -160 -28 $SEAT LoungeBenchE
# two round tables (SOLID pedestal + SEMISOLID wider cap so they read as tables, not barrels)
for xy in "144,-64" "352,-224"; do IFS=, read cx cy <<<"$xy"
  cyl 12 44 $cx $cy -26 $COL    LngTablePed solid 12
  n=$($U brush build cylinder --csg add --solidity semisolid --sides 16 --radius 30 --height 6 \
      --at $cx,$cy,-1 --texture $BARTOP --base-name LngTableCap | $U actor add -)
  $U brush poly find "$n" --facing +Z | $U brush poly scale - --by 0.4,0.4 >/dev/null
  snap
  TABLECAP["$cx,$cy"]=$n
done

snap
# ========================= HERO BAR (+Y wall) =========================
add 992 80 96   -144 512 48  $BARBODY BarBody              # counter body (thick, X[-640,352])
BARTOP_N=$($U brush build cube --csg add --width 1024 --breadth 112 --height 12 \
    --at -144,508,102 --texture $BARTOP --base-name BarTop | $U actor add -); snap  # glossy overhanging top
ss 1008 8 8     -144 456 90  $TRIM   BarNosing             # front nosing lip under the top
add 992 12 12   -144 470 6   $TRIM   BarKick               # base kick trim (overlaps body 4uu)
non 4 112 12 -654 508 102 $TRIM BarTopEndL                 # trim end-cap, west edge of the top
non 4 112 12  366 508 102 $TRIM BarTopEndR                 # trim end-cap, east edge of the top
FR=$($U brush build cylinder --csg add --solidity semisolid --sides 12 --radius 5 \
     --height 960 --at -144,444,20 --rotate 16384,0,0 --texture $TRIM --base-name BarFootrail \
     | $U actor add -)                                     # brass-look footrail along the front
$U brush poly find "$FR" --item Side | $U brush poly align --ring - >/dev/null
snap
# mirrored black back-bar: glossy glass wall + metal mullions + trimmed shelves + rows of lit bottles
BB=$($U brush build cube --csg add --solidity nonsolid --width 992 --breadth 12 --height 240 \
     --at -144,566,220 --texture $MIRROR --base-name BackBarWall | $U actor add -)
$U brush poly find "$BB" --facing -Y | $U brush poly scale - --by 1,1 >/dev/null
snap
for x in -560 -400 -240 -80 80 240; do non 8 8 240 $x 558 220 $TRIM BackBarMullion; done
declare -A SHELF
for z in 128 208 288; do
  n=$($U brush build cube --csg add --solidity nonsolid --width 992 --breadth 8 --height 6 \
      --at -144,556,$z --texture $BARTOP --base-name BackBarShelf | $U actor add -)
  snap
  SHELF[$z]=$n
  non 992 3 3 -144 551 $((z-5)) $TRIM BackBarShelfLip      # front lip trim under each shelf
done
# bottles: real DX bottle skins, alternating, standing on each shelf (6-sided = bottle silhouette).
# Ring-align + tighten the UV scale (cyl() alone leaves label textures unaligned/stretched), so
# capture each brush name here instead of going through cyl(). Packed tight (46uu pitch, ~2x the
# earlier density) so the shelves read as stocked, not a sparse grid of bottles in empty cells;
# a slight height/radius alternation breaks the perfectly-uniform silhouette. Placed at an
# approximate Z then flush()-corrected to a measured 1uu embed into the shelf — `brush measure
# relation`, not a hand-tuned constant, is what keeps this from floating (see git log: a fixed z
# offset here used to leave bottles floating ~3-5uu above the shelf).
bt=0
for sz in 128 208 288; do for x in $(seq -600 46 320); do
  case $((bt % 3)) in 0) T=$BOTL1;; 1) T=$BOTL2;; *) T=$BOTL3;; esac
  if [ $((bt % 2)) -eq 0 ]; then rad=5; ht=24; else rad=6; ht=29; fi
  n=$($U brush build cylinder --csg add --solidity nonsolid --sides 6 --radius $rad --height $ht \
      --at $x,550,$(( sz + 3 + ht/2 )) --texture $T --base-name Bottle | $U actor add -)
  $U brush poly find "$n" --item Side | $U brush poly align --ring - >/dev/null
  $U brush poly find "$n" --item Side | $U brush poly scale - --by 0.35,0.35 >/dev/null
  snap
  flush "${SHELF[$sz]}" "$n" -1
  bt=$((bt+1)); done; done
# STATEMENT sign on the tall back wall above the bar (was dead space).
# Frame the 512x256 logo on the visible -Y face. That face's default mapping runs texture-U
# backwards (mirrored) and its V at 2x density (crops one word), so: rotate 180 to un-mirror,
# scale V 0.6 so both words fit one tile, pan to centre. Verified in-game (NEON STRATA upright).
# Pan V uses 192 (not the equivalent -64) — a negative Pan round-trips through materialize as its
# 16-bit-wrapped positive form (65472) and fails post-verify; see
# dev/docs/board/inbox/level-materialize-post-verify-rejects-a. 192 = -64 mod 256 (the texture's
# tile period), same visual pan, no wraparound.
BS=$($U brush build cube --csg add --solidity nonsolid --width 512 --breadth 8 --height 256 \
     --at -144,570,384 --texture $SIGN --base-name BarStatementSign | $U actor add -)
$U brush poly set "$BS":all --add-flag unlit >/dev/null
$U brush poly find "$BS" --facing -Y | $U brush poly rotate - --by 32768 >/dev/null
$U brush poly find "$BS" --facing -Y | $U brush poly scale  - --by 1,0.6  >/dev/null
$U brush poly find "$BS" --facing -Y | $U brush poly pan    - --to 256,192 >/dev/null

snap
# ========================= BOOTHS (right wall X=768, face -X) =========================
# BOOTHWOOD (warm mahogany raised panel) on both the back and dividers so the whole enclosure reads
# as one wood-paneled booth (steel trim on the dividers clashed against the wood back), SEAT fabric
# + a QUILT (tufted leather) cushion cap on the seat. Silhouette does more work: the back is tallest
# and set back against the wall, the dividers are lower wing walls that reach out PAST the seat
# front, the seat is lowest and topped with a proud cushion — distinct planes, not just colours.
booth(){ # $1 tag  $2 Yc
  add 32 176 104 752 $2 52  $BOOTHWOOD BoothBack$1          # back panel, flush to the wall, tallest
  add 96 160 20  684 $2 10  $SEAT      BoothSeat$1           # fabric seat base (lower, top Z=20)
  n=$($U brush build cube --csg add --width 78 --breadth 138 --height 10 \
      --at 680,$2,25 --texture $QUILT --base-name BoothCushion$1 | $U actor add -)
  $U brush poly find "$n" --facing +Z | $U brush poly scale - --by 0.4,0.4 >/dev/null  # zoom into the tufted crop, not the whole seat atlas
  snap
  add 120 16 88  676 $(( $2 - 88 )) 44 $BOOTHWOOD BoothDivA$1  # wing dividers: taller than the seat,
  add 120 16 88  676 $(( $2 + 88 )) 44 $BOOTHWOOD BoothDivB$1  # reach past the seat front for privacy — match the back panel, was steel trim clashing with the wood
  cyl 18 44 636 $2 22 $BARTOP BoothTablePed$1 solid 12
  n=$($U brush build cylinder --csg add --solidity semisolid --sides 16 --radius 26 --height 6 \
      --at 636,$2,46 --texture $BARTOP --base-name BoothTableCap$1 | $U actor add -)
  $U brush poly find "$n" --facing +Z | $U brush poly scale - --by 0.4,0.4 >/dev/null
  snap
  TABLECAP["636,$2"]=$n
}
booth A 208
booth B 400

snap
# ========================= ENTRANCE (-Y wall): flanking couches =========================
add 240 56 32 -560 -540 16 $SEAT CouchL                    # seat, top Z=32
add 240 8 48  -560 -566 40 $SEAT CouchBackL                # backrest
add 240 56 32  560 -540 16 $SEAT CouchR
add 240 8 48   560 -566 40 $SEAT CouchBackR

snap
# ========================= COLUMNS (4, semisolid, full height) + recessed LED strips =========
# first column: placed 64uu off the grid, then nudged back onto it (final position is unchanged)
C1=$($U brush build cube --csg add --solidity semisolid --width 48 --breadth 48 --height 512 \
     --at -384,288,256 --texture $COL --base-name Column | $U actor add -)
snap
$U actor move "$C1" --by -64,0,0 >/dev/null
snap force
sign 6 6 320 -478 288 250 $LED_VT ColStrip
for xy in "256,288" "-448,-448" "256,-448"; do IFS=, read px py <<<"$xy"
  ss 48 48 512 $px $py 256 $COL Column
  sign 6 6 320 $(( px - 30 )) $py 250 $LED_VT ColStrip      # white-cyan LED tube 5uu off the -X column face
done

snap
# ========================= CEILING BEAM GRID (solid) =========================
add 1536 32 40 0 -160 492 $WALL BeamX1
add 1536 32 40 0 288  492 $WALL BeamX2
add 32 1152 40 -448 0 492 $WALL BeamY1
add 32 1152 40 256  0 492 $WALL BeamY2

snap
# ========================= EXTRA NEON SIGNS (wall strips + a hanging blade) =========
# SIGN2 is a fine vertical-tube-bank texture but reads as a fat windowpane grid when stretched
# flat across a 256-wide panel — shrink its apparent size so it repeats as dense thin tubes.
# Each panel sits flush against the wall with zero depth cues (no bracket/housing), reading as
# floating rather than mounted — a trim frame just behind it (8uu margin) fixes that.
non 4 272 112 -768 -160 300 $TRIM SignWestFrame
SW=$($U brush build cube --csg add --solidity nonsolid --width 8 --breadth 256 --height 96 \
     --at -762,-160,300 --texture $SIGN2 --base-name SignWest | $U actor add -)
$U brush poly set "$SW":all --add-flag unlit >/dev/null
$U brush poly find "$SW" --facing +X | $U brush poly scale - --by 0.2,1 >/dev/null
snap
non 4 272 112 768 288 300 $TRIM SignEastFrame
SE=$($U brush build cube --csg add --solidity nonsolid --width 8 --breadth 256 --height 96 \
     --at 762,288,300 --texture $SIGN2 --base-name SignEast | $U actor add -)
$U brush poly set "$SE":all --add-flag unlit >/dev/null
$U brush poly find "$SE" --facing -X | $U brush poly scale - --by 0.2,1 >/dev/null
snap
sign 8 160 48  256 -160 320 $SIGN3 SignBlade              # hanging blade over the lounge pit

snap
# ========================= LED-STRIP FIXTURES (visible light sources) =========================
# under-bar counter strip (electric blue) on the counter front, under the overhang
sign 1000 4 10 -144 470 34 $LED_BL UnderBarLED
for x in -540 -300 -60 180 340; do light $x 462 40 155 55 130 9 UnderBarGlow; done
# dance-floor edge strips (cyan) on the pit lip, N & S runs
sign 500 4 8 -480 96   10 $LED_BL DanceEdgeN
sign 500 4 8 -480 -416 10 $LED_BL DanceEdgeS
for x in -640 -480 -320; do light $x 96 20 155 55 120 8 DanceEdgeGlow; light $x -416 20 155 55 120 8 DanceEdgeGlow; done
# lounge-pit edge strips (magenta = red tex tinted) N & S runs
sign 440 4 8 256 96   10 $LED_MG PitEdgeN
sign 440 4 8 256 -416 10 $LED_MG PitEdgeS
for x in 120 256 392; do light $x 96 20 220 40 120 8 PitEdgeGlow; light $x -416 20 220 40 120 8 PitEdgeGlow; done
# ceiling-beam tube runs (cyan-white) under the two X beams
sign 1440 20 6 0 -160 468 $LED_CY BeamLEDx1
sign 1440 20 6 0 288  468 $LED_CY BeamLEDx2
for x in -560 -160 240 560; do light $x -160 458 155 40 95 14 BeamGlow; light $x 288 458 155 40 95 14 BeamGlow; done

snap
# ========================= PLAYER START (entry walkway, facing the bar) =========================
$U actor build Engine.PlayerStart --at -96,-520,40 --rotate 0,16384,0 --base-name Start | $U actor add - >/dev/null

snap
# ============================ LIGHTING (per-zone key hues + motivated fills) ============================
# --- BAR: warm amber key along the counter (Hue ~25) ---
# brightness/radius are all -25% from the original values throughout this section (owner call,
# 2026-09-01) -- hue/saturation untouched, only intensity/reach.
for x in -560 -320 -80 160 320; do light $x 470 130 25 120 131 9 BarAmber; done
light -300 470 60 24 130 113 8 BarAmberLo
light 200  470 60 24 130 113 8 BarAmberLo
# amber bleed onto the open floor in front of the bar, where a patron would stand
light -560 430 30 25 100 98 15 BarFloorGlow
light -80  430 30 25 100 98 15 BarFloorGlow
light 320  430 30 25 100 98 15 BarFloorGlow
# green back-bar glow (colocated with the glass so it spills forward) ---
# warm backlight so the bottles glow/silhouette against the black mirror wall
for x in -520 -240 40 280; do light $x 552 200 25 110 124 8 BackBarWarm; done
for x in -400 0 240; do light $x 552 110 25 120 113 7 BackBarWarmLo; done
# statement sign backers (magenta + cyan pools on the back wall) ---
light -360 560 410 220 180 158 15 SignPoolMag
light 72   560 410 175 180 158 15 SignPoolCyan
# --- DANCE: cyan (Hue 175) — overhead wash + saturated underfloor glow ---
light -480 -160 300 175 100 150 20 DanceWash
light -480 -160 60  175 110 143 12 DanceKey
light -640 -320 -40 175 90 128 7 DanceUnder
light -320 -320 -40 175 90 128 7 DanceUnder
light -640 0    -40 175 90 128 7 DanceUnder
light -320 0    -40 175 90 128 7 DanceUnder
# --- LOUNGE PIT: magenta / purple (Hue 210-218) ---
light 160 -96  -30 215 120 124 9 LoungeMag
light 352 -224 -30 210 120 113 8 LoungePurp
light 256 -160 40  218 90 75 8 LoungeWash
light 256 -160 -40 215 130 105 7 LoungeUnder
# --- extra neon signs backed by colocated coloured pools ---
light -740 -160 300 220 180 150 14 SignWestPool
light 740  288  300 175 180 150 14 SignEastPool
light 256  -160 300 220 170 143 12 SignBladePool
# --- BOOTHS: warm pool lights over the seating (nearest existing light is 200+uu overhead, on
# the wall sign, not the tables) ---
light 660 208 110 25 120 113 11 BoothGlowA
light 660 400 110 25 120 113 11 BoothGlowB
# --- MOTIVATED FILLS for the dead zones (columns, upper walls, ceiling) — dim, never flat ---
k=0
for xy in "-448,288" "256,288" "-448,-448" "256,-448"; do IFS=, read px py <<<"$xy"
  if [ $((k%2)) -eq 0 ]; then h=175; else h=220; fi                 # alternate cyan / magenta rims
  light $(( px - 30 )) $py 240 $h 40 90 21 ColumnRim
  k=$((k+1))
done
light 0 0    460 200 60 34 23 CeilWash                    # dim cool ceiling wash
light -300 470 470 26 80 34 18 CeilWashBar                # dim warm over the bar soffit line
light 0 288  360 200 70 41 18 BackWallFill               # upper back wall reads
light 0 -540 200 210 70 45 17 EntryFill                  # entrance reads


snap
# ============================ NO CROWD — the lit space carries itself ============================
# empty bar stools along the counter front (solid seat on a semisolid post)
# first seat: placed 100uu short of the counter, then pushed in to the front line (final unchanged)
S1=$($U brush build cylinder --csg add --solidity solid --sides 12 --radius 14 --height 8 \
     --at -520,330,76 --rotate 0,0,0 --texture $BARTOP --base-name StoolSeat | $U actor add -)
snap
$U actor move "$S1" --by 0,100,0 >/dev/null
snap force
$U brush poly find "$S1" --facing +Z | $U brush poly scale - --by 0.4,0.4 >/dev/null
cyl 5 72 -520 430 38 $TRIM StoolPost semisolid 8
for x in -380 -240 -100 100 240; do
  n=$($U brush build cylinder --csg add --solidity solid --sides 12 --radius 14 --height 8 \
      --at $x,430,76 --texture $BARTOP --base-name StoolSeat | $U actor add -)
  $U brush poly find "$n" --facing +Z | $U brush poly scale - --by 0.4,0.4 >/dev/null
  snap
  cyl 5  72 $x 430 38 $TRIM   StoolPost semisolid 8
done
# glasses left on the bar top, flush()-corrected to a measured 1uu embed against BarTop (not a
# hand-tuned Z constant — same fix as the shelved bottles above)
for x in -560 -420 -280 -140 -50 40 180 300 340; do
  n=$($U brush build cylinder --csg add --solidity nonsolid --sides 6 --radius 4 --height 12 \
      --at $x,500,113 --texture $GLASS --base-name BarGlass | $U actor add -)
  snap
  flush "$BARTOP_N" "$n" -1
done
# a liquor bottle + a glass standing on each lounge + booth table (gz is a rough starting guess
# at the table-top z, close enough that brush measure relation ranks the cap<->prop face pair
# unambiguously), flush()-corrected against that table's own cap (captured into TABLECAP above)
for xy in "144,-64,2" "352,-224,2" "636,208,49" "636,400,49"; do IFS=, read gx gy gz <<<"$xy"
  cap="${TABLECAP[$gx,$gy]}"
  n=$($U brush build cylinder --csg add --solidity nonsolid --sides 6 --radius 5 --height 20 \
      --at $gx,$gy,$(( gz + 10 )) --texture $BOTL2 --base-name TblBottle | $U actor add -)
  snap
  flush "$cap" "$n" -1
  n=$($U brush build cylinder --csg add --solidity nonsolid --sides 6 --radius 4 --height 12 \
      --at $(( gx + 15 )),$gy,$(( gz + 5 )) --texture $GLASS --base-name TblGlass | $U actor add -)
  snap
  flush "$cap" "$n" -1
done

snap
echo "BUILD DONE"

#!/usr/bin/env bash
# Writes a realistic uedctl T3D-tree fixture into $1 (a directory).
# Layout mirrors uedctl `read_state_dir`: actors/<safe_name>.t3d (one canonical
# actor block per file), a newline-delimited `order` (CSG precedence), plus small
# `packages` / `name` metadata files. Properties are emitted one-per-line, sorted,
# to model uedctl's canonical/deterministic emission.
set -euo pipefail
DIR="${1:?usage: build_tree.sh <dir>}"
mkdir -p "$DIR/actors"

# --- point actors -----------------------------------------------------------
cat > "$DIR/actors/PlayerStart0.t3d" <<'EOF'
Begin Actor Class=PlayerStart Name=PlayerStart0
    Location=(X=100.000000,Y=200.000000,Z=32.000000)
    Rotation=(Yaw=16384)
    Tag=Start
    Name=PlayerStart0
End Actor
EOF

cat > "$DIR/actors/Light0.t3d" <<'EOF'
Begin Actor Class=Light Name=Light0
    Location=(X=512.000000,Y=512.000000,Z=256.000000)
    LightBrightness=180
    LightHue=40
    Tag=CeilingLight
    Name=Light0
End Actor
EOF

cat > "$DIR/actors/Light1.t3d" <<'EOF'
Begin Actor Class=Light Name=Light1
    Location=(X=-512.000000,Y=512.000000,Z=256.000000)
    LightBrightness=140
    LightHue=120
    Tag=CornerLight
    Name=Light1
End Actor
EOF

cat > "$DIR/actors/AmmoClip0.t3d" <<'EOF'
Begin Actor Class=AmmoClip Name=AmmoClip0
    Location=(X=64.000000,Y=-128.000000,Z=8.000000)
    Tag=Loot
    Name=AmmoClip0
End Actor
EOF

cat > "$DIR/actors/Computer0.t3d" <<'EOF'
Begin Actor Class=Computers Name=Computer0
    Location=(X=800.000000,Y=0.000000,Z=48.000000)
    Rotation=(Yaw=32768)
    Tag=SecTerminal
    userName0=admin
    Name=Computer0
End Actor
EOF

cat > "$DIR/actors/Trigger0.t3d" <<'EOF'
Begin Actor Class=Trigger Name=Trigger0
    Location=(X=0.000000,Y=0.000000,Z=16.000000)
    CollisionRadius=48.000000
    Event=OpenDoor
    Tag=EntryTrig
    Name=Trigger0
End Actor
EOF

# --- brush actors (carry a Begin Brush ... End Brush polylist) --------------
cat > "$DIR/actors/Brush_Room.t3d" <<'EOF'
Begin Actor Class=Brush Name=Brush_Room
    CsgOper=CSG_Subtract
    Group="main_room"
    Location=(X=0.000000,Y=0.000000,Z=0.000000)
    Tag=Room
    Begin Brush Name=Model_Room
       Begin PolyList
          Begin Polygon Item=OUTSIDE Link=0
             Origin   -00256.000000,-00256.000000,+00000.000000
             Normal   +00000.000000,+00000.000000,+00001.000000
             TextureU +00001.000000,+00000.000000,+00000.000000
             TextureV +00000.000000,+00001.000000,+00000.000000
             Vertex   -00256.000000,-00256.000000,+00000.000000
             Vertex   +00256.000000,-00256.000000,+00000.000000
             Vertex   +00256.000000,+00256.000000,+00000.000000
             Vertex   -00256.000000,+00256.000000,+00000.000000
          End Polygon
       End PolyList
    End Brush
    Name=Brush_Room
End Actor
EOF

cat > "$DIR/actors/Brush_Door.t3d" <<'EOF'
Begin Actor Class=Brush Name=Brush_Door
    CsgOper=CSG_Subtract
    Group="doorway"
    Location=(X=256.000000,Y=0.000000,Z=0.000000)
    Tag=Door
    Begin Brush Name=Model_Door
       Begin PolyList
          Begin Polygon Item=OUTSIDE Link=0
             Origin   -00032.000000,-00064.000000,+00000.000000
             Normal   +00000.000000,+00000.000000,+00001.000000
             TextureU +00001.000000,+00000.000000,+00000.000000
             TextureV +00000.000000,+00001.000000,+00000.000000
             Vertex   -00032.000000,-00064.000000,+00000.000000
             Vertex   +00032.000000,-00064.000000,+00000.000000
             Vertex   +00032.000000,+00064.000000,+00000.000000
             Vertex   -00032.000000,+00064.000000,+00000.000000
          End Polygon
       End PolyList
    End Brush
    Name=Brush_Door
End Actor
EOF

# --- order (CSG precedence) + metadata --------------------------------------
cat > "$DIR/order" <<'EOF'
Brush_Room
Brush_Door
PlayerStart0
Light0
Light1
AmmoClip0
Computer0
Trigger0
EOF

cat > "$DIR/packages" <<'EOF'
DeusEx
Engine
EOF

printf 'LUM_Spike\n' > "$DIR/name"

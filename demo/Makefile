# Demo pipeline: club (level) -> shots (renders) -> mp4 (video).
PY ?= python3

.PHONY: club shots mp4 clean
club:  ; ./showcase-bar.sh              # builds the NEON STRATA club in $UEDCLI_LEVEL
shots: ; ./capture-club-shots.sh        # -> out/mp4src/club/shot-*.png (needs the game container)
mp4:   ; $(PY) mp4.py                   # -> out/pitch.mp4 (needs ffmpeg)
clean: ; rm -rf out

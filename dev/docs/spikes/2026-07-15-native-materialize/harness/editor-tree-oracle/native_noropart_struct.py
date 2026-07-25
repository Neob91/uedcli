#!/usr/bin/env python3
"""Dump native NOREPART committed incremental tree (plane bits) for first-N mover-clean UNATCO brushes.
Usage: native_struct.py N > out.log   (STRUCT lines to stderr are redirected to stdout here)."""
import os, sys, io, ctypes
sys.path.insert(0,'/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl')
sys.path.insert(0,'/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/dev/docs/spikes/2026-07-15-native-materialize/harness')
os.environ['UEDCTL_BSPCSG_NOREPART']='1'
os.environ['UEDCTL_BSPCSG_TREE_STRUCT']='1'
import unatco_subset as US
from spike_classindex import class_index   # the schema-aware mover gate's ClassIndex
from uedctl.native import materialize as M
import uedctl_native

N=int(sys.argv[1])
level,_ = US.trunk.read_level(US.FULL_TRUNK)
brushes=[nm for nm in US._brush_order(level)[:N] if M._in_world_csg(level.actors[nm], class_index())]
bs=[M._build_brush_input(nm, level.actors[nm]) for nm in brushes]
# capture fd 2 (Rust eprintln) to a file
outpath=sys.argv[2] if len(sys.argv)>2 else f'/dev/stderr'
fd=os.open(outpath, os.O_WRONLY|os.O_CREAT|os.O_TRUNC, 0o644)
saved=os.dup(2); os.dup2(fd,2)
try:
    mdl=uedctl_native.build_geometry_bspcsg(bs)
finally:
    os.dup2(saved,2); os.close(saved); os.close(fd)
sys.stderr.write(f'built N={N} worldbrushes={len(bs)}\n')

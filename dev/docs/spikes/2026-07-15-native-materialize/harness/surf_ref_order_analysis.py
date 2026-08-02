#!/usr/bin/env python3
"""Surfs-section residual analysis: WHY the raw Surfs bytes only match ~21% vs the editor.

This is the durable evidence behind spike section 83 ("Surfs iActor / texture_ref parity is a
session artifact").  It answers, against the golden `Test_Castle.dx`:

  1. Which surf FIELDS actually diverge?  (per-field positional byte match)
  2. Do the diverging fields cascade (shift later bytes) or just mismatch in place?  (ref WIDTHS)
  3. Is the divergence deterministically fixable from the trunk, or a session/creation-order
     artifact of the editor's object-table numbering?  (reorder simulations + ceilings)

Findings (2026-07-18, `NativeCastle.dx` vs `Test_Castle.dx`):
  * Only `texture_ref` (import index) and `iActor` (owning-brush export index) diverge.  All 8
    geometric/flag fields are byte-exact (pBase 87%, the other 7 100%).
  * `texture_ref` is 1 byte on EVERY surf both sides -> value-only mismatch, NO cascade (485 B).
  * `iActor` width matches only 274/485 -> the width mismatch shifts each following surf, which is
    what collapses the interleaved section to 21%.
  * The editor's export order (hence iActor index) and import order (hence texture_ref index) are
    session CREATION-order: they are NOT the trunk order, NOT the ULevel Actors[] order, and NOT
    FName-hash-derivable (same-prefix random-suffix names like Moon_* CLUSTER in the export table,
    which a name hash would scatter).
  * Reordering native's brush actors into TRUNK order (any block offset) recovers Surfs to at most
    ~26.6%.  Only assigning each brush the editor's EXACT export index recovers it to 93.3% (the
    remainder being texture_ref + the pBase residual).  => per-surf iActor byte-parity is a session
    artifact, not a deterministic lever, against this golden.

CAVEAT: the golden here is the HAND-AUTHORED Test_Castle.dx, not an UnrealEd re-import of our T3D
trunk (the fidelity bar direction/materialize.md actually names).  A clean editor re-import MIGHT emit exports
in deterministic T3D order; settling that needs an editor-materialize (follow-up spike).

Usage:  .venv/bin/python .../harness/surf_ref_order_analysis.py [NATIVE.dx] [EDITOR.dx]
"""
from __future__ import annotations

import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path("/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "dev/docs/spikes/2026-06-27-decontainerize-uedcli/harness"))

import utexture_decode as UT  # noqa: E402
from uedcli.native import umodel as UM  # noqa: E402
from uedcli.native.codec import write_ci, ref_export, deref  # noqa: E402

NATIVE = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/NativeCastle.dx"
EDITOR = "/home/neob91/Games/LutrisDX/drive_c/DX/Maps/Test_Castle.dx"
TRUNK = "/home/neob91/Games/LutrisDX/drive_c/DX/LUM/_scratch/castle/uedcli/maps/foobar"

FIELDS = ["texture_ref", "poly_flags", "p_base", "v_normal", "v_texture_u", "v_texture_v",
          "i_light_map", "i_brush_poly", "i_zone", "i_actor"]


def largest_model(pkg):
    return max((i for i in range(len(pkg.exports))
                if pkg.class_of_export(i) == "Model" and pkg.exports[i]["ssize"] > 0),
               key=lambda i: pkg.exports[i]["ssize"])


def model_of(path):
    pkg = UT.load_package(path)
    e = pkg.exports[largest_model(pkg)]
    return UM.parse_model_body(pkg.buf, e["soff"], e["ssize"]), pkg


def enc_field(s, f):
    if f == "poly_flags":
        return struct.pack("<I", s.poly_flags & 0xFFFFFFFF)
    if f == "i_zone":
        return struct.pack("<HH", s.i_zone[0] & 0xFFFF, s.i_zone[1] & 0xFFFF)
    return write_ci(getattr(s, f))


def enc_surf(s, i_actor, texture_ref):
    o = bytearray()
    o += write_ci(texture_ref)
    o += struct.pack("<I", s.poly_flags & 0xFFFFFFFF)
    o += write_ci(s.p_base); o += write_ci(s.v_normal)
    o += write_ci(s.v_texture_u); o += write_ci(s.v_texture_v)
    o += write_ci(s.i_light_map); o += write_ci(s.i_brush_poly)
    o += struct.pack("<HH", s.i_zone[0] & 0xFFFF, s.i_zone[1] & 0xFFFF)
    o += write_ci(i_actor)
    return bytes(o)


def surfs_section_2(model, iactor_override=None, texture_override=None):
    out = bytearray(); out += write_ci(len(model.surfs))
    for k, s in enumerate(model.surfs):
        ia = iactor_override[k] if iactor_override is not None else s.i_actor
        tx = texture_override[k] if texture_override is not None else s.texture_ref
        out += enc_surf(s, ia, tx)
    return bytes(out)


def exp_name(pkg, i):
    return pkg.names[pkg.exports[i]["nm"]]


def main():
    nat_p = sys.argv[1] if len(sys.argv) > 1 else NATIVE
    ed_p = sys.argv[2] if len(sys.argv) > 2 else EDITOR
    nm, npk = model_of(nat_p)
    em, epk = model_of(ed_p)
    n = min(len(nm.surfs), len(em.surfs))
    print(f"NATIVE {nat_p}\nEDITOR {ed_p}\nsurfs: native={len(nm.surfs)} editor={len(em.surfs)}\n")

    # (1) per-field positional byte match
    print("== per-field positional byte match (native vs editor) ==")
    print(f"  {'field':14s} {'nat B':>7} {'ed B':>7} {'match':>7} {'%':>6}  identical/surf")
    for f in FIELDS:
        nb = b"".join(enc_field(nm.surfs[i], f) for i in range(n))
        eb = b"".join(enc_field(em.surfs[i], f) for i in range(n))
        m = sum(1 for i in range(min(len(nb), len(eb))) if nb[i] == eb[i])
        idc = sum(1 for i in range(n) if enc_field(nm.surfs[i], f) == enc_field(em.surfs[i], f))
        print(f"  {f:14s} {len(nb):>7} {len(eb):>7} {m:>7} {100.0*m/max(1,len(eb)):>5.1f}%  {idc}/{n}")

    # (2) ref widths
    tw = sum(1 for i in range(n)
             if len(write_ci(nm.surfs[i].texture_ref)) == len(write_ci(em.surfs[i].texture_ref)))
    iw = sum(1 for i in range(n)
             if len(write_ci(nm.surfs[i].i_actor)) == len(write_ci(em.surfs[i].i_actor)))
    print(f"\n== ref widths ==\n  texture_ref width match: {tw}/{n}  (native hist "
          f"{dict(Counter(len(write_ci(s.texture_ref)) for s in nm.surfs))})")
    print(f"  iActor      width match: {iw}/{n}  (native {dict(Counter(len(write_ci(s.i_actor)) for s in nm.surfs))}"
          f" editor {dict(Counter(len(write_ci(s.i_actor)) for s in em.surfs))})")

    # (3) reorder ceilings.  We can override BOTH ref fields (iActor and/or texture_ref) so the
    # two contributions are separable.  The iActor override drives the cascade; texture is flat.
    eb = surfs_section_2(em)

    def score(iactor_override=None, texture_override=None):
        nb = surfs_section_2(nm, iactor_override, texture_override)
        c = min(len(nb), len(eb))
        return 100.0 * sum(1 for i in range(c) if nb[i] == eb[i]) / len(eb)

    nat_bn = [exp_name(npk, deref(s.i_actor)[1])
              if deref(s.i_actor) and deref(s.i_actor)[0] == "export" else None
              for s in nm.surfs]
    ed_name2exp = {exp_name(epk, i): i for i in range(len(epk.exports))
                   if epk.class_of_export(i) == "Brush"}
    # editor-EXACT per-surf refs (by matching brush/texture NAME) — the "perfect order" ceiling.
    perfect_ia = [ref_export(ed_name2exp[b]) if b in ed_name2exp else nm.surfs[k].i_actor
                  for k, b in enumerate(nat_bn)]
    perfect_tex = [em.surfs[k].texture_ref for k in range(len(nm.surfs))]

    print("\n== Surfs section reorder ceilings (interleaved raw bytes) ==")
    print(f"  A  baseline native                         : {score():.1f}%")
    print(f"  Tx perfect texture VALUES only (iActor nat) : {score(None, perfect_tex):.1f}%"
          "   (flat 1-byte field: iActor cascade swamps it)")
    print(f"  B  editor-EXACT iActor indices              : {score(perfect_ia):.1f}%"
          "   (session order; NOT trunk-reachable)")
    print(f"  B+ editor-EXACT iActor + texture            : {score(perfect_ia, perfect_tex):.1f}%"
          "   (remainder = pBase ~114 B)")

    # Deterministic-from-trunk candidate orderings for the brush block, each over a FULL offset
    # sweep (the editor's real brush block sits at export idx ~39-164, so a narrow sweep understates
    # the ceiling — reviewer-caught 2026-07-18).
    try:
        from uedcli import trunk
        lvl, _ = trunk.read_level(Path(TRUNK))
        tb = [nn for nn in lvl.order if lvl.actors[nn].brush is not None]
        first_ref, seen = [], set()
        for b in nat_bn:
            if b and b not in seen:
                seen.add(b); first_ref.append(b)
        ed_order = [exp_name(epk, i) for i in range(len(epk.exports))
                    if epk.class_of_export(i) == "Brush" and exp_name(epk, i) in set(tb)]

        def sweep(order):
            best = (0.0, 0)
            for off in range(0, 260):
                n2e = {"Brush0": off}
                for i, b in enumerate(order):
                    n2e[b] = off + 1 + i
                ov = [ref_export(n2e[b]) if b in n2e else nm.surfs[k].i_actor
                      for k, b in enumerate(nat_bn)]
                sc = score(ov)
                if sc > best[0]:
                    best = (sc, off)
            return best

        print("  -- deterministic-from-trunk brush orderings (full offset sweep) --")
        for label, order in [("C1 trunk (file) order", tb),
                             ("C2 first-reference order", first_ref),
                             ("C3 name-sorted order", sorted(tb))]:
            sc, off = sweep(order)
            print(f"  {label:30s}: {sc:.1f}%  (best @offset {off})   deterministic")
        sc, off = sweep(ed_order)
        print(f"  {'D  editor brush ORDER, compacted':30s}: {sc:.1f}%  (best @offset {off})"
              "   (order is session; shown to isolate ORDER vs offset)")
    except Exception as ex:
        print(f"  C/D trunk candidates unavailable: {ex}")


if __name__ == "__main__":
    main()

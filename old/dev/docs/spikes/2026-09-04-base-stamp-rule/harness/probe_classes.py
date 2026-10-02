#!/usr/bin/env python3
"""The spanning probe matrix for the UED22 `Base=LevelInfo` MAP-IMPORT stamp rule.

Each probe is one REAL, CONCRETE (SpawnActor won't place an abstract class) DeusEx/Engine actor
class, chosen to bracket every clause of the candidate gates:

  disasm gate:  Base==NULL & bCollideWorld==True & IsA(Decoration|Inventory|Pawn) &
                Physics in {PHYS_None, PHYS_Rotating}   (all on class-default values)
  native gate:  bStatic==False & bCollideWorld==True & Physics==PHYS_None

The matrix crosses ancestry (Decoration / Inventory / Pawn / Effects / Projectile / Light /
NavigationPoint / Keypoint / Triggers / Mover) with class-default Physics (None / Falling /
Rotating / MovingBrush) and bCollideWorld (True / False) and bStatic (True / False).

No probe authors Base or Physics -> spawn-time value == class default, so the editor's decision
reads ONLY class defaults, and the derived predicate is over class defaults.
"""
from __future__ import annotations

# (probe name, class, note on what clause it brackets)
PROBES: list[tuple[str, str, str]] = [
    # --- Decoration, bCollideWorld=True, varying Physics ---
    ("probe_pinball",       "DeusEx.Pinball",           "Deco Falling  bCW=T"),
    ("probe_toilet",        "DeusEx.Toilet",            "Deco None     bCW=T"),
    ("probe_trashbag",      "DeusEx.TrashBag",          "Deco Falling  bCW=T"),
    ("probe_datacube",      "DeusEx.DataCube",          "Deco Falling  bCW=T"),
    ("probe_computerpers",  "DeusEx.ComputerPersonal",  "Deco Falling  bCW=T"),
    # --- Decoration but bCollideWorld=False (does Deco alone suffice, or is bCW required?) ---
    ("probe_seccamera",     "DeusEx.SecurityCamera",    "Deco Rotating bCW=F"),
    # --- Inventory, bCollideWorld=False (does IsA(Inventory) override bCW?) ---
    ("probe_ammorocket",    "DeusEx.AmmoRocket",        "Inv  Falling  bCW=F"),
    ("probe_weaponpistol",  "DeusEx.WeaponPistol",      "Inv  Falling  bCW=F"),
    # --- Pawn, bCollideWorld=True ---
    ("probe_bartender",     "DeusEx.Bartender",         "Pawn None     bCW=T"),
    # --- Effects, bCollideWorld=True, NOT Deco/Inv/Pawn (IsA-clause test) ---
    ("probe_spark",         "DeusEx.Spark",             "Effects None  bCW=T"),
    ("probe_particleproxy", "DeusEx.ParticleProxy",     "Effects None  bCW=T"),
    # --- Projectile, bCollideWorld=True, Falling, NOT Deco/Inv/Pawn (the KEY IsA-clause test) ---
    ("probe_gasgrenade",    "DeusEx.GasGrenade",        "Projectile Falling bCW=T"),
    # --- Light: bStatic=True, bCollideWorld=False ---
    ("probe_light",         "Engine.Light",             "Light bStatic=T bCW=F"),
    # --- NavigationPoint: bStatic=True, bCollideWorld=False ---
    ("probe_pathnode",      "Engine.PathNode",          "Nav bStatic=T bCW=F"),
    ("probe_patrolpoint",   "Engine.PatrolPoint",       "Nav bStatic=T bCW=F"),
    # --- Keypoint variants: bStatic True vs False, bCollideWorld=False ---
    ("probe_ambientsound",  "Engine.AmbientSound",      "Keypoint bStatic=T bCW=F"),
    ("probe_interppoint",   "Engine.InterpolationPoint","Keypoint bStatic=F bCW=F"),
    ("probe_movercollider", "DeusEx.MoverCollider",     "Keypoint bStatic=F bCW=F"),
    # --- Triggers: bCollideWorld=False, not Deco/Inv/Pawn ---
    ("probe_trigger",       "Engine.Trigger",           "Triggers bCW=F"),
    # --- Deco/Pawn with EXOTIC class-default Physics, all bCollideWorld=True: decisively test
    #     whether a physics clause exists within the stamped ancestry set (the disasm claims only
    #     {PHYS_None, PHYS_Rotating}). ---
    ("probe_alarmlight",    "DeusEx.AlarmLight",        "Deco Rotating bCW=T"),
    ("probe_satdish",       "DeusEx.SatelliteDish",     "Deco Rotating bCW=T"),
    ("probe_poolball",      "DeusEx.Poolball",          "Deco Rolling  bCW=T"),
    ("probe_fish",          "DeusEx.Fish",              "Pawn Swimming bCW=T"),
    ("probe_fly",           "DeusEx.Fly",               "Pawn Flying   bCW=T"),
    # --- Decoration with bStatic=True AND bCollideWorld=True: the decisive test of native's stray
    #     `bStatic==False` clause (does a STATIC world-colliding deco still get Base stamped?). ---
    ("probe_carwrecked",    "DeusEx.CarWrecked",        "Deco None bStatic=T bCW=T"),
    ("probe_fireplug",      "DeusEx.FirePlug",          "Deco None bStatic=T bCW=T"),
]

# A mover is a BRUSH actor (Physics=PHYS_MovingBrush) built on a separate editor path; probed with a
# real cube brush so it imports cleanly.
MOVER_PROBE = ("probe_mover", "DeusEx.DeusExMover", "Mover MovingBrush bCW=F")

# What is the `--faces` value name for the CSG-solved world render?

## Context

A new mode renders the built world (native CSG solve, UnrealEd-parity) alongside the existing
`wire` / `flat` / `textured`. Recommended: `world` (reads as "the built world" vs the per-brush
modes). Alternatives: `solid`, `csg`, `built`. Pure naming — no behaviour rides on it, but it is the
user-facing flag value and `conventions.md` wants self-explanatory help.

## Answer

<!-- Empty = open. -->

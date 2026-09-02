+++
priority = "p3"
kind = "chore"
summary = "Lighting lesson: `LE_NonIncidence` fill lights over-brighten baked in-game lighting"
+++

# Lighting lesson: `LE_NonIncidence` fill lights over-brighten baked in-game lighting

p3.
In `level photo --mode lit` the castle looked moody (good contrast); in-game the same lights
washed the walls near-fullbright. Cause: I used many `LE_NonIncidence` fill lights (ignore surface
normals → brighten everything) layered with the existing 28 lights. Lesson for the substrate notes:
preview-lit ≠ in-game baked lighting; use FAR fewer/dimmer fills, rely on motivated torch pools +
deliberate dark gaps. Worth a line in a lighting doc. Andrzej, 2026-07-13.

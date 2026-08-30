+++
priority = "p?"
kind = "implement"
summary = "Draw an actual world-space gridline overlay for orthographic (2D) panes in level actor preview."
+++

# Add visual grid for 2D views in level actor preview

Level actor preview's orthographic/2D panes currently carry no gridline overlay (only the
addressable coordinate gutter — see `remove-numbering-grid-from-level-actor-preview`, filed
separately, which removes that). Add real gridlines drawn in the 2D projection so scale/position
is readable at a glance, distinct from the addressable-cell labeling this replaces.

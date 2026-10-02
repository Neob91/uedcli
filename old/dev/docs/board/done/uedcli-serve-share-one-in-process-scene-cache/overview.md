+++
priority = "p1"
kind = "implement"
summary = "uedcli serve: share one in-process scene cache across /scene, /atlas, /lightmap"
+++

# uedcli serve: share one in-process scene cache across /scene, /atlas, /lightmap

Done. `/scene`, `/atlas`, `/lightmap` now share one generation-guarded trunk/geometry cache instead
of each redoing the trunk-read and CSG solve independently.

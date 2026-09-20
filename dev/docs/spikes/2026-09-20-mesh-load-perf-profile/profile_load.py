"""Profile a single POST /load against showcase_bar -- reproduces exactly what the GUI's
Reload button triggers server-side, via the real route handler code (not a synthetic call),
so the profile reflects the actual /load code path."""
import cProfile
import pstats
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from fastapi.testclient import TestClient

from uedcli import config
from uedcli.serve.app import create_app

PROJECT_ROOT = Path(__file__).resolve().parents[4] / "dev" / "games"
LEVEL = "showcase_bar"

project = config.resolve_project(env_project=None, cwd=str(PROJECT_ROOT))
app = create_app(project, LEVEL)
client = TestClient(app)

# First /load populates the trunk (and, per the fix, seeds the read-route cache) -- this is the
# ACTUAL cost the GUI's Reload pays every time, warm process or not.
profiler = cProfile.Profile()
profiler.enable()
r = client.post(f"/api/level/{LEVEL}/load")
profiler.disable()

print("status:", r.status_code, r.json())

stats = pstats.Stats(profiler)
stats.sort_stats("cumulative")
print("\n=== top 40 by cumulative time ===")
stats.print_stats(40)

print("\n=== top 25 by own (tottime) ===")
stats.sort_stats("tottime")
stats.print_stats(25)

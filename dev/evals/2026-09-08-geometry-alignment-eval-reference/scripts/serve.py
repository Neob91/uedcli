"""Serves the reference-solution page + its images statically, plus a tiny
JSON API for manual grading (grade_store.py):

  GET  /api/grades          -> {"<task_id>/<run_id>": {score, note, updated_at}, ...}
  POST /api/grade           body {task_id, run_id, score (0-10 or null), note} -> the saved record

Replaces plain `python -m http.server` on the same port -- cloudflared just
proxies to the port, so swapping the process behind it doesn't change the
public URL. Stdlib only.

Usage: serve.py [port]  (default 8756)
"""
import http.server, json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import grade_store

ROOT = pathlib.Path("/workspace/uedcli/.claude/worktrees/geom-eval/dev/evals/2026-09-08-geometry-alignment-eval-reference")

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def do_GET(self):
        if self.path == "/api/grades":
            return self._json(200, grade_store.all_grades())
        return super().do_GET()

    def do_POST(self):
        if self.path != "/api/grade":
            return self._json(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            record = grade_store.put(body["task_id"], body["run_id"], body.get("score"), body.get("note", ""))
        except (KeyError, ValueError, json.JSONDecodeError) as e:
            return self._json(400, {"error": str(e)})
        return self._json(200, record)

    def _json(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8756
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()

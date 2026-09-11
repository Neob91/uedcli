"""Build index.html from every specs/<id>.py's `before` block plus every
rendered execution under runs/<task_id>/*/manifest.json (written by
render_manual.py). No task metadata lives in this file -- add a new task by
adding a new specs/<file>.py, not by editing this script; executions appear
automatically as render_manual.py writes them, no registration needed.
Grading is manual: each execution card POSTs a score (0-10) + note to
serve.py's /api/grade and reloads it from /api/grades -- this script only
lays out the form, it never computes a verdict."""
import json, pathlib, sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from registry import TASKS

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST_IMG = ROOT / "img"
RUNS = ROOT / "runs"

used = set()  # (task_id, name) pairs actually referenced, for the missing-file check
def img(task_id, name):
    used.add((task_id, name))
    return f"img/{task_id}/{name}.png"

run_used = set()  # (task_id, run_id, relpath) -- relpath already includes ".png"
def run_img(task_id, run_id, relpath):
    run_used.add((task_id, run_id, relpath))
    return f"runs/{task_id}/{run_id}/img/{relpath}"

ALL_CAROUSELS = {}
CAROUSEL_GROUPS = {}  # key -> count of leading "diagram" items in ALL_CAROUSELS[key];
                      # the rest are "photo" items -- drives the lightbox's d/p group switch

def discover_executions(task_id):
    d = RUNS / task_id
    if not d.exists():
        return []
    runs = []
    for p in sorted(d.iterdir()):
        mf = p / "manifest.json"
        if mf.exists():
            runs.append(json.loads(mf.read_text()))
    runs.sort(key=lambda r: r["rendered_at"], reverse=True)
    return runs

BUCKET_ORDER = {"created": 0, "updated": 1, "deleted": 2}

def execution_card(task_id, task, run):
    run_id = run["run_id"]
    key = f"{task_id}__exec__{run_id}"
    gid = f"{task_id}--{run_id}"

    entries = sorted(run["entries"], key=lambda e: (BUCKET_ORDER[e["bucket"]], e["actor"]))
    undeclared_count = sum(1 for e in entries if not e["declared"])
    items = [{"default": 1, "variants": [
                {"src": run_img(task_id, run_id, e["img_before"]), "cap": f"BEFORE — {e['actor']}: {e['what']}"},
                {"src": run_img(task_id, run_id, e["img_after"]), "cap": f"{e['label']} — {e['actor']}: {e['what']}"},
              ]} for e in entries]
    items += [{"default": 0, "variants": [
                {"src": run_img(task_id, run_id, n), "cap": f"Photo, panorama frame {i}"},
                {"src": img(task_id, f"pan_before_{i}"), "cap": f"BEFORE — panorama frame {i}"},
              ]} for i, n in enumerate(run["panorama"])]
    ALL_CAROUSELS[key] = items
    CAROUSEL_GROUPS[key] = len(entries)

    grid = "".join(
        f'<figure class="egrid-item b-{e["bucket"]}{"" if e["declared"] else " undeclared"}">'
        f'<img src="{run_img(task_id, run_id, e["img_after"])}" alt="{e["actor"]}" loading="lazy" tabindex="0" '
        f'onclick="openLB(\'{key}\',{i})" onkeydown="if(event.key===\'Enter\')openLB(\'{key}\',{i})">'
        f'<figcaption><span class="elbl b-{e["bucket"]}">{e["label"]}</span> {e["actor"]}'
        f'<span class="ewhat">{e["what"]}</span></figcaption></figure>'
        for i, e in enumerate(entries))

    pan_thumbs = "".join(
        f'<img class="cthumb" src="{run_img(task_id, run_id, n)}" alt="panorama" loading="lazy" tabindex="0" '
        f'onclick="openLB(\'{key}\',{len(entries)+i})" onkeydown="if(event.key===\'Enter\')openLB(\'{key}\',{len(entries)+i})">'
        for i, n in enumerate(run["panorama"]))

    return f"""<div class="scen">
      <button class="scenhead" onclick="toggleScen(this)">
        <span class="chev">&#9656;</span><span class="stitle">{run['label']}</span>
        <span class="tmeta" data-gradebadge="{gid}">not yet graded</span>
      </button>
      <div class="scenbody" hidden>
        <p class="sdesc">Subject trunk: <code>{run['subject_trunk']}</code> · rendered {run['rendered_at'][:19]}Z</p>
        <div class="striplabel">Panorama</div>
        <div class="carousel">{pan_thumbs}</div>
        <div class="striplabel">{len(entries)} actor(s) actually differ from baseline{
            f' &mdash; {undeclared_count} not declared in the task spec' if undeclared_count else ''
        }</div>
        <div class="egrid">{grid}</div>
        <div class="gradebox" data-task="{task_id}" data-run="{run_id}">
          <label>Score (0–10)
            <input type="number" min="0" max="10" step="1" class="gscore" placeholder="—">
          </label>
          <label class="gnotelbl">Notes
            <textarea class="gnote" rows="3" placeholder="What's wrong, or why it's right..."></textarea>
          </label>
          <div class="grow">
            <button class="gsave" onclick="saveGrade(this)">Save grade</button>
            <span class="gstatus">not yet graded</span>
          </div>
        </div>
      </div></div>"""

def task_block(task_id, task):
    before = task["before"]
    bid = f"{task_id}__before"
    quad_cap = "Whole-room quad view (Top / Front / Iso / Side), before any edit."
    ALL_CAROUSELS[bid] = [{"default": 0, "variants": [{"src": img(task_id, before["quad"]), "cap": quad_cap}]}] + \
                          [{"default": 0, "variants": [{"src": img(task_id, n), "cap": "Panorama frame, before any edit."}]}
                           for n in before["photos"]]
    CAROUSEL_GROUPS[bid] = 1
    before_quad_html = (f'<figure class="dg dg-quad"><img src="{img(task_id, before["quad"])}" alt="{quad_cap}" '
                         f'onclick="openLB(\'{bid}\',0)"><figcaption>{before["note"]}</figcaption></figure>')
    before_thumbs = "".join(f'<img class="cthumb" src="{img(task_id, n)}" alt="panorama" loading="lazy" tabindex="0" '
                             f'onclick="openLB(\'{bid}\',{i+1})" onkeydown="if(event.key===\'Enter\')openLB(\'{bid}\',{i+1})">'
                             for i, n in enumerate(before["photos"]))
    runs = discover_executions(task_id)
    exec_html = ('<p class="sdesc">No executions rendered yet for this task — run '
                 '<code>scripts/render_manual.py '
                 f'{task_id} &lt;subject_trunk&gt;</code> and rebuild the page.</p>')
    if runs:
        exec_html = "".join(execution_card(task_id, task, r) for r in runs)
    return f"""<div class="taskblk">
      <button class="taskhead" onclick="toggleTask(this)">
        <span class="tchev">&#9656;</span><h2>{task['title']}</h2>
      </button>
      <div class="taskbody" hidden>
        <div class="task"><span class="t">REQUEST:</span> {task['req']}</div>
        <div class="beforeblk">
          <div class="diagrams">{before_quad_html}</div>
          <div class="striplabel">Panorama — before</div>
          <div class="carousel">{before_thumbs}</div>
        </div>
        <h3 class="scenh">Executions</h3>
        {exec_html}
      </div></div>"""

BODY = "".join(task_block(tid, task) for tid, task in TASKS.items())
CAROUSEL_JSON = json.dumps(ALL_CAROUSELS)
CAROUSEL_GROUPS_JSON = json.dumps(CAROUSEL_GROUPS)

# Flat, page-order list of every execution + its task context -- drives the
# sidebar tree (grouped by task_id, first-seen order) and the inbox queue
# (filtered to ungraded, same order) client-side.
EXEC_META = [dict(task_id=task_id, run_id=run["run_id"], label=run["label"],
                   task_title=task["title"], task_req=task["req"])
             for task_id, task in TASKS.items()
             for run in discover_executions(task_id)]
EXEC_META_JSON = json.dumps(EXEC_META)

HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Widen &amp; Ceiling · Reference Solutions</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--ground:#12130f;--panel:#1b1c16;--panel2:#22241c;--line:#33352a;--ink:#e7e3d4;--dim:#9a9585;--faint:#6f6a5c;
--gold:#c9a24b;--gold-soft:#e0c274;--cyan:#57d4e0;--good:#5bbf7a;--bad:#e8574d;
--mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;--body:'IBM Plex Sans',system-ui,sans-serif;--disp:'Rajdhani',var(--body);}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--body);line-height:1.55;font-size:16px;-webkit-font-smoothing:antialiased}
img{max-width:100%}
.wrap{max-width:1040px;margin:0 auto;padding:clamp(20px,4vw,52px)}
h1,h2,h3{font-family:var(--disp);font-weight:600;text-wrap:balance;letter-spacing:.01em;margin:0}
.eyebrow{font-family:var(--mono);font-size:12.5px;letter-spacing:.22em;text-transform:uppercase;color:var(--gold);margin:0 0 14px}
.lede{font-size:clamp(26px,4vw,40px);line-height:1.08;margin:0 0 16px;letter-spacing:-.01em}

.layout{display:flex;align-items:flex-start}
.mainarea{flex:1;min-width:0}
.sidebar{width:240px;flex-shrink:0;position:sticky;top:0;height:100vh;overflow-y:auto;
  border-right:1px solid var(--line);background:var(--panel);padding:16px 12px}
.sbhead{margin:0 0 14px}
.inboxbtn{width:100%;font:inherit;font-size:13px;font-weight:600;background:var(--gold);color:#1a1608;
  border:0;border-radius:4px;padding:10px;cursor:pointer}
.inboxbtn:hover{background:var(--gold-soft)}
.inboxbtn:disabled{opacity:.4;cursor:default}
.sbtask{margin:0 0 14px}
.sbtasktitle{font-family:var(--mono);font-size:10px;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);margin:0 0 6px;padding:0 6px}
.sbexecs{list-style:none;margin:0;padding:0}
.sbexec{width:100%;text-align:left;display:flex;align-items:center;gap:8px;background:transparent;border:0;
  border-radius:3px;padding:6px 8px;font:inherit;font-size:12.5px;color:var(--dim);cursor:pointer}
.sbexec:hover{background:var(--panel2);color:var(--ink)}
.sbexec.active{background:var(--panel2);color:var(--ink);font-weight:600}
.sbdot{width:8px;height:8px;border-radius:50%;background:var(--faint);flex-shrink:0}
.sbdot.graded{background:var(--good)}
.sbtoggle{display:none;position:fixed;top:14px;left:14px;z-index:46;font:inherit;font-size:16px;
  background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:4px;padding:8px 12px;cursor:pointer}

#focusPane{display:none}
body.focus-mode .taskblk{display:none}
body.focus-mode #focusPane{display:block}
.focusexit{font:inherit;font-size:12px;color:var(--dim);background:transparent;border:1px solid var(--line);
  border-radius:3px;padding:6px 10px;cursor:pointer;margin:0 0 14px}
.focusbanner{margin:0 0 20px;padding:14px 16px;border:1px solid var(--line);border-left:3px solid var(--gold);
  background:var(--panel2);border-radius:4px;transition:border-color .3s,background-color .3s}
.focusbanner.flash{border-left-color:var(--cyan);background:color-mix(in srgb,var(--cyan) 14%,var(--panel2))}
.focusbanner h2{font-size:17px;margin:0 0 4px}
.focusbanner p{margin:0;font-size:13.5px;color:var(--dim)}

@media (max-width: 820px){
  .sbtoggle{display:inline-flex}
  .sidebar{position:fixed;top:0;bottom:0;left:-260px;z-index:45;transition:left .2s;box-shadow:4px 0 24px rgba(0,0,0,.5)}
  .sidebar.open{left:0}
}

.taskblk{margin:28px 0 0;border:1px solid var(--line);border-radius:6px;overflow:hidden;background:var(--panel)}
.taskhead{width:100%;text-align:left;background:var(--panel2);border:0;border-bottom:1px solid var(--line);padding:16px 20px;
  display:flex;align-items:center;gap:12px;cursor:pointer;font:inherit;color:inherit}
.taskhead h2{font-size:clamp(19px,2.6vw,25px);flex:1}
.tchev{font-size:18px;color:var(--gold);transition:transform .15s;flex-shrink:0}
.taskblk.open .tchev{transform:rotate(90deg)}
.taskblk.open .taskhead{border-bottom-color:var(--gold)}
.taskbody{padding:20px}
.task{margin:0 0 20px;padding:14px 16px;border:1px solid var(--line);border-left:3px solid var(--gold);background:var(--panel2);border-radius:2px;font-size:15px;color:var(--dim)}
.task .t{font-family:var(--mono);color:var(--gold);font-size:12px;letter-spacing:.1em}

.beforeblk{margin:0 0 26px;padding:14px;border:1px solid color-mix(in srgb,var(--gold) 30%,var(--line));border-radius:4px;background:var(--panel2)}
.diagrams{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:8px;background:#13140d;padding:8px;border-radius:3px}
.dg{margin:0}.dg img{display:block;width:100%;height:auto;border-radius:2px;cursor:zoom-in}
.dg-quad{max-width:560px;margin:0 auto}
.dg figcaption{font-family:var(--mono);font-size:11px;color:var(--dim);padding:5px 2px 2px}
.striplabel{font-family:var(--mono);font-size:11px;color:var(--faint);letter-spacing:.06em;margin:12px 0 8px}

.scenh{font-size:13px;font-family:var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--faint);margin:24px 0 10px;padding-top:14px;border-top:1px solid var(--line)}
.scen{border:1px solid var(--line);border-radius:4px;margin:0 0 10px;overflow:hidden;background:var(--panel2)}
.scenhead{width:100%;text-align:left;background:transparent;border:0;padding:12px 16px;display:flex;align-items:center;gap:10px;cursor:pointer;font:inherit;color:inherit}
.chev{font-size:13px;color:var(--gold);transition:transform .15s;flex-shrink:0}
.scen.open .chev{transform:rotate(90deg)}
.stitle{font-size:15.5px;font-weight:600;flex:1}
.scenbody{padding:0 16px 16px}
.sdesc{color:var(--dim);font-size:14px;margin:0 0 12px}
.carousel{display:flex;flex-wrap:wrap;gap:6px}
.cthumb{width:130px;height:97px;object-fit:cover;border-radius:2px;border:1px solid var(--line);cursor:zoom-in;transition:border-color .12s}
.cthumb:hover,.cthumb:focus{border-color:var(--gold);outline:none}
.diffbox{margin:14px 0 0;font-size:13px}
.diffbox summary{cursor:pointer;color:var(--gold-soft);font-family:var(--mono);font-size:12px}
.diffbox a{color:var(--cyan)}
.diffpre{margin:10px 0 0;padding:12px;background:#0d0e08;border:1px solid var(--line);border-radius:3px;overflow-x:auto;
  color:var(--dim);font-family:var(--mono);font-size:11.5px;line-height:1.55;white-space:pre}
.nochange{color:var(--gold-soft);font-family:var(--mono);font-size:12px;margin:10px 0 0}
.tmeta{font-family:var(--mono);font-size:11.5px;color:var(--faint);margin-left:auto}
.tmeta.graded{color:var(--good)}

.egrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin:0 0 4px}
.egrid-item{margin:0;background:#13140d;border:1px solid var(--line);border-left:3px solid var(--faint);border-radius:3px;overflow:hidden}
.egrid-item img{display:block;width:100%;height:auto;cursor:zoom-in}
.egrid-item figcaption{font-size:11.5px;color:var(--dim);padding:6px 8px 8px}
.egrid-item .ewhat{display:block;color:var(--faint);font-size:10.5px;margin-top:2px}
.elbl{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;padding:1px 5px;border-radius:2px;margin-right:5px}
.egrid-item.b-created{border-left-color:var(--cyan)}.elbl.b-created{background:color-mix(in srgb,var(--cyan) 25%,transparent);color:var(--cyan)}
.egrid-item.b-updated{border-left-color:var(--gold)}.elbl.b-updated{background:color-mix(in srgb,var(--gold) 25%,transparent);color:var(--gold-soft)}
.egrid-item.b-deleted{border-left-color:var(--bad)}.elbl.b-deleted{background:color-mix(in srgb,var(--bad) 25%,transparent);color:var(--bad)}
.egrid-item.undeclared{outline:2px dashed var(--bad);outline-offset:-1px}

.gradebox{margin:18px 0 0;padding:14px 16px;border:1px solid color-mix(in srgb,var(--cyan) 35%,var(--line));border-radius:4px;background:#13140d;display:flex;flex-wrap:wrap;gap:14px 20px;align-items:flex-end}
.gradebox label{display:flex;flex-direction:column;gap:5px;font-family:var(--mono);font-size:11px;letter-spacing:.05em;text-transform:uppercase;color:var(--faint)}
.gradebox .gnotelbl{flex:1;min-width:220px}
.gradebox input.gscore{width:70px;font:inherit;font-size:16px;background:var(--panel2);border:1px solid var(--line);border-radius:3px;color:var(--ink);padding:6px 8px}
.gradebox textarea.gnote{font:inherit;font-size:13.5px;background:var(--panel2);border:1px solid var(--line);border-radius:3px;color:var(--ink);padding:8px;resize:vertical;min-height:38px}
.gradebox .grow{display:flex;align-items:center;gap:10px}
.gradebox .gsave{font:inherit;font-size:13px;font-weight:600;background:var(--gold);color:#1a1608;border:0;border-radius:3px;padding:8px 16px;cursor:pointer}
.gradebox .gsave:hover{background:var(--gold-soft)}
.gradebox .gsave:disabled{opacity:.5;cursor:default}
.gradebox .gstatus{font-family:var(--mono);font-size:11.5px;color:var(--faint)}
.gradebox .gstatus.saved{color:var(--good)}
.gradebox .gstatus.error{color:var(--bad)}

code{font-family:var(--mono);font-size:.9em;background:var(--panel2);padding:1px 5px;border-radius:2px;color:var(--gold-soft)}

.lb{position:fixed;inset:0;background:rgba(6,7,4,.94);display:flex;flex-direction:column;align-items:center;justify-content:center;z-index:50;padding:24px}
.lb[hidden]{display:none}
.lbimgwrap{position:relative;max-width:100%;max-height:78vh;display:flex;align-items:center;justify-content:center;overflow:auto}
.lb img{max-width:100%;max-height:78vh;border-radius:3px;box-shadow:0 8px 40px rgba(0,0,0,.6);cursor:zoom-in}
.lb img.zoomed{max-width:none;max-height:none;cursor:zoom-out}
.lbcap{color:var(--ink);font-size:15px;line-height:1.4;max-width:70ch;text-align:center;margin-top:16px;padding:0 12px;
  height:5.6em;overflow-y:auto;display:flex;align-items:center;justify-content:center}
.lbnav{position:fixed;top:0;bottom:0;width:80px;background:transparent;border:0;color:var(--ink);font-size:36px;cursor:pointer;opacity:.7;transition:opacity .12s}
.lbnav:hover{opacity:1}
.lbprev{left:0}.lbnext{right:0}
.lbclose{position:fixed;top:14px;right:18px;font-family:var(--mono);font-size:12px;color:var(--dim);background:transparent;border:1px solid var(--line);border-radius:3px;padding:6px 10px;cursor:pointer}
.lbcount{position:fixed;top:16px;left:18px;font-family:var(--mono);font-size:12px;color:var(--dim)}
.lbvariant{position:fixed;top:16px;left:50%;transform:translateX(-50%);font-family:var(--mono);font-size:12px;color:var(--cyan);letter-spacing:.04em;background:rgba(6,7,4,.6);padding:5px 12px;border-radius:12px}
.lbvnav{position:fixed;left:50%;transform:translateX(-50%);width:56px;height:44px;background:rgba(6,7,4,.55);border:1px solid var(--line);border-radius:8px;color:var(--ink);font-size:20px;line-height:1;cursor:pointer;opacity:.75;transition:opacity .12s;display:flex;align-items:center;justify-content:center}
.lbvnav:hover{opacity:1}
.lbvnav:disabled{opacity:.2;cursor:default}
.lbvup{top:52px}
.lbvdown{bottom:52px}
</style></head>
<body>
<button class="sbtoggle" onclick="document.getElementById('sidebar').classList.toggle('open')">&#9776;</button>
<div class="layout">
  <nav id="sidebar" class="sidebar">
    <div class="sbhead"><button id="inboxBtn" class="inboxbtn" onclick="startInbox()">Start inbox</button></div>
    <div id="sbtree" class="sbtree"></div>
  </nav>
  <div class="mainarea"><div class="wrap">
    <p class="eyebrow">uedcli · geometry-alignment eval</p>
    <h1 class="lede">Grade subagent executions.</h1>
    <div id="focusPane">
      <button class="focusexit" onclick="exitFocusMode()">&larr; Back to all</button>
      <div id="focusBanner" class="focusbanner"><h2 id="focusTitle"></h2><p id="focusReq"></p></div>
      <div id="focusSlot"></div>
    </div>
    __BODY__
  </div></div>
</div>

<div id="lb" class="lb" hidden>
  <button class="lbclose" onclick="closeLB()">✕ close (Esc)</button>
  <span id="lbcount" class="lbcount"></span>
  <span id="lbvariant" class="lbvariant"></span>
  <button class="lbnav lbprev" onclick="lbStep(-1)" aria-label="previous">&#10094;</button>
  <button class="lbnav lbnext" onclick="lbStep(1)" aria-label="next">&#10095;</button>
  <button id="lbvup" class="lbvnav lbvup" onclick="cycleVariant(-1)" aria-label="previous view">&#9650;</button>
  <button id="lbvdown" class="lbvnav lbvdown" onclick="cycleVariant(1)" aria-label="next view">&#9660;</button>
  <div id="lbimgwrap" class="lbimgwrap"><img id="lbimg" alt="" onclick="toggleZoom(event)"></div>
  <p id="lbcap" class="lbcap"></p>
</div>

<script>
const CAROUSELS = __CAROUSEL_JSON__;
const CAROUSEL_GROUPS = __CAROUSEL_GROUPS_JSON__;
const EXEC_META = __EXEC_META_JSON__;
let GRADES = {};
let lbScen = null, lbIdx = 0;
let lbGroupIdx = {diagrams: 0, photos: 0};

function toggleTask(btn){
  const blk = btn.closest('.taskblk');
  const wasOpen = blk.classList.contains('open');
  document.querySelectorAll('.taskblk.open').forEach(b => {
    b.classList.remove('open');
    b.querySelector('.taskbody').hidden = true;
  });
  if (!wasOpen){
    blk.classList.add('open');
    blk.querySelector('.taskbody').hidden = false;
  }
}
function toggleScen(btn){
  const scen = btn.closest('.scen');
  const body = scen.querySelector('.scenbody');
  const open = scen.classList.toggle('open');
  body.hidden = !open;
}

function escapeHtml(s){
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function buildSidebar(){
  const tree = document.getElementById('sbtree');
  let html = '', curTask = null;
  for (const e of EXEC_META){
    if (e.task_id !== curTask){
      if (curTask !== null) html += '</ul></div>';
      html += `<div class="sbtask"><div class="sbtasktitle">${escapeHtml(e.task_title)}</div><ul class="sbexecs">`;
      curTask = e.task_id;
    }
    html += `<li><button class="sbexec" data-task="${e.task_id}" data-run="${e.run_id}" `
          + `onclick="sidebarClick('${e.task_id}','${e.run_id}')"><span class="sbdot"></span>`
          + `${escapeHtml(e.label)}</button></li>`;
  }
  if (curTask !== null) html += '</ul></div>';
  tree.innerHTML = html;
}

// Focus mode: one execution's existing card, relocated (not cloned -- its
// onclick handlers and data- attributes travel with it) into #focusPane.
// focusedOrigin remembers where to put it back on exit.
let focusedOrigin = null;   // {node, parent, next}
let lastFocusedTaskId = null;
let inboxActive = false;

function focusExec(taskId, runId){
  const scen = document.querySelector(`.gradebox[data-task="${taskId}"][data-run="${runId}"]`).closest('.scen');
  if (focusedOrigin && focusedOrigin.node !== scen){
    focusedOrigin.parent.insertBefore(focusedOrigin.node, focusedOrigin.next);
  }
  if (!focusedOrigin || focusedOrigin.node !== scen){
    focusedOrigin = {node: scen, parent: scen.parentNode, next: scen.nextSibling};
  }
  scen.classList.add('open');
  scen.querySelector('.scenbody').hidden = false;
  document.getElementById('focusSlot').appendChild(scen);

  const meta = EXEC_META.find(e => e.task_id === taskId && e.run_id === runId);
  document.getElementById('focusTitle').textContent = meta.task_title;
  document.getElementById('focusReq').innerHTML = meta.task_req;
  const banner = document.getElementById('focusBanner');
  if (taskId !== lastFocusedTaskId){
    banner.classList.add('flash');
    setTimeout(() => banner.classList.remove('flash'), 900);
  }
  lastFocusedTaskId = taskId;

  document.querySelectorAll('.sbexec.active').forEach(b => b.classList.remove('active'));
  const sb = document.querySelector(`.sbexec[data-task="${taskId}"][data-run="${runId}"]`);
  if (sb) sb.classList.add('active');

  scen.querySelector('.gsave').textContent = inboxActive ? 'Save & next' : 'Save grade';
  document.body.classList.add('focus-mode');
  document.getElementById('sidebar').classList.remove('open');
  window.scrollTo(0, 0);
}
function exitFocusMode(){
  inboxActive = false;
  if (focusedOrigin) focusedOrigin.parent.insertBefore(focusedOrigin.node, focusedOrigin.next);
  focusedOrigin = null;
  lastFocusedTaskId = null;
  document.body.classList.remove('focus-mode');
  document.querySelectorAll('.sbexec.active').forEach(b => b.classList.remove('active'));
}
function sidebarClick(taskId, runId){
  inboxActive = false;
  focusExec(taskId, runId);
}
function computeUngraded(){
  return EXEC_META.filter(e => {
    const g = GRADES[`${e.task_id}/${e.run_id}`];
    return !g || g.score === null || g.score === undefined;
  });
}
function updateInboxButton(){
  const n = computeUngraded().length;
  const btn = document.getElementById('inboxBtn');
  btn.textContent = n ? `Start inbox (${n} ungraded)` : 'All graded';
  btn.disabled = n === 0;
}
function startInbox(){
  inboxActive = true;
  advanceInbox();
}
function advanceInbox(){
  const queue = computeUngraded();
  if (queue.length === 0){
    inboxActive = false;
    if (focusedOrigin) focusedOrigin.parent.insertBefore(focusedOrigin.node, focusedOrigin.next);
    focusedOrigin = null;
    lastFocusedTaskId = null;
    document.querySelectorAll('.sbexec.active').forEach(b => b.classList.remove('active'));
    document.getElementById('focusTitle').textContent = 'All caught up';
    document.getElementById('focusReq').textContent = 'Nothing ungraded left in the queue.';
    document.body.classList.add('focus-mode');
    return;
  }
  focusExec(queue[0].task_id, queue[0].run_id);
}

function applyGrade(gid, rec){
  GRADES[`${rec.task_id}/${rec.run_id}`] = rec;
  const box = document.querySelector(`.gradebox[data-task="${rec.task_id}"][data-run="${rec.run_id}"]`);
  const badge = document.querySelector(`[data-gradebadge="${gid}"]`);
  const graded = rec.score !== null && rec.score !== undefined;
  if (box){
    box.querySelector('.gscore').value = graded ? rec.score : '';
    box.querySelector('.gnote').value = rec.note || '';
    setStatus(box, rec);
  }
  if (badge){
    badge.textContent = graded ? `graded ${rec.score}/10` : 'not yet graded';
    badge.classList.toggle('graded', graded);
  }
  const dot = document.querySelector(`.sbexec[data-task="${rec.task_id}"][data-run="${rec.run_id}"] .sbdot`);
  if (dot) dot.classList.toggle('graded', graded);
  updateInboxButton();
}
function setStatus(box, rec){
  const s = box.querySelector('.gstatus');
  s.classList.remove('error');
  if (rec && rec.updated_at){
    s.textContent = `saved ${rec.updated_at.slice(0,19)}Z`;
    s.classList.add('saved');
  } else {
    s.textContent = 'not yet graded';
    s.classList.remove('saved');
  }
}
async function loadGrades(){
  try {
    const res = await fetch('/api/grades');
    const grades = await res.json();
    for (const key in grades){
      const rec = grades[key];
      applyGrade(`${rec.task_id}--${rec.run_id}`, rec);
    }
    updateInboxButton();  // still correct even if `grades` was empty
  } catch (e) { console.error('loadGrades failed', e); }
}
async function saveGrade(btn){
  const box = btn.closest('.gradebox');
  const task_id = box.dataset.task, run_id = box.dataset.run;
  const scoreRaw = box.querySelector('.gscore').value;
  const score = scoreRaw === '' ? null : Math.max(0, Math.min(10, parseInt(scoreRaw, 10)));
  const note = box.querySelector('.gnote').value;
  btn.disabled = true;
  const s = box.querySelector('.gstatus');
  s.textContent = 'saving…'; s.classList.remove('saved','error');
  try {
    const res = await fetch('/api/grade', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({task_id, run_id, score, note}),
    });
    if (!res.ok) throw new Error((await res.json()).error || res.statusText);
    const rec = await res.json();
    applyGrade(`${task_id}--${run_id}`, rec);
    if (inboxActive) setTimeout(advanceInbox, 350);  // brief pause so "saved" is visible before the jump
  } catch (e) {
    s.textContent = 'save failed: ' + e.message;
    s.classList.add('error');
  } finally {
    btn.disabled = false;
  }
}
buildSidebar();
loadGrades();
let lbVariant = 0;
function nDiagrams(){ return CAROUSEL_GROUPS[lbScen] || 0; }
function groupOf(idx){ return idx < nDiagrams() ? 'diagrams' : 'photos'; }
function groupBounds(name){
  const nd = nDiagrams(), total = CAROUSELS[lbScen].length;
  return name === 'diagrams' ? [0, nd] : [nd, total];
}
function openLB(scenId, idx){
  lbScen = scenId; lbIdx = idx;
  lbVariant = CAROUSELS[lbScen][lbIdx].default || 0;
  const nd = nDiagrams(), total = CAROUSELS[lbScen].length;
  lbGroupIdx = {diagrams: nd > 0 ? 0 : -1, photos: nd < total ? nd : -1};
  lbGroupIdx[groupOf(idx)] = idx;
  renderLB();
  document.getElementById('lb').hidden = false;
}
// Jump to the other group (d/p), landing on that group's last-viewed index
// so switching back and forth doesn't lose your place in either one.
function jumpGroup(name){
  const [lo, hi] = groupBounds(name);
  if (lo >= hi) return;  // this execution has nothing in that group
  lbIdx = Math.min(Math.max(lbGroupIdx[name], lo), hi - 1);
  lbVariant = Math.min(lbVariant, CAROUSELS[lbScen][lbIdx].variants.length - 1);
  renderLB();
}
function openLBGroup(scenId, name){
  lbScen = scenId;
  const [lo, hi] = groupBounds(name);
  if (lo >= hi) return;
  openLB(scenId, lo);
}
function renderLB(){
  renderVariant();
  const grp = groupOf(lbIdx);
  const [lo, hi] = groupBounds(grp);
  const label = grp === 'diagrams' ? 'diagram' : 'photo';
  document.getElementById('lbcount').textContent = `${label} ${lbIdx - lo + 1} / ${hi - lo}`;
}
function renderVariant(){
  const item = CAROUSELS[lbScen][lbIdx];
  const v = item.variants[lbVariant];
  const img = document.getElementById('lbimg');
  img.src = v.src;
  img.classList.remove('zoomed');
  document.getElementById('lbimgwrap').scrollTo(0, 0);
  document.getElementById('lbcap').textContent = v.cap;
  const vbar = document.getElementById('lbvariant');
  const hasVariants = item.variants.length > 1;
  vbar.hidden = !hasVariants;
  if (hasVariants) vbar.textContent = `view ${lbVariant+1}/${item.variants.length} — ↑↓ or swipe`;
  document.getElementById('lbvup').disabled = !hasVariants;
  document.getElementById('lbvdown').disabled = !hasVariants;
}
function lbStep(d){
  const list = CAROUSELS[lbScen];
  const grp = groupOf(lbIdx);
  const [lo, hi] = groupBounds(grp);
  const span = hi - lo;
  lbIdx = lo + (((lbIdx - lo) + d + span) % span);
  lbGroupIdx[grp] = lbIdx;
  // left/right moves between actors/frames within the same group (diagrams
  // or photos, never crossing) but keeps the current before/after (up/down)
  // choice, clamped in case the new item has fewer variants than the one
  // you were just on
  lbVariant = Math.min(lbVariant, list[lbIdx].variants.length - 1);
  renderLB();
}
function cycleVariant(d){
  const item = CAROUSELS[lbScen][lbIdx];
  if (item.variants.length < 2) return;
  lbVariant = (lbVariant + d + item.variants.length) % item.variants.length;
  renderVariant();
}
function toggleZoom(e){
  e.stopPropagation();
  document.getElementById('lbimg').classList.toggle('zoomed');
}
function closeLB(){ document.getElementById('lb').hidden = true; }
document.addEventListener('keydown', e => {
  if (document.getElementById('lb').hidden) return;
  // stopImmediatePropagation so the focus-pane listener (registered later,
  // gated on the lightbox being hidden) doesn't also see this same Escape
  // once closeLB() has already flipped that hidden flag
  if (e.key === 'Escape') { closeLB(); e.stopImmediatePropagation(); }
  if (e.key === 'ArrowLeft') lbStep(-1);
  if (e.key === 'ArrowRight') lbStep(1);
  if (e.key === 'ArrowUp') { e.preventDefault(); cycleVariant(-1); }
  if (e.key === 'ArrowDown') { e.preventDefault(); cycleVariant(1); }
  if (!e.ctrlKey && !e.metaKey && !e.altKey){
    if (e.key === 'd' || e.key === 'D') jumpGroup('diagrams');
    if (e.key === 'p' || e.key === 'P') jumpGroup('photos');
  }
});
document.getElementById('lb').addEventListener('click', e => {
  if (e.target.id === 'lb') closeLB();
});
let lbTouchX = null, lbTouchY = null;
document.getElementById('lb').addEventListener('touchstart', e => {
  // a tap that starts on a button (close/prev/next/up/down) is its own
  // gesture -- swipe detection would preventDefault the touchmove and
  // suppress the button's synthetic click, so leave it alone entirely
  if (e.touches.length !== 1 || e.target.closest('button')) { lbTouchX = null; return; }
  lbTouchX = e.touches[0].clientX;
  lbTouchY = e.touches[0].clientY;
}, {passive: true});
document.getElementById('lb').addEventListener('touchmove', e => {
  // block the page (and the modal backdrop) from scrolling under a swipe;
  // NOT blocked while zoomed, so panning a zoomed image via native
  // touch-scroll still works
  if (lbTouchX !== null && !document.getElementById('lbimg').classList.contains('zoomed')) {
    e.preventDefault();
  }
}, {passive: false});
document.getElementById('lb').addEventListener('touchend', e => {
  if (lbTouchX === null) return;
  // zoomed images pan via native touch-scroll -- don't hijack that as a swipe
  if (document.getElementById('lbimg').classList.contains('zoomed')) { lbTouchX = null; return; }
  const dx = e.changedTouches[0].clientX - lbTouchX;
  const dy = e.changedTouches[0].clientY - lbTouchY;
  lbTouchX = null;
  const SWIPE = 40;
  if (Math.max(Math.abs(dx), Math.abs(dy)) < SWIPE) return;  // tap, not a swipe
  if (Math.abs(dx) > Math.abs(dy)) lbStep(dx < 0 ? 1 : -1);
  else cycleVariant(dy < 0 ? -1 : 1);
});

// Focus-pane keyboard nav: g focuses the score field, n the notes field, d/p
// open the lightbox straight to that group. Off whenever any grading field
// has focus (score or notes) so typing "d" types "d" and nothing else --
// browsers don't reliably block letter keys on type=number, so the score
// field gets no exemption either.
function isTypingTarget(el){
  if (!el) return false;
  return el.tagName === 'TEXTAREA' || el.tagName === 'INPUT';
}
function execKey(box){ return `${box.dataset.task}__exec__${box.dataset.run}`; }
document.addEventListener('keydown', e => {
  if (!document.body.classList.contains('focus-mode')) return;
  if (!document.getElementById('lb').hidden) return;  // lightbox owns its own keys while open
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === 'Escape'){ exitFocusMode(); return; }
  if (isTypingTarget(e.target)) return;
  const box = document.querySelector('#focusSlot .gradebox');
  if (!box) return;
  const key = execKey(box);
  if (e.key === 'd' || e.key === 'D') openLBGroup(key, 'diagrams');
  else if (e.key === 'p' || e.key === 'P') openLBGroup(key, 'photos');
  else if (e.key === 'g' || e.key === 'G'){ e.preventDefault(); const f = box.querySelector('.gscore'); f.focus(); f.select(); }
  else if (e.key === 'n' || e.key === 'N'){ e.preventDefault(); box.querySelector('.gnote').focus(); }
});

// Enter in either grading field saves (and advances, if inbox mode is
// active) -- the only way to advance; Shift+Enter still inserts a newline
// in the notes textarea.
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter' || e.shiftKey) return;
  if (!e.target.classList || !(e.target.classList.contains('gnote') || e.target.classList.contains('gscore'))) return;
  e.preventDefault();
  saveGrade(e.target.closest('.gradebox').querySelector('.gsave'));
});
</script>
</body></html>
"""
(ROOT / "index.html").write_text(HTML.replace("__BODY__", BODY)
                                  .replace("__CAROUSEL_JSON__", CAROUSEL_JSON)
                                  .replace("__CAROUSEL_GROUPS_JSON__", CAROUSEL_GROUPS_JSON)
                                  .replace("__EXEC_META_JSON__", EXEC_META_JSON))

missing = [f"{t}/{n}" for t, n in sorted(used) if not (DEST_IMG / t / f"{n}.png").exists()]
missing += [f"runs/{t}/{r}/img/{n}" for t, r, n in sorted(run_used) if not (RUNS / t / r / "img" / n).exists()]
print("wrote", ROOT / "index.html")
print("images used:", len(used), "+", len(run_used), "trial images; missing:", missing)

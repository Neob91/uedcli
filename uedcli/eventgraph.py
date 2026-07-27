"""Tag↔Event wiring analysis — pure, offline, model-side.

In UnrealEngine-1 / Deus Ex, actors are wired to each other by name-matching two properties:

  * an actor's **`Event`** property is the event it FIRES (a Trigger with `Event=OpenDoor`
    broadcasts "OpenDoor" when it fires);
  * an actor's **`Tag`** property is its receiver identity — every actor whose `Tag=OpenDoor`
    reacts when "OpenDoor" is fired.

So a directed edge **A → B** exists when `A.Event == B.Tag` (both non-empty). This module builds
that graph from a parsed `Level` and lints it (dangling wires, unreachable movers, cycles). It is
100% string/property scanning over the model — no editor, no container, no CSG.

Unset-`Tag` convention (load-bearing — see dev/docs/decisions.md 2026-07-18 20:54 UTC):
UnrealEngine defaults an unset `Tag` to the actor's class name at runtime. We deliberately treat
ONLY an explicitly-set, non-empty `Tag` as a matchable receiver — a default/class-name Tag is NOT
an edge target. Reason: relying on the class-name default would wire together every same-class
actor whenever some unrelated Trigger happens to fire that class name, which is almost never the
author's intent and would flood the graph with spurious edges. The cost is that a mapper who
*intentionally* leaves Tag unset and fires the class name sees no edge; that pattern is rare and
the explicit-Tag form is the norm.

Scope limit (see dev/docs/board/inbox/): the edge model reads the single `Event` property only.
Multi-event actors that fire through ARRAY properties (Dispatcher `OutEvents(n)`, Counter, etc.)
are not modelled here — those extra fired events produce no edges yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import Actor, Level
from .movers import is_mover

# Engine.Mover InitialState values that move the mover WITHOUT a matching trigger Event
# (self-opening / bump-opening / looping). A mover in one of these states with an unused Tag is
# working as intended, so the unreachable-mover lint skips it. Case-folded on compare. This list is
# the common Deus Ex / Unreal set; an unset InitialState is treated as trigger-driven (the usual
# authored-door case), so an explicit Tag that nothing targets still flags.
_SELF_MOVING_STATES = {
    "standopentimed", "loopmove", "constantloop",
    "bumpopentimed", "bumpbutton", "bumpopenaway",
}


@dataclass
class Node:
    """One actor that participates in eventing."""
    name: str
    cls: str
    event: str | None
    tag: str | None
    is_mover: bool


@dataclass
class Edge:
    """A directed trigger wire: `src.Event == dst.tag`."""
    src: str
    dst: str
    event: str


@dataclass
class EventGraph:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


@dataclass
class Finding:
    """One lint result. `kind` is a stable slug; `message` is the human line. `actor`/`actors`/
    `event`/`tag` carry the machine detail (only the relevant ones are set per kind)."""
    kind: str
    message: str
    actor: str | None = None
    actors: list[str] | None = None
    event: str | None = None
    tag: str | None = None


def _prop(actor: Actor, key: str) -> str | None:
    """First value of prop `key` (case-insensitive), stripped; None if absent or empty/whitespace.

    Props are stored quote-stripped already (model._parse_actor), but we also treat an empty or
    whitespace-only value as absent — an `Event=""` or `Tag=` is not a live wire."""
    kf = key.casefold()
    for k, v in actor.props:
        if k.casefold() == kf:
            s = (v or "").strip()
            return s or None
    return None


def build_graph(level: Level, index) -> EventGraph:
    """Build the Tag↔Event graph for a parsed level. `index` is a `classindex.ClassIndex` — the
    node rule below asks whether an actor is a Mover, and that is decided schema-aware by
    `movers.is_mover` against the game's `.u` class hierarchy.

    A node is any actor with a non-empty `Event` OR a non-empty `Tag`, OR any Mover (so a mover
    still appears in the graph/DOT even when it carries no eventing props). Note this only makes a
    tagless mover a visible NODE — the unreachable-mover LINT deliberately fires only on a mover
    with an EXPLICIT unused Tag (a tagless mover's trigger mechanism — bump/loop — isn't reliably
    knowable offline; see `lint_graph`). An edge A → B is emitted for every actor
    B whose explicit `Tag` equals A's `Event` (case-insensitive FName match; self-edges kept).
    Node/edge order follows level order (list_actors' deterministic order is not needed here — we
    iterate level.actors in insertion order, which for a trunk load mirrors the on-disk set)."""
    nodes: list[Node] = []
    for name, a in level.actors.items():
        event = _prop(a, "Event")
        tag = _prop(a, "Tag")
        mover = is_mover(a, index)
        if event is None and tag is None and not mover:
            continue
        nodes.append(Node(name=name, cls=a.cls, event=event, tag=tag, is_mover=mover))

    # Receivers indexed by case-folded Tag → list of node names (an event can drive several).
    receivers: dict[str, list[str]] = {}
    for n in nodes:
        if n.tag is not None:
            receivers.setdefault(n.tag.casefold(), []).append(n.name)

    edges: list[Edge] = []
    for n in nodes:
        if n.event is None:
            continue
        for dst in receivers.get(n.event.casefold(), []):
            edges.append(Edge(src=n.name, dst=dst, event=n.event))
    return EventGraph(nodes=nodes, edges=edges)


def _self_moving(node: Node, level: Level) -> bool:
    """True if `node` is a mover whose InitialState moves it without a trigger (self/bump/loop)."""
    state = _prop(level.actors[node.name], "InitialState")
    return state is not None and state.casefold() in _SELF_MOVING_STATES


def _extract_cycle(scc: set[str], adj: dict[str, list[str]], order: dict[str, int]) -> list[str]:
    """Return ONE concrete directed cycle (a real edge path) through the strongly-connected set
    `scc`, as an ordered list of member names. Greedy walk: from the lowest-index member, always
    step to the lowest-index in-SCC successor (a real edge — every SCC member has one, by strong
    connectivity) until we revisit a node already on the path; the tail from that node closes the
    cycle. Deterministic. A self-loop SCC (size 1) returns `[node]`. Unlike sorting the SCC members,
    every consecutive pair here is a genuine `Event→Tag` edge, so the printed `A -> B -> … -> A`
    never claims a wire that doesn't exist (review 2026-07-18)."""
    start = min(scc, key=lambda x: order[x])
    path = [start]
    pos = {start: 0}
    node = start
    while True:
        nxt = min((w for w in adj[node] if w in scc), key=lambda x: order[x])
        if nxt in pos:
            return path[pos[nxt]:]                # the closed cycle (tail from the revisited node)
        pos[nxt] = len(path)
        path.append(nxt)
        node = nxt


def _find_cycles(graph: EventGraph) -> list[list[str]]:
    """Directed cycles via Tarjan strongly-connected components: every SCC of size >1 contains a
    cycle; a size-1 SCC is a cycle only if the node has a self-edge. For each such SCC, return ONE
    concrete cycle path (`_extract_cycle`) — real edges in traversal order, not the sorted member
    set. Iterative Tarjan (no recursion-depth risk on a large level)."""
    names = [n.name for n in graph.nodes]
    order = {name: i for i, name in enumerate(names)}
    adj: dict[str, list[str]] = {name: [] for name in names}
    self_loop: set[str] = set()
    for e in graph.edges:
        if e.src in adj and e.dst in adj:      # both endpoints are nodes (always true here)
            adj[e.src].append(e.dst)
            if e.src == e.dst:
                self_loop.add(e.src)

    index_of: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    sccs: list[list[str]] = []

    for root in names:
        if root in index_of:
            continue
        # work stack of (node, next-neighbour-index)
        work: list[tuple[str, int]] = [(root, 0)]
        index_of[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, ni = work[-1]
            if ni < len(adj[node]):
                work[-1] = (node, ni + 1)
                w = adj[node][ni]
                if w not in index_of:
                    index_of[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, 0))
                elif w in on_stack:
                    low[node] = min(low[node], index_of[w])
            else:
                if low[node] == index_of[node]:      # SCC root — pop it
                    comp: list[str] = []
                    while True:
                        m = stack.pop()
                        on_stack.discard(m)
                        comp.append(m)
                        if m == node:
                            break
                    if len(comp) > 1 or (len(comp) == 1 and comp[0] in self_loop):
                        sccs.append(_extract_cycle(set(comp), adj, order))
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
    # deterministic order: by first member's node index
    return sorted(sccs, key=lambda c: order[c[0]])


def lint_graph(graph: EventGraph, level: Level) -> list[Finding]:
    """Lint the wiring. Findings, most-actionable groups first:
      * `dangling_event`  — an `Event` matching no actor's Tag (fires into the void);
      * `unreachable_tag` — an explicit `Tag` no `Event` targets (unreachable receiver); movers
        are EXCLUDED (they get the mover-specific finding);
      * `unreachable_mover` — a Mover with an explicit Tag nothing targets AND not self-moving
        (nothing can ever move it);
      * `cycle` — a directed trigger cycle (member names).
    """
    tags_present = {n.tag.casefold() for n in graph.nodes if n.tag is not None}
    events_present = {n.event.casefold() for n in graph.nodes if n.event is not None}
    findings: list[Finding] = []

    # dangling events — fire into the void
    for n in graph.nodes:
        if n.event is not None and n.event.casefold() not in tags_present:
            findings.append(Finding(
                kind="dangling_event", actor=n.name, event=n.event,
                message=f"{n.name} ({n.cls}) fires Event={n.event!r} but no actor has that Tag"))

    # unreachable receivers (non-movers) + unreachable movers
    for n in graph.nodes:
        if n.tag is None or n.tag.casefold() in events_present:
            continue                                  # tagless, or something targets this tag
        if n.is_mover:
            if _self_moving(n, level):
                continue                              # self/bump/loop mover — the tag being idle is fine
            findings.append(Finding(
                kind="unreachable_mover", actor=n.name, tag=n.tag,
                message=f"{n.name} ({n.cls}) is a Mover with Tag={n.tag!r} that no Event triggers "
                        f"— nothing can move it"))
        else:
            findings.append(Finding(
                kind="unreachable_tag", actor=n.name, tag=n.tag,
                message=f"{n.name} ({n.cls}) has Tag={n.tag!r} that no Event targets "
                        f"— unreachable receiver"))

    # cycles
    for comp in _find_cycles(graph):
        findings.append(Finding(
            kind="cycle", actors=comp,
            message="trigger cycle: " + " -> ".join(comp) + f" -> {comp[0]}"))
    return findings


# ── formatters ────────────────────────────────────────────────────────────────

def format_text(graph: EventGraph) -> str:
    """The wiring, one edge per line: `Src (Class) --Event--> Dst (Class)`. Empty string when the
    graph has no edges (isolated participating nodes surface only in the lint / --json)."""
    cls = {n.name: n.cls for n in graph.nodes}
    lines = [f"{e.src} ({cls.get(e.src, '?')}) --{e.event}--> {e.dst} ({cls.get(e.dst, '?')})"
             for e in graph.edges]
    return "\n".join(lines)


def _dot_quote(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def format_dot(graph: EventGraph) -> str:
    """Graphviz DOT of the whole graph (every participating node + every edge), for `dot -Tpng`.
    A mover node is drawn as a box; a firing Event with no receiver is not an edge, so isolated
    nodes still appear (declared up front)."""
    out = ["digraph events {", "  rankdir=LR;", '  node [shape=ellipse];']
    for n in graph.nodes:
        shape = "box" if n.is_mover else "ellipse"
        # `\\n` emits the two-char DOT line-break escape (name/cls escaped SEPARATELY so the
        # break isn't itself backslash-escaped into a literal `\n`).
        label = f"{_dot_quote(n.name)}\\n({_dot_quote(n.cls)})"
        out.append(f'  "{_dot_quote(n.name)}" [label="{label}", shape={shape}];')
    for e in graph.edges:
        out.append(f'  "{_dot_quote(e.src)}" -> "{_dot_quote(e.dst)}" '
                   f'[label="{_dot_quote(e.event)}"];')
    out.append("}")
    return "\n".join(out)


def to_json_obj(graph: EventGraph, findings: list[Finding]) -> dict:
    """Structured `{nodes, edges, lint}` for scripts. Node/edge/lint fields mirror the dataclasses;
    lint entries drop the None fields so each kind carries only its relevant keys."""
    def lint_entry(f: Finding) -> dict:
        d: dict = {"kind": f.kind, "message": f.message}
        if f.actor is not None:
            d["actor"] = f.actor
        if f.actors is not None:
            d["actors"] = f.actors
        if f.event is not None:
            d["event"] = f.event
        if f.tag is not None:
            d["tag"] = f.tag
        return d

    return {
        "nodes": [{"name": n.name, "class": n.cls, "event": n.event, "tag": n.tag,
                   "is_mover": n.is_mover} for n in graph.nodes],
        "edges": [{"from": e.src, "to": e.dst, "event": e.event} for e in graph.edges],
        "lint": [lint_entry(f) for f in findings],
    }

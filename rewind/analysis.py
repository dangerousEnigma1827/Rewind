"""Analysis engine. Pure functions over a run's raw events; no printing.

Evidence levels (every Finding carries one):
  OBSERVED  a recorded event, reported as-is
  DERIVED   deterministic computation over observed events (ancestry, ordering, attribution)
  INFERRED  a heuristic explanation; only emitted with the observed/derived findings that support it
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

from .store import Event

OBSERVED, DERIVED, INFERRED = "observed", "derived", "inferred"
STORY_KINDS = ("run.start", "run.end", "run.signal", "http.in", "http.out", "log",
               "error.uncaught", "error.logged", "mutation", "mutation.capped", "instrument")
ERROR_KINDS = ("error.uncaught", "error.logged")


def short_fn(fn: str | None) -> str:
    """V8 names like `Timeout.paymentConfirmed` or `Server.<anonymous>` -> the part a human wrote."""
    if not fn:
        return "<anonymous>"
    tail = fn.split(".")[-1]
    return fn if tail == "<anonymous>" and "." in fn else tail


def is_user_frame(f: dict) -> bool:
    return "node_modules/" not in f["file"] and not f["file"].startswith("node:")


def user_frame(stack: list | None) -> dict | None:
    return next((f for f in stack or [] if is_user_frame(f)), None)


def where(f: dict | None) -> str:
    return f"{f['file']}:{f['line']}" if f else "?"


@dataclass
class Finding:
    level: str
    text: str
    evidence: list[int] = field(default_factory=list)  # backing event seqs


@dataclass
class Request:
    id: int
    anchor: int       # asyncId of the HTTPINCOMINGMESSAGE the handler runs in
    inbound: Event
    outbound: Event | None = None

    @property
    def label(self) -> str:
        return f"#{self.id} {self.inbound.name}"


class Run:
    """Indexes over one run's events. Built once; every view reads from here."""

    def __init__(self, events: list[Event], meta: dict | None = None):
        self.events = events
        self.meta = meta or {}
        self.by_seq = {e.seq: e for e in events}
        self.inits: dict[int, Event] = {}
        self.children: dict[int, list[int]] = {}
        self.fired: dict[int, list[Event]] = {}     # aid -> its async.before events (callback runs)
        self.emitted: dict[int, list[Event]] = {}   # eid -> story events emitted while it ran
        self.requests: dict[int, Request] = {}
        anchors = {}
        for e in events:
            if e.kind == "async.init":
                self.inits[e.aid] = e
                self.children.setdefault(e.tid, []).append(e.aid)
            elif e.kind == "async.before":
                self.fired.setdefault(e.aid, []).append(e)
            if e.kind in STORY_KINDS:
                self.emitted.setdefault(e.eid, []).append(e)
            if e.kind == "http.in":
                r = Request(e.data["req"], e.aid, e)
                self.requests[r.id] = r
                anchors[e.aid] = r.id
            elif e.kind == "http.out" and e.data["req"] in self.requests:
                self.requests[e.data["req"]].outbound = e
        self.anchors = anchors
        self._req_cache: dict[int, int | None] = {}

    # ---- ancestry ----------------------------------------------------------------
    def chain(self, aid: int) -> list[Event]:
        """init events from `aid` up to the root, nearest first (DERIVED from triggerAsyncId links)."""
        out, seen = [], set()
        while aid in self.inits and aid not in seen:
            seen.add(aid)
            out.append(self.inits[aid])
            aid = self.inits[aid].tid
        return out

    def request_of(self, aid: int | None) -> int | None:
        if aid is None:
            return None
        if aid not in self._req_cache:
            hit = next((self.anchors[i.aid] for i in self.chain(aid) if i.aid in self.anchors), None)
            if hit is None and aid in self.anchors:
                hit = self.anchors[aid]
            self._req_cache[aid] = hit
        return self._req_cache[aid]

    def site(self, aid: int) -> dict | None:
        """Where in user code the resource `aid` was created (OBSERVED creation stack)."""
        i = self.inits.get(aid)
        return user_frame(i.stack) if i else None

    def describe(self, aid: int) -> str:
        i = self.inits.get(aid)
        if i is None:
            return "main module" if aid == 1 else f"async {aid}"
        if aid in self.anchors:
            return f"request {self.requests[self.anchors[aid]].label}"
        name = f" {i.name}" if i.name and i.name != "<anonymous>" else ""
        f = user_frame(i.stack)
        if f:
            frm = f" from {short_fn(f['fn'])}" if short_fn(f["fn"]) not in ("<anonymous>", i.name) else ""
        else:  # internal hop (e.g. fs read step): name the user code it continues
            up = next((user_frame(c.stack) for c in self.chain(aid)[1:] if user_frame(c.stack)), None)
            frm = f" via {short_fn(up['fn'])}" if up and short_fn(up["fn"]) != "<anonymous>" else ""
        return f"{i.type}{name}{frm}"

    def user_chain(self, aid: int) -> list[Event]:
        """Ancestry with frameless internal hops (fs open/stat/read, bare promises) collapsed."""
        return [i for i in self.chain(aid) if user_frame(i.stack) or i.aid in self.anchors]

    # ---- story -------------------------------------------------------------------
    @cached_property
    def story(self) -> list[Event]:
        return [e for e in self.events if e.kind in STORY_KINDS]

    @cached_property
    def errors(self) -> list[Event]:
        return [e for e in self.events if e.kind in ERROR_KINDS]

    def callback_fires(self) -> list[Event]:
        """async.before events of resources created from user code: 'your callback ran here'."""
        return [e for e in self.events if e.kind == "async.before" and self.site(e.aid)]

    @cached_property
    def watch(self) -> list[str]:
        start = next((e for e in self.events if e.kind == "run.start"), None)
        return (start.data or {}).get("watch") or [] if start else []

    @cached_property
    def cwd(self) -> str | None:
        start = next((e for e in self.events if e.kind == "run.start"), None)
        return (start.data or {}).get("cwd") if start else None

    def source_line(self, f: dict | None) -> str | None:
        if not f:
            return None
        p = Path(f["file"])
        if not p.is_absolute() and self.cwd:
            p = Path(self.cwd) / p
        try:
            return p.read_text(encoding="utf-8").splitlines()[f["line"] - 1]
        except (OSError, IndexError, UnicodeDecodeError):
            return None


# ---- tree ------------------------------------------------------------------------
@dataclass
class Node:
    aid: int
    init: Event | None
    children: list["Node"] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)  # story events emitted while this resource's callback ran
    hidden: int = 0                                     # collapsed frameless hops folded into this node


def interesting(e: Event) -> bool:
    return e.kind not in ("instrument", "run.start")


def build_tree(run: Run, root: int = 1, full: bool = False) -> tuple[Node, int]:
    """Async causality tree. Unless `full`, keeps only branches leading to story events and folds
    frameless internal hops into their nearest user-visible descendant. Returns (root, pruned_count)."""
    pruned = 0

    def build(aid: int) -> Node | None:
        nonlocal pruned
        node = Node(aid, run.inits.get(aid), events=[e for e in run.emitted.get(aid, []) if interesting(e)])
        for c in run.children.get(aid, []):
            child = build(c)
            if child:
                node.children.append(child)
        if full or aid == root:
            return node
        if not node.events and not node.children and aid not in run.anchors:
            pruned += 1
            return None
        if node.init and not user_frame(node.init.stack) and aid not in run.anchors and not node.events:
            if len(node.children) == 1:  # fold internal hop into its only child
                node.children[0].hidden += node.hidden + 1
                return node.children[0]
        return node

    return build(root), pruned


# ---- why -----------------------------------------------------------------------------
RACE_INFERENCE = ("Shared module-level state is written by one request and read by another while both are "
                  "in flight: a race between concurrent requests. Keep this state per request.")


@dataclass
class Investigation:
    error: Event
    findings: list[Finding]
    chain: list[Event]
    request: Request | None
    branch: list[Event]  # story events on the error's causal branch, in order


def investigate(run: Run, error: Event) -> Investigation:
    F: list[Finding] = []
    frame = user_frame(error.stack)
    origin = (error.data or {}).get("origin")
    kind = {"uncaughtException": "uncaught exception", "unhandledRejection": "unhandled promise rejection"}.get(origin, "logged error")
    F.append(Finding(OBSERVED, f"{(error.data or {}).get('error') or 'Error'}: {error.name}  ({kind})", [error.seq]))
    if frame:
        F.append(Finding(OBSERVED, f"thrown in {short_fn(frame['fn'])} at {where(frame)}", [error.seq]))

    ctx = error.eid
    chain = run.chain(ctx)
    if chain:
        head = chain[0]
        what = "a rejected promise" if head.type == "PROMISE" else f"the callback of {run.describe(ctx)}"
        F.append(Finding(OBSERVED, f"running inside {what}, created at {where(run.site(ctx))}", [head.seq, error.seq]))
    hops = run.user_chain(ctx)
    if len(hops) > 1:
        path = " ← ".join(f"{run.describe(h.aid)} ({where(run.site(h.aid))})" if h.aid not in run.anchors else run.describe(h.aid) for h in hops)
        F.append(Finding(DERIVED, f"scheduled by: {path}", [h.seq for h in hops]))

    rid = run.request_of(ctx)
    req = run.requests.get(rid) if rid else None
    if req:
        F.append(Finding(DERIVED, f"belongs to request {req.label} (its async ancestry reaches that request's handler)", [req.inbound.seq]))

    on_chain = {h.aid for h in chain} | {ctx}
    branch = [e for e in run.story if e.eid in on_chain and e.seq <= error.seq and e.kind not in ("instrument",)]
    if req:  # whole request branch, not just the direct ancestry
        branch = [e for e in run.story if e.seq <= error.seq and (run.request_of(e.eid) == rid or e.eid in on_chain)
                  and e.kind not in ("instrument", "run.start")]

    # concurrency: other requests that ran callbacks while this one was in flight
    overlapping = []
    if req:
        for other in run.requests.values():
            if other.id == rid:
                continue
            ran = [e for e in run.events if req.inbound.seq < e.seq < error.seq and e.kind == "async.before" and run.request_of(e.aid) == other.id]
            if ran:
                overlapping.append((other, ran))
        for other, ran in overlapping:
            F.append(Finding(DERIVED, f"request {other.label} ran {len(ran)} callback(s) while {req.label} was in flight",
                             [other.inbound.seq, ran[0].seq, ran[-1].seq]))

    F.extend(_shared_state_findings(run, error, frame, req, overlapping))
    return Investigation(error, F, chain, req, branch)


def _shared_state_findings(run: Run, error: Event, frame, req, overlapping) -> list[Finding]:
    F: list[Finding] = []
    line = run.source_line(frame)
    if not line:
        return F
    names = set(re.findall(r"[A-Za-z_$][\w$]*", line))
    watched = [w for w in run.watch if w in names]
    if watched:
        for name in watched:
            F.append(Finding(DERIVED, f"the failing line reads watched variable `{name}`:  {line.strip()}", [error.seq]))
            writes = [e for e in run.events if e.kind == "mutation" and e.name == name and e.seq < error.seq]
            if not writes:
                F.append(Finding(OBSERVED, f"no recorded writes to `{name}` before the error", []))
                continue
            last = writes[-1]
            wr = run.request_of(last.eid)
            who = f"request {run.requests[wr].label}" if wr else run.describe(last.eid)
            d = last.data or {}
            F.append(Finding(OBSERVED, f"last write before the error: `{name}{d.get('path', '')}` {d.get('op')} at {d.get('loc')} "
                                       f"in {run.describe(last.eid)}, value {d.get('after')}", [last.seq]))
            F.append(Finding(DERIVED, f"that write was made by {who}", [last.seq]))
            if req and wr and wr != req.id:
                own = [w for w in writes if run.request_of(w.eid) == req.id]
                if own:
                    F.append(Finding(DERIVED, f"{req.label} wrote `{name}` itself at seq {own[-1].seq}; {who} overwrote it at seq "
                                              f"{last.seq}, before {req.label} read it at seq {error.seq}", [own[-1].seq, last.seq, error.seq]))
                F.append(Finding(INFERRED, RACE_INFERENCE, [last.seq, error.seq] + ([own[-1].seq] if own else [])))
        return F
    # Without --watch we must not claim a mutation. Only point at module-level names on the failing line.
    top = _top_level_names(run, frame)
    suspects = sorted(n for n in names & top if not _is_function(run, frame, n))
    if suspects and overlapping:
        F.append(Finding(DERIVED, f"the failing line uses module-level binding(s) {', '.join('`'+s+'`' for s in suspects)}, "
                                  f"shared by every request:  {line.strip()}", [error.seq]))
        F.append(Finding(INFERRED, f"shared state suspected; writes were not recorded. Re-record with "
                                   f"`--watch {','.join(suspects)}` to confirm who changed it.", [error.seq]))
    return F


_DECL = re.compile(r"^(?:let|var|const)\s+([A-Za-z_$][\w$]*)|^(?:let|var|const)\s*\{([^}]*)\}|^function\s+([A-Za-z_$][\w$]*)", re.M)


def _source(run: Run, frame) -> str:
    p = Path(frame["file"])
    if not p.is_absolute() and run.cwd:
        p = Path(run.cwd) / p
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return ""


def _top_level_names(run: Run, frame) -> set[str]:
    # shortcut: column-0 declarations approximate "top level"; good for conventional formatting.
    names = set()
    for m in _DECL.finditer(_source(run, frame)):
        names.update(x.strip() for x in (m.group(2) or "").split(",") if x.strip())
        names.update(x for x in (m.group(1), m.group(3)) if x)
    return names


def _is_function(run: Run, frame, name: str) -> bool:
    return bool(re.search(rf"^function\s+{re.escape(name)}\b|^(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?:require\(|\(|function|async)", _source(run, frame), re.M))


# ---- diff ------------------------------------------------------------------------------
def tokens(run: Run) -> list[tuple[str, Event]]:
    """Run -> comparable tokens with ids and timings normalised away."""
    out = []
    for e in sorted(run.story + run.callback_fires(), key=lambda e: e.seq):
        rid = run.request_of(e.eid if e.kind != "async.before" else e.aid)
        tag = f"#{rid} " if rid else ""
        if e.kind == "async.before":
            out.append((f"{tag}▸ {run.describe(e.aid)} @ {where(run.site(e.aid))}", e))
        elif e.kind == "mutation":
            d = e.data or {}
            out.append((f"{tag}✎ {e.name}{d.get('path', '')} {d.get('op')} @ {d.get('loc')}", e))
        elif e.kind in ("http.in", "http.out", "log", "error.uncaught", "error.logged", "run.end"):
            label = e.name if e.kind != "run.end" else f"exit {(e.data or {}).get('code')}"
            out.append((f"{tag}{e.kind} {label}", e))
    return out


@dataclass
class DiffResult:
    a: list[tuple[str, Event]]
    b: list[tuple[str, Event]]
    opcodes: list[tuple[str, int, int, int, int]]
    findings: list[Finding]

    @property
    def first_divergence(self):
        return next((op for op in self.opcodes if op[0] != "equal"), None)


def diff(a: Run, b: Run) -> DiffResult:
    import difflib
    ta, tb = tokens(a), tokens(b)
    sm = difflib.SequenceMatcher(a=[t for t, _ in ta], b=[t for t, _ in tb], autojunk=False)
    ops = sm.get_opcodes()
    F: list[Finding] = []
    same = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag == "equal")
    F.append(Finding(DERIVED, f"{same} of {len(ta)} / {len(tb)} normalised steps match", []))
    first = next((op for op in ops if op[0] != "equal"), None)
    if first is None:
        F.append(Finding(DERIVED, "no divergence: both runs took the same observable path", []))
        return DiffResult(ta, tb, ops, F)
    tag, i1, i2, j1, j2 = first
    before = ta[i1 - 1][0] if i1 else "start"
    F.append(Finding(DERIVED, f"runs diverge after: {before}", [ta[i1 - 1][1].seq] if i1 else []))
    if j1 < len(tb):
        F.append(Finding(OBSERVED, f"B does instead: {tb[j1][0]}", [tb[j1][1].seq]))
    if i1 < len(ta):
        F.append(Finding(OBSERVED, f"where A did: {ta[i1][0]}", [ta[i1][1].seq]))
    # ordering inversions of matching steps = interleaving changed
    pos_a = {t: i for i, (t, _) in enumerate(ta)}
    moved = [t for t, _ in tb if t in pos_a]
    inversions = sum(1 for x, y in zip(moved, moved[1:]) if pos_a[x] > pos_a[y])
    if inversions:
        F.append(Finding(DERIVED, f"{inversions} step(s) common to both runs happen in a different order: the interleaving changed", []))
    ea, eb = a.errors, b.errors
    if bool(ea) != bool(eb):
        bad, good = ("A", "B") if ea else ("B", "A")
        F.append(Finding(INFERRED, f"run {bad} fails and {good} does not; the first divergence above is the earliest "
                                   f"observable point where their executions part ways, so start investigating there.", []))
    return DiffResult(ta, tb, ops, F)

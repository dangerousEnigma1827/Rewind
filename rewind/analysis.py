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

from .store import Event, resolve_file

OBSERVED, DERIVED, INFERRED = "observed", "derived", "inferred"
STORY_KINDS = ("run.start", "run.end", "run.signal", "http.in", "http.out", "http.abort", "log",
               "error.uncaught", "error.logged", "mutation", "mutation.capped", "instrument", "snapshot",
               "read", "read.capped")
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


def creator(init: Event) -> int:
    """The execution that created a resource. Native resources with no JS context (accepted sockets, file
    handles) record eid 0; for those the trigger is all there is."""
    return init.eid or init.tid


@dataclass
class Finding:
    level: str
    text: str
    evidence: list[int] = field(default_factory=list)  # backing event seqs
    run: str | None = None  # diff findings: which run ("A"/"B") the seqs belong to


@dataclass
class Request:
    id: int
    anchor: int       # asyncId of the HTTPINCOMINGMESSAGE the handler runs in
    inbound: Event
    outbound: Event | None = None
    end: Event | None = None  # http.end: the first res.end() call, in the context that made it (recorders since F15)

    @property
    def label(self) -> str:
        return f"#{self.id} {self.inbound.name}"


class Run:
    """Indexes over one run's events. Built once; every view reads from here."""

    def __init__(self, events: list[Event], meta: dict | None = None, sources: dict[str, str | None] | None = None):
        self.events = events
        self.meta = meta or {}
        self.sources = sources  # store.sources(): recorded source snapshots; None = legacy run, read the disk
        self.by_seq = {e.seq: e for e in events}
        self.inits: dict[int, Event] = {}
        self.children: dict[int, list[int]] = {}
        self.fired: dict[int, list[Event]] = {}     # aid -> its async.before events (callback runs)
        self.resolves: dict[int, list[Event]] = {}  # aid -> its async.resolve events (a promise settling)
        self.emitted: dict[int, list[Event]] = {}   # eid -> story events emitted while it ran
        self.requests: dict[int, Request] = {}
        anchors, ends = {}, {}
        for e in events:
            if e.kind == "async.init":
                self.inits[e.aid] = e
                self.children.setdefault(creator(e), []).append(e.aid)
            elif e.kind == "async.before":
                self.fired.setdefault(e.aid, []).append(e)
            elif e.kind == "async.resolve":
                self.resolves.setdefault(e.aid, []).append(e)
            if e.kind in STORY_KINDS:
                self.emitted.setdefault(e.eid, []).append(e)
            if e.kind == "http.in":
                r = Request(e.data["req"], e.aid, e)
                self.requests[r.id] = r
                anchors[e.aid] = r.id
            elif e.kind == "http.out" and e.data["req"] in self.requests:
                self.requests[e.data["req"]].outbound = e
            elif e.kind == "http.end":
                ends.setdefault(e.data["req"], e)
        for rid, e in ends.items():
            if rid in self.requests:
                self.requests[rid].end = e
        self.anchors = anchors
        self._req_cache: dict[int, int | None] = {}
        self._trig_cache: dict[int, int | None] = {}

    # ---- ancestry ----------------------------------------------------------------
    # Two links per resource. `creator` (init.eid): the execution that created it, i.e. the code that called
    # setTimeout / then / await / new Promise. `tid` (triggerAsyncId): for a promise reaction, the PROMISE it
    # continues. They differ when a request awaits a promise another request created (a cache, a single-flight
    # call): following tid would hand the awaiting request's work to the creator's request (spikes/causal S3).
    def chain(self, aid: int) -> list[Event]:
        """init events from `aid` up to the root, nearest first, following the creating execution (DERIVED)."""
        return list(self.ancestors(aid))

    def ancestors(self, aid: int):
        """chain() lazily: callers looking for the nearest match don't walk a thousands-deep await loop."""
        seen = set()
        while aid in self.inits and aid not in seen:
            seen.add(aid)
            yield self.inits[aid]
            aid = creator(self.inits[aid])

    def request_of(self, aid: int | None) -> int | None:
        """The request whose code (transitively) scheduled `aid`: the creation chain reaches its handler."""
        return self._request(aid, creator, self._req_cache)

    def trigger_request_of(self, aid: int | None) -> int | None:
        """The request reached by trigger links alone (what Rewind used before F15; kept to report disagreement)."""
        return self._request(aid, lambda i: i.tid, self._trig_cache)

    def _request(self, aid, up, cache) -> int | None:
        """First request anchor on the walk from `aid`. Every resource on the walk is cached with the answer, so a
        long `await` loop (each continuation created by the previous one) costs O(depth) once, not per event."""
        if aid is None:
            return None
        path, seen, hit = [], set(), None
        while aid is not None and aid not in seen:
            if aid in cache:
                hit = cache[aid]
                break
            path.append(aid)
            if aid in self.anchors:
                hit = self.anchors[aid]
                break
            seen.add(aid)
            i = self.inits.get(aid)
            aid = up(i) if i else None
        for a in path:
            cache[a] = hit
        return hit

    # ---- what released a callback (promise reactions only) --------------------------
    def released(self, aid: int, at: int | None = None) -> tuple[Event, bool] | None:
        """For a promise reaction `aid` (a then/await continuation): the async.resolve of the promise it continues
        that precedes its run, and whether it actually waited, i.e. was created before that settlement.

        None unless the run in progress at seq `at` (default: the first run) is the reaction's FIRST run: Node runs a thenable
        job (a then-callback returning a thenable) as a later run of the same asyncId, and that run wasn't released
        by the parent. None for promises whose trigger is their own creating execution (`new Promise`,
        `Promise.resolve`, async-function promises): they aren't reactions. That also skips the rare reaction
        made on the very promise whose callback is running, a missed edge rather than a false one. None for timers,
        I/O and handlers: they run on their own clock."""
        i = self.inits.get(aid)
        if i is None or i.type != "PROMISE" or i.tid == i.eid:
            return None
        runs = self.fired.get(aid, [])
        if not runs:
            return None
        if at is not None:  # the run in progress at `at` must be the first one
            current = [b for b in runs if b.seq <= at]
            if not current or current[-1] is not runs[0]:
                return None
        settled = [r for r in self.resolves.get(i.tid, []) if r.seq < runs[0].seq]
        return (settled[-1], i.seq < settled[-1].seq) if settled else None

    def settled_by(self, aid: int, at: int) -> Event | None:
        """The async.resolve that settled promise `aid` at or before seq `at`. For an unhandled rejection the error's
        context is the rejected promise itself, which never ran: this says who rejected it."""
        i = self.inits.get(aid)
        if i is None or i.type != "PROMISE":
            return None
        rs = [r for r in self.resolves.get(aid, []) if r.seq <= at]
        return rs[-1] if rs else None

    def release_chain(self, aid: int, at: int | None = None) -> tuple[list[tuple[int, Event, bool]], int]:
        """From a callback context back to what released it, through Node's internal reaction promises
        (adoption, Promise.all, events.once). Returns ([(reaction aid, resolve event, waited)], releaser aid),
        nearest first; the releaser is the first context that wasn't itself released (a timer, I/O, a handler).
        A hop that didn't wait (its promise had already settled) ends the chain: what settled it earlier didn't hold
        this callback back, and walking on would make an `await` loop quadratic."""
        hops, seen = [], set()
        while aid not in seen:
            seen.add(aid)
            hit = self.released(aid, at)
            if hit is None:
                break
            hops.append((aid, *hit))
            aid, at = hit[0].eid, hit[0].seq
            if not hit[1]:
                break
        return hops, aid

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
            up = next((user_frame(c.stack) for c in self.ancestors(creator(i)) if user_frame(c.stack)), None)
            frm = f" via {short_fn(up['fn'])}" if up and short_fn(up["fn"]) != "<anonymous>" else ""
        return f"{i.type}{name}{frm}"

    def user_hops(self, aid: int) -> list[tuple[Event, int]]:
        """user_chain() with consecutive identical hops (same type, callback and creation site, as an `await` in a
        loop gives) merged: [(nearest hop of the run, how many)]."""
        out: list[tuple[Event, int]] = []
        for i in self.user_chain(aid):
            if out and i.aid not in self.anchors and out[-1][0].aid not in self.anchors and \
                    (out[-1][0].type, out[-1][0].name, self.site(out[-1][0].aid)) == (i.type, i.name, self.site(i.aid)):
                out[-1] = (out[-1][0], out[-1][1] + 1)
            else:
                out.append((i, 1))
        return out

    def user_chain(self, aid: int) -> list[Event]:
        """Ancestry with frameless internal hops (fs open/stat/read, bare promises) collapsed,
        ending at the owning request's anchor when there is one."""
        out = []
        for i in self.chain(aid):
            if i.aid in self.anchors:
                return out + [i]
            if user_frame(i.stack):
                out.append(i)
        return out

    # ---- story -------------------------------------------------------------------
    @cached_property
    def story(self) -> list[Event]:
        return [e for e in self.events if e.kind in STORY_KINDS]

    @cached_property
    def errors(self) -> list[Event]:
        return [e for e in self.events if e.kind in ERROR_KINDS]

    @cached_property
    def effectful(self) -> set[int]:
        """aids whose own callback or descendants emitted a story event (DERIVED)."""
        out: set[int] = set()
        for e in self.story:
            if e.kind in ("run.start", "instrument", "read", "read.capped"):  # reading isn't an effect
                continue
            for i in self.chain(e.eid):
                if i.aid in out:
                    break
                out.add(i.aid)
        return out

    def callback_fires(self) -> list[Event]:
        """async.before events of resources created from user code: 'your callback ran here'."""
        return [e for e in self.events if e.kind == "async.before" and self.site(e.aid)]

    @cached_property
    def watch(self) -> list[str]:
        start = next((e for e in self.events if e.kind == "run.start"), None)
        return (start.data or {}).get("watch") or [] if start else []

    @cached_property
    def reads_recorded(self) -> bool:
        """Reads of watched names were instrumented (--watch, without REWIND_READS=0; recorders before F11: no)."""
        start = next((e for e in self.events if e.kind == "run.start"), None)
        return bool(start and (start.data or {}).get("reads"))

    @cached_property
    def cwd(self) -> str | None:
        start = next((e for e in self.events if e.kind == "run.start"), None)
        return (start.data or {}).get("cwd") if start else None

    def source_text(self, file: str) -> str | None:
        """The file as it was when the run was recorded. Snapshotted runs never read the disk: a file that changed
        before ingest, or was never snapshotted, has no text rather than the wrong text."""
        if self.sources is not None:
            return self.sources.get(file)
        try:  # legacy run ingested before snapshots: the current file is all there is
            return resolve_file(file, self.cwd).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def source_line(self, f: dict | None) -> str | None:
        text = self.source_text(f["file"]) if f else None
        try:
            return text.splitlines()[f["line"] - 1] if text is not None else None
        except IndexError:
            return None


# ---- tree ------------------------------------------------------------------------
@dataclass
class Node:
    aid: int
    init: Event | None
    children: list["Node"] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)  # story events emitted while this resource's callback ran
    hidden: int = 0                                     # collapsed frameless hops folded into this node
    released_by: tuple[int, Event] | None = None        # (releaser aid, settling resolve): only when that releaser
                                                        # belongs to another request, or to none
    repeat: int = 1                                     # identical nested resources merged into this one (a loop)


def interesting(e: Event) -> bool:
    return e.kind not in ("instrument", "run.start")


def build_tree(run: Run, root: int = 1, full: bool = False) -> tuple[Node, int]:
    """Async causality tree. Unless `full`, keeps only branches leading to story events and folds
    frameless internal hops into their nearest user-visible descendant. Returns (root, pruned_count).

    Parent = the execution that created the resource. A response is shown under the callback that called
    res.end() (http.end) when that callback belongs to the same request; otherwise it stays on the request.
    Unless `full`, a chain of identical resources (same type, callback and site, each the only child of the last,
    with nothing emitted on the way: an `await` in a loop) merges into one node with a `repeat` count.
    Built iteratively: such chains can be thousands deep."""
    pruned = 0
    moved: dict[int, list[Event]] = {}
    for r in run.requests.values():
        if r.end and r.outbound and r.end.eid != r.anchor and run.request_of(r.end.eid) == r.id:
            moved.setdefault(r.end.eid, []).append(r.outbound)
    gone = {e.seq for es in moved.values() for e in es}

    order, stack, seen = [], [root], set()
    while stack:  # preorder; reversed, every resource comes after all of its descendants
        aid = stack.pop()
        if aid in seen:
            continue
        seen.add(aid)
        order.append(aid)
        stack.extend(run.children.get(aid, []))
    built: dict[int, Node | None] = {}
    for aid in reversed(order):
        events = [e for e in run.emitted.get(aid, []) if interesting(e) and e.seq not in gone]
        node = Node(aid, run.inits.get(aid), events=sorted(events + moved.get(aid, []), key=lambda e: e.seq))
        if node.init and node.init.type == "PROMISE":
            hops, releaser = run.release_chain(aid)
            if hops and hops[0][2] and run.request_of(releaser) != run.request_of(aid):
                node.released_by = (releaser, hops[-1][1])
        node.children = [c for c in (built.pop(k, None) for k in run.children.get(aid, [])) if c]
        built[aid] = node if full or aid == root else _simplify(run, node)
        if built[aid] is None:
            pruned += 1
    return built[root], pruned


def _same_kind(run: Run, a: Node, b: Node) -> bool:
    return (a.init is not None and b.init is not None and a.init.type == b.init.type and a.init.name == b.init.name
            and run.site(a.aid) == run.site(b.aid) and a.released_by is None and b.released_by is None)


def _simplify(run: Run, node: Node) -> Node | None:
    """Prune a quiet leaf, fold a frameless hop into its only child, merge a repeat into its identical child."""
    quiet = not node.events and node.aid not in run.anchors
    if quiet and not node.children:
        return None
    if quiet and len(node.children) == 1:
        child = node.children[0]
        if node.init and not user_frame(node.init.stack):  # fold internal hop into its only child
            child.hidden += node.hidden + 1
            return child
        if _same_kind(run, node, child):
            child.repeat += node.repeat
            child.hidden += node.hidden
            return child
    return node


# ---- why -----------------------------------------------------------------------------
RACE_INFERENCE = ("likely root cause: a race on shared module-level state. Another request overwrote it between this "
                  "request's own write and its read, so this request computed with another request's data. "
                  "Fix: keep this state per request instead of in a module-level variable.")


@dataclass
class Investigation:
    target: Event
    findings: list[Finding]
    chain: list[Event]
    request: Request | None
    branch: list[Event]  # story events of the target's request (or causal chain), up to the target


def _req_label(run: Run, rid: int | None, aid: int) -> str:
    return f"request {run.requests[rid].label}" if rid else run.describe(aid)


def investigate(run: Run, target: Event) -> Investigation:
    """Explain `target` (an error, or any recorded event). Every statement is a graded Finding."""
    F: list[Finding] = []
    is_error = target.kind in ERROR_KINDS
    frame = user_frame(target.stack) if is_error else None
    if is_error:
        origin = (target.data or {}).get("origin")
        how = {"uncaughtException": "uncaught exception", "unhandledRejection": "unhandled promise rejection"}.get(origin, "logged error")
        F.append(Finding(OBSERVED, f"{(target.data or {}).get('error') or 'Error'}: {target.name}  ({how})", [target.seq]))
        if frame:
            F.append(Finding(OBSERVED, f"thrown in {short_fn(frame['fn'])} at {where(frame)}", [target.seq]))
    else:
        F.append(Finding(OBSERVED, f"{target.kind}: {target.name}", [target.seq]))

    ctx = target.eid
    chain = run.chain(ctx)
    if chain:
        what = "a rejected promise" if chain[0].type == "PROMISE" and is_error else f"the callback of {run.describe(ctx)}"
        site = run.site(ctx)  # a request anchor has no creation site in user code
        F.append(Finding(OBSERVED, f"ran inside {what}{', created at ' + where(site) if site else ''}", [chain[0].seq, target.seq]))
    hops = run.user_hops(ctx)
    if len(hops) > 1 or (hops and hops[0][1] > 1):
        path = " ← ".join((run.describe(h.aid) if h.aid in run.anchors else f"{run.describe(h.aid)} ({where(run.site(h.aid))})")
                          + (f" ×{n}" if n > 1 else "") for h, n in hops)
        F.append(Finding(DERIVED, f"causal chain: {path}", [h.seq for h, _ in hops]))

    rid = run.request_of(ctx)
    req = run.requests.get(rid) if rid else None
    if req:
        F.append(Finding(DERIVED, f"belongs to request {req.label}: its async ancestry reaches that request's handler", [req.inbound.seq]))
        branch = [e for e in run.story if e.seq <= target.seq and run.request_of(e.eid) == rid and e.kind not in ("instrument", "run.start")]
    else:
        on_chain = {h.aid for h in chain} | {ctx}
        branch = [e for e in run.story if e.seq <= target.seq and e.eid in on_chain and e.kind != "instrument"]
    F.extend(_attribution_findings(run, ctx, req))
    F.extend(_wait_findings(run, target, ctx, req))
    if target.kind in ("http.out", "http.end") and (target.data or {}).get("req") in run.requests:
        F.extend(response_findings(run, run.requests[target.data["req"]]))

    overlapping = []
    if req:
        for other in run.requests.values():
            if other.id == rid:
                continue
            # observable actions only: internal timers (e.g. http's date cache) are real but not informative
            acts = [e for e in run.story if req.inbound.seq < e.seq < target.seq and not e.kind.startswith("run.")
                    and run.request_of(e.eid) == other.id]
            if acts:
                overlapping.append(other)
                kinds = ", ".join(sorted({{"http.in": "arrived", "http.out": "responded", "log": "logged", "mutation": "wrote state", "read": "read state"}.get(a.kind, a.kind) for a in acts}))
                F.append(Finding(DERIVED, f"request {other.label} was active while {req.label} was in flight ({kinds})",
                                 [a.seq for a in acts]))

    line = run.source_line(frame) if frame else None
    names_on_line = set(re.findall(r"[A-Za-z_$][\w$]*", line)) if line else set()
    if run.watch:
        for name in run.watch:
            F.extend(_watched_findings(run, target, req, name, line if name in names_on_line else None))
        F.extend(_snapshot_findings(run, target))
    elif is_error and line:
        # Without --watch no mutation may be claimed: only point at module-level names on the failing line.
        top = _top_level_names(run, frame)
        suspects = sorted(n for n in names_on_line & top if not _is_function(run, frame, n))
        if suspects and overlapping:
            F.append(Finding(DERIVED, f"the failing line uses module-level binding(s) {', '.join('`' + x + '`' for x in suspects)}, "
                                      f"shared by every request:  {line.strip()}", [target.seq]))
            F.append(Finding(INFERRED, f"shared state suspected, but writes were not recorded. Re-record with "
                                       f"`--watch {','.join(suspects)}` to confirm who changed it.", [target.seq]))
    return Investigation(target, F, chain, req, branch)


def _attribution_findings(run: Run, ctx: int, req: Request | None) -> list[Finding]:
    """When trigger links alone point at another request, say so instead of silently picking one."""
    trig = run.trigger_request_of(ctx)
    if not req or trig in (None, req.id):
        return []
    i = run.inits.get(ctx)
    return [Finding(DERIVED, f"it continues a promise that request {run.requests[trig].label}'s code created, but "
                             f"{req.label}'s own code scheduled it (the await or then ran there), so it is "
                             f"attributed to {req.label}", [i.seq] if i else [])]


def _promise_name(run: Run, reaction: int) -> str:
    """The promise a reaction continues, by its creation site in user code when it has one."""
    p = run.inits[reaction].tid
    return f"the promise created at {where(run.site(p))}" if run.site(p) else "a promise created inside Node or a library"


def _in(run: Run, aid: int) -> str:
    """`Timeout work (app.js:12)`: a context and, when it has one, its creation site in user code."""
    site = run.site(aid)
    return f"{run.describe(aid)}{' (' + where(site) + ')' if site else ''}"


def _wait_findings(run: Run, target: Event, ctx: int, req: Request | None) -> list[Finding]:
    """What the target's callback waited on and who settled it (promise reactions only). For an unhandled
    rejection the context is the rejected promise, which never ran: then, who rejected it and from where."""
    F: list[Finding] = []
    hops, releaser = run.release_chain(ctx, target.seq)
    rejection = (target.kind == "error.uncaught" and (target.data or {}).get("origin") == "unhandledRejection"
                 and not run.fired.get(ctx))
    if rejection:
        rejected = run.settled_by(ctx, target.seq)
        if rejected is None:
            return []
        site = run.site(ctx)
        F.append(Finding(OBSERVED, f"the rejected promise{' (created at ' + where(site) + ')' if site else ''} was "
                                   f"settled at seq {rejected.seq} inside {_in(run, rejected.eid)}", [rejected.seq]))
        hops, releaser = run.release_chain(rejected.eid, rejected.seq)
        last = hops[-1][1] if hops else rejected
        if hops:
            F.append(Finding(OBSERVED, f"{_promise_name(run, hops[-1][0])} settled at seq {last.seq} inside "
                                       f"{_in(run, releaser)}", [last.seq]))
            F.append(Finding(DERIVED, f"so the rejection started in {run.describe(releaser)} and reached this promise "
                                      f"through {plural_(len(hops), 'promise hop')}",
                             [last.seq, *[h[1].seq for h in hops], rejected.seq]))
    else:
        if not hops:
            return []
        first_aid, first_res, waited = hops[0]
        cont = run.inits[first_aid]
        awaited = _promise_name(run, first_aid)
        if not waited:
            F.append(Finding(DERIVED, f"it awaited {awaited}, which had already settled (seq {first_res.seq}) before the "
                                      f"await (seq {cont.seq}): it did not wait on other work", [first_res.seq, cont.seq]))
            return F
        last_aid, last, _ = hops[-1]
        F.append(Finding(OBSERVED, f"{_promise_name(run, last_aid)} settled at seq {last.seq} inside {_in(run, releaser)}",
                         [last.seq]))
        ms = (run.fired[first_aid][0].t - cont.t) / 1000
        via = (f" ({awaited} settled through {plural_(len(hops) - 1, 'internal promise hop')} from it)"
               if len(hops) > 1 else "")
        F.append(Finding(DERIVED, f"so this callback ran only after that settlement: it awaited {awaited} from seq "
                                  f"{cont.seq} and resumed {ms:.1f} ms later{via}", [cont.seq, *[h[1].seq for h in hops]]))
    rr = run.request_of(releaser)
    if req and rr != req.id:
        owner = f"request {run.requests[rr].label}" if rr else "work outside any request"
        how = f"{req.label}'s rejection came from" if rejection else f"{req.label} waited on"
        F.append(Finding(DERIVED, f"the settling callback belongs to {owner}: {how} "
                                  f"{'work started by ' + owner if rr else owner}", [last.seq, req.inbound.seq]))
        if rr:
            hedge = ("this failure may come from that request's work rather than its own" if target.kind in ERROR_KINDS
                     else "a failure or delay there is inherited by it")
            F.append(Finding(INFERRED, f"{req.label} depends on request {run.requests[rr].label}'s shared in-flight work "
                                       f"(e.g. a cached or single-flight promise, a lock or an event): {hedge}",
                             [last.seq, target.seq]))
    return F


# ---- why a response was sent (F15) -----------------------------------------------------------
@dataclass
class Step:
    aid: int
    link: str            # how it follows the previous step: "start" (the request's arrival, first),
                         # "scheduled" (the previous step created it), "released" (it waited on a promise the previous
                         # step settled), "unlinked" (no recorded link: another request's arrival, a timer outside any
                         # request, or a gap in the recording)
    start: Event         # the async.before (or http.in) that started this step
    request: int | None
    arrival: bool = False


PATH_LIMIT = 10_000  # steps walked back from end(); a longer path starts "unlinked" rather than at the arrival


def response_path(run: Run, req: Request) -> list[Step]:
    """From the request's arrival to its res.end() call. Walking back from the end() context, the step before a
    callback is whoever settled the promise it waited on (when it waited) or else whoever created it. Derived from
    creation links and promise settlements. [] without an http.end event (recordings before F15)."""
    if req.end is None:
        return []
    back, aid, at, seen = [], req.end.eid, req.end.seq, set()
    while aid not in seen and len(back) < PATH_LIMIT:
        seen.add(aid)
        if aid in run.anchors:  # a request's arrival: this one's, or another request's
            other = run.requests[run.anchors[aid]]
            back.append(Step(aid, "start", other.inbound, other.id, arrival=True))
            break
        runs = [b for b in run.fired.get(aid, []) if b.seq <= at]
        i = run.inits.get(aid)
        if not runs or i is None:
            break
        hops, releaser = run.release_chain(aid, at)
        if hops and hops[0][2]:
            back.append(Step(aid, "released", runs[-1], run.request_of(aid)))
            aid, at = releaser, hops[-1][1].seq
        else:
            back.append(Step(aid, "scheduled", runs[-1], run.request_of(aid)))
            aid, at = creator(i), i.seq
    steps = back[::-1]
    if steps and not (steps[0].arrival and steps[0].request == req.id):
        steps[0].link = "unlinked"
        steps.insert(0, Step(req.anchor, "start", req.inbound, req.id, arrival=True))
    return steps


@dataclass
class PathEntry:
    """One line of a response path as shown: a step, or a run of internal steps folded into one."""
    link: str            # Step.link of its first step
    what: str            # "arrived", "request #6 GET /x arrived", "Timeout later", "3 internal steps"
    site: str | None     # creation site in user code
    request: int | None  # set when the step belongs to ANOTHER request than the one explained
    ms: float            # since the explained request arrived
    seqs: list[int]
    times: int = 1       # consecutive identical steps merged into this entry (e.g. an `await` in a loop)
    arrival: bool = False


ARROW = {"start": "", "scheduled": "→", "released": "⇠", "unlinked": "…"}


def path_entries(run: Run, req: Request, steps: list[Step]) -> list[PathEntry]:
    """Steps as shown: two or more consecutive internal steps (no frame from user code, reached by scheduling,
    neither first nor last) fold into one entry, and consecutive identical entries (same link, callback, site
    and request, as an `await` in a loop gives) merge into one with a count and the time of the last."""
    out: list[PathEntry] = []
    for e in _entries(run, req, steps):
        p = out[-1] if out else None
        if p and (p.link, p.what, p.site, p.request) == (e.link, e.what, e.site, e.request) and e.link != "start":
            p.times, p.ms, p.seqs = p.times + e.times, e.ms, p.seqs + e.seqs
        else:
            out.append(e)
    return out


def _entries(run: Run, req: Request, steps: list[Step]) -> list[PathEntry]:
    t0, out, k = req.inbound.t, [], 0
    internal = lambda j: (0 < j < len(steps) - 1 and not steps[j].arrival and steps[j].link == "scheduled"
                          and run.site(steps[j].aid) is None)
    while k < len(steps):
        j = k
        while internal(k) and internal(j + 1):
            j += 1
        s = steps[k]
        other = s.request if s.request not in (req.id, None) else None
        if j > k:
            out.append(PathEntry(s.link, f"{j - k + 1} internal steps", None, other, (steps[j].start.t - t0) / 1000,
                                 [x.start.seq for x in steps[k:j + 1]]))
        else:
            what = (("arrived" if s.request == req.id else f"request {run.requests[s.request].label} arrived")
                    if s.arrival else run.describe(s.aid))
            site = None if s.arrival else run.site(s.aid)
            out.append(PathEntry(s.link, what, where(site) if site else None, None if s.arrival else other,
                                 (s.start.t - t0) / 1000, [s.start.seq], arrival=s.arrival))
        k = j + 1
    return out


def response_findings(run: Run, req: Request) -> list[Finding]:
    """Who sent the response and the path to it (needs the http.end event; recordings before F15 lack it)."""
    F: list[Finding] = []
    end = req.end
    if end is None:
        if req.outbound is not None:
            F.append(Finding(DERIVED, "no res.end() call was recorded for this response (recorded before Rewind "
                                      "tracked it), so the callback that sent it is unknown", [req.outbound.seq]))
        return F
    f = user_frame(end.stack)
    who = run.describe(end.eid)
    if f:
        F.append(Finding(OBSERVED, f"res.end() was called in {who} at {where(f)}", [end.seq]))
    else:
        up = next((c for c in run.ancestors(end.eid) if user_frame(c.stack)), None)
        F.append(Finding(OBSERVED, f"res.end() was called by Node internals in {who}, with no frame from your code "
                                   f"(for example stream.pipe ending the response)", [end.seq]))
        if up:
            F.append(Finding(DERIVED, f"that internal work was started by {run.describe(up.aid)} at {where(run.site(up.aid))}",
                             [up.seq, end.seq]))
    er = run.request_of(end.eid)
    if er != req.id:
        owner, who_ended = ((f"request {run.requests[er].label}", "another request's code") if er else
                            ("code outside any request", "code outside any request"))
        F.append(Finding(DERIVED, f"that callback belongs to {owner}, not to {req.label}: {who_ended} ended "
                                  f"this response", [end.seq, req.inbound.seq]))
    steps = response_path(run, req)
    if len(steps) > 1:
        F.extend(_path_findings(run, req, steps, end))
    return F


def entry_text(e: PathEntry) -> str:
    return " ".join(x for x in (ARROW[e.link], e.what, e.site, f"×{e.times}" if e.times > 1 else None,
                                f"[request #{e.request}]" if e.request else None) if x)


def _path_findings(run: Run, req: Request, steps: list[Step], end: Event) -> list[Finding]:
    total = end.t - req.inbound.t
    parts = [f"{entry_text(e)} {e.ms:+.1f} ms" for e in path_entries(run, req, steps)]  # ms since this request arrived
    F = [Finding(DERIVED, f"path to the response (→ scheduled, ⇠ waited until settled, … no recorded link; ms since "
                          f"this request arrived): {'  '.join(parts)}  end() {total / 1000:+.1f} ms",
                 [s.start.seq for s in steps] + [end.seq])]
    others = sorted({s.request for s in steps if s.request not in (req.id, None)})
    if others:
        names = ", ".join(f"request {run.requests[o].label}" for o in others)
        F.append(Finding(DERIVED, f"the path runs through work of {names}: {req.label}'s response depended on it",
                         [s.start.seq for s in steps if s.request in others]))
    # only gaps inside this request's lifetime: steps of another request can start before it arrived
    gaps = [(b.start.t - a.start.t, a, b) for a, b in zip(steps, steps[1:])
            if a.start.t >= req.inbound.t and b.start.t >= a.start.t]
    dt, a, b = max(gaps, key=lambda g: g[0]) if gaps else (0, None, None)
    if total > 0 and dt / total >= 0.5:
        def name(s: Step) -> str:
            if s.arrival:
                return "the arrival" if s.request == req.id else f"the arrival of request {run.requests[s.request].label}"
            return _in(run, s.aid)
        F.append(Finding(DERIVED, f"most of the time ({dt / 1000:.1f} of {total / 1000:.1f} ms) passed between "
                                  f"{name(a)} and {name(b)}", [a.start.seq, b.start.seq]))
    return F


def _watched_findings(run: Run, target: Event, req: Request | None, name: str, failing_line: str | None) -> list[Finding]:
    F: list[Finding] = []
    writes = [e for e in run.events if e.kind == "mutation" and e.name == name and e.seq < target.seq]
    if failing_line:
        F.append(Finding(DERIVED, f"the failing line reads watched variable `{name}`:  {failing_line.strip()}", [target.seq]))
    rd = _relevant_read(run, target, req, name) if run.reads_recorded else None
    if rd is not None:
        d_ = rd.data or {}
        reader = f"request {req.label}" if req and run.request_of(rd.eid) == req.id else run.describe(rd.eid)
        F.append(Finding(OBSERVED, f"{reader} read `{name}` at {d_.get('loc')} (seq {rd.seq}), value {d_.get('value')}", [rd.seq]))
        prior = next((w for w in reversed(writes) if w.seq < rd.seq), None)
        if prior is not None and (prior.data or {}).get("path") == "" and prior.data.get("after") != d_.get("value"):
            F.append(Finding(DERIVED, f"that value differs from the last recorded write before it (seq {prior.seq}: "
                                      f"{prior.data.get('after')}), so `{name}` was changed in between by "
                                      f"{_unseen_write(run, name, rd.seq)}", [prior.seq, rd.seq]))
    if not writes:
        if failing_line:
            F.append(Finding(OBSERVED, f"no writes to `{name}` were recorded before this point", []))
        return F
    last = writes[-1]
    d = last.data or {}
    last_rid = run.request_of(last.eid)
    if failing_line or (req and last_rid and last_rid != req.id):
        F.append(Finding(OBSERVED, f"last write to `{name}` before this point: `{name}{d.get('path', '')}` {d.get('op')} at "
                                   f"{d.get('loc')}, new value {d.get('after')}", [last.seq]))
        F.append(Finding(DERIVED, f"that write was made by {_req_label(run, last_rid, last.eid)}", [last.seq]))
    if not req:
        return F
    own = [w for w in writes if run.request_of(w.eid) == req.id]
    since = own[-1].seq if own else req.inbound.seq
    foreign = [w for w in writes if w.seq > since and run.request_of(w.eid) not in (None, req.id)]
    if not foreign:
        return F
    by = sorted({run.request_of(w.eid) for w in foreign})
    who = ", ".join(f"#{b}" for b in by)
    if own:
        F.append(Finding(DERIVED, f"{req.label} set `{name}` itself (seq {own[-1].seq}); request {who} overwrote it "
                                  f"(seq {', '.join(str(w.seq) for w in foreign)}) before this point (seq {target.seq})",
                         [own[-1].seq, *[w.seq for w in foreign], target.seq]))
    else:
        F.append(Finding(DERIVED, f"request {who} wrote `{name}` while {req.label} was in flight", [w.seq for w in foreign]))
    if run.reads_recorded:  # F11: the read itself is evidence, so the race no longer rests on source text alone
        rd = _relevant_read(run, target, req, name)
        if rd is None:
            F.append(Finding(DERIVED, f"no read of `{name}` by {req.label} was recorded before this point, so these "
                                      f"overwrites aren't shown to have reached it (reads through an alias made earlier, "
                                      f"or in code --watch doesn't instrument, aren't seen)", [target.seq]))
            return F
        lastw = next((w for w in reversed(writes) if w.seq < rd.seq), None)
        lw_rid = run.request_of(lastw.eid) if lastw else None
        if lastw is None or lw_rid in (None, req.id):
            F.append(Finding(DERIVED, f"{req.label} read `{name}` (seq {rd.seq}) before request {who}'s overwrite reached "
                                      f"it: the last recorded write before that read was "
                                      f"{'its own' if lastw is not None else 'none'}, so the overwrite can't explain that read",
                             [rd.seq, *([lastw.seq] if lastw else []), foreign[0].seq]))
            return F
        F.append(Finding(DERIVED, f"{req.label} read `{name}` (seq {rd.seq}) after request #{lw_rid}'s write (seq {lastw.seq}), "
                                  f"with no write of its own in between: by the recorded writes, it read request "
                                  f"#{lw_rid}'s value", [*[w.seq for w in own[-1:]], lastw.seq, rd.seq]))
        at_failure = target.kind in ERROR_KINDS and (failing_line or rd.eid == target.eid)
        F.append(Finding(INFERRED, RACE_INFERENCE if at_failure else
                         f"likely a race between concurrent requests: {req.label} computed with request #{lw_rid}'s "
                         f"data instead of its own", [*[w.seq for w in own[-1:]], lastw.seq, rd.seq, target.seq]))
        return F
    if failing_line:
        F.append(Finding(INFERRED, RACE_INFERENCE, [*[w.seq for w in own[-1:]], last.seq, target.seq]))
    else:
        F.append(Finding(INFERRED, f"if {req.label} read `{name}` after seq {foreign[-1].seq}, it got request {who}'s data, not its own: "
                                   f"a likely race between concurrent requests. (Reads are not recorded, so this is not proven.)",
                         [*[w.seq for w in own[-1:]], foreign[-1].seq, target.seq]))
    return F


def _relevant_read(run: Run, target: Event, req: Request | None, name: str) -> Event | None:
    """The recorded read of `name` behind `target`: at the failing line in the same callback for an error, else the
    latest read in the same callback, else the latest read anywhere in the target's request."""
    reads = [e for e in run.events if e.kind == "read" and e.name == name and e.seq < target.seq]
    same = [e for e in reads if e.eid == target.eid]
    frame = user_frame(target.stack) if target.kind in ERROR_KINDS else None
    if frame:
        at = [e for e in same if str((e.data or {}).get("loc", "")).rsplit(":", 1)[0] == where(frame)]
        if at:
            return at[-1]
    if same:
        return same[-1]
    mine = [e for e in reads if req and run.request_of(e.eid) == req.id]
    return mine[-1] if mine else None


def _unseen_write(run: Run, name: str, upto: int) -> str:
    capped = any(e.kind == "mutation.capped" and e.name == name and e.seq < upto for e in run.events)
    return ("one of the writes past the recording cap, or a write --watch doesn't see" if capped else
            "a write --watch doesn't see (through an alias, inside a called function, or in node_modules)")


def snapshot_of(run: Run, error: Event) -> Event | None:
    """The watched-value snapshot the recorder took for this uncaught error (it carries the error's seq)."""
    return next((e for e in run.events if e.kind == "snapshot" and (e.data or {}).get("error") == error.seq), None)


def _snapshot_findings(run: Run, target: Event) -> list[Finding]:
    snap = snapshot_of(run, target) if target.kind == "error.uncaught" else None
    if snap is None:
        return []
    F: list[Finding] = []
    values = snap.data.get("values") or []
    dup = {v["name"] for v in values if sum(w["name"] == v["name"] for w in values) > 1}
    for v in values:
        name, value, file = v["name"], v.get("value"), v.get("file")
        label = f"`{name}`" + (f" in {file}" if name in dup else "")
        F.append(Finding(OBSERVED, f"{label} when the error was thrown: {value}", [snap.seq]))
        # Only a whole-variable write records the whole value, so only that can be compared with the snapshot.
        writes = [e for e in run.events if e.kind == "mutation" and e.name == name and e.seq < target.seq
                  and str((e.data or {}).get("loc", "")).rsplit(":", 2)[0] == file]
        last = writes[-1] if writes else None
        if last is not None and (last.data or {}).get("path") == "" and last.data.get("after") != value:
            F.append(Finding(DERIVED, f"{label} differs from the value recorded at its last write (seq {last.seq}: "
                                      f"{last.data.get('after')}), so it was changed after that by "
                                      f"{_unseen_write(run, name, target.seq)}",
                             [last.seq, snap.seq]))
    return F


_DECL = re.compile(r"^(?:let|var|const)\s+([A-Za-z_$][\w$]*)|^(?:let|var|const)\s*\{([^}]*)\}|^function\s+([A-Za-z_$][\w$]*)", re.M)


def _source(run: Run, frame) -> str:
    return run.source_text(frame["file"]) or ""


def _top_level_names(run: Run, frame) -> set[str]:
    # shortcut: column-0 declarations approximate "top level"; good for conventional formatting.
    names = set()
    for m in _DECL.finditer(_source(run, frame)):
        names.update(x.strip() for x in (m.group(2) or "").split(",") if x.strip())
        names.update(x for x in (m.group(1), m.group(3)) if x)
    return names


def _is_function(run: Run, frame, name: str) -> bool:
    return bool(re.search(rf"^function\s+{re.escape(name)}\b|^(?:const|let|var)\s+{re.escape(name)}\s*=\s*(?:require\(|\(|function|async)", _source(run, frame), re.M))


# ---- pending ---------------------------------------------------------------------------
# Resource types whose fate the recorder sees: callbacks fire (async.before), promises settle (async.resolve, which
# fires for rejections too), timers can be cleared (async.cancel). Other types (sockets, DNS, ...) aren't judged.
UNFINISHED = {"Timeout": "never ran", "Immediate": "never ran", "TickObject": "never ran",
              "FSREQCALLBACK": "never completed", "FSREQPROMISE": "never completed", "PROMISE": "never settled"}


@dataclass
class Pending:
    complete: bool                      # recording reached run.end or a flushed run.signal, with no torn lines
    states: dict[int, str]              # request id -> completed | failed | cancelled | unresolved
    ops: list[tuple[int | None, Event]]  # (request id or None, async.init) of unfinished operations from user code
    findings: list[Finding]


def plural_(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def recording_end(run: Run) -> tuple[bool, Event | None]:
    """(complete, last lifecycle event). Only run.end or run.signal flush every buffered event; without one (SIGKILL,
    power loss) or with torn lines, missing events prove nothing."""
    end = next((e for e in reversed(run.events) if e.kind in ("run.end", "run.signal")), None)
    return end is not None and not (run.meta.get("skipped_lines") or 0), end


def pending(run: Run) -> Pending:
    """What had not finished when the recording ended: requests without a response, and operations created from
    user code that never ran or settled. Absence is only evidence in a complete recording."""
    F: list[Finding] = []
    complete, end = recording_end(run)
    aborts = {e.data["req"]: e for e in run.events if e.kind == "http.abort"}
    fatal = next((e for e in run.events if e.kind == "error.uncaught"), None)
    code = (end.data or {}).get("code") if end is not None and end.kind == "run.end" else None
    if fatal is not None and code not in (None, 0):
        ended, reason = f"exited with code {code} after an uncaught error (seq {fatal.seq})", "the process exited after an uncaught error"
    elif end is not None and end.kind == "run.signal":
        ended, reason = f"stopped by {end.name}", f"it was still in flight when {end.name} arrived"
    elif end is not None:
        ended, reason = f"exited with code {code}", f"the process exited (code {code}) while it was in flight"
    else:
        ended, reason = "has no run.end", "the recording is incomplete, so a response may have been lost with it"
    if complete:
        F.append(Finding(OBSERVED, f"recording complete: the program {ended}", [end.seq]))
    else:
        last = run.events[-1].seq if run.events else 0
        why_ = "it has no run.end (killed or crashed hard)" if end is None else "torn lines were skipped at ingest"
        F.append(Finding(DERIVED, f"recording incomplete: {why_}. Events after seq {last} may be lost, so nothing is "
                                  f"reported as never finishing", [last] if run.events else []))

    states: dict[int, str] = {}
    for r in run.requests.values():
        if r.outbound:
            states[r.id] = "failed" if (r.outbound.data or {}).get("status", 0) >= 500 else "completed"
        elif r.id in aborts:
            states[r.id] = "cancelled"
        else:
            states[r.id] = "unresolved"
    counts = {s: sum(v == s for v in states.values()) for s in ("completed", "failed", "cancelled", "unresolved")}
    if states:
        F.append(Finding(DERIVED, f"{len(states)} request{'s' if len(states) != 1 else ''}: {counts['completed']} completed, "
                                  f"{counts['failed']} failed (5xx), {counts['cancelled']} cancelled by the client, "
                                  f"{counts['unresolved']} without a response", [r.inbound.seq for r in run.requests.values()]))
    for rid, st in states.items():
        r = run.requests[rid]
        if st == "failed":
            F.append(Finding(OBSERVED, f"request {r.label} responded {r.outbound.data.get('status')}", [r.outbound.seq]))
        elif st == "cancelled":
            a = aborts[rid]
            F.append(Finding(OBSERVED, f"request {r.label}: the connection closed {a.data.get('ms', 0):.0f} ms after it "
                                       f"arrived, before a response was sent (client gave up)", [a.seq]))
        elif st == "unresolved":
            F.append(Finding(DERIVED, f"request {r.label} arrived (seq {r.inbound.seq}) but no response was recorded: {reason}",
                             [r.inbound.seq] + ([end.seq] if end is not None else [])))
            if r.end is not None:  # the code did answer; the response just never finished going out
                F.append(Finding(OBSERVED, f"request {r.label}: res.end() was called at seq {r.end.seq} in "
                                           f"{_in(run, r.end.eid)}, but the response never finished", [r.end.seq]))

    ops: list[tuple[int | None, Event]] = []
    if complete:
        settled = {e.aid for e in run.events if e.kind in ("async.resolve", "async.cancel")}

        def fate(i: Event) -> str:
            if i.type != "Timeout" or (i.data or {}).get("delay") is None:
                return UNFINISHED[i.type]
            due = i.t / 1000 + i.data["delay"]  # ms since recorder start
            return "never ran" if end.t / 1000 >= due else f"was not due yet ({i.data['delay']} ms timer)"

        hidden = 0
        for aid, i in run.inits.items():
            if i.type in UNFINISHED and run.site(aid) and aid not in settled and (i.type == "PROMISE" or aid not in run.fired):
                rid = run.request_of(aid)
                if rid and states.get(rid) != "unresolved":
                    hidden += 1  # leftovers of a request that already finished (cleanup timers, Node's date cache)
                else:
                    ops.append((rid, i))
        grouped: dict[tuple, list[Event]] = {}
        for rid, i in ops:
            grouped.setdefault((rid, i.type, where(run.site(i.aid)), fate(i)), []).append(i)
        for (rid, typ, at, verb), inits in grouped.items():
            owner = f"request {run.requests[rid].label}" if rid else "outside any request"
            times = f" (×{len(inits)})" if len(inits) > 1 else ""
            F.append(Finding(DERIVED, f"{owner}: {run.describe(inits[0].aid)} created at {at} {verb} when the "
                                      f"recording ended{times}", [i.seq for i in inits]))
        if hidden:
            F.append(Finding(DERIVED, f"not listed: {plural_(hidden, 'unfinished operation')} under requests that already "
                                      f"responded or were cancelled", []))
        if fatal is None or code in (None, 0):  # after a crash, unfinished work is a consequence, not a stall
            for rid, st in states.items():
                if st != "unresolved":
                    continue
                r, mine = run.requests[rid], [i for orid, i in ops if orid == rid]
                if r.end is not None:
                    F.append(Finding(INFERRED, f"request {r.label} was answered by your code, but the program ended "
                                               f"before the response finished sending (it {ended})",
                                     [r.end.seq, end.seq]))
                elif mine:
                    i = max(mine, key=lambda x: x.seq)  # the most recent unfinished step is what it was waiting on
                    verb = fate(i)
                    head = "likely stalled" if not verb.startswith("was not due") else "likely still waiting"
                    F.append(Finding(INFERRED, f"request {r.label} {head}: it was waiting on {run.describe(i.aid)} "
                                               f"({where(run.site(i.aid))}), which {verb}",
                                     [r.inbound.seq, i.seq, end.seq]))
                else:
                    F.append(Finding(INFERRED, f"request {r.label} had no unfinished operation from your code when the "
                                               f"recording ended: its handler may have returned without sending a response "
                                               f"(e.g. a missing res.end())", [r.inbound.seq, end.seq]))
    return Pending(complete, states, ops, F)


# ---- state at a point (F14) -----------------------------------------------------------
@dataclass
class VarState:
    name: str
    file: str | None
    status: str                     # known | partial | unknown
    value: str | None               # latest whole value recorded at or before the point (None: unknown)
    basis: Event | None             # the write, read or snapshot that recorded it
    later: list[Event]              # property writes after `basis`: the whole value isn't reconstructable past them
    findings: list[Finding]


@dataclass
class StateAt:
    target: Event
    request: Request | None
    in_flight: list[Request]
    complete: bool
    vars: list[VarState]
    findings: list[Finding]


def _file_of(loc) -> str:
    return str(loc or "").rsplit(":", 2)[0]


def state_at(run: Run, seq: int) -> StateAt:
    """Each watched variable as far as recorded evidence shows at `seq`. Never merges: a value is the latest
    whole-value evidence (a whole-variable write, a read, an error snapshot), labelled with where it came from."""
    target = run.by_seq[seq]
    complete, _ = recording_end(run)
    F: list[Finding] = []
    if not complete:
        F.append(Finding(DERIVED, f"recording incomplete: it ends at seq {run.events[-1].seq}; everything up to seq {seq} "
                                  f"that was recorded is used, but later events may be lost", []))
    aborts = {e.data["req"]: e for e in run.events if e.kind == "http.abort"}
    in_flight = [r for r in run.requests.values() if r.inbound.seq <= seq
                 and not (r.outbound and r.outbound.seq <= seq) and not (r.id in aborts and aborts[r.id].seq <= seq)]

    whole: dict[tuple, list[tuple[Event, str, str]]] = {}   # key -> [(event, value, how)] in seq order
    partial: dict[tuple, list[Event]] = {}
    caps: dict[str, Event] = {}
    for e in run.events:
        if e.seq > seq:
            break
        d = e.data or {}
        if e.kind == "mutation":
            key = (e.name, _file_of(d.get("loc")))
            if d.get("path") == "":
                whole.setdefault(key, []).append((e, d.get("after"), "write"))
            else:
                partial.setdefault(key, []).append(e)
        elif e.kind == "read":
            whole.setdefault((e.name, _file_of(d.get("loc"))), []).append((e, d.get("value"), "read"))
        elif e.kind == "snapshot":
            for v in d.get("values") or []:
                whole.setdefault((v["name"], v.get("file")), []).append((e, v.get("value"), "snapshot"))
        elif e.kind == "mutation.capped":
            caps.setdefault(e.name, e)
    keys = sorted(set(whole) | set(partial), key=lambda k: (k[0], k[1] or ""))
    keys += [(n, None) for n in run.watch if not any(k[0] == n for k in keys)]

    out: list[VarState] = []
    for name, file in keys:
        ev, parts, VF = whole.get((name, file), []), partial.get((name, file), []), []
        basis, value, how = ev[-1] if ev else (None, None, None)
        later = [p for p in parts if basis is None or p.seq > basis.seq]
        cap = caps.get(name)
        if basis is not None:
            who = _req_label(run, run.request_of(basis.eid), basis.eid)
            at = (basis.data or {}).get("loc") or file
            what = {"write": f"written at seq {basis.seq} by {who} ({at})", "read": f"read at seq {basis.seq} by {who} ({at})",
                    "snapshot": f"captured at seq {basis.seq}, when the uncaught error (seq {basis.data.get('error')}) was thrown"}[how]
            VF.append(Finding(OBSERVED, what, [basis.seq]))
            if how != "write":  # which recorded write that value goes back to
                w = next((x for x, _, h in reversed(ev[:-1]) if h == "write"), None)
                if w is not None:
                    VF.append(Finding(DERIVED, f"the last recorded whole-value write before it: seq {w.seq} by "
                                               f"{_req_label(run, run.request_of(w.eid), w.eid)} ({(w.data or {}).get('loc')})",
                                      [w.seq, basis.seq]))
                else:
                    VF.append(Finding(DERIVED, f"no whole-value write of `{name}` was recorded before it", [basis.seq]))
            if basis.seq < seq:
                VF.append(Finding(DERIVED, f"latest recorded value, as of seq {basis.seq} ({plural_(seq - basis.seq, 'event')} "
                                           f"before seq {seq}); not proven to be the value at seq {seq}", [basis.seq]))
            prev = ev[-2] if len(ev) > 1 else None
            if prev and how != "write" and not any(prev[0].seq < p.seq < basis.seq for p in parts) and prev[1] != value:
                VF.append(Finding(DERIVED, f"differs from the previous recorded value (seq {prev[0].seq}: {prev[1]}), with no "
                                           f"recorded write in between: changed by {_unseen_write(run, name, basis.seq)}",
                                  [prev[0].seq, basis.seq]))
            if str(value or "").endswith("…"):
                VF.append(Finding(DERIVED, "the value preview is truncated at 200 characters", [basis.seq]))
        status = "known" if basis is not None else "unknown"
        if later:
            status = "partial"
            VF.append(Finding(DERIVED, f"the whole value is unknown after seq {later[0].seq}: {len(later)} later property "
                                       f"write{'s' if len(later) > 1 else ''} changed it, and only the changed part is recorded",
                              [p.seq for p in later]))
            for p in later:
                pd = p.data or {}
                VF.append(Finding(OBSERVED, f"seq {p.seq}: `{name}{pd.get('path', '')}` {pd.get('op')} {pd.get('after')}  "
                                            f"({pd.get('loc')}, {_req_label(run, run.request_of(p.eid), p.eid)})", [p.seq]))
        if cap is not None and (basis is None or basis.seq < cap.seq):
            status, value = "unknown", None
            VF.append(Finding(DERIVED, f"more than {cap.data.get('cap')} writes: writes after seq {cap.seq} weren't recorded, "
                                       f"and no read since then shows the value", [cap.seq]))
        if basis is None and not later:
            VF.append(Finding(DERIVED, f"no write, read or snapshot of `{name}` was recorded at or before seq {seq} "
                                       f"(the value from its declaration isn't recorded)", []))
        out.append(VarState(name, file, status, value if status != "unknown" else None, basis, later, VF))
    if not run.watch:
        F.append(Finding(DERIVED, "this run was recorded without --watch: no variable state exists. Re-record with "
                                  "`--watch <variable>` to inspect state", []))
    elif out:
        F.append(Finding(DERIVED, "values come only from recorded writes, reads and error snapshots. A write --watch "
                                  "doesn't see (through an alias, inside a called function, in node_modules) can change a "
                                  "variable without trace until the next read", []))
    req = run.requests.get(run.request_of(target.eid if not target.kind.startswith("async.") else target.aid) or -1)
    return StateAt(target, req, in_flight, complete, out, F)


# ---- diff ------------------------------------------------------------------------------
def tokens(run: Run, everything: bool = False, watched: set[str] | None = None) -> list[tuple[str, Event]]:
    """Run -> comparable tokens with ids and timings normalised away. By default callbacks that belong to no
    request (test harness, process plumbing) are left out so the diff is about the application."""
    out = []
    for e in sorted(run.story + run.callback_fires(), key=lambda e: e.seq):
        rid = run.request_of(e.eid if e.kind != "async.before" else e.aid)
        tag = f"#{rid} " if rid else ""
        if e.kind == "async.before":
            # only callbacks with an observable effect: internal timers (http date cache) fire nondeterministically
            if everything or (rid and e.aid in run.effectful):
                out.append((f"{tag}▸ {run.describe(e.aid)} @ {where(run.site(e.aid))}", e))
        elif e.kind == "mutation":
            if watched is not None and e.name not in watched:
                continue
            d = e.data or {}
            out.append((f"{tag}✎ {e.name}{d.get('path', '')} {d.get('op')} @ {d.get('loc')}", e))
        elif e.kind in ("http.in", "http.out", "log", "error.uncaught", "error.logged", "run.end"):
            label = e.name if e.kind != "run.end" else f"exit {(e.data or {}).get('code')}"
            out.append((f"{tag if e.kind != 'run.end' else ''}{e.kind} {label}", e))
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


def diff(a: Run, b: Run, everything: bool = False) -> DiffResult:
    import difflib
    from collections import Counter
    # writes are only comparable for variables watched in both runs
    common = set(a.watch) & set(b.watch)
    ta, tb = tokens(a, everything, common), tokens(b, everything, common)
    sm = difflib.SequenceMatcher(a=[t for t, _ in ta], b=[t for t, _ in tb], autojunk=False)
    ops = sm.get_opcodes()
    F: list[Finding] = []
    only = sorted(set(a.watch) ^ set(b.watch))
    if only:
        F.append(Finding(DERIVED, f"writes to {', '.join('`' + v + '`' for v in only)} left out: watched in only one run "
                                  f"(record both with the same --watch to compare them)", []))
    same = sum(i2 - i1 for tag, i1, i2, _, _ in ops if tag == "equal")
    F.append(Finding(DERIVED, f"{same} of {len(ta)} (A) / {len(tb)} (B) normalised steps line up", []))
    first = next((op for op in ops if op[0] != "equal"), None)
    if first is None:
        F.append(Finding(DERIVED, "no divergence: both runs took the same observable path", []))
        return DiffResult(ta, tb, ops, F)
    _, i1, i2, j1, j2 = first
    if i1:
        F.append(Finding(DERIVED, f"identical up to and including: {ta[i1 - 1][0]}", [ta[i1 - 1][1].seq], "A"))
    if i1 < len(ta):
        F.append(Finding(OBSERVED, f"next, A does: {ta[i1][0]}", [ta[i1][1].seq], "A"))
    if j1 < len(tb):
        F.append(Finding(OBSERVED, f"next, B does: {tb[j1][0]}", [tb[j1][1].seq], "B"))
    a_only = Counter(t for tag, x1, x2, _, _ in ops if tag != "equal" for t, _ in ta[x1:x2])
    b_only = Counter(t for tag, _, _, y1, y2 in ops if tag != "equal" for t, _ in tb[y1:y2])
    moved = a_only & b_only
    later = next((k for k in range(i1, len(ta)) if j1 < len(tb) and ta[k][0] == tb[j1][0]), None)
    if later is not None:
        F.append(Finding(DERIVED, f"that step also happens in A, but {later - i1} step(s) later: the interleaving changed, "
                                  f"not the code path", [ta[later][1].seq], "A"))
    if moved:
        F.append(Finding(DERIVED, f"{sum(moved.values())} step(s) occur in both runs at different positions (reordered)", []))
    gone, new = a_only - b_only, b_only - a_only
    if gone:
        F.append(Finding(DERIVED, f"{sum(gone.values())} step(s) only in A, e.g. {next(iter(gone))}",
                         [next(e.seq for t, e in ta if t == next(iter(gone)))], "A"))
    if new:
        F.append(Finding(DERIVED, f"{sum(new.values())} step(s) only in B, e.g. {next(iter(new))}",
                         [next(e.seq for t, e in tb if t == next(iter(new)))], "B"))
    ea, eb = a.errors, b.errors
    if bool(ea) != bool(eb):
        bad, good, err = ("A", "B", ea[0]) if ea else ("B", "A", eb[0])
        F.append(Finding(INFERRED, f"run {bad} fails and {good} does not. The first divergence above is the earliest observable "
                                   f"point where they part ways; it is the place to start, not necessarily the cause. "
                                   f"Run `rewind why` on {bad} for the causal story.", [err.seq], bad))
    return DiffResult(ta, tb, ops, F)

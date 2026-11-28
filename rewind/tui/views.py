"""Renderables for the TUI, built from the analysis engine's objects and render.py's markup helpers.

No debugging logic lives here: every fact comes from rewind.analysis (Run, investigate, pending, state_at, diff,
build_tree); this module only lays it out and words it for someone new to Rewind. Pure functions, testable without
a running app.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from rich.console import Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from .. import analysis as A
from .. import render as R
from . import theme as TH
from .theme import STYLES

# ---- vocabulary ---------------------------------------------------------------------------------
LEVEL_NAME = {A.OBSERVED: "observed", A.DERIVED: "derived", A.INFERRED: "inferred"}
LEVEL_MEANING = {A.OBSERVED: "recorded: an event Rewind saw, reported as-is",
                 A.DERIVED: "derived: computed from recorded events, with no guessing",
                 A.INFERRED: "inferred: Rewind's interpretation of the evidence, not proven"}
GROUPS = [(A.OBSERVED, "RECORDED", "what Rewind saw, reported as-is"),
          (A.DERIVED, "DERIVED", "computed from the recorded events"),
          (A.INFERRED, "INTERPRETATION", "Rewind's best explanation, not proven")]
STATUS_WORD = {"ok": "[ok]● ok[/]", "failed": "[err]× failed[/]", "crashed": "[warn]◌ incomplete[/]"}
STATUS = {"ok": "[ok]●[/]", "failed": "[err]×[/]", "crashed": "[warn]◌[/]"}
REQ_STATE = {"completed": "[ok]●[/]", "failed": "[err]×[/]", "cancelled": "[warn]−[/]", "unresolved": "[warn]◌[/]"}
REQ_LEGEND = "[ok]●[/] answered  [err]×[/] 5xx  [warn]◌[/] no response  [warn]−[/] client gave up"
VAR_STATUS = {"known": "[ok]known[/]", "partial": "[warn]partial[/]", "unknown": "[mute]unknown[/]"}
TIMELINE_LEGEND = ("[text2]→[/] request in  [text2]←[/] response  [text]»[/] log  [warn]✎[/] write  [r1]◌[/] read  "
                   "[err]×[/] error  [uv]◉[/] start/exit")

# Windows Terminal draws U+2716 ✖ from an emoji font (two cells, recoloured), which breaks alignment.
TUI_GLYPHS = str.maketrans({"✖": "×"})


def T(markup: str) -> Text:
    """CLI markup -> Text in the Ultraviolet palette (glyphs swapped when a classic console's font lacks them)."""
    markup = markup.translate(TUI_GLYPHS)
    if R.GLYPHS_MISSING:
        markup = markup.translate(R.GLYPH_TABLE)
    return R.rich_text(markup, STYLES)


def grid(*cols: dict) -> Table:
    g = Table.grid(padding=(0, 1), expand=True)
    for c in cols:
        g.add_column(**c)
    return g


def _two_col(left: Text, right: Text) -> Table:
    """A list row that never wraps: the left side gives way (ellipsis) so the right side stays whole."""
    g = Table.grid(expand=True)
    g.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    g.add_column(no_wrap=True, justify="right")
    g.add_row(left, right)
    return g


def command(row) -> str:
    return " ".join((json.loads(row["cmd"]) or []) if row["cmd"] else [])


# ---- brand --------------------------------------------------------------------------------------
def wordmark(width: int) -> Group:
    """The CLI's half-block REWIND wordmark, rows stepping through the violets (render._splash); compact below 50."""
    if width < 50:
        return Group(T("[uv.b]◂◂[/] [title]r e w i n d[/]"))
    rows = [T(f"[{tone}]{row}[/]") for row, tone in zip(R.WORDMARK, ("uv.hi", "uv", "uv.lo"))]
    return Group(*rows)


def topbar(*crumbs: str, right: str = "") -> Table:
    left = T("[uv.b]◂◂ rewind[/]" + "".join(f" [dim]›[/] {c}" for c in crumbs))
    return _two_col(left, T(right))


# ---- runs and requests --------------------------------------------------------------------------
def run_option(row, wide: bool = False) -> Table:
    label = f" [label]{escape(row['label'])}[/]" if row["label"] else ""
    errs = f"[err.t]{R.plural(row['error_count'], 'error')}[/]" if row["error_count"] else "[mute]no errors[/]"
    g = _two_col(T(f"{STATUS.get(row['status'], '·')} [id]{row['id']}[/]{label}"), T(errs if wide else
                 (f" [err.t]{row['error_count']} err[/]" if row["error_count"] else "")))
    sub = f"  [dim]{R.ago(row['started_at'])} · {row['event_count']:,} events"
    sub += f" · {escape(command(row))}[/]" if wide else "[/]"
    g.add_row(T(sub), Text(""))
    return g


def request_option(run: A.Run, req: A.Request, state: str) -> Table:
    out = req.outbound
    tail = (f"[{'err.t' if out.data.get('status', 0) >= 500 else 'mute'}]{out.data.get('status')}[/] "
            f"[dim]{out.data.get('ms', 0):.0f}ms[/]") if out else {"cancelled": "[warn]gave up[/]",
                                                                 "unresolved": "[warn]no response[/]"}.get(state, "")
    return _two_col(T(f"{REQ_STATE.get(state, '·')} {R.req_tag(req.id)} [bold]{escape(req.inbound.name)}[/]"), T(f" {tail}"))


# ---- timeline -----------------------------------------------------------------------------------
def timeline_cells(run: A.Run, e, width: int) -> tuple[Text, Text, Text, Text, Text]:
    seq, ms, _rail, req, glyph, text, ctx = R.event_row(run, e)
    body = T(text)
    if ctx:
        body.append("  ")
        body.append_text(T(ctx))
    if e.kind in A.ERROR_KINDS:
        body.stylize(STYLES["err.t"], 0, len(body.plain.split("  ")[0]))
    body.truncate(max(width, 10), overflow="ellipsis")
    return T(f"[dim]{seq}[/]"), T(f"[dim]{ms}[/]"), T(req), T(glyph), body


KIND_WORD = {"http.in": "request arrived", "http.end": "res.end() called", "http.out": "response sent",
             "http.abort": "client gave up", "log": "log line",
             "mutation": "write to a watched variable", "read": "read of a watched variable",
             "error.uncaught": "uncaught error", "error.logged": "logged error", "run.start": "program started",
             "run.end": "program exited", "run.signal": "stopped by a signal", "snapshot": "watched values at the error",
             "async.init": "async operation created", "async.before": "callback started",
             "async.after": "callback finished", "async.resolve": "promise settled", "async.cancel": "timer cleared",
             "instrument": "file instrumented for --watch", "source": "source file loaded",
             "mutation.capped": "write limit reached", "read.capped": "read limit reached"}


def event_detail(run: A.Run, e) -> Group:
    d = e.data or {}
    head = T(f"[{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] [title]{KIND_WORD.get(e.kind, e.kind)}[/]  "
             f"[dim]seq {e.seq} · {e.t / 1000:.1f} ms[/]")
    parts: list = [head, Text()] + ([] if e.kind in ("mutation", "read") else [T(R.event_text(run, e))])
    g = grid({"style": STYLES["text3"], "no_wrap": True, "width": 10}, {"ratio": 1, "overflow": "fold"})
    ctx_aid = e.aid if e.kind.startswith("async.") else e.eid
    rid = None if e.kind.startswith("run.") else run.request_of(ctx_aid)
    if rid:
        g.add_row("request", T(f"{R.req_tag(rid)} [bold]{escape(run.requests[rid].inbound.name)}[/]"))
    if not e.kind.startswith(("run.", "async.")) and e.kind not in ("http.in", "source"):
        g.add_row("ran in", T(escape(run.describe(e.eid))))
        site = run.site(e.eid)
        if site:
            g.add_row("scheduled", T(f"[loc]{escape(A.where(site))}[/] [dim]in[/] {escape(A.short_fn(site['fn']))}"))
    if e.kind.startswith("async.") and e.aid is not None:
        site = run.site(e.aid)
        g.add_row("operation", T(escape(run.describe(e.aid))))
        if site:
            g.add_row("created", T(f"[loc]{escape(A.where(site))}[/] [dim]in[/] {escape(A.short_fn(site['fn']))}"))
    frame = A.user_frame(e.stack)
    if frame:
        g.add_row("at", T(f"[loc]{escape(A.where(frame))}[/] [dim]in[/] [fn]{escape(A.short_fn(frame['fn']))}[/]"))
        src = run.source_line(frame)
        if src is not None:
            g.add_row("", T(f"[dim]{frame['line']:>4} │[/] {escape(src.strip())}"))
        elif run.sources is not None:
            g.add_row("", T("[mute]source not shown: the file changed before the recording was stored[/]"))
    for f in [f for f in (e.stack or []) if A.is_user_frame(f)][1:5]:
        g.add_row("", T(f"[dim]{escape(A.short_fn(f['fn']))}  {escape(A.where(f))}[/]"))
    if e.kind == "mutation":
        g.add_row("variable", T(f"[fn]{escape(e.name + d.get('path', ''))}[/] {escape(d.get('op', ''))}  [loc]{escape(d.get('loc', ''))}[/]"))
        g.add_row("before", Text(str(d.get("before")), style=STYLES["mute"]))
        g.add_row("after", Text(str(d.get("after")), style=STYLES["warn"]))
    elif e.kind == "read":
        g.add_row("variable", T(f"[fn]{escape(e.name or '')}[/]  [loc]{escape(d.get('loc', ''))}[/]"))
        g.add_row("value read", Text(str(d.get("value")), style=STYLES["kind.read"]))
    elif e.kind == "snapshot":
        for v in d.get("values", []):
            g.add_row(R.clip(v["name"], 10), Text(str(v.get("value"))))
    elif e.kind in ("http.out", "http.abort", "http.in"):
        for k in ("status", "ms", "method", "url"):
            if k in d:
                g.add_row(k, Text(f"{d[k]:.1f}" if k == "ms" else str(d[k])))
        end = run.requests[d["req"]].end if e.kind == "http.out" and d.get("req") in run.requests else None
        if end is not None:  # the response's own context is the request; http.end names the callback that sent it
            g.add_row("sent from", T(escape(run.describe(end.eid))))
    elif e.kind in A.ERROR_KINDS:
        g.add_row("how", Text({"uncaughtException": "uncaught exception", "unhandledRejection": "unhandled promise rejection"}
                              .get((d.get("origin") or ""), "logged with console.error")))
    parts += [Text(), g, Text(), T("[key]w[/] [text3]explain this event[/]   [key]s[/] [text3]variables at this point[/]")]
    return Group(*parts)


# ---- findings -----------------------------------------------------------------------------------
def finding_option(f: A.Finding) -> Text:
    t = T(f"{R.LEVEL[f.level]} ")
    style = {A.OBSERVED: "text", A.DERIVED: "text", A.INFERRED: "hyp"}[f.level]
    t.append_text(T(f"[{style}]{escape(f.text)}[/]"))
    if f.run:
        t.append(f"  run {f.run}", style=STYLES["dim"])
    return t


def group_header(level: str) -> Text:
    _, name, what = next(g for g in GROUPS if g[0] == level)
    return T(f"{R.LEVEL[level]} [eyebrow]{name}[/]  [dim]{what}[/]")


def finding_detail(run: A.Run | None, f: A.Finding, cursor: int | None) -> Group:
    parts: list = [T(f"{R.LEVEL[f.level]} [title]{LEVEL_NAME[f.level].upper()}[/]"),
                   T(f"[text3]{LEVEL_MEANING[f.level]}[/]"), Text(),
                   T(f"[{'hyp' if f.level == A.INFERRED else 'text'}]{escape(f.text)}[/]"), Text()]
    if not f.evidence:
        parts.append(T("[mute]no single events back this finding: it summarises the run[/]"))
        return Group(*parts)
    parts.append(T(f"[eyebrow]EVIDENCE[/]  [dim]{len(f.evidence)} recorded event{'s' if len(f.evidence) != 1 else ''}"
                   f"{' in run ' + f.run if f.run else ''}[/]"))
    g = grid({"no_wrap": True, "width": 1}, {"no_wrap": True, "justify": "right", "width": 5},
             {"ratio": 1, "overflow": "ellipsis", "no_wrap": True})
    for i, s in enumerate(f.evidence):
        e = run.by_seq.get(s) if run else None
        mark = T("[uv.b]▸[/]") if i == cursor else Text(" ")
        g.add_row(mark, T(f"[dim]{s}[/]"), T(f"[{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] {R.event_text(run, e)}")
                  if e else T("[err.t]missing from this recording[/]"))
    parts += [g, Text(), T("[key]enter[/] [text3]show it in the timeline[/]   [key]] [[/] [text3]next / previous[/]")]
    return Group(*parts)


def why_head(run: A.Run, inv: A.Investigation, position: str) -> Group:
    e = inv.target
    parts: list = [T(f"[eyebrow]EXPLAINING[/] [dim]{position}[/]" + (f"  [dim]·[/] {R.req_tag(inv.request.id)} "
                     f"[bold]{escape(inv.request.inbound.name)}[/]" if inv.request else ""))]
    if e.kind in A.ERROR_KINDS:
        d = e.data or {}
        parts.append(T(f"[err]× {escape(d.get('error') or 'Error')}[/]  [err.t]{escape(e.name or '')}[/]"))
        frame = A.user_frame(e.stack)
        if frame:
            src = run.source_line(frame)
            parts.append(T(f"  [loc]{escape(A.where(frame))}[/] [dim]in[/] [fn]{escape(A.short_fn(frame['fn']))}[/]"))
            if src:
                parts.append(T(f"  [dim]{frame['line']:>4} │[/] {escape(src.strip())}"))
    else:
        parts.append(T(f"[{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] {R.event_text(run, e)}"))
    return Group(*parts)


# ---- overview: what happened and where to look ---------------------------------------------------
@dataclass
class Item:
    id: str | None      # None: a heading or a line of information, not selectable
    prompt: object


def overview(run: A.Run, row, pend: A.Pending, why: A.Investigation | None) -> list[Item]:
    """Start-here summary. Selects from analysis results; asserts nothing the engine didn't."""
    items: list[Item] = []
    states = pend.states
    bad = [r for r in run.requests.values() if states.get(r.id) in ("failed", "unresolved", "cancelled")]
    items.append(Item(None, T("[eyebrow]WHAT HAPPENED[/]")))
    code = row["exit_code"]
    items.append(Item(None, T(f"  [text2]The program[/] {('[ok]exited normally[/]' if code == 0 else f'[err.t]exited with code {code}[/]') if row['status'] != 'crashed' else '[warn]was killed before the recording finished[/]'}"
                              f"[text2]; Rewind recorded {row['event_count']:,} events.[/]")))
    if run.requests:
        n = {s: sum(v == s for v in states.values()) for s in ("completed", "failed", "unresolved", "cancelled")}
        items.append(Item(None, T(f"  [text2]{R.plural(len(run.requests), 'HTTP request')}:[/] [ok]{n['completed']} answered[/]"
                                  + (f", [err.t]{n['failed']} failed[/]" if n["failed"] else "")
                                  + (f", [warn]{n['unresolved']} never answered[/]" if n["unresolved"] else "")
                                  + (f", [warn]{n['cancelled']} abandoned by the client[/]" if n["cancelled"] else ""))))
    else:
        items.append(Item(None, T("  [text2]No HTTP requests were recorded (the program isn't an http server, or got none).[/]")))
    if not run.watch:
        items.append(Item(None, T("  [dim]No variables were watched. Record again with watched variables to see who changed shared state.[/]")))
    if not pend.complete:
        items.append(Item(None, T("  [warn]◌ The recording is incomplete:[/] [text2]events after the last one may be lost.[/]")))

    look = [Item(f"err:{e.seq}", T(f"  [err]×[/] [err.t]{escape((e.data or {}).get('error') or 'Error')}: {escape(R.clip(e.name or '', 60))}[/]"
                                    + (f"  [dim]in[/] {R.req_tag(run.request_of(e.eid))}" if run.request_of(e.eid) else "")
                                    + "  [dim]→ explain[/]")) for e in run.errors[:5]]
    look += [Item(f"req:{r.id}", T(f"  {REQ_STATE[states[r.id]]} {R.req_tag(r.id)} [bold]{escape(r.inbound.name)}[/] "
                                   f"[dim]{ {'failed': 'failed', 'unresolved': 'never answered', 'cancelled': 'abandoned by the client'}[states[r.id]] } → its events[/]"))
             for r in bad[:6]]
    if look:
        items.append(Item(None, Text("")))
        items.append(Item(None, T("[eyebrow]LOOK HERE FIRST[/]")))
        items += look
    keys = []
    if why is not None:
        keys += [("why", i, f) for i, f in enumerate(why.findings) if f.level == A.INFERRED or
                 (f.level == A.DERIVED and ("read request" in f.text or "overwrote" in f.text))]
    keys += [("pending", i, f) for i, f in enumerate(pend.findings) if f.level == A.INFERRED]
    if keys:
        items.append(Item(None, Text("")))
        items.append(Item(None, T("[eyebrow]REWIND'S KEY FINDINGS[/]  [dim]enter shows the evidence behind each[/]")))
        items += [Item(f"find:{src}:{i}", finding_option(f)) for src, i, f in keys]
    items.append(Item(None, Text("")))
    items.append(Item(None, T("[eyebrow]NEXT[/]")))
    tips = []
    if run.errors:
        tips.append("[key]w[/] [text2]explains the first error step by step[/]")
    tips += ["[key]t[/] [text2]shows every event in order[/]", "[key]p[/] [text2]lists what never finished[/]"]
    if run.watch:
        tips.append("[key]s[/] [text2]shows watched variables at any point[/]")
    tips.append("[key]d[/] [text2]compares this run with another recording[/]")
    items += [Item(None, T("  " + t)) for t in tips]
    return items


# ---- state at a point ---------------------------------------------------------------------------
def state_view(run: A.Run, st: A.StateAt) -> Group:
    e = st.target
    parts: list = [T(f"[eyebrow]AT EVENT[/] [id]{e.seq}[/]  [{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] "
                     f"{R.event_text(run, e)}" + (f"  [dim]·[/] {R.req_tag(st.request.id)}" if st.request else ""))]
    if st.in_flight:
        parts.append(T("[text3]requests in progress[/]  " + "  ".join(f"{R.req_tag(r.id)} {escape(r.inbound.name)}" for r in st.in_flight)))
    for f in st.findings:
        parts.append(finding_option(f))
    for v in st.vars:
        parts.append(Text())
        parts.append(T(f"[fn]{escape(v.name)}[/]  {VAR_STATUS[v.status]}" + (f"  [dim]{escape(v.file)}[/]" if v.file else "")))
        if v.value is not None:
            parts.append(Text("  " + v.value, style=STYLES["warn"] if v.status == "partial" else STYLES["text"]))
        for f in v.findings:
            line = Text("  ")
            line.append_text(finding_option(f))
            parts.append(line)
    if not st.vars and not st.findings:
        parts.append(T("[mute]nothing recorded[/]"))
    return Group(*parts)


# ---- diff ---------------------------------------------------------------------------------------
def diff_view(res, a_title: str, b_title: str, context: int = 3) -> Group:
    parts: list = [T(f"[eyebrow]COMPARING[/]  [text3]A[/] {a_title}  [dim]with[/]  [text3]B[/] {b_title}"), Text()]
    first = res.first_divergence
    if first is None:
        parts.append(T("[ok]●[/] [text2]both runs took the same observable path[/]"))
        return Group(*parts)
    _, i1, i2, j1, j2 = first
    g = grid({"no_wrap": True, "width": 1}, {"no_wrap": True, "justify": "right", "width": 5}, {"ratio": 1, "no_wrap": True, "overflow": "ellipsis"})
    for t, e in res.a[max(0, i1 - context):i1]:
        g.add_row(" ", T(f"[dim]{e.seq}[/]"), T(f"[mute]{escape(t)}[/]"))
    g.add_row(" ", Text(""), T("[uv.b]▼ first point where they differ[/]"))
    for t, e in res.a[i1:min(i2, i1 + context) or i1 + 1]:
        g.add_row(T("[text3]A[/]"), T(f"[dim]{e.seq}[/]"), T(f"[text2]{escape(t)}[/]"))
    for t, e in res.b[j1:min(j2, j1 + context) or j1 + 1]:
        g.add_row(T("[uv.b]B[/]"), T(f"[dim]{e.seq}[/]"), T(f"[text]{escape(t)}[/]"))
    parts.append(g)
    return Group(*parts)


# ---- help ---------------------------------------------------------------------------------------
# (keys, what it does). Descriptions stay short enough to fit one line in the two-column layout.
HELP = {
    "Getting started": [(["n"], "record a program"), (["h"], "home: your recordings"), (["enter"], "open the selected item"),
                        (["?"], "this help")],
    "Recording": [(["enter"], "start, from the form"), (["ctrl+s"], "start recording"), (["esc"], "stop, or go back"),
                  (["enter"], "open the finished run")],
    "Navigation": [(["tab"], "next panel"), (["shift+tab"], "previous panel"), (["1–4"], "jump to a panel"),
                   (["↑", "↓"], "move in a list"), (["j", "k"], "move in a list"), (["g", "G"], "first / last row"),
                   (["<", ">"], "previous / next view")],
    "Investigation": [(["o"], "Overview: start here"), (["w"], "Explain the selected event"), (["t"], "Timeline: every event"),
                      (["p"], "Unfinished: never completed"), (["s"], "Variables at the selected event"),
                      (["e"], "Tree: who scheduled what"), (["d"], "Compare with another recording")],
    "Evidence": [(["enter"], "show a finding's evidence"), (["]"], "next evidence event"), (["["], "previous evidence event"),
                 (["b"], "use as the comparison run")],
    "General": [(["/"], "search the timeline"), (["f"], "filter the timeline by kind"), (["c"], "show callback starts"),
                (["a"], "show every recorded event"), (["esc"], "clear search and filters"), (["i"], "show or hide details"),
                (["\\"], "show or hide the sidebar"), (["r"], "reload recordings"), (["q"], "quit")],
}
HELP_COLUMNS = (["Getting started", "Navigation", "Evidence"], ["Recording", "Investigation", "General"])


def keycaps(keys: list[str]) -> Text:
    """Keys drawn as compact keycaps:  n  ,  ctrl+s ."""
    t = Text()
    for i, k in enumerate(keys):
        if i:
            t.append(" ")
        t.append(f" {k} ", style=STYLES["cap"])
    return t


def _help_section(names: list[str]) -> Table:
    g = Table.grid(padding=(0, 2), expand=True)
    g.add_column(no_wrap=True, width=11, justify="right")
    g.add_column(ratio=1, overflow="fold")
    for n, name in enumerate(names):
        if n:
            g.add_row("", "")
        g.add_row(Text(""), T(f"[eyebrow]{name.upper()}[/]"))
        for keys, what in HELP[name]:
            g.add_row(keycaps(keys), Text(what, style=STYLES["text2"]))
    return g


def help_content(two_columns: bool = True) -> Group:
    if two_columns:
        cols = Table.grid(padding=(0, 4), expand=True)
        cols.add_column(ratio=1)
        cols.add_column(ratio=1)
        cols.add_row(_help_section(HELP_COLUMNS[0]), _help_section(HELP_COLUMNS[1]))
        body = cols
    else:
        body = _help_section([n for col in zip(*HELP_COLUMNS) for n in col])
    legend = Table.grid(padding=(0, 2), expand=True)
    legend.add_column(no_wrap=True, width=11, justify="right")
    legend.add_column(ratio=1)
    legend.add_row(Text(""), T("[eyebrow]HOW SURE IS A FINDING?[/]"))
    for level, name, what in GROUPS:
        legend.add_row(T(f"{R.LEVEL[level]}"), T(f"[text]{name.capitalize()}[/]  [text3]{what}[/]"))
    return Group(body, Text(), legend)


def help_head() -> Table:
    return _two_col(T("[uv.b]◂◂[/] [title]Keyboard shortcuts[/]"), Text.assemble(keycaps(["esc"]), (" close", STYLES["text3"])))


def help_foot(scrolls: bool) -> Text:
    hint = "  [dim]·[/]  [text3]↓ scroll for more[/]" if scrolls else ""
    return T(f"[dim]press[/] [cap] esc [/] [dim]or[/] [cap] ? [/] [dim]to close[/]{hint}")

"""Renderables for the TUI, built from the analysis engine's objects and render.py's markup helpers.

No debugging logic lives here: every fact comes from rewind.analysis (Run, investigate, pending, state_at, diff,
build_tree); this module only lays it out. Pure functions, so they are testable without a running app.
"""
from __future__ import annotations

import json

from rich.console import Group
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from .. import analysis as A
from .. import render as R
from .theme import STYLES

LEVEL_NAME = {A.OBSERVED: "observed", A.DERIVED: "derived", A.INFERRED: "inferred"}
LEVEL_MEANING = {A.OBSERVED: "a recorded event, reported as-is",
                 A.DERIVED: "computed deterministically from recorded events",
                 A.INFERRED: "a heuristic explanation, citing the evidence below"}
STATUS = {"ok": "[ok]●[/]", "failed": "[err]✖[/]", "crashed": "[write]◌[/]"}
REQ_STATE = {"completed": "[ok]●[/]", "failed": "[err]✖[/]", "cancelled": "[write]−[/]", "unresolved": "[write]◌[/]"}
VAR_STATUS = {"known": "[ok]known[/]", "partial": "[write]partial[/]", "unknown": "[mute]unknown[/]"}


# Windows Terminal (and other terminals whose monospace font lacks it) draws U+2716 ✖ from an emoji font: two cells
# wide and recoloured, which breaks column alignment. A full-screen app needs every glyph one cell wide.
TUI_GLYPHS = str.maketrans({"✖": "×"})


def T(markup: str) -> Text:
    """CLI markup -> Text in the TUI palette (glyphs swapped when a classic console's font lacks them)."""
    markup = markup.translate(TUI_GLYPHS)
    if R.GLYPHS_MISSING:
        markup = markup.translate(R.GLYPH_TABLE)
    return R.rich_text(markup, STYLES)


def grid(*cols: dict) -> Table:
    g = Table.grid(padding=(0, 1), expand=True)
    for c in cols:
        g.add_column(**c)
    return g


# ---- runs and requests --------------------------------------------------------------------------
def _two_col(left: Text, right: Text) -> Table:
    """A list row that never wraps: the left side gives way (ellipsis) so the right side stays whole."""
    g = Table.grid(expand=True)
    g.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    g.add_column(no_wrap=True, justify="right")
    g.add_row(left, right)
    return g


def run_option(row) -> Table:
    label = f" [label]{escape(row['label'])}[/]" if row["label"] else ""
    errs = f" [err.t]{row['error_count']} err[/]" if row["error_count"] else ""
    g = _two_col(T(f"{STATUS.get(row['status'], '·')} [id]{row['id']}[/]{label}"), T(errs))
    g.add_row(T(f"  [dim]{R.ago(row['started_at'])} · {row['event_count']:,} events[/]"), Text(""))
    return g


def command(row) -> str:
    return " ".join((json.loads(row["cmd"]) or []) if row["cmd"] else [])


def request_option(run: A.Run, req: A.Request, state: str) -> Table:
    out = req.outbound
    tail = (f"[{'err.t' if out.data.get('status', 0) >= 500 else 'mute'}]{out.data.get('status')}[/] "
            f"[dim]{out.data.get('ms', 0):.0f}ms[/]") if out else {"cancelled": "[write]cancelled[/]",
                                                                 "unresolved": "[write]no reply[/]"}.get(state, "")
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


def event_detail(run: A.Run, e) -> Group:
    d = e.data or {}
    head = T(f"[{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] [title]{escape(e.kind)}[/]  "
             f"[mute]seq[/] [id]{e.seq}[/]  [mute]{e.t / 1000:.1f} ms[/]")
    parts: list = [head, Text()] + ([] if e.kind in ("mutation", "read") else [T(R.event_text(run, e))])
    g = grid({"style": STYLES["mute"], "no_wrap": True, "width": 9}, {"ratio": 1, "overflow": "fold"})
    ctx_aid = e.aid if e.kind.startswith("async.") else e.eid
    rid = None if e.kind.startswith("run.") else run.request_of(ctx_aid)
    if rid:
        g.add_row("request", T(f"{R.req_tag(rid)} [bold]{escape(run.requests[rid].inbound.name)}[/]"))
    if not e.kind.startswith(("run.", "async.")) and e.kind not in ("http.in", "source"):
        g.add_row("ran in", T(escape(run.describe(e.eid))))
        site = run.site(e.eid)
        if site:
            g.add_row("scheduled", T(f"[loc]{escape(A.where(site))}[/] [mute]in[/] {escape(A.short_fn(site['fn']))}"))
    if e.kind.startswith("async.") and e.aid is not None:
        site = run.site(e.aid)
        g.add_row("resource", T(escape(run.describe(e.aid))))
        if site:
            g.add_row("created", T(f"[loc]{escape(A.where(site))}[/] [mute]in[/] {escape(A.short_fn(site['fn']))}"))
    frame = A.user_frame(e.stack)
    if frame:
        g.add_row("at", T(f"[loc]{escape(A.where(frame))}[/] [mute]in[/] [fn]{escape(A.short_fn(frame['fn']))}[/]"))
        src = run.source_line(frame)
        if src is not None:
            g.add_row("", T(f"[dim]{frame['line']:>4} │[/] {escape(src.strip())}"))
        elif run.sources is not None:
            g.add_row("", T("[mute]source not available: the file changed before ingest, or wasn't snapshotted[/]"))
    for f in [f for f in (e.stack or []) if A.is_user_frame(f)][1:5]:
        g.add_row("", T(f"[dim]{escape(A.short_fn(f['fn']))}  {escape(A.where(f))}[/]"))
    if e.kind == "mutation":
        g.add_row("write", T(f"[fn]{escape(e.name + d.get('path', ''))}[/] {escape(d.get('op', ''))}  [loc]{escape(d.get('loc', ''))}[/]"))
        g.add_row("before", Text(str(d.get("before")), style=STYLES["mute"]))
        g.add_row("after", Text(str(d.get("after")), style=STYLES["write"]))
    elif e.kind == "read":
        g.add_row("read", T(f"[fn]{escape(e.name or '')}[/]  [loc]{escape(d.get('loc', ''))}[/]"))
        g.add_row("value", Text(str(d.get("value")), style=STYLES["kind.read"]))
    elif e.kind == "snapshot":
        for v in d.get("values", []):
            g.add_row(R.clip(v["name"], 9), Text(str(v.get("value"))))
    elif e.kind in ("http.out", "http.abort", "http.in"):
        for k in ("status", "ms", "method", "url"):
            if k in d:
                g.add_row(k, Text(f"{d[k]:.1f}" if k == "ms" else str(d[k])))
    elif e.kind in A.ERROR_KINDS:
        g.add_row("origin", Text(str(d.get("origin") or e.kind)))
    parts += [Text(), g, Text(), T("[dim]w[/] [mute]why this event[/]   [dim]s[/] [mute]state at this seq[/]")]
    return Group(*parts)


# ---- findings -----------------------------------------------------------------------------------
def finding_option(f: A.Finding) -> Text:
    t = T(f"{R.LEVEL[f.level]} ")
    body = T(f"[{R.LEVEL_TEXT[f.level]}]{escape(f.text)}[/]")
    t.append_text(body)
    if f.run:
        t.append(f"  run {f.run}", style=STYLES["dim"])
    return t


def finding_detail(run: A.Run | None, f: A.Finding, cursor: int | None) -> Group:
    parts: list = [T(f"{R.LEVEL[f.level]} [title]{LEVEL_NAME[f.level]}[/]  [mute]{LEVEL_MEANING[f.level]}[/]"), Text(),
                   T(f"[{R.LEVEL_TEXT[f.level]}]{escape(f.text)}[/]"), Text()]
    if not f.evidence:
        parts.append(T("[mute]no event seqs back this finding directly (it summarises the run)[/]"))
        return Group(*parts)
    parts.append(T(f"[mute]evidence[/] [dim]· {len(f.evidence)} event{'s' if len(f.evidence) != 1 else ''}"
                   f"{' in run ' + f.run if f.run else ''}[/]"))
    g = grid({"no_wrap": True, "width": 2}, {"no_wrap": True, "justify": "right", "width": 5}, {"ratio": 1, "overflow": "ellipsis", "no_wrap": True})
    for i, s in enumerate(f.evidence):
        e = run.by_seq.get(s) if run else None
        mark = T("[green]▸[/]") if i == cursor else Text(" ")
        g.add_row(mark, T(f"[id]{s}[/]"), T(f"[{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] {R.event_text(run, e)}")
                  if e else T("[err.t]missing from this recording[/]"))
    parts += [g, Text(), T("[dim]enter[/] [mute]jump to evidence[/]   [dim]] [[/] [mute]next / previous[/]")]
    return Group(*parts)


def why_head(run: A.Run, inv: A.Investigation, position: str) -> Group:
    e = inv.target
    parts: list = [T(f"[mute]why[/] [dim]·[/] [mute]{position}[/]" + (f"  [dim]·[/] {R.req_tag(inv.request.id)} "
                     f"[bold]{escape(inv.request.inbound.name)}[/]" if inv.request else ""))]
    if e.kind in A.ERROR_KINDS:
        d = e.data or {}
        parts.append(T(f"[err]✖ {escape(d.get('error') or 'Error')}[/]  [err.t]{escape(e.name or '')}[/]"))
        frame = A.user_frame(e.stack)
        if frame:
            src = run.source_line(frame)
            parts.append(T(f"  [loc]{escape(A.where(frame))}[/] [mute]in[/] [fn]{escape(A.short_fn(frame['fn']))}[/]"))
            if src:
                parts.append(T(f"  [dim]{frame['line']:>4} │[/] {escape(src.strip())}"))
    else:
        parts.append(T(f"[{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] {R.event_text(run, e)}"))
    parts.append(T("[obs]●[/] [mute]observed[/]  [uv]◆[/] [mute]derived[/]  [hyp]? inferred[/]"))
    return Group(*parts)


# ---- state at a point ---------------------------------------------------------------------------
def state_view(run: A.Run, st: A.StateAt) -> Group:
    e = st.target
    parts: list = [T(f"[mute]state at[/] [id]seq {e.seq}[/]  [{R.kind_style(e.kind)}]{R.GLYPH.get(e.kind, '·')}[/] "
                     f"{R.event_text(run, e)}" + (f"  [mute]·[/] {R.req_tag(st.request.id)}" if st.request else ""))]
    if st.in_flight:
        parts.append(T("[mute]in flight[/]  " + "  ".join(f"{R.req_tag(r.id)} {escape(r.inbound.name)}" for r in st.in_flight)))
    for f in st.findings:
        parts.append(finding_option(f))
    for v in st.vars:
        parts.append(Text())
        parts.append(T(f"[fn]{escape(v.name)}[/]  {VAR_STATUS[v.status]}" + (f"  [dim]{escape(v.file)}[/]" if v.file else "")))
        if v.value is not None:
            parts.append(Text("  " + v.value, style=STYLES["write"] if v.status == "partial" else ""))
        for f in v.findings:
            line = Text("  ")
            line.append_text(finding_option(f))
            parts.append(line)
    if not st.vars and not st.findings:
        parts.append(T("[mute]nothing recorded[/]"))
    return Group(*parts)


# ---- diff ---------------------------------------------------------------------------------------
def diff_view(res, a_title: str, b_title: str, context: int = 3) -> Group:
    parts: list = [T(f"[mute]A[/] {a_title}   [mute]B[/] {b_title}"), Text()]
    first = res.first_divergence
    if first is None:
        parts.append(T("[ok]●[/] both runs took the same observable path"))
        return Group(*parts)
    _, i1, i2, j1, j2 = first
    g = grid({"no_wrap": True, "width": 1}, {"no_wrap": True, "justify": "right", "width": 5}, {"ratio": 1, "no_wrap": True, "overflow": "ellipsis"})
    for t, e in res.a[max(0, i1 - context):i1]:
        g.add_row(" ", T(f"[dim]{e.seq}[/]"), T(f"[mute]{escape(t)}[/]"))
    g.add_row(" ", Text(""), T("[uv]▼ first divergence[/]"))
    for t, e in res.a[i1:min(i2, i1 + context) or i1 + 1]:
        g.add_row(T("[err.t]-[/]"), T(f"[dim]{e.seq}[/]"), T(f"[err.t]{escape(t)}[/]"))
    for t, e in res.b[j1:min(j2, j1 + context) or j1 + 1]:
        g.add_row(T("[ok]+[/]"), T(f"[dim]{e.seq}[/]"), T(f"[ok]{escape(t)}[/]"))
    parts.append(g)
    return Group(*parts)


# ---- chrome -------------------------------------------------------------------------------------
def header(row, run: A.Run | None, baseline: str | None, home: str) -> Text:
    t = T("[green]◂◂[/] [title]rewind[/]")
    if row is not None:
        label = f" [label]{escape(row['label'])}[/]" if row["label"] else ""
        status = {"ok": "[ok]● ok[/]", "failed": "[err.t]✖ failed[/]", "crashed": "[write]◌ incomplete[/]"}.get(row["status"], "")
        t.append_text(T(f"   [mute]run[/] [id]{row['id']}[/]{label}  {status}  [mute]{R.plural(row['event_count'], 'event')} · "
                        f"{R.plural(len(run.requests) if run else 0, 'request')} · {R.plural(row['error_count'], 'error')}[/]"))
        if run is not None and run.watch:
            t.append_text(T(f"  [mute]watch[/] [write]{escape(','.join(run.watch))}[/]"))
    if baseline:
        t.append_text(T(f"   [mute]baseline[/] [uv]{escape(baseline)}[/]"))
    t.append_text(T(f"   [dim]{escape(home)}[/]"))
    return t


def welcome(home: str) -> Group:
    return Group(
        T("[green]◂◂[/] [title]rewind[/]  [mute]postmortem debugging for Node.js[/]"), Text(),
        T(f"[mute]No recordings in[/] [loc]{escape(home)}[/] [mute]yet.[/]"), Text(),
        T("[mute]Record a run, then come back here:[/]"),
        T("  [green]rewind record[/] -l bad -w currentCart -- node demo/traffic.js"),
        T("  [green]rewind record[/] -l good -w currentCart -- node demo/traffic.js --sequential"), Text(),
        T("[dim]r[/] [mute]refresh[/]   [dim]?[/] [mute]help[/]   [dim]q[/] [mute]quit[/]"))


HELP = [
    ("Navigate", [("tab / shift+tab", "next / previous panel"), ("1 2 3 4", "runs · requests · main view · details"),
                  ("↑ ↓  j k", "move in a list"), ("enter", "open the selected run, request or finding"),
                  ("g / G", "first / last row")]),
    ("Views", [("t", "timeline"), ("w", "why: explain the selected event (or the first error)"),
               ("p", "pending: what never finished"), ("s", "state of watched variables at the selected seq"),
               ("e", "async tree"), ("d", "diff against the baseline run")]),
    ("Timeline", [("/", "search event text"), ("f", "cycle kind filter"), ("c", "toggle callback firings"),
                  ("a", "toggle every recorded event"), ("esc", "clear search and filters")]),
    ("Evidence", [("enter", "jump to the finding's first evidence event"), ("] [", "next / previous evidence event")]),
    ("Runs", [("b", "make the selected run the diff baseline"), ("r", "reload runs from disk")]),
    ("App", [("i", "show / hide details"), ("\\", "show / hide sidebar"), ("?", "this help"), ("q", "quit")]),
]


def _help_column(sections) -> Table:
    g = grid({"no_wrap": True, "width": 15, "style": STYLES["green"]}, {"ratio": 1})
    for n, (section, keys) in enumerate(sections):
        if n:
            g.add_row("", "")
        g.add_row(Text(section, style=STYLES["title"]), "")
        for k, what in keys:
            g.add_row(k, what)
    return g


def help_view() -> Group:
    cols = Table.grid(padding=(0, 4), expand=True)
    cols.add_column(ratio=1)
    cols.add_column(ratio=1)
    cols.add_row(_help_column(HELP[:3]), _help_column(HELP[3:]))
    return Group(T("[green]◂◂[/] [title]rewind[/]  [mute]keyboard[/]"), Text(), cols, Text(),
                 T("[obs]●[/] [mute]observed: a recorded event[/]   [uv]◆[/] [mute]derived: computed from events[/]   "
                   "[hyp]? inferred: a cited heuristic[/]"), Text(), T("[dim]esc or ? to close[/]"))

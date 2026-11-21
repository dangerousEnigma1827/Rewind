"""Terminal presentation. pacman/makepkg-flavoured: `::` section headers, `==>` steps, quiet greys, one accent."""
from __future__ import annotations

import json
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.theme import Theme

THEME = Theme({
    "hdr": "bold blue", "step": "bold green", "accent": "bold cyan", "dim": "grey50", "faint": "grey35",
    "ok": "green", "err": "bold red", "warn": "yellow", "id": "magenta", "loc": "cyan", "fn": "bold",
    "kind.log": "white", "kind.http": "blue", "kind.error": "bold red", "kind.mutation": "bold yellow",
    "kind.async": "grey50", "kind.run": "bold blue",
})
console = Console(theme=THEME, highlight=False)
STATUS = {"ok": "[ok]ok[/]", "failed": "[err]failed[/]", "crashed": "[warn]crashed[/]"}


def header(text: str):
    console.print(f"[hdr]::[/] [bold]{text}[/]")


def step(text: str):
    console.print(f"[step]==>[/] {text}")


def fail(text: str):
    console.print(f"[err]error:[/] {text}")


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def ago(iso: str | None) -> str:
    if not iso:
        return "?"
    s = (datetime.now() - datetime.fromisoformat(iso)).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= size:
            return f"{int(s // size)}{unit} ago"
    return f"{int(s)}s ago"


def run_summary(row: dict, secs: float):
    errs = row["error_count"]
    err = f"[err]{plural(errs, 'error')}[/]" if errs else "[ok]no errors[/]"
    label = f" [accent]{row['label']}[/]" if row.get("label") else ""
    console.print(f"[step]==>[/] recorded run [id]{row['id']}[/]{label}  {plural(row['event_count'], 'event')}  {err}  "
                  f"exit {row['exit_code']}  {STATUS[row['status']]}  [dim]({secs:.1f}s)[/]")
    if row.get("skipped_lines"):
        console.print(f"[warn]warning:[/] {row['skipped_lines']} torn line(s) skipped — process was killed mid-write")


def runs_table(rows):
    t = Table(box=None, expand=True, header_style="dim", pad_edge=False, padding=(0, 2))
    for c in ("run", "label", "status", "events", "errors", "exit", "when", "command"):
        t.add_column(c, justify="right" if c in ("events", "errors", "exit") else "left",
                     no_wrap=True, overflow="ellipsis", ratio=1 if c == "command" else None)
    for r in rows:
        cmd = " ".join(json.loads(r["cmd"]) or []) if r["cmd"] else ""
        t.add_row(f"[id]{r['id']}[/]", r["label"] or "[faint]-[/]", STATUS.get(r["status"], r["status"]),
                  f"{r['event_count']:,}", f"[err]{r['error_count']}[/]" if r["error_count"] else "[faint]0[/]",
                  str(r["exit_code"]), f"[dim]{ago(r['started_at'])}[/]", f"[dim]{cmd}[/]")
    console.print(t)


# ---- shared bits for analysis views -------------------------------------------------
from rich.markup import escape  # noqa: E402
from rich.tree import Tree  # noqa: E402

from . import analysis as A  # noqa: E402

REQ_COLORS = ["cyan", "magenta", "yellow", "green", "blue", "bright_red"]
GLYPH = {"run.start": "◉", "run.end": "◉", "run.signal": "◉", "http.in": "→", "http.out": "←", "log": "»",
         "error.uncaught": "✖", "error.logged": "✖", "mutation": "✎", "mutation.capped": "✎", "async.before": "▸",
         "instrument": "⚙"}
LEVEL = {A.OBSERVED: "[ok]●[/]", A.DERIVED: "[accent]◆[/]", A.INFERRED: "[warn]?[/]"}


def req_tag(rid):
    return f"[{REQ_COLORS[(rid - 1) % len(REQ_COLORS)]}]#{rid}[/]" if rid else "[faint]··[/]"


def clip(v, n: int = 48) -> str:
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def kind_style(kind: str) -> str:
    return {"http": "kind.http", "log": "kind.log", "error": "kind.error", "mutation": "kind.mutation",
            "async": "kind.async", "run": "kind.run"}.get(kind.split(".")[0], "white")


def event_text(run, e) -> str:
    d = e.data or {}
    if e.kind == "async.before":
        return f"{escape(run.describe(e.aid))} [dim]fired · scheduled at[/] [loc]{escape(A.where(run.site(e.aid)))}[/]"
    if e.kind == "async.init":
        return f"{escape(run.describe(e.aid))} [dim]created at[/] [loc]{escape(A.where(A.user_frame(e.stack)))}[/]"
    if e.kind in ("async.after", "async.resolve"):
        return f"[dim]{escape(run.describe(e.aid))}[/]"
    if e.kind == "mutation":
        return (f"[fn]{escape(e.name + d.get('path', ''))}[/] {escape(d.get('op', ''))} "
                f"[dim]{escape(clip(d.get('before')))} →[/] {escape(clip(d.get('after')))}  [loc]{escape(d.get('loc', ''))}[/]")
    if e.kind == "mutation.capped":
        return f"[warn]{escape(e.name)}: more than {d.get('cap')} writes, further writes counted only[/]"
    if e.kind == "http.out":
        st = d.get("status", 0)
        return f"[{'err' if st >= 500 else 'ok'}]{st}[/] {escape(e.name.split(' ', 1)[1])} [dim]{d.get('ms', 0):.1f}ms[/]"
    if e.kind in A.ERROR_KINDS:
        return f"[err]{escape(d.get('error') or '')}: {escape(e.name or '')}[/]  [loc]{escape(A.where(A.user_frame(e.stack)))}[/]"
    if e.kind == "run.start":
        return f"[dim]node {escape(' '.join(d.get('argv', [])))}  {d.get('node', '')}[/]"
    if e.kind == "run.end":
        return f"exit {d.get('code')}"
    if e.kind == "instrument":
        return (f"[dim]{escape(e.name)} {escape(str(d.get('file')))} ({plural(d.get('writes', 0), 'write site')}, "
                f"watch={','.join(d.get('watch', []))})[/]")
    return escape(e.name or "")


def context(run, e) -> str:
    if e.kind.startswith(("run.", "async.")) or e.kind in ("http.in", "http.out", "instrument"):
        return ""
    return f"[faint]in {escape(run.describe(e.eid))}[/]"


def timeline(run, rows, show_context=True):
    t = Table(box=None, expand=True, header_style="dim", pad_edge=False, padding=(0, 1))
    t.add_column("seq", justify="right", style="faint", no_wrap=True)
    t.add_column("ms", justify="right", style="dim", no_wrap=True)
    t.add_column("req", no_wrap=True)
    t.add_column("", no_wrap=True)
    t.add_column("event", ratio=3, overflow="fold")
    if show_context:
        t.add_column("context", ratio=1, overflow="ellipsis", no_wrap=True)
    for e in rows:
        rid = None if e.kind.startswith("run.") else run.request_of(e.aid if e.kind.startswith("async.") else e.eid)
        cells = [str(e.seq), f"{e.t / 1000:.1f}", req_tag(rid), f"[{kind_style(e.kind)}]{GLYPH.get(e.kind, '·')}[/]",
                 event_text(run, e)]
        if show_context:
            cells.append(context(run, e))
        t.add_row(*cells)
    console.print(t)


def tree(run, root, pruned: int, title: str):
    def label(n) -> str:
        if n.init is None:
            return f"[kind.run]◉[/] [bold]{escape(title)}[/]"
        rid = run.anchors.get(n.aid)
        hidden = f" [faint]+{n.hidden} internal[/]" if n.hidden else ""
        if rid:
            return f"{req_tag(rid)} [kind.http]{escape(run.requests[rid].inbound.name)}[/]{hidden}"
        site = run.site(n.aid)
        name = f" [fn]{escape(n.init.name)}[/]" if n.init.name and n.init.name != "<anonymous>" else ""
        where_ = f" [dim]at[/] [loc]{escape(A.where(site))}[/] [dim]in {escape(A.short_fn(site['fn']))}[/]" if site else ""
        ran = "" if run.fired.get(n.aid) else " [faint](never ran)[/]"
        err = " [err]✖[/]" if any(e.kind in A.ERROR_KINDS for e in n.events) else ""
        return f"[kind.async]{escape(n.init.type)}[/]{name}{where_}{hidden}{ran}{err}"

    def add(parent, n):
        for e in n.events:
            parent.add(f"[{kind_style(e.kind)}]{GLYPH.get(e.kind, '·')}[/] {event_text(run, e)}")
        for c in n.children:
            add(parent.add(label(c)), c)

    t = Tree(label(root), guide_style="faint")
    add(t, root)
    console.print(t)
    if pruned:
        console.print(f"[faint]{plural(pruned, 'quiet async resource')} with no observable effect hidden (--full shows all)[/]")



def findings(fs, evidence: bool):
    for f in fs:
        side = f"{f.run} " if f.run else ""
        ev = f"  [faint]{side}seq {', '.join(map(str, f.evidence))}[/]" if evidence and f.evidence else ""
        console.print(f"  {LEVEL[f.level]} {escape(f.text)}{ev}", soft_wrap=False)


def why(run, inv, title: str, evidence: bool, position: str):
    e = inv.target
    header(f"why · {title} · {position}")
    if e.kind in A.ERROR_KINDS:
        f = A.user_frame(e.stack)
        console.print(f"\n  [err]✖ {escape((e.data or {}).get('error') or 'Error')}: {escape(e.name or '')}[/]")
        if f:
            console.print(f"    [loc]{escape(A.where(f))}[/] [dim]in[/] [fn]{escape(A.short_fn(f['fn']))}[/]")
            src = run.source_line(f)
            if src:
                console.print(f"    [faint]{f['line']:>4} │[/] {escape(src.strip())}")
    else:
        console.print(f"\n  [{kind_style(e.kind)}]{GLYPH.get(e.kind, '·')}[/] {event_text(run, e)}")
    console.print()
    step("findings  [dim]([/][ok]●[/] [dim]observed  [/][accent]◆[/] [dim]derived  [/][warn]?[/] [dim]inferred)[/]")
    findings(inv.findings, evidence)
    hops = run.user_chain(e.eid)
    if hops:
        console.print()
        step("causal chain  [dim](innermost first)[/]")
        for i, h in enumerate(hops):
            arrow = "  " if i == 0 else "[faint]↑ [/]"
            if h.aid in run.anchors:
                console.print(f"  {arrow}{req_tag(run.anchors[h.aid])} [kind.http]{escape(run.requests[run.anchors[h.aid]].inbound.name)}[/]")
            else:
                site = run.site(h.aid)
                console.print(f"  {arrow}[kind.async]{escape(h.type)}[/]{' [fn]' + escape(h.name) + '[/]' if h.name and h.name != '<anonymous>' else ''}"
                              f"  [dim]scheduled in[/] {escape(A.short_fn(site['fn']))} [loc]{escape(A.where(site))}[/]")
    if inv.branch:
        console.print()
        req = inv.request
        step(f"story of {'request ' + req_tag(req.id) + ' ' + escape(req.inbound.name) if req else 'this causal branch'}"
             + ("  [dim]+ other requests' writes to watched variables[/]" if run.watch and req else ""))
        rows = list(inv.branch)
        if run.watch and req:
            rows += [m for m in run.events if m.kind == "mutation" and req.inbound.seq < m.seq < e.seq
                     and run.request_of(m.eid) not in (req.id,) and m.seq not in {r.seq for r in rows}]
        timeline(run, sorted(rows + ([e] if e not in rows else []), key=lambda x: x.seq), show_context=False)



def _diff_line(mark: str, style: str, tok: str, seq: int | None):
    seq_s = f"{seq:>5}" if seq is not None else "     "
    console.print(f"  [{style}]{mark}[/] [faint]{seq_s}[/]  [{style if mark != ' ' else 'dim'}]{escape(tok)}[/]", soft_wrap=False,
                  overflow="ellipsis", no_wrap=True)


def diff(res, title_a: str, title_b: str, evidence: bool, context: int = 2):
    header(f"diff · A = {title_a}  ·  B = {title_b}")
    console.print()
    step("findings  [dim]([/][ok]●[/] [dim]observed  [/][accent]◆[/] [dim]derived  [/][warn]?[/] [dim]inferred)[/]")
    findings(res.findings, evidence)
    console.print()
    step("aligned steps  [dim](seq is from A, or B for + lines; ids and timings normalised away)[/]")
    first = res.first_divergence
    for n, (tag, i1, i2, j1, j2) in enumerate(res.opcodes):
        if tag == "equal":
            rows = list(range(i1, i2))
            head = rows[:context] if n else []
            tail = rows[-context:] if n < len(res.opcodes) - 1 else []
            if len(rows) > len(head) + len(tail):
                for k in head:
                    _diff_line(" ", "dim", res.a[k][0], res.a[k][1].seq)
                console.print(f"  [faint]  ·····  {len(rows) - len(head) - len(tail)} identical steps[/]")
                for k in tail:
                    _diff_line(" ", "dim", res.a[k][0], res.a[k][1].seq)
            else:
                for k in rows:
                    _diff_line(" ", "dim", res.a[k][0], res.a[k][1].seq)
            continue
        if (tag, i1, i2, j1, j2) == first:
            console.print("  [warn]  ▼ first divergence[/]")
        for k in range(i1, i2):
            _diff_line("-", "red", res.a[k][0], res.a[k][1].seq)
        for k in range(j1, j2):
            _diff_line("+", "green", res.b[k][0], res.b[k][1].seq)

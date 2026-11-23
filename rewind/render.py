"""Terminal presentation: the Ultraviolet identity.

Forensic UV light reveals traces you can't otherwise see. One violet accent marks what Rewind *derived*
(and the wordmark); text stays in the terminal's own colour; one mid grey carries secondary detail; warm
red is reserved for errors. Certainty is brightness: observed findings are bold, derived ones carry the
violet ◆, inferred ones are dim italic.

Every colour is a mid-tone with roughly equal contrast on black and white, so the same palette works on
dark and light terminals (tests/test_render.py checks this). With colour off, glyphs and indentation
carry the structure.
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import nullcontext
from datetime import datetime

from rich.cells import cell_len
from rich.console import Console
from rich.markup import escape
from rich.padding import Padding
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from . import analysis as A

PALETTE = {"uv": "#7F5AF0", "uv.hi": "#8D6CFF", "uv.lo": "#6A48D8", "mute": "#7E7E8C", "err": "#E5484D",
           "ok": "#23905C", "write": "#A8741F", "r1": "#2C8C99", "r2": "#C0567A", "r3": "#7D8A2E", "r4": "#5A7FC0"}
P = PALETTE
THEME = Theme({
    "uv": P["uv"], "uv.b": f"bold {P['uv']}", "uv.hi": P["uv.hi"], "uv.lo": P["uv.lo"],
    "id": P["uv"], "mute": P["mute"], "hyp": f"italic {P['mute']}",
    "obs": "bold", "fn": "bold", "label": "bold", "loc": "none",
    "err": f"bold {P['err']}", "err.t": P["err"], "ok": P["ok"], "write": P["write"],
    "r1": P["r1"], "r2": P["r2"], "r3": P["r3"], "r4": P["r4"],
    "kind.log": "none", "kind.http": "none", "kind.error": f"bold {P['err']}", "kind.mutation": P["write"],
    "kind.async": P["mute"], "kind.run": P["uv"],
})
# Classic Windows consoles (conhost) can't fall back to another font, so a glyph missing from the console font
# prints as a box. Lucida Console (PowerShell 5.1's default) lacks ● ◆ ✖ ✎ ▸ ◉ ⚙ ◂ ┈ ┃ ◌; these one-cell
# stand-ins exist in Lucida Console, Consolas and Cascadia Mono (tests/test_render.py checks via GDI).
FALLBACK = {"◂": "◄", "●": "•", "◆": "♦", "✖": "×", "✎": "=", "▸": "►", "◉": "○", "⚙": "*", "┈": "·", "┃": "║", "◌": "○"}


def _font_has(face: str, glyphs: str) -> bool:
    import ctypes
    from ctypes import wintypes
    gdi, user = ctypes.windll.gdi32, ctypes.windll.user32
    gdi.CreateFontW.restype, user.GetDC.restype = wintypes.HFONT, wintypes.HDC
    gdi.SelectObject.argtypes, gdi.SelectObject.restype = [wintypes.HDC, wintypes.HGDIOBJ], wintypes.HGDIOBJ
    gdi.DeleteObject.argtypes, user.ReleaseDC.argtypes = [wintypes.HGDIOBJ], [wintypes.HWND, wintypes.HDC]
    gdi.GetGlyphIndicesW.argtypes = [wintypes.HDC, wintypes.LPCWSTR, ctypes.c_int, ctypes.POINTER(wintypes.WORD), wintypes.DWORD]
    hdc = user.GetDC(None)
    font = gdi.CreateFontW(16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, face)
    old = gdi.SelectObject(hdc, font)
    idx = (wintypes.WORD * len(glyphs))()
    gdi.GetGlyphIndicesW(hdc, glyphs, len(glyphs), idx, 1)  # GGI_MARK_NONEXISTING_GLYPHS: missing -> 0xFFFF
    gdi.SelectObject(hdc, old); gdi.DeleteObject(font); user.ReleaseDC(None, hdc)
    return all(i != 0xFFFF for i in idx)


def _console_font_lacks_glyphs(std_handle: int) -> bool:
    if os.name != "nt" or os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"):
        return False  # not Windows, or Windows Terminal / VS Code, which do font fallback
    try:
        import ctypes
        from ctypes import wintypes

        class FontInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.ULONG), ("nFont", wintypes.DWORD), ("dwFontSize", wintypes._COORD),
                        ("FontFamily", wintypes.UINT), ("FontWeight", wintypes.UINT), ("FaceName", wintypes.WCHAR * 32)]
        k32 = ctypes.windll.kernel32
        k32.GetStdHandle.restype = wintypes.HANDLE
        info = FontInfo(cbSize=ctypes.sizeof(FontInfo))
        if not k32.GetCurrentConsoleFontEx(k32.GetStdHandle(std_handle), False, ctypes.byref(info)):
            return False  # not a console: pipe or file, written as-is
        return not _font_has(info.FaceName, "".join(FALLBACK))
    except Exception:
        return False


class _GlyphSafe:
    """Writes through to the live sys stream, swapping glyphs the console font lacks for its stand-ins."""
    _table = str.maketrans(FALLBACK)

    def __init__(self, name: str):
        self._name = name

    def write(self, s: str):
        return getattr(sys, self._name).write(s.translate(self._table))

    def __getattr__(self, attr):
        return getattr(getattr(sys, self._name), attr)


def _make_console(stderr: bool) -> Console:
    safe = _console_font_lacks_glyphs(-12 if stderr else -11)
    return Console(theme=THEME, highlight=False, stderr=stderr, file=_GlyphSafe("stderr" if stderr else "stdout") if safe else None)


console = _make_console(stderr=False)
err_console = _make_console(stderr=True)

MARK = "[uv.b]◂◂[/]"
LEGEND = "[obs]●[/] [mute]observed[/]  [uv]◆[/] [mute]derived[/]  [hyp]? inferred[/]"
STATUS = {"ok": "[ok]● ok[/]", "failed": "[err.t]✖ failed[/]", "crashed": "[write]◌ crashed[/]"}
STATUS_WORD = {"ok": "[ok]ok[/]", "failed": "[err.t]failed[/]", "crashed": "[write]crashed[/]"}
STATUS_GLYPH = {"ok": "[ok]●[/]", "failed": "[err]✖[/]", "crashed": "[write]◌[/]"}


def width() -> int:
    return min(console.width, 110)


def title(cmd: str, subject: str = "", meta: str = ""):
    """Every analysis view opens with the same mark: ◂◂ command  subject  · meta"""
    console.print(f"  {MARK} [bold]{cmd}[/]" + (f"  {subject}" if subject else "") + (f"  [mute]· {meta}[/]" if meta else ""))


def section(name: str, right: str = ""):
    """A quiet labelled rule instead of a box: name ┈┈┈┈┈┈ right"""
    used = cell_len(Text.from_markup(name).plain) + (cell_len(Text.from_markup(right).plain) + 1 if right else 0)
    fill = max(width() - 6 - used, 3)
    console.print(f"  [bold]{name}[/] [mute]{'┈' * fill}[/]" + (f" {right}" if right else ""))


def fail(text: str):
    console.print(f"  [err]✖[/] [err.t]error:[/] {escape(text)}")


def working(msg: str):
    """Spinner for short internal work (ingest) on interactive terminals only; never while the program prints."""
    return console.status(f"[mute]{msg}[/]", spinner="point", spinner_style="uv") if console.is_terminal else nullcontext()


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


# ---- landing and help ---------------------------------------------------------------------------

GROUPS = (("capture", (("record", "-- node app.js", "run a program under the recorder"),
                       ("runs", "", "everything recorded here, newest first"))),
          ("inspect", (("timeline", "<run>", "what happened, in order"),
                       ("tree", "<run>", "who scheduled whom"))),
          ("explain", (("why", "<run>", "why an error (or any event) happened"),
                       ("diff", "<a> <b>", "where two executions part ways"))))


def _ref(row) -> str:
    return row["label"] or row["id"]


TAGLINE = "Postmortem debugging for asynchronous Node.js."
# The wordmark, as 6-pixel-tall bitmaps drawn with half blocks (3 terminal rows). Only █ ▀ ▄ are used:
# they exist in Lucida Console, Consolas and Cascadia Mono, so no console font shows boxes.
LETTERS = {
    "R": ["####.", "#...#", "####.", "#.#..", "#..#.", "#...#"],
    "E": ["#####", "#....", "####.", "#....", "#....", "#####"],
    "W": ["#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"],
    "I": ["###", ".#.", ".#.", ".#.", ".#.", "###"],
    "N": ["#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#"],
    "D": ["####.", "#...#", "#...#", "#...#", "#...#", "####."],
}


def _wordmark(word: str = "REWIND", gap: int = 2) -> list[str]:
    px = [(" " * gap).join(LETTERS[c][r] for c in word).replace(" ", ".") for r in range(6)]
    cell = {("#", "#"): "█", ("#", "."): "▀", (".", "#"): "▄"}
    return ["".join(cell.get(p, " ") for p in zip(top, bot)) for top, bot in zip(px[0::2], px[1::2])]


WORDMARK = _wordmark()          # 38 cells
WORDMARK_TIGHT = _wordmark(gap=1)  # 33 cells, for 45-47 column terminals


def _splash(version: str):
    """The product name first. Wordmark rows step from light to deep violet (UV light from above); the version
    sits on its baseline, and the ruler's ◆, the version and the tagline all end in the same column."""
    room = width() - 2
    columns = console.width + console.legacy_windows  # the terminal's real width: Rich keeps one column free in legacy mode
    fits = [m for m in (WORDMARK, WORDMARK_TIGHT) if len(m[0]) + 2 + len(version) <= room] if columns >= 45 else []
    mark = fits[0] if fits else None
    span = min(max(len(mark[0]) + 2 + len(version) if mark else 0, len(TAGLINE)), room)
    console.print()
    if mark:
        for i, (row, tone) in enumerate(zip(mark, ("uv.hi", "uv", "uv.lo"))):
            tail = f"{' ' * (span - len(row) - len(version))}[mute]{version}[/]" if i == 2 else ""
            console.print(f"  [{tone}]{row}[/]{tail}")
    else:  # below 45 columns: the compact mark, nothing wraps
        console.print(f"  [uv.b]◂◂[/] [bold]r e w i n d[/]  [mute]{version}[/]")
    console.print("  [mute]" + "".join("┼" if i % 8 == 7 else "─" for i in range(span - 1)) + "[/][uv]◆[/]")
    console.print(Padding(Text(TAGLINE, style="mute"), (0, 0, 0, 2)))  # wraps with its indent when narrow
    console.print()


def landing(rows: list, home: str, version: str):
    """`rewind` with no command: the wordmark, what is recorded here, the workflows, and a next step."""
    _splash(version)

    def block(*lines, last=False):  # every block shares one 8-cell label column, so content always starts at the same place
        g = Table.grid(padding=(0, 3))
        g.add_column(style="mute", no_wrap=True, width=8)
        g.add_column(overflow="fold")
        for label_, content in lines:
            g.add_row(label_, content)
        console.print(Padding(g, (0, 0, 0, 2)))
        if not last:  # no trailing blank: at 80x24 the whole screen, prompt included, stays in view
            console.print()

    if rows:
        last = rows[0]
        errs = f"[err.t]{plural(last['error_count'], 'error')}[/]" if last["error_count"] else "[mute]no errors[/]"
        label = f" [label]{escape(last['label'])}[/]" if last["label"] else ""
        block(("here", f"[bold]{plural(len(rows), 'run')}[/]  [mute]latest[/] [id]{last['id']}[/]{label}  "
                       f"{STATUS[last['status']]} [mute]·[/] {errs} [mute]· {ago(last['started_at'])}[/]"),
              ("", f"[mute]{escape(home)}[/]"))
    else:
        block(("here", "[mute]no runs recorded yet[/]"), ("", f"[mute]{escape(home)}[/]"))

    wide = width() >= 64  # narrower: each description goes under its command instead of in a squeezed column
    g = Table.grid(padding=(0, 3))
    g.add_column(style="mute", no_wrap=True, width=8)
    if wide:
        g.add_column(style="bold", no_wrap=True, width=8)
        g.add_column(style="mute", no_wrap=True, width=14)
    g.add_column(style="mute", overflow="fold")
    for name, cmds in GROUPS:
        for i, (cmd, args, desc) in enumerate(cmds):
            label_ = name if i == 0 else ""
            if wide:
                g.add_row(label_, cmd, escape(args), desc)
            else:
                g.add_row(label_, f"[bold]{cmd}[/] {escape(args)}\n{desc}")
        g.add_row(*[""] * len(g.columns))
    console.print(Padding(g, (0, 0, 0, 2)))

    if not rows:
        nxt, why = "rewind record -- node app.js", "record your first run"
    elif rows[0]["status"] == "ok":
        nxt, why = f"rewind timeline {_ref(rows[0])}", "see what the latest run did"
    else:
        nxt, why = f"rewind why {_ref(rows[0])}", f"the latest run {rows[0]['status']}"
    block(("evidence", LEGEND))
    block(("next", f"[bold]{escape(nxt)}[/]   [mute]{why}[/]"), ("", "[mute]rewind <command> --help for every option[/]"), last=True)


def command_help(cmd, ctx):
    """Per-command help in the same visual language as the views (replaces Typer's boxed panels)."""
    from typer.core import TyperArgument
    console.print()
    console.print(f"  {MARK} [bold]{escape(ctx.command_path)}[/] [mute]{escape(' '.join(cmd.collect_usage_pieces(ctx)))}[/]")
    if cmd.help:
        console.print()
        console.print(Padding(cmd.help.strip(), (0, 0, 0, 5)))
    params = [p for p in cmd.get_params(ctx) if not getattr(p, "hidden", False)]
    for name, group in (("arguments", [p for p in params if isinstance(p, TyperArgument)]),
                        ("options", [p for p in params if not isinstance(p, TyperArgument)])):
        if not group:
            continue
        console.print()
        section(name)
        g = Table.grid(padding=(0, 3))
        g.add_column(style="bold", no_wrap=True)
        g.add_column(overflow="fold")
        for p in group:
            if isinstance(p, TyperArgument):
                names = p.name + ("" if p.required else " [mute](optional)[/]")
            else:
                opts = sorted(p.opts + p.secondary_opts, key=len)
                is_int = getattr(getattr(p, "type_descriptor", None), "annotation", None) is int
                names = ", ".join(opts) + ("" if p.is_flag else f" [mute]{'N' if is_int else 'TEXT'}[/]")
            default = p.default if not getattr(p, "is_flag", False) and p.default not in (None, "") and not p.required else None
            g.add_row(names, escape(p.help or "") + (f"  [mute]default {default}[/]" if default is not None else ""))
        console.print(Padding(g, (0, 0, 0, 4)))
    console.print()


def usage_error(e):
    """Replaces Typer's boxed error panel: same information (message, usage, where to get help), on stderr."""
    if e.__class__.__name__ == "NoArgsIsHelpError":  # the landing screen was already printed
        return
    err_console.print(f"  [err]✖[/] [err.t]error:[/] {escape(e.format_message())}")
    ctx = getattr(e, "ctx", None)
    if ctx is not None:
        err_console.print(f"    [mute]usage[/]  {escape(ctx.get_usage().removeprefix('Usage: '))}")
        err_console.print(f"    [mute]help[/]   {escape(ctx.command_path)} --help")


# ---- record and runs ----------------------------------------------------------------------------

def recording(run_id: str, cmd: str, watch: str | None):
    console.print(f"  {MARK} [bold]recording[/] [id]{run_id}[/]  [mute]{escape(cmd)}[/]"
                  + (f"  [mute]watch=[/][bold]{escape(watch)}[/]" if watch else ""))


def run_summary(row: dict, secs: float):
    errs = row["error_count"]
    err = f"[err.t]{plural(errs, 'error')}[/]" if errs else "[ok]no errors[/]"
    label = f" [label]{escape(row['label'])}[/]" if row.get("label") else ""
    console.print(f"  {STATUS_GLYPH[row['status']]} recorded run [id]{row['id']}[/]{label}  "
                  f"[mute]{plural(row['event_count'], 'event')} ·[/] {err} [mute]· exit {row['exit_code']} ·[/] "
                  f"{STATUS_WORD[row['status']]}  [mute]{secs:.1f}s[/]")
    if row.get("skipped_lines"):
        console.print(f"  [write]![/] warning: {row['skipped_lines']} torn line(s) skipped — process was killed mid-write")


def runs_table(rows, home: str):
    title("runs", f"[bold]{plural(len(rows), 'run')}[/]", "newest first")
    console.print(f"     [mute]{escape(home)}[/]")
    console.print()
    cols = ("run", "label", "status", "events", "errors", "exit", "when", "command")
    cells = []
    for r in rows:
        cmd = " ".join(json.loads(r["cmd"]) or []) if r["cmd"] else ""
        cells.append((f"[id]{r['id']}[/]", f"[label]{escape(r['label'])}[/]" if r["label"] else "[mute]-[/]",
                      STATUS.get(r["status"], r["status"]), f"{r['event_count']:,}",
                      f"[err.t]{r['error_count']}[/]" if r["error_count"] else "[mute]0[/]",
                      str(r["exit_code"]), f"[mute]{ago(r['started_at'])}[/]", f"[mute]{escape(cmd)}[/]"))
    nat = [max(cell_len(Text.from_markup(x).plain) for x in (c, *(row[i] for row in cells))) for i, c in enumerate(cols)]
    # Every column but command must fit whole, or ids and labels get cut to "ff2e5…"; narrower: keep the essentials.
    wide = sum(nat[:-1]) + 4 * (len(cols) - 1) + 2 + 1 <= console.width  # 4-cell gaps, indent, a 1-cell "…" command
    keep = range(len(cols)) if wide else (0, 1, 2, 4)  # run, label, status, errors
    # compact: the label gives way (to at most 20 cells, less if the line is short) so ids, status and errors stay whole
    label_max = None if wide else max(1, min(20, console.width - 2 - nat[0] - nat[2] - nat[4] - 2 * 3))
    t = Table(box=None, expand=wide, header_style="mute", pad_edge=False, padding=(0, 2 if wide else 1))
    for i in keep:
        c = cols[i]
        t.add_column(c, justify="right" if c in ("events", "errors", "exit") else "left",
                     no_wrap=True, overflow="ellipsis", ratio=1 if c == "command" else None,
                     max_width=label_max if c == "label" else None)
    for row in cells:
        t.add_row(*(row[i] for i in keep))
    console.print(Padding(t, (0, 0, 0, 2)))


# ---- shared bits for analysis views -------------------------------------------------------------

REQ_TONES = ["r1", "r2", "r3", "r4"]
GLYPH = {"run.start": "◉", "run.end": "◉", "run.signal": "◉", "http.in": "→", "http.out": "←", "log": "»",
         "error.uncaught": "✖", "error.logged": "✖", "mutation": "✎", "mutation.capped": "✎", "async.before": "▸",
         "instrument": "⚙"}
LEVEL = {A.OBSERVED: "[obs]●[/]", A.DERIVED: "[uv]◆[/]", A.INFERRED: "[hyp]?[/]"}
LEVEL_TEXT = {A.OBSERVED: "obs", A.DERIVED: "none", A.INFERRED: "hyp"}


def req_tag(rid):
    return f"[{REQ_TONES[(rid - 1) % len(REQ_TONES)]}]#{rid}[/]" if rid else "[mute]··[/]"


def clip(v, n: int = 48) -> str:
    s = str(v)
    return s if len(s) <= n else s[: n - 1] + "…"


def kind_style(kind: str) -> str:
    return {"http": "kind.http", "log": "kind.log", "error": "kind.error", "mutation": "kind.mutation",
            "async": "kind.async", "run": "kind.run"}.get(kind.split(".")[0], "none")


def event_text(run, e) -> str:
    d = e.data or {}
    if e.kind == "async.before":
        return f"{escape(run.describe(e.aid))} [mute]fired · scheduled at[/] [loc]{escape(A.where(run.site(e.aid)))}[/]"
    if e.kind == "async.init":
        return f"{escape(run.describe(e.aid))} [mute]created at[/] [loc]{escape(A.where(A.user_frame(e.stack)))}[/]"
    if e.kind in ("async.after", "async.resolve"):
        return f"[mute]{escape(run.describe(e.aid))}[/]"
    if e.kind == "mutation":
        return (f"[fn]{escape(e.name + d.get('path', ''))}[/] {escape(d.get('op', ''))} "
                f"[mute]{escape(clip(d.get('before')))} →[/] {escape(clip(d.get('after')))}  [loc]{escape(d.get('loc', ''))}[/]")
    if e.kind == "mutation.capped":
        return f"[write]{escape(e.name)}: more than {d.get('cap')} writes, further writes counted only[/]"
    if e.kind == "http.out":
        st = d.get("status", 0)
        return f"[{'err.t' if st >= 500 else 'ok'}]{st}[/] {escape(e.name.split(' ', 1)[1])} [mute]{d.get('ms', 0):.1f}ms[/]"
    if e.kind in A.ERROR_KINDS:
        return f"[err.t]{escape(d.get('error') or '')}: {escape(e.name or '')}[/]  [loc]{escape(A.where(A.user_frame(e.stack)))}[/]"
    if e.kind == "run.start":
        return f"[mute]node {escape(' '.join(d.get('argv', [])))}  {d.get('node', '')}[/]"
    if e.kind == "run.end":
        return f"exit {d.get('code')}"
    if e.kind == "instrument":
        return (f"[mute]{escape(e.name)} {escape(str(d.get('file')))} ({plural(d.get('writes', 0), 'write site')}, "
                f"watch={','.join(d.get('watch', []))})[/]")
    return escape(e.name or "")


def context(run, e) -> str:
    if e.kind.startswith(("run.", "async.")) or e.kind in ("http.in", "http.out", "instrument"):
        return ""
    return f"[mute]in {escape(run.describe(e.eid))}[/]"


def timeline(run, rows, show_context=True):
    """Chronological: seq and time on the left of a time rail; errors break the rail in red."""
    t = Table(box=None, expand=True, header_style="mute", pad_edge=False, padding=(0, 1))
    t.add_column("seq", justify="right", style="mute", no_wrap=True)
    t.add_column("ms", justify="right", style="mute", no_wrap=True)
    t.add_column("", no_wrap=True)
    t.add_column("req", no_wrap=True)
    t.add_column("", no_wrap=True)
    t.add_column("event", ratio=3, overflow="fold")
    if show_context:
        t.add_column("context", ratio=1, overflow="ellipsis", no_wrap=True)
    for e in rows:
        rid = None if e.kind.startswith("run.") else run.request_of(e.aid if e.kind.startswith("async.") else e.eid)
        rail = "[err]┃[/]" if e.kind in A.ERROR_KINDS else "[mute]│[/]"
        cells = [str(e.seq), f"{e.t / 1000:.1f}", rail, req_tag(rid), f"[{kind_style(e.kind)}]{GLYPH.get(e.kind, '·')}[/]",
                 event_text(run, e)]
        if show_context:
            cells.append(context(run, e))
        t.add_row(*cells)
    console.print(Padding(t, (0, 0, 0, 2)))


def tree(run, root, pruned: int, title_: str):
    """Lineage: requests in their tone, scheduling sites under each callback, errors marked where they ran."""
    def label(n) -> str:
        if n.init is None:
            return f"[kind.run]◉[/] [bold]{escape(title_)}[/]"
        rid = run.anchors.get(n.aid)
        hidden = f" [mute]+{n.hidden} internal[/]" if n.hidden else ""
        if rid:
            return f"{req_tag(rid)} [bold]{escape(run.requests[rid].inbound.name)}[/]{hidden}"
        site = run.site(n.aid)
        name = f" [fn]{escape(n.init.name)}[/]" if n.init.name and n.init.name != "<anonymous>" else ""
        where_ = f" [mute]at[/] [loc]{escape(A.where(site))}[/] [mute]in {escape(A.short_fn(site['fn']))}[/]" if site else ""
        ran = "" if run.fired.get(n.aid) else " [mute](never ran)[/]"
        err = " [err]✖[/]" if any(e.kind in A.ERROR_KINDS for e in n.events) else ""
        return f"[kind.async]{escape(n.init.type)}[/]{name}{where_}{hidden}{ran}{err}"

    def add(parent, n):
        for e in n.events:
            parent.add(f"[{kind_style(e.kind)}]{GLYPH.get(e.kind, '·')}[/] {event_text(run, e)}")
        for c in n.children:
            add(parent.add(label(c)), c)

    t = Tree(label(root), guide_style="mute")
    add(t, root)
    console.print(Padding(t, (0, 0, 0, 2)))
    if pruned:
        console.print()
        console.print(f"  [mute]{plural(pruned, 'quiet async resource')} with no observable effect hidden (--full shows all)[/]")


def findings(fs, evidence: bool):
    """The evidence hierarchy: certainty is brightness. Evidence seqs sit in their own right-hand column."""
    g = Table.grid(padding=(0, 1), expand=True)
    g.add_column(no_wrap=True)
    g.add_column(ratio=1, overflow="fold")
    if evidence:
        g.add_column(no_wrap=True, justify="right", style="mute")
    for f in fs:
        cells = [LEVEL[f.level], f"[{LEVEL_TEXT[f.level]}]{escape(f.text)}[/]"]
        if evidence:
            cells.append(f"{f.run + ' ' if f.run else ''}seq {', '.join(map(str, f.evidence))}" if f.evidence else "")
        g.add_row(*cells)
    console.print(Padding(g, (0, 0, 0, 2)), width=width())


def why(run, inv, title_: str, evidence: bool, position: str):
    """A forensic report: the exhibit, the graded findings, the causal chain, then the request's story."""
    e = inv.target
    title("why", title_, position)
    console.print()
    if e.kind in A.ERROR_KINDS:
        f = A.user_frame(e.stack)
        console.print(f"  [err]✖ {escape((e.data or {}).get('error') or 'Error')}[/]  [err.t]{escape(e.name or '')}[/]")
        if f:
            console.print(f"    [loc]{escape(A.where(f))}[/]  [mute]in[/] [fn]{escape(A.short_fn(f['fn']))}[/]")
            src = run.source_line(f)
            if src:
                console.print(f"    [mute]{f['line']:>4} │[/] {escape(src.strip())}")
    else:
        console.print(f"  [{kind_style(e.kind)}]{GLYPH.get(e.kind, '·')}[/] {event_text(run, e)}")
    console.print()
    section("findings", LEGEND)
    findings(inv.findings, evidence)
    hops = run.user_chain(e.eid)
    if hops:
        console.print()
        section("causal chain", "[mute]innermost first[/]")
        for i, h in enumerate(hops):
            arrow = "  " if i == 0 else "[mute]↑ [/]"
            if h.aid in run.anchors:
                console.print(f"  {arrow}{req_tag(run.anchors[h.aid])} [bold]{escape(run.requests[run.anchors[h.aid]].inbound.name)}[/]")
            else:
                site = run.site(h.aid)
                console.print(f"  {arrow}[kind.async]{escape(h.type)}[/]{' [fn]' + escape(h.name) + '[/]' if h.name and h.name != '<anonymous>' else ''}"
                              f"  [mute]scheduled in[/] {escape(A.short_fn(site['fn']))} [loc]{escape(A.where(site))}[/]")
    if inv.branch:
        console.print()
        req = inv.request
        section(f"story of {'request ' + req_tag(req.id) + ' ' + escape(req.inbound.name) if req else 'this causal branch'}",
                "[mute]+ other requests' writes to watched variables[/]" if run.watch and req else "")
        rows = list(inv.branch)
        if run.watch and req:
            rows += [m for m in run.events if m.kind == "mutation" and req.inbound.seq < m.seq < e.seq
                     and run.request_of(m.eid) not in (req.id,) and m.seq not in {r.seq for r in rows}]
        timeline(run, sorted(rows + ([e] if e not in rows else []), key=lambda x: x.seq), show_context=False)


def _diff_line(mark: str, style: str, tok: str, seq: int | None):
    seq_s = f"{seq:>5}" if seq is not None else "     "
    console.print(f"  [{style}]{mark}[/] [mute]{seq_s}[/]  [{style if mark != ' ' else 'mute'}]{escape(tok)}[/]", soft_wrap=False,
                  overflow="ellipsis", no_wrap=True)


def diff(res, title_a: str, title_b: str, evidence: bool, context: int = 2):
    """Two executions side by side in one stream: shared steps fade, A-only and B-only steps stand out."""
    title("diff", f"[mute]A[/] {title_a}  [mute]·[/]  [mute]B[/] {title_b}")
    console.print()
    section("findings", LEGEND)
    findings(res.findings, evidence)
    console.print()
    section("aligned steps", "[mute]- only in A   + only in B   seq from A, or B on + lines[/]")
    first = res.first_divergence
    for n, (tag, i1, i2, j1, j2) in enumerate(res.opcodes):
        if tag == "equal":
            rows = list(range(i1, i2))
            head = rows[:context] if n else []
            tail = rows[-context:] if n < len(res.opcodes) - 1 else []
            if len(rows) > len(head) + len(tail):
                for k in head:
                    _diff_line(" ", "mute", res.a[k][0], res.a[k][1].seq)
                console.print(f"  [mute]  ·····  {len(rows) - len(head) - len(tail)} identical steps[/]")
                for k in tail:
                    _diff_line(" ", "mute", res.a[k][0], res.a[k][1].seq)
            else:
                for k in rows:
                    _diff_line(" ", "mute", res.a[k][0], res.a[k][1].seq)
            continue
        if (tag, i1, i2, j1, j2) == first:
            console.print(f"  [uv.b]  ▼ first divergence[/] [uv]{'┈' * max(width() - 26, 3)}[/]")
        for k in range(i1, i2):
            _diff_line("-", "err.t", res.a[k][0], res.a[k][1].seq)
        for k in range(j1, j2):
            _diff_line("+", "ok", res.b[k][0], res.b[k][1].seq)

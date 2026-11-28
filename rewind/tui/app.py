"""`rewind` (on an interactive terminal) / `rewind ui`: the interactive app.

Screens: Home (start here: record a program, the sample, recent recordings) -> Record (run a program under the
recorder) -> the investigation of one run (this module's main screen) -> Help. The investigation has a sidebar
(recordings, requests), the main views (Overview, Explain, Timeline, Unfinished, Variables, Async tree, Compare) and
a details pane. Every fact shown comes from rewind.store and rewind.analysis; views.py words and lays it out.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from rich.console import Group
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.scrollbar import ScrollBar
from textual.widgets import DataTable, Footer, Input, OptionList, Static, TabbedContent, TabPane, Tree
from textual.widgets.option_list import Option

from .. import analysis as A
from .. import store
from . import views as V
from .screens import HelpScreen, HomeScreen, RecordScreen
from .scrollbar import ThinScrollBarRender
from .theme import CSS, STYLES, THEME

ScrollBar.renderer = ThinScrollBarRender  # every scrollable region in the app gets the thin Ultraviolet scrollbar

KINDS = [("all events", None), ("requests", ("http",)), ("logs", ("log",)), ("errors", ("error",)),
         ("writes", ("mutation",)), ("reads", ("read",)), ("snapshots", ("snapshot",))]
RAW_LIMIT = 20000  # rows the "every event" view shows; the CLI's --raw has no limit
TABS = [("overview", "Overview", "o"), ("why", "Explain", "w"), ("timeline", "Timeline", "t"),
        ("pending", "Unfinished", "p"), ("state", "Variables", "s"), ("tree", "Tree", "e"), ("diff", "Compare", "d")]
INTRO = {
    "overview": "Start here: what happened in this run, and where to look first.",
    "why": "Why did it happen? Rewind traces the selected event (by default the first error) back through the callbacks "
           "and requests that led to it. Findings are grouped by how certain they are.",
    "timeline": "Everything recorded, in order. seq is the event number, ms the time since start, #N the request it "
                "belongs to.",
    "pending": "Requests and operations that never reached an outcome: no response, a promise that never settled, a "
               "timer that never fired. Only claimed when the recording is complete.",
    "state": "Watched variables as last recorded at the event selected in the Timeline. Pick another event there and "
             "press s.",
    "tree": "Who scheduled what: each request, the timers, file reads and promises it started, and what each did. "
            "Select a request on the left to see only its tree.",
    "diff": "Compare this recording (B) with another one (A) to find the first point where their executions differ. "
            "Pick the other recording:",
}
INVESTIGATION_ONLY = {"search", "why", "view", "step_view", "state", "diff", "baseline", "kind_filter", "callbacks", "raw",
                      "evidence", "reload", "details", "toggle", "clear", "focus_panel", "cursor", "edge", "home",
                      "new_recording"}


def home_path() -> Path:
    return Path(os.environ.get("REWIND_HOME") or Path.cwd() / ".rewind")  # same rule as store.home(), never creating it


class Session:
    """Read-only access to the runs recorded in one REWIND_HOME, with loaded runs cached."""

    def __init__(self, home: Path):
        self.home = home
        self.db: sqlite3.Connection | None = None
        self.rows: list = []
        self.cache: dict[str, tuple] = {}

    def reload(self):
        if self.db is None and (self.home / "rewind.db").exists():
            self.db = store.connect(self.home)
        self.rows = store.runs(self.db) if self.db is not None else []
        self.cache.clear()

    def row(self, run_id: str):
        return next((r for r in self.rows if r["id"] == run_id), None)

    def load(self, run_id: str) -> tuple:
        if run_id not in self.cache:
            row = self.row(run_id)
            run = A.Run(store.events(self.db, run_id), dict(row), store.sources(self.db, run_id))
            self.cache[run_id] = (row, run, A.pending(run))
        return self.cache[run_id]


class Panel(Vertical):
    def __init__(self, *children, title: str = "", **kw):
        super().__init__(*children, **kw)
        self.add_class("panel")
        self.border_title = title


class RewindApp(App):
    CSS = CSS
    TITLE = "rewind"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("question_mark", "help", "help"),
        Binding("h", "home", "home"),
        Binding("n", "new_recording", "record"),
        Binding("slash", "search", "search"),
        Binding("q", "quit", "quit"),
        Binding("greater_than_sign", "step_view(1)", "next view", key_display=">"),
        Binding("less_than_sign", "step_view(-1)", "previous view", show=False, key_display="<"),
        Binding("o", "view('overview')", "overview", show=False),
        Binding("w", "why", "explain", show=False),
        Binding("t", "view('timeline')", "timeline", show=False),
        Binding("p", "view('pending')", "unfinished", show=False),
        Binding("s", "state", "variables", show=False),
        Binding("e", "view('tree')", "async tree", show=False),
        Binding("d", "diff", "compare", show=False),
        Binding("b", "baseline", "compare against", show=False),
        Binding("f", "kind_filter", "filter", show=False),
        Binding("c", "callbacks", "callbacks", show=False),
        Binding("a", "raw", "all events", show=False),
        Binding("right_square_bracket", "evidence(1)", "next evidence", show=False),
        Binding("left_square_bracket", "evidence(-1)", "previous evidence", show=False),
        Binding("r", "reload", "reload", show=False),
        Binding("i", "details", "details", show=False),
        Binding("backslash", "toggle('-hide-sidebar')", "sidebar", show=False),
        Binding("escape", "clear", "clear", show=False),
        Binding("1", "focus_panel('runs')", show=False), Binding("2", "focus_panel('requests')", show=False),
        Binding("3", "focus_panel('main')", show=False), Binding("4", "focus_panel('details')", show=False),
        Binding("j", "cursor(1)", show=False), Binding("k", "cursor(-1)", show=False),
        Binding("g", "edge('first')", show=False), Binding("G", "edge('last')", show=False),
    ]

    def __init__(self, home: Path | None = None):
        super().__init__()
        self.session = Session(home or home_path())
        self.row = self.current = self.pend = None
        self.req_filter: int | None = None
        self.kind_idx, self.search_text, self.callbacks, self.raw = 0, "", False, False
        self.shown: list[int] = []                       # seqs currently in the timeline, in order
        self.lists: dict[str, list[A.Finding]] = {"why": [], "pending": [], "diff": []}
        self.overview_items: list[V.Item] = []
        self.why_inv: A.Investigation | None = None
        self.active: tuple[str, A.Finding] | None = None  # the finding whose evidence ] and [ walk through
        self.ev_cursor = 0
        self.baseline: str | None = None
        self.diff_pair: tuple[str, str] | None = None
        self.why_target: int | None = None
        self._picked = False

    # ---- layout -------------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(id="topbar", classes="topbar")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Panel(OptionList(id="runs"), title="Recordings", id="runs-panel")
                yield Panel(OptionList(id="requests"), Static(V.T(V.REQ_LEGEND), classes="legend"),
                            title="Requests", id="requests-panel")
            with Panel(id="main"):
                with TabbedContent(id="views", initial="overview"):
                    for pane_id, label, key in TABS:
                        with TabPane(f"{label} [{V.TH.C['dim']}]{key}[/]", id=pane_id):  # every tab shows its key
                            yield from self._pane(pane_id)
            with VerticalScroll(id="details-panel", classes="panel"):
                yield Static(id="details")
        yield Footer()

    def _pane(self, pane_id: str):
        label, key = next((lbl, k) for p, lbl, k in TABS if p == pane_id)
        intro = f"[text3]{INTRO[pane_id]}[/]  [dim]key[/] [key]{key}[/]" + (f"\n{V.TIMELINE_LEGEND}" if pane_id == "timeline" else "")
        yield Static(V.T(intro), classes="intro")
        if pane_id == "overview":
            yield OptionList(id="overview-list")
        elif pane_id == "why":
            yield Static(id="why-head")
            yield OptionList(id="why-list")
        elif pane_id == "timeline":
            yield Static(id="filterbar")
            yield Input(placeholder="search event text · enter to keep · esc to clear", id="search")
            yield DataTable(id="table", cursor_type="row", zebra_stripes=False, show_cursor=True)
        elif pane_id == "pending":
            yield OptionList(id="pending-list")
        elif pane_id == "state":
            with VerticalScroll():
                yield Static(id="state-body")
        elif pane_id == "tree":
            yield Tree("tree", id="tree-view")
        elif pane_id == "diff":
            yield OptionList(id="compare-runs")
            yield Static(id="diff-head")
            yield OptionList(id="diff-list")

    def on_mount(self):
        self.register_theme(THEME)
        self.theme = "ultraviolet"
        self._q("#details-panel").border_title = "Details"
        t = self._q("#table", DataTable)
        for label, key in (("seq", "seq"), ("ms", "ms"), ("req", "req"), (" ", "g"), ("event", "event")):
            t.add_column(label, key=key)
        self._q("#tree-view", Tree).show_root = True
        self._layout(self.size.width, self.size.height)
        self.session.reload()
        self._fill_runs()
        if self.session.rows:
            self.open_run(self.session.rows[0]["id"])
        self.push_screen(HomeScreen())

    def _q(self, selector: str, expect_type=None):
        """Query the investigation screen, whichever screen is on top (Home, Record and Help sit above it)."""
        return self.screen_stack[0].query_one(selector, expect_type) if expect_type else self.screen_stack[0].query_one(selector)

    def check_action(self, action: str, parameters) -> bool | None:
        if action == "quit" and isinstance(self.screen, RecordScreen) and self.screen.state in ("running", "stopping"):
            return False  # stop the recording first (esc): quitting would orphan the program
        # investigation keys only act on the investigation screen, never behind Home, Record or Help
        if action in INVESTIGATION_ONLY and self.screen is not self.screen_stack[0]:
            return False
        if action in INVESTIGATION_ONLY - {"home", "new_recording", "reload"} and self.current is None:
            return False
        return True

    def on_resize(self, event):
        self._layout(event.size.width, event.size.height)
        if self.current is not None:
            self.call_after_refresh(self.refresh_timeline, True)

    def _layout(self, w: int, h: int):
        main = self.screen_stack[0] if self.screen_stack else self.screen
        main.set_class(120 <= w < 150, "-medium")
        main.set_class(100 <= w < 120, "-compact")
        main.set_class(w < 100, "-narrow")
        main.set_class(h < 30, "-short")

    # ---- screens ------------------------------------------------------------------------------
    def action_help(self):
        if not isinstance(self.screen, HelpScreen):
            self.push_screen(HelpScreen())

    def action_home(self):
        self.push_screen(HomeScreen())

    def action_new_recording(self):
        cmd = V.command(self.row) if self.row else ""
        self.push_screen(RecordScreen(cmd, "", ""))

    def open_run_from_home(self, run_id: str):
        """Leave Home or Record for the investigation of `run_id` (a new recording, or one picked from the list)."""
        while len(self.screen_stack) > 1:
            self.pop_screen()
        self.session.reload()
        self._fill_runs(keep=run_id)
        self.open_run(run_id)
        self.action_view("overview")
        self._q("#overview-list", OptionList).focus()

    # ---- runs ---------------------------------------------------------------------------------
    def _fill_runs(self, keep: str | None = None):
        runs = self._q("#runs", OptionList)
        with runs.prevent(OptionList.OptionHighlighted):
            runs.clear_options()
            runs.add_options([Option(V.run_option(r), id=r["id"]) for r in self.session.rows])
            ids = [r["id"] for r in self.session.rows]
            if ids:
                runs.highlighted = ids.index(keep) if keep in ids else 0
        self._q("#runs-panel").border_title = f"Recordings [{len(self.session.rows)}]"

    def action_reload(self):
        keep = self.row["id"] if self.row else None
        self.session.reload()
        if not self.session.rows:
            self.push_screen(HomeScreen())
            return
        self._fill_runs(keep)
        ids = [r["id"] for r in self.session.rows]
        self.open_run(keep if keep in ids else ids[0])
        self.notify(f"{V.R.plural(len(ids), 'recording')} loaded")

    @on(OptionList.OptionHighlighted, "#runs")
    def _run_highlighted(self, ev: OptionList.OptionHighlighted):
        if ev.option_id and (self.row is None or ev.option_id != self.row["id"]):
            self.open_run(ev.option_id)

    def open_run(self, run_id: str, keep_filters: bool = False):
        self.row, self.current, self.pend = self.session.load(run_id)
        self._picked = False  # no timeline event chosen yet in this run
        if not keep_filters:
            self.req_filter, self.search_text, self.kind_idx, self.raw = None, "", 0, False
            self._q("#search", Input).value = ""
        reqs = self._q("#requests", OptionList)
        with reqs.prevent(OptionList.OptionHighlighted):
            reqs.clear_options()
            if self.current.requests:
                reqs.add_option(Option(V.T(f"[uv]◇[/] [bold]All requests[/]  [dim]{len(self.current.requests)}[/]"), id="all"))
                reqs.add_options([Option(V.request_option(self.current, r, self.pend.states.get(r.id, "")), id=str(r.id))
                                  for r in self.current.requests.values()])
                reqs.highlighted = 0 if self.req_filter is None else 1 + list(self.current.requests).index(self.req_filter)
            else:
                reqs.add_option(Option(V.T("[mute]No HTTP requests in this run.[/]"), id="none", disabled=True))
        self._q("#requests-panel").border_title = f"Requests [{len(self.current.requests)}]"
        errors = self.current.errors
        self.why_target = errors[0].seq if errors else None
        self._topbar()
        self.refresh_timeline()
        self.refresh_why()
        self.refresh_pending()
        self.refresh_overview()
        self.refresh_compare_runs()
        active = self._q("#views", TabbedContent).active
        if active == "tree":
            self.refresh_tree()
        if active == "state":
            self.refresh_state()
        self._main_title()
        self.call_after_refresh(self._detail_for_focus)

    def _topbar(self):
        r = self.row
        crumbs = []
        if r is not None:
            label = f" [label]{V.escape(r['label'])}[/]" if r["label"] else ""
            crumbs.append(f"[id]{r['id']}[/]{label}  {V.STATUS_WORD.get(r['status'], '')}")
            facts = (f"[dim]{V.R.plural(len(self.current.requests), 'request')} · {V.R.plural(r['error_count'], 'error')}"
                     + (f" · watching[/] [warn]{V.escape(', '.join(self.current.watch))}[/]" if self.current.watch else "[/]"))
            crumbs.append(facts)
        if self.baseline:
            b = self.session.row(self.baseline)
            if b:
                crumbs.append(f"[dim]compare against[/] [uv]{V.escape(b['label'] or b['id'])}[/]")
        self._q("#topbar", Static).update(V.topbar(*crumbs, right="[key]h[/] [dim]home[/]  [key]n[/] [dim]record[/]  "
                                                          "[key]?[/] [dim]help[/]"))

    def _run_summary(self):
        r, run = self.row, self.current
        counts = {s: sum(v == s for v in self.pend.states.values()) for s in ("completed", "failed", "cancelled", "unresolved")}
        g = V.grid({"style": STYLES["text3"], "no_wrap": True, "width": 10}, {"ratio": 1, "overflow": "fold"})
        g.add_row("command", Text(V.command(r)))
        g.add_row("result", V.T(f"{V.STATUS_WORD.get(r['status'], '')}  [dim]exit code[/] {r['exit_code']}"))
        g.add_row("events", V.T(f"{r['event_count']:,}  [dim]errors[/] {r['error_count']}"))
        g.add_row("requests", V.T(f"{len(run.requests)}"))
        if run.requests:
            g.add_row("", V.T(f"[ok]●[/] {counts['completed']} answered  [err]×[/] {counts['failed']} failed"))
            g.add_row("", V.T(f"[warn]◌[/] {counts['unresolved']} no response  [warn]−[/] {counts['cancelled']} gave up"))
        g.add_row("watching", V.T((V.escape(", ".join(run.watch)) or "[dim]nothing[/]") + ("  [dim]writes and reads[/]" if run.reads_recorded else "")))
        g.add_row("node", V.T(f"{(run.events[0].data or {}).get('node', '?') if run.events and run.events[0].kind == 'run.start' else '?'}"))
        g.add_row("recorded", V.T(f"{r['started_at'] or '?'}  [dim]{V.R.ago(r['started_at'])}[/]"))
        lines = [V.T(f"[eyebrow]RECORDING[/]  [id]{r['id']}[/]" + (f" [label]{V.escape(r['label'])}[/]" if r["label"] else "")), Text(), g, Text()]
        if not self.pend.complete:
            lines += [V.T("[warn]◌ Incomplete recording:[/] [text3]events after the last one may be lost, so a missing "
                          "event proves nothing.[/]"), Text()]
        lines.append(V.T("[key]enter[/] [text3]investigate[/]   [key]b[/] [text3]compare other runs against this one[/]"))
        self.show_detail(Group(*lines), "Recording")

    @on(OptionList.OptionSelected, "#runs")
    def _run_selected(self, ev):
        self.action_view("overview")
        self.action_focus_panel("main")

    # ---- requests -----------------------------------------------------------------------------
    @on(OptionList.OptionHighlighted, "#requests")
    def _req_highlighted(self, ev: OptionList.OptionHighlighted):
        if ev.option_id in (None, "none"):
            return
        rid = None if ev.option_id == "all" else int(ev.option_id)
        if rid != self.req_filter:
            self.req_filter = rid
            self.refresh_timeline()
            if self._q("#views", TabbedContent).active == "tree":
                self.refresh_tree()
        if ev.option_list.has_focus:
            self._request_detail(rid)

    def _request_detail(self, rid: int | None):
        if rid is None:
            self._run_summary()
            return
        r = self.current.requests[rid]
        st = self.pend.states.get(rid, "")
        mine = [f for f in self.pend.findings if f"request {r.label}" in f.text or f"#{rid} " in f.text]
        parts = [V.T(f"[eyebrow]REQUEST[/]  {V.R.req_tag(rid)} [bold]{V.escape(r.inbound.name)}[/]"), Text(),
                 V.T({"completed": "[ok]● answered[/]", "failed": "[err]× failed (5xx)[/]",
                      "cancelled": "[warn]− the client gave up before a response[/]",
                      "unresolved": "[warn]◌ no response was recorded[/]"}.get(st, "")), Text(),
                 V.T(f"[text3]arrived[/]   seq {r.inbound.seq}  [dim]{r.inbound.t / 1000:.1f} ms[/]")]
        if r.outbound:
            parts.append(V.T(f"[text3]responded[/] seq {r.outbound.seq}  status {r.outbound.data.get('status')}  "
                             f"[dim]{r.outbound.data.get('ms', 0):.1f} ms[/]"))
        if mine:
            parts += [Text()] + [V.finding_option(f) for f in mine]
        parts += [Text(), V.T("[key]enter[/] [text3]show only this request's events[/]")]
        self.show_detail(Group(*parts), "Request")

    @on(OptionList.OptionSelected, "#requests")
    def _req_selected(self, ev):
        self.action_view("timeline")
        self.action_focus_panel("main")

    # ---- overview -----------------------------------------------------------------------------
    def refresh_overview(self):
        why = self.why_inv if self.why_inv and self.current.errors and self.why_inv.target is self.current.errors[0] else (
            A.investigate(self.current, self.current.errors[0]) if self.current.errors else None)
        self.overview_items = V.overview(self.current, self.row, self.pend, why)
        self._overview_why = why
        ol = self._q("#overview-list", OptionList)
        with ol.prevent(OptionList.OptionHighlighted):
            ol.clear_options()
            for i, it in enumerate(self.overview_items):
                ol.add_option(Option(it.prompt, id=it.id or f"info:{i}", disabled=it.id is None))
            first = next((i for i, it in enumerate(self.overview_items) if it.id), None)
            if first is not None:
                ol.highlighted = first

    def _overview_finding(self, oid: str) -> tuple[str, A.Finding] | None:
        _, src, i = oid.split(":")
        findings = self._overview_why.findings if src == "why" else self.pend.findings
        return src, findings[int(i)]

    @on(OptionList.OptionHighlighted, "#overview-list")
    def _overview_highlighted(self, ev: OptionList.OptionHighlighted):
        if ev.option_list.has_focus:
            self._overview_detail(ev.option_id)

    def _overview_detail(self, oid: str | None):
        if not oid or oid.startswith("info:"):
            return
        kind, _, rest = oid.partition(":")
        if kind == "err":
            self._row_detail(int(rest))
        elif kind == "req":
            self._request_detail(int(rest))
        elif kind == "find":
            src, f = self._overview_finding(oid)
            self.active, self.ev_cursor = (src, f), 0
            self.show_detail(V.finding_detail(self.current, f, None), f"{V.LEVEL_NAME[f.level].capitalize()} finding")

    @on(OptionList.OptionSelected, "#overview-list")
    def _overview_selected(self, ev: OptionList.OptionSelected):
        kind, _, rest = (ev.option_id or "").partition(":")
        if kind == "err":
            self.why_target = int(rest)
            self.refresh_why()
            self.action_view("why")
            self._q("#why-list", OptionList).focus()
        elif kind == "req":
            reqs = self._q("#requests", OptionList)
            reqs.highlighted = 1 + list(self.current.requests).index(int(rest))
            self.req_filter = int(rest)
            self.refresh_timeline()
            self.action_view("timeline")
            self._q("#table", DataTable).focus()
        elif kind == "find":
            self.active, self.ev_cursor = self._overview_finding(ev.option_id), 0
            self._jump_evidence()

    # ---- timeline -----------------------------------------------------------------------------
    def timeline_rows(self) -> list:
        run = self.current
        if self.raw:
            rows = run.events[:RAW_LIMIT]
        else:
            rows = sorted(run.story + (run.callback_fires() if self.callbacks else []), key=lambda e: e.seq)
        kinds = KINDS[self.kind_idx][1]
        if kinds:
            rows = [e for e in rows if e.kind.split(".")[0] in kinds]
        if self.req_filter is not None:
            rows = [e for e in rows if run.request_of(e.aid if e.kind.startswith("async.") else e.eid) == self.req_filter]
        if self.search_text:
            q = self.search_text.lower()
            rows = [e for e in rows if q in V.T(V.R.event_text(run, e)).plain.lower() or q in e.kind]
        return rows

    def refresh_timeline(self, keep_cursor: bool = True):
        t = self._q("#table", DataTable)
        cur = self.shown[t.cursor_row] if keep_cursor and self.shown and 0 <= t.cursor_row < len(self.shown) else None
        rows = self.timeline_rows()
        # the main panel's width, not the table's: the table has no size while its tab is hidden
        width = max(self._q("#main").size.width - 4 - 28, 20)
        t.clear()
        for e in rows:
            t.add_row(*V.timeline_cells(self.current, e, width), key=str(e.seq))
        self.shown = [e.seq for e in rows]
        if cur in self.shown:
            t.move_cursor(row=self.shown.index(cur), animate=False)
        bits = [KINDS[self.kind_idx][0]]
        if self.req_filter:
            bits.append(f"request #{self.req_filter} only")
        if self.callbacks:
            bits.append("with callback starts")
        if self.raw:
            bits = ["every recorded event" + (f" (first {RAW_LIMIT:,})" if len(self.current.events) > RAW_LIMIT else "")]
        if self.search_text:
            bits.append(f"matching “{self.search_text}”")
        self._q("#filterbar", Static).update(V.T(
            f"[uv]{' · '.join(bits)}[/]  [dim]{len(rows):,} of {len(self.current.events):,} events[/]   "
            "[key]/[/] [dim]search[/] [key]f[/] [dim]kind[/] [key]c[/] [dim]callbacks[/] [key]a[/] [dim]all[/]"))
        if not rows and t.has_focus:
            self.show_detail(V.T("[text3]No events match. Press[/] [key]esc[/] [text3]to clear the search and filters.[/]"), "Timeline")

    @on(DataTable.RowHighlighted, "#table")
    def _row_highlighted(self, ev: DataTable.RowHighlighted):
        if self.current is None or ev.row_key is None or ev.row_key.value is None or not ev.data_table.has_focus:
            return
        self._picked = True
        self._row_detail(int(ev.row_key.value))

    def _row_detail(self, seq: int):
        e = self.current.by_seq.get(seq)
        if e is None:
            return
        body = V.event_detail(self.current, e)
        if self.active and e.seq in self.active[1].evidence:
            f = self.active[1]
            i = f.evidence.index(e.seq)
            body = Group(V.T(f"{V.R.LEVEL[f.level]} [eyebrow]EVIDENCE {i + 1} OF {len(f.evidence)}[/] [dim]for:[/]"),
                         V.T(f"[{'hyp' if f.level == A.INFERRED else 'text2'}]{V.escape(f.text)}[/]"),
                         V.T("[key]] [[/] [dim]next / previous evidence[/]"), Text(), body)
        self.show_detail(body, f"Event {e.seq}")

    def selected_seq(self) -> int | None:
        t = self._q("#table", DataTable)
        return self.shown[t.cursor_row] if self.shown and 0 <= t.cursor_row < len(self.shown) else None

    def action_search(self):
        self.action_view("timeline")
        s = self._q("#search", Input)
        s.add_class("-shown")
        s.focus()

    @on(Input.Changed, "#search")
    def _search_changed(self, ev: Input.Changed):
        self.search_text = ev.value.strip()
        self.refresh_timeline()

    @on(Input.Submitted, "#search")
    def _search_submitted(self, ev):
        self._q("#table", DataTable).focus()

    def action_kind_filter(self):
        self.kind_idx = (self.kind_idx + 1) % len(KINDS)
        self.raw = False
        self.action_view("timeline")
        self.refresh_timeline()

    def action_callbacks(self):
        self.callbacks, self.raw = not self.callbacks, False
        self.refresh_timeline()

    def action_raw(self):
        self.raw = not self.raw
        self.refresh_timeline()

    def action_clear(self):
        s = self._q("#search", Input)
        changed = self.search_text or self.kind_idx or self.raw or self.callbacks or s.has_class("-shown")
        s.value, self.search_text = "", ""
        s.remove_class("-shown")
        self.kind_idx, self.raw, self.callbacks = 0, False, False
        if changed:
            self.refresh_timeline()
            self._q("#table", DataTable).focus()

    # ---- findings: explain / unfinished / compare ------------------------------------------------
    def _fill(self, name: str, findings: list[A.Finding], empty: str):
        """Findings grouped by how certain they are: recorded, derived, Rewind's interpretation."""
        ol = self._q(f"#{name}-list", OptionList)
        self.lists[name] = findings
        with ol.prevent(OptionList.OptionHighlighted):
            ol.clear_options()
            if not findings:
                ol.add_option(Option(V.T(f"[text3]{empty}[/]"), id="empty", disabled=True))
                return
            first = None
            for level, _, _ in V.GROUPS:
                idx = [i for i, f in enumerate(findings) if f.level == level]
                if not idx:
                    continue
                if ol.option_count:
                    ol.add_option(Option(Text(""), id=f"gap:{level}", disabled=True))
                ol.add_option(Option(V.group_header(level), id=f"group:{level}", disabled=True))
                for i in idx:
                    ol.add_option(Option(V.finding_option(findings[i]), id=str(i)))
                    first = ol.option_count - 1 if first is None else first
            ol.highlighted = first

    def refresh_why(self):
        head = self._q("#why-head", Static)
        if self.why_target is None:
            self.why_inv = None
            head.update(V.T("[ok]●[/] [text2]No errors were recorded in this run.[/]"))
            self._fill("why", [], "Select any event in the Timeline and press w to have Rewind explain it.")
            return
        inv = A.investigate(self.current, self.current.by_seq[self.why_target])
        self.why_inv = inv
        errors = self.current.errors
        pos = f"error {errors.index(inv.target) + 1} of {len(errors)}" if inv.target in errors else f"event {inv.target.seq}"
        head.update(V.why_head(self.current, inv, pos))
        self._fill("why", inv.findings, "nothing to explain")

    def refresh_pending(self):
        self._fill("pending", self.pend.findings, "nothing to report")

    @on(OptionList.OptionHighlighted, "#why-list, #pending-list, #diff-list")
    def _finding_highlighted(self, ev: OptionList.OptionHighlighted):
        if ev.option_list.has_focus:
            self._finding_detail(ev.option_list)

    def _finding_detail(self, ol: OptionList):
        name = ol.id.removesuffix("-list")
        if ol.highlighted is None or not self.lists[name]:
            return
        oid = ol.get_option_at_index(ol.highlighted).id
        if not oid or not oid.isdigit():
            return
        f = self.lists[name][int(oid)]
        self.active, self.ev_cursor = (name, f), 0
        self.show_detail(V.finding_detail(self._run_for(f), f, None), f"{V.LEVEL_NAME[f.level].capitalize()} finding")

    def on_descendant_focus(self, event):
        self.call_after_refresh(self._detail_for_focus)

    def _detail_for_focus(self):
        """The details pane always describes the focused panel's selected item."""
        w = self.focused
        if self.current is None or w is None or self.screen is not self.screen_stack[0]:
            return
        if w.id == "runs":
            self._run_summary()
        elif w.id == "requests" and w.highlighted is not None:
            oid = w.get_option_at_index(w.highlighted).id
            if oid not in (None, "none"):
                self._request_detail(None if oid == "all" else int(oid))
        elif w.id == "table":
            seq = self.selected_seq()
            if seq is not None:
                self._row_detail(seq)
        elif w.id == "overview-list" and w.highlighted is not None:
            self._overview_detail(w.get_option_at_index(w.highlighted).id)
        elif w.id in ("why-list", "pending-list", "diff-list"):
            self._finding_detail(w)
        elif w.id == "compare-runs":
            self._compare_hint()
        elif w.id == "tree-view" and w.cursor_node is not None:
            self._tree_detail(w.cursor_node)

    @on(OptionList.OptionSelected, "#why-list, #pending-list, #diff-list")
    def _finding_selected(self, ev: OptionList.OptionSelected):
        if self.active and self.active[1].evidence:
            self.ev_cursor = 0
            self._jump_evidence()

    def _run_for(self, f: A.Finding) -> A.Run:
        if f.run and self.diff_pair:
            return self.session.load(self.diff_pair[0] if f.run == "A" else self.diff_pair[1])[1]
        return self.current

    def action_evidence(self, step: int):
        if not self.active or not self.active[1].evidence:
            self.notify("Select a finding first (Overview, Explain, Unfinished or Compare), then use ] and [ to walk "
                        "through its evidence.", severity="warning")
            return
        n = len(self.active[1].evidence)
        self.ev_cursor = (self.ev_cursor + step) % n
        self._jump_evidence()

    def _jump_evidence(self):
        name, f = self.active
        if not f.evidence:
            self.notify("This finding summarises the run; no single event backs it.")
            return
        seq = f.evidence[self.ev_cursor]
        if f.run and self.diff_pair:
            target = self.diff_pair[0] if f.run == "A" else self.diff_pair[1]
            if target != self.row["id"]:
                self._select_run(target)
        self.jump(seq)

    def _select_run(self, run_id: str):
        runs = self._q("#runs", OptionList)
        ids = [r["id"] for r in self.session.rows]
        self.open_run(run_id, keep_filters=True)
        with runs.prevent(OptionList.OptionHighlighted):
            runs.highlighted = ids.index(run_id)

    def jump(self, seq: int):
        """Show event `seq` in the timeline, widening the filters only as far as needed to reach it."""
        if seq not in self.current.by_seq:
            self.notify(f"Event {seq} is not in this recording", severity="error")
            return
        if seq not in self.shown:
            self.search_text, self.kind_idx = "", 0
            self._q("#search", Input).value = ""
            if seq not in [e.seq for e in self.timeline_rows()]:
                self.req_filter = None
            if seq not in [e.seq for e in self.timeline_rows()]:
                self.raw = True
                self.notify(f"Showing every recorded event, to reach event {seq}")
            self.refresh_timeline(keep_cursor=False)
        self.action_view("timeline")
        t = self._q("#table", DataTable)
        if seq in self.shown:
            t.move_cursor(row=self.shown.index(seq), animate=False)
            t.focus()

    # ---- explain / variables / tree / compare ---------------------------------------------------
    def action_why(self):
        views = self._q("#views", TabbedContent)
        seq = self.selected_seq()
        e = self.current.by_seq.get(seq) if seq is not None else None
        explainable = e is not None and not e.kind.startswith(("run.", "async.")) and e.kind not in ("instrument", "source")
        if views.active == "timeline" and self.focused is self._q("#table") and explainable:
            self.why_target = seq
        elif self.why_target is None and self.current.errors:
            self.why_target = self.current.errors[0].seq
        self.refresh_why()
        self.action_view("why")
        self._q("#why-list", OptionList).focus()

    def action_state(self):
        self.refresh_state()
        self.action_view("state")

    def refresh_state(self):
        # the event the user picked in the timeline; until they pick one, the first error (or the end of the run)
        seq = self.selected_seq() if self._picked else None
        if seq is None:
            seq = self.current.errors[0].seq if self.current.errors else (self.current.events[-1].seq if self.current.events else None)
        if seq is None:
            return
        body = V.state_view(self.current, A.state_at(self.current, seq))
        if not self.current.watch:
            body = Group(body, Text(), V.T("[text3]To see variables, record this program again and fill in[/] [text]Watch "
                                           "variables[/] [text3](press[/] [key]n[/][text3]).[/]"))
        self._q("#state-body", Static).update(body)

    def refresh_tree(self):
        tree = self._q("#tree-view", Tree)
        tree.clear()
        root_aid = self.current.requests[self.req_filter].anchor if self.req_filter else 1
        node, pruned = A.build_tree(self.current, root_aid)
        title = "main module" if root_aid == 1 else self.current.requests[self.req_filter].label
        tree.root.set_label(V.T(V.R.tree_label(self.current, node, title)))
        tree.root.data = ("aid", node.aid)

        stack = [(tree.root, node)]  # iterative: async trees can be deeper than Python's recursion limit
        while stack:
            parent, n = stack.pop()
            for e in n.events:
                parent.add_leaf(V.T(f"[{V.R.kind_style(e.kind)}]{V.R.GLYPH.get(e.kind, '·')}[/] {V.R.event_text(self.current, e)}"),
                                data=("seq", e.seq))
            stack.extend(reversed([(parent.add(V.T(V.R.tree_label(self.current, c, title)), data=("aid", c.aid), expand=True), c)
                                   for c in n.children]))
        tree.root.expand()
        if pruned:
            tree.root.add_leaf(V.T(f"[dim]{pruned} operations with no visible effect hidden[/]"))

    @on(Tree.NodeHighlighted, "#tree-view")
    def _tree_highlighted(self, ev: Tree.NodeHighlighted):
        if ev.control.has_focus:
            self._tree_detail(ev.node)

    def _tree_detail(self, node):
        data = node.data
        if not data:
            return
        kind, val = data
        e = self.current.by_seq.get(val) if kind == "seq" else self.current.inits.get(val)
        if e is not None:
            self.show_detail(V.event_detail(self.current, e), f"Event {e.seq}")

    def refresh_compare_runs(self):
        ol = self._q("#compare-runs", OptionList)
        others = [r for r in self.session.rows if r["id"] != self.row["id"]]
        with ol.prevent(OptionList.OptionHighlighted):
            ol.clear_options()
            if not others:
                ol.add_option(Option(V.T("[text3]There's no other recording yet. Record the program again (for example "
                                         "after a fix, or one request at a time) to compare.[/]"), id="none", disabled=True))
                return
            ol.add_options([Option(V.run_option(r), id=r["id"]) for r in others])
            ids = [r["id"] for r in others]
            ol.highlighted = ids.index(self.baseline) if self.baseline in ids else 0
        if not (self.diff_pair and self.diff_pair[1] == self.row["id"]):
            self._q("#diff-head", Static).update(V.T("[text3]Select a recording above and press[/] [key]enter[/] "
                                                            "[text3]to compare.[/]"))
            self._fill("diff", [], "Record both runs with the same watched variables to compare their writes too.")

    def _compare_hint(self):
        self.show_detail(V.T("[eyebrow]COMPARE[/]\n\n[text2]Rewind lines up the two recordings step by step (ignoring "
                             "ids and timing) and shows the first point where they differ: a different order of the "
                             "same steps (a race), or a step that only one run took (a different code path).[/]\n\n"
                             "[key]enter[/] [text3]compare with the selected recording[/]"), "Compare")

    @on(OptionList.OptionSelected, "#compare-runs")
    def _compare_selected(self, ev: OptionList.OptionSelected):
        if ev.option_id and ev.option_id != "none":
            self._compare(ev.option_id)

    def _compare(self, other: str):
        a_row, a_run, _ = self.session.load(other)
        res = A.diff(a_run, self.current)
        self.diff_pair = (other, self.row["id"])
        name = lambda r: f"[id]{r['id']}[/]" + (f" [label]{V.escape(r['label'])}[/]" if r["label"] else "")
        self._q("#diff-head", Static).update(V.diff_view(res, name(a_row), name(self.row)))
        self._fill("diff", res.findings, "no findings")
        self._q("#diff-list", OptionList).focus()

    def action_baseline(self):
        self.baseline = self.row["id"]
        self._topbar()
        self.notify(f"Other runs will be compared against {self.row['label'] or self.row['id']}. Open another "
                    "recording and press d.")

    def action_diff(self):
        self.action_view("diff")
        if self.baseline and self.baseline != self.row["id"]:
            self._compare(self.baseline)
        else:
            self._q("#compare-runs", OptionList).focus()

    # ---- navigation ---------------------------------------------------------------------------
    def action_step_view(self, step: int):
        """< and >: the previous / next view, wrapping around, so the far tabs are one key away from either end."""
        ids = [p for p, _, _ in TABS]
        cur = self._q("#views", TabbedContent).active
        self.action_view(ids[(ids.index(cur) + step) % len(ids)] if cur in ids else ids[0])
        self.action_focus_panel("main")

    def action_view(self, name: str):
        views = self._q("#views", TabbedContent)
        # If focus is inside the current view, it must move into the new one: otherwise Textual hands it to a sibling
        # in the now-hidden pane, and TabbedContent switches straight back to that pane.
        f = self.focused
        inside = f is not None and views in f.ancestors
        if views.active != name:
            views.active = name
            if inside:
                self.action_focus_panel("main")
        if name == "tree":
            self.refresh_tree()
        if name == "state":
            self.refresh_state()
        self._main_title()

    @on(TabbedContent.TabActivated, "#views")
    def _tab(self, ev):
        name = ev.pane.id if ev.pane else None
        if name == "timeline" and self.current is not None:
            self.call_after_refresh(self.refresh_timeline, True)
        if name == "tree" and self.current is not None:
            self.refresh_tree()
        if name == "state" and self.current is not None:
            self.refresh_state()
        self._main_title()

    def _main_title(self):
        main = self._q("#main")
        main.border_title = (self.row["label"] or self.row["id"]) if self.row else ""
        main.border_subtitle = {"timeline": "w explain · s variables · enter details",
                                "overview": "enter opens the selected item", "why": "enter shows evidence · ] [ walk it",
                                "pending": "enter shows evidence · ] [ walk it", "state": "follows the timeline's selection",
                                "tree": "who scheduled whom", "diff": "A = picked recording · B = this one"
                                }.get(self._q("#views", TabbedContent).active, "")

    def action_focus_panel(self, name: str):
        if name == "main":
            active = self._q("#views", TabbedContent).active
            target = {"timeline": "#table", "why": "#why-list", "pending": "#pending-list", "tree": "#tree-view",
                      "diff": "#diff-list", "state": "#state-body", "overview": "#overview-list"}.get(active, "#table")
            w = self._q(target)
            if target == "#diff-list" and not self.lists["diff"]:
                w = self._q("#compare-runs")
            (w.parent if target == "#state-body" else w).focus()
        else:
            self._q({"runs": "#runs", "requests": "#requests", "details": "#details-panel"}[name]).focus()

    def action_cursor(self, step: int):
        w = self.focused
        action = "action_cursor_down" if step > 0 else "action_cursor_up"
        if w is not None and hasattr(w, action):
            getattr(w, action)()
        elif w is not None and hasattr(w, "action_scroll_down"):
            (w.action_scroll_down if step > 0 else w.action_scroll_up)()

    def action_edge(self, which: str):
        w = self.focused
        name = "action_scroll_home" if which == "first" else "action_scroll_end"
        if isinstance(w, DataTable) and self.shown:
            w.move_cursor(row=0 if which == "first" else len(self.shown) - 1)
        elif isinstance(w, OptionList) and w.option_count:
            (w.action_first if which == "first" else w.action_last)()
        elif w is not None and hasattr(w, name):
            getattr(w, name)()

    def action_toggle(self, cls: str):
        self.screen_stack[0].toggle_class(cls)

    def action_details(self):
        main = self.screen_stack[0]
        crowded = main.has_class("-narrow") or main.has_class("-compact")
        main.toggle_class("-show-details" if crowded else "-hide-details")

    def show_detail(self, renderable, title: str = "Details"):
        self._q("#details", Static).update(renderable)
        panel = self._q("#details-panel")
        panel.border_title = title
        panel.scroll_home(animate=False)


def run_app(home: Path | None = None):
    RewindApp(home).run()

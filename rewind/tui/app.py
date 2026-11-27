"""`rewind` (on an interactive terminal) / `rewind ui`: the interactive investigation app.

Layout: a sidebar (runs, requests), the main view (timeline, why, pending, state, tree, diff) and a details pane.
Every fact shown comes from rewind.store and rewind.analysis; views.py lays them out.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, OptionList, Static, TabbedContent, TabPane, Tree
from textual.widgets.option_list import Option

from .. import analysis as A
from .. import store
from . import views as V
from .theme import CSS, STYLES

KINDS = [("all events", None), ("http", ("http",)), ("logs", ("log",)), ("errors", ("error",)),
         ("writes", ("mutation",)), ("reads", ("read",)), ("snapshots", ("snapshot",))]
RAW_LIMIT = 20000  # rows the "every event" view shows; the CLI's --raw has no limit


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


class HelpScreen(ModalScreen):
    BINDINGS = [Binding("escape,question_mark,q", "dismiss", "close")]

    def compose(self) -> ComposeResult:
        with Center():
            with VerticalScroll(id="help-card"):
                yield Static(V.help_view())


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
        Binding("q", "quit", "quit"),
        Binding("question_mark", "help", "help"),
        Binding("slash", "search", "search"),
        Binding("w", "why", "why"),
        Binding("p", "view('pending')", "pending"),
        Binding("s", "state", "state"),
        Binding("e", "view('tree')", "tree"),
        Binding("d", "diff", "diff"),
        Binding("b", "baseline", "baseline"),
        Binding("t", "view('timeline')", "timeline", show=False),
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
        self.active: tuple[str, A.Finding] | None = None  # the finding whose evidence ] and [ walk through
        self.ev_cursor = 0
        self.baseline: str | None = None
        self.diff_pair: tuple[str, str] | None = None
        self.why_target: int | None = None

    # ---- layout -------------------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Static(id="topbar")
        with Vertical(id="welcome"):
            with Center():
                yield Static(id="welcome-card")
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                yield Panel(OptionList(id="runs"), title="runs", id="runs-panel")
                yield Panel(OptionList(id="requests"), title="requests", id="requests-panel")
            with Panel(title="timeline", id="main"):
                with TabbedContent(id="views", initial="timeline"):
                    with TabPane("timeline", id="timeline"):
                        yield Static(id="filterbar")
                        yield Input(placeholder="search event text, enter to keep, esc to clear", id="search")
                        yield DataTable(id="table", cursor_type="row", zebra_stripes=False, show_cursor=True)
                    with TabPane("why", id="why"):
                        yield Static(id="why-head")
                        yield OptionList(id="why-list")
                    with TabPane("pending", id="pending"):
                        yield OptionList(id="pending-list")
                    with TabPane("state", id="state"):
                        with VerticalScroll():
                            yield Static(id="state-body")
                    with TabPane("tree", id="tree"):
                        yield Tree("tree", id="tree-view")
                    with TabPane("diff", id="diff"):
                        yield Static(id="diff-head")
                        yield OptionList(id="diff-list")
            with VerticalScroll(id="details-panel", classes="panel"):
                yield Static(id="details")
        yield Footer()

    def on_mount(self):
        self.query_one("#details-panel").border_title = "details"
        t = self.query_one("#table", DataTable)
        for label, key in (("seq", "seq"), ("ms", "ms"), ("req", "req"), (" ", "g"), ("event", "event")):
            t.add_column(label, key=key)
        self.query_one("#tree-view", Tree).show_root = True
        self._layout(self.size.width, self.size.height)
        self.action_reload()

    def on_resize(self, event):
        self._layout(event.size.width, event.size.height)
        if self.current is not None:
            self.call_after_refresh(self.refresh_timeline, True)

    def _layout(self, w: int, h: int):
        self.screen.set_class(120 <= w < 150, "-medium")
        self.screen.set_class(100 <= w < 120, "-compact")
        self.screen.set_class(w < 100, "-narrow")
        self.screen.set_class(h < 30, "-short")

    # ---- runs ---------------------------------------------------------------------------------
    def action_reload(self):
        keep = self.row["id"] if self.row else None
        self.session.reload()
        has = bool(self.session.rows)
        self.query_one("#welcome").display = not has
        self.query_one("#body").display = has
        runs = self.query_one("#runs", OptionList)
        runs.clear_options()
        if not has:
            self.query_one("#welcome-card", Static).update(V.welcome(str(self.session.home)))
            self.row = self.current = self.pend = None
            self._topbar()
            return
        runs.add_options([Option(V.run_option(r), id=r["id"]) for r in self.session.rows])
        self.query_one("#runs-panel").border_title = f"runs [{len(self.session.rows)}]"
        ids = [r["id"] for r in self.session.rows]
        runs.highlighted = ids.index(keep) if keep in ids else 0
        self.open_run(ids[runs.highlighted])
        runs.focus()

    @on(OptionList.OptionHighlighted, "#runs")
    def _run_highlighted(self, ev: OptionList.OptionHighlighted):
        if ev.option_id and (self.row is None or ev.option_id != self.row["id"]):
            self.open_run(ev.option_id)

    def open_run(self, run_id: str, keep_filters: bool = False):
        self.row, self.current, self.pend = self.session.load(run_id)
        if not keep_filters:
            self.req_filter, self.search_text, self.kind_idx, self.raw = None, "", 0, False
            self.query_one("#search", Input).value = ""
        reqs = self.query_one("#requests", OptionList)
        reqs.clear_options()
        if self.current.requests:
            reqs.add_option(Option(V.T(f"[mute]◇[/] [bold]all requests[/]  [dim]{len(self.current.requests)}[/]"), id="all"))
            reqs.add_options([Option(V.request_option(self.current, r, self.pend.states.get(r.id, "")), id=str(r.id))
                              for r in self.current.requests.values()])
            with reqs.prevent(OptionList.OptionHighlighted):
                reqs.highlighted = 0 if self.req_filter is None else 1 + list(self.current.requests).index(self.req_filter)
        else:
            reqs.add_option(Option(V.T("[mute]no HTTP requests in this run[/]"), id="none", disabled=True))
        self.query_one("#requests-panel").border_title = f"requests [{len(self.current.requests)}]"
        errors = self.current.errors
        self.why_target = errors[0].seq if errors else None
        self._topbar()
        self.refresh_timeline()
        self.refresh_why()
        self.refresh_pending()
        if self.query_one("#views", TabbedContent).active == "tree":
            self.refresh_tree()
        if self.query_one("#views", TabbedContent).active == "state":
            self.refresh_state()
        self.call_after_refresh(self._detail_for_focus)

    def _topbar(self):
        base = None
        if self.baseline:
            b = self.session.row(self.baseline)
            base = (b["label"] or b["id"]) if b else None
        self.query_one("#topbar", Static).update(V.header(self.row, self.current, base, str(self.session.home)))

    def _run_summary(self):
        r, run = self.row, self.current
        from rich.console import Group
        counts = {s: sum(v == s for v in self.pend.states.values()) for s in ("completed", "failed", "cancelled", "unresolved")}
        g = V.grid({"style": STYLES["mute"], "no_wrap": True, "width": 9}, {"ratio": 1, "overflow": "fold"})
        g.add_row("command", Text(V.command(r)))
        g.add_row("status", V.T(f"{V.STATUS.get(r['status'], '')} {r['status']}  [mute]exit[/] {r['exit_code']}"))
        g.add_row("events", V.T(f"{r['event_count']:,}  [mute]errors[/] {r['error_count']}"))
        g.add_row("requests", V.T(f"{len(run.requests)}"))
        if run.requests:
            g.add_row("", V.T(f"[ok]●[/] {counts['completed']} completed  [err]✖[/] {counts['failed']} failed"))
            g.add_row("", V.T(f"[write]−[/] {counts['cancelled']} cancelled  [write]◌[/] {counts['unresolved']} unanswered"))
        g.add_row("watch", V.T((", ".join(run.watch) or "[dim]none[/]") + ("  [dim]+ reads[/]" if run.reads_recorded else "")))
        g.add_row("node", V.T(f"{(run.events[0].data or {}).get('node', '?') if run.events and run.events[0].kind == 'run.start' else '?'}"))
        g.add_row("recorded", V.T(f"{r['started_at'] or '?'}  [dim]{V.R.ago(r['started_at'])}[/]"))
        lines = [V.T(f"[id]{r['id']}[/]" + (f" [label]{r['label']}[/]" if r["label"] else "")), Text(), g, Text()]
        if not self.pend.complete:
            lines += [V.T("[write]◌ recording incomplete[/] [mute]: events after the last one may be lost, so absence "
                          "of an event proves nothing[/]"), Text()]
        lines.append(V.T("[dim]enter[/] [mute]investigate[/]   [dim]b[/] [mute]baseline for diff[/]"))
        self.show_detail(Group(*lines), "run")

    @on(OptionList.OptionSelected, "#runs")
    def _run_selected(self, ev):
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
            if self.query_one("#views", TabbedContent).active == "tree":
                self.refresh_tree()
        if ev.option_list.has_focus:
            self._request_detail(rid)

    def _request_detail(self, rid: int | None):
        if rid is None:
            self._run_summary()
        else:
            r = self.current.requests[rid]
            st = self.pend.states.get(rid, "")
            mine = [f for f in self.pend.findings if f"request {r.label}" in f.text or f"#{rid} " in f.text]
            from rich.console import Group
            parts = [V.request_option(self.current, r, st), Text(), V.T(f"[mute]arrived[/]  seq {r.inbound.seq}  "
                     f"[dim]{r.inbound.t / 1000:.1f} ms[/]")]
            if r.outbound:
                parts.append(V.T(f"[mute]responded[/] seq {r.outbound.seq}  status {r.outbound.data.get('status')}  "
                                 f"[dim]{r.outbound.data.get('ms', 0):.1f} ms[/]"))
            parts += [Text()] + [V.finding_option(f) for f in mine]
            self.show_detail(Group(*parts), "request")

    @on(OptionList.OptionSelected, "#requests")
    def _req_selected(self, ev):
        self.action_view("timeline")
        self.action_focus_panel("main")

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
        t = self.query_one("#table", DataTable)
        cur = self.shown[t.cursor_row] if keep_cursor and self.shown and 0 <= t.cursor_row < len(self.shown) else None
        rows = self.timeline_rows()
        width = max(t.size.width - 28, 20)
        t.clear()
        for e in rows:
            t.add_row(*V.timeline_cells(self.current, e, width), key=str(e.seq))
        self.shown = [e.seq for e in rows]
        if cur in self.shown:
            t.move_cursor(row=self.shown.index(cur), animate=False)
        bits = [KINDS[self.kind_idx][0]]
        if self.req_filter:
            bits.append(f"request #{self.req_filter}")
        if self.callbacks:
            bits.append("+ callbacks")
        if self.raw:
            bits = ["every recorded event" + (f" (first {RAW_LIMIT:,})" if len(self.current.events) > RAW_LIMIT else "")]
        if self.search_text:
            bits.append(f"“{self.search_text}”")
        self.query_one("#filterbar", Static).update(V.T(
            f"[mute]{' · '.join(bits)}[/]  [dim]{len(rows):,} of {len(self.current.events):,} events  "
            f"/ search · f kind · c callbacks · a all[/]"))
        if not rows:
            self.show_detail(V.T("[mute]no events match: esc clears the search and filters[/]"), "timeline")
        self._main_title()

    @on(DataTable.RowHighlighted, "#table")
    def _row_highlighted(self, ev: DataTable.RowHighlighted):
        if self.current is None or ev.row_key is None or ev.row_key.value is None or not ev.data_table.has_focus:
            return
        self._row_detail(int(ev.row_key.value))

    def _row_detail(self, seq: int):
        e = self.current.by_seq.get(seq)
        if e is None:
            return
        body = V.event_detail(self.current, e)
        if self.active and e.seq in self.active[1].evidence:
            from rich.console import Group
            f = self.active[1]
            i = f.evidence.index(e.seq)
            body = Group(V.T(f"{V.R.LEVEL[f.level]} [mute]evidence {i + 1} of {len(f.evidence)} for:[/]"),
                         V.T(f"[{V.R.LEVEL_TEXT[f.level]}]{V.escape(f.text)}[/]"), Text(), body)
        self.show_detail(body, f"seq {e.seq}")

    def selected_seq(self) -> int | None:
        t = self.query_one("#table", DataTable)
        return self.shown[t.cursor_row] if self.shown and 0 <= t.cursor_row < len(self.shown) else None

    def action_search(self):
        if self.current is None:
            return
        self.action_view("timeline")
        s = self.query_one("#search", Input)
        s.add_class("-shown")
        s.focus()

    @on(Input.Changed, "#search")
    def _search_changed(self, ev: Input.Changed):
        self.search_text = ev.value.strip()
        self.refresh_timeline()

    @on(Input.Submitted, "#search")
    def _search_submitted(self, ev):
        self.query_one("#table", DataTable).focus()

    def action_kind_filter(self):
        if self.current is None:
            return
        self.kind_idx = (self.kind_idx + 1) % len(KINDS)
        self.raw = False
        self.action_view("timeline")
        self.refresh_timeline()

    def action_callbacks(self):
        if self.current is not None:
            self.callbacks, self.raw = not self.callbacks, False
            self.refresh_timeline()

    def action_raw(self):
        if self.current is not None:
            self.raw = not self.raw
            self.refresh_timeline()

    def action_clear(self):
        s = self.query_one("#search", Input)
        if self.current is None:
            return
        changed = self.search_text or self.kind_idx or self.raw or self.callbacks or s.has_class("-shown")
        s.value, self.search_text = "", ""
        s.remove_class("-shown")
        self.kind_idx, self.raw, self.callbacks = 0, False, False
        if changed:
            self.refresh_timeline()
            self.query_one("#table", DataTable).focus()

    # ---- findings: why / pending / diff ---------------------------------------------------------
    def _fill(self, name: str, findings: list[A.Finding], empty: str):
        ol = self.query_one(f"#{name}-list", OptionList)
        ol.clear_options()
        self.lists[name] = findings
        if findings:
            for i, f in enumerate(findings):
                if i:
                    ol.add_option(None)  # a hairline between findings: long ones wrap, and must stay apart
                ol.add_option(Option(V.finding_option(f), id=str(i)))
            with ol.prevent(OptionList.OptionHighlighted):
                ol.highlighted = 0
        else:
            ol.add_option(Option(V.T(f"[mute]{empty}[/]"), id="empty", disabled=True))

    def refresh_why(self):
        head = self.query_one("#why-head", Static)
        if self.why_target is None:
            head.update(V.T("[ok]●[/] [mute]no errors recorded in this run[/]"))
            self._fill("why", [], "Select any event in the timeline and press w to explain it.")
            return
        inv = A.investigate(self.current, self.current.by_seq[self.why_target])
        errors = self.current.errors
        pos = f"error {errors.index(inv.target) + 1} of {len(errors)}" if inv.target in errors else f"event seq {inv.target.seq}"
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
        if oid in (None, "empty"):
            return
        f = self.lists[name][int(oid)]
        self.active, self.ev_cursor = (name, f), 0
        self.show_detail(V.finding_detail(self._run_for(f), f, None), f"{V.LEVEL_NAME[f.level]} finding")

    def on_descendant_focus(self, event):
        self.call_after_refresh(self._detail_for_focus)

    def _detail_for_focus(self):
        """The details pane always describes the focused panel's selected item."""
        w = self.focused
        if self.current is None or w is None:
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
        elif w.id in ("why-list", "pending-list", "diff-list"):
            self._finding_detail(w)
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
            self.notify("select a finding with evidence first (why, pending or diff)", severity="warning")
            return
        n = len(self.active[1].evidence)
        self.ev_cursor = (self.ev_cursor + step) % n
        self._jump_evidence()

    def _jump_evidence(self):
        name, f = self.active
        seq = f.evidence[self.ev_cursor]
        if f.run and self.diff_pair:
            target = self.diff_pair[0] if f.run == "A" else self.diff_pair[1]
            if target != self.row["id"]:
                self._select_run(target)
        self.jump(seq)

    def _select_run(self, run_id: str):
        runs = self.query_one("#runs", OptionList)
        ids = [r["id"] for r in self.session.rows]
        self.open_run(run_id)
        with runs.prevent(OptionList.OptionHighlighted):
            runs.highlighted = ids.index(run_id)

    def jump(self, seq: int):
        """Show event `seq` in the timeline, widening the filters only as far as needed to reach it."""
        if seq not in self.current.by_seq:
            self.notify(f"seq {seq} is not in this recording", severity="error")
            return
        if seq not in self.shown:
            self.search_text, self.kind_idx = "", 0
            self.query_one("#search", Input).value = ""
            if seq not in [e.seq for e in self.timeline_rows()]:
                self.req_filter = None
            if seq not in [e.seq for e in self.timeline_rows()]:
                self.raw = True
                self.notify(f"showing every recorded event to reach seq {seq}")
            self.refresh_timeline(keep_cursor=False)
        self.action_view("timeline")
        t = self.query_one("#table", DataTable)
        if seq in self.shown:
            t.move_cursor(row=self.shown.index(seq), animate=False)
            t.focus()

    # ---- state / tree / diff ------------------------------------------------------------------
    def action_why(self):
        if self.current is None:
            return
        views = self.query_one("#views", TabbedContent)
        seq = self.selected_seq()
        e = self.current.by_seq.get(seq) if seq is not None else None
        explainable = e is not None and not e.kind.startswith(("run.", "async.")) and e.kind not in ("instrument", "source")
        if views.active == "timeline" and self.focused is self.query_one("#table") and explainable:
            self.why_target = seq
        elif self.why_target is None and self.current.errors:
            self.why_target = self.current.errors[0].seq
        self.refresh_why()
        self.action_view("why")
        self.query_one("#why-list", OptionList).focus()

    def action_state(self):
        if self.current is None:
            return
        self.refresh_state()
        self.action_view("state")

    def refresh_state(self):
        seq = self.selected_seq()
        if seq is None:
            seq = self.current.events[-1].seq if self.current.events else None
        if seq is None:
            return
        self.query_one("#state-body", Static).update(V.state_view(self.current, A.state_at(self.current, seq)))

    def refresh_tree(self):
        tree = self.query_one("#tree-view", Tree)
        tree.clear()
        root_aid = self.current.requests[self.req_filter].anchor if self.req_filter else 1
        node, pruned = A.build_tree(self.current, root_aid)
        title = "main module" if root_aid == 1 else self.current.requests[self.req_filter].label
        tree.root.set_label(V.T(V.R.tree_label(self.current, node, title)))
        tree.root.data = ("aid", node.aid)

        def add(parent, n):
            for e in n.events:
                parent.add_leaf(V.T(f"[{V.R.kind_style(e.kind)}]{V.R.GLYPH.get(e.kind, '·')}[/] {V.R.event_text(self.current, e)}"),
                                data=("seq", e.seq))
            for c in n.children:
                add(parent.add(V.T(V.R.tree_label(self.current, c, title)), data=("aid", c.aid), expand=True), c)
        add(tree.root, node)
        tree.root.expand()
        if pruned:
            tree.root.add_leaf(V.T(f"[dim]{pruned} quiet async resources hidden[/]"))

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
            self.show_detail(V.event_detail(self.current, e), f"seq {e.seq}")

    def action_baseline(self):
        if self.row is None:
            return
        self.baseline = self.row["id"]
        self._topbar()
        self.notify(f"baseline: {self.row['label'] or self.row['id']}. Select another run and press d to compare")

    def action_diff(self):
        if self.row is None:
            return
        if not self.baseline or self.baseline == self.row["id"]:
            self.query_one("#diff-head", Static).update(V.T(
                "[mute]Press[/] [green]b[/] [mute]on a run to make it the baseline, then select another run and press[/] "
                "[green]d[/][mute]. Record both with the same --watch to compare their writes.[/]"))
            self._fill("diff", [], "no comparison yet")
            self.action_view("diff")
            return
        a_row, a_run, _ = self.session.load(self.baseline)
        res = A.diff(a_run, self.current)
        self.diff_pair = (self.baseline, self.row["id"])
        name = lambda r: f"[id]{r['id']}[/]" + (f" [label]{r['label']}[/]" if r["label"] else "")
        self.query_one("#diff-head", Static).update(V.diff_view(res, name(a_row), name(self.row)))
        self._fill("diff", res.findings, "no findings")
        self.action_view("diff")
        self.query_one("#diff-list", OptionList).focus()

    # ---- navigation ---------------------------------------------------------------------------
    def action_view(self, name: str):
        if self.current is None:
            return
        views = self.query_one("#views", TabbedContent)
        if views.active != name:
            views.active = name
        if name == "tree":
            self.refresh_tree()
        if name == "state":
            self.refresh_state()
        self._main_title()

    @on(TabbedContent.TabActivated, "#views")
    def _tab(self, ev):
        name = ev.pane.id if ev.pane else None
        if name == "tree" and self.current is not None:
            self.refresh_tree()
        if name == "state" and self.current is not None:
            self.refresh_state()
        self._main_title()

    def _main_title(self):
        views = self.query_one("#views", TabbedContent)
        main = self.query_one("#main")
        main.border_title = "investigate"
        main.border_subtitle = {"timeline": "w why · s state · enter details", "why": "enter jump · ] [ evidence",
                                "pending": "enter jump · ] [ evidence", "state": "at the timeline's selected seq",
                                "tree": "who scheduled whom", "diff": "baseline (A) vs selected run (B)"}.get(views.active, "")

    def action_focus_panel(self, name: str):
        if name == "main":
            active = self.query_one("#views", TabbedContent).active
            target = {"timeline": "#table", "why": "#why-list", "pending": "#pending-list", "tree": "#tree-view",
                      "diff": "#diff-list", "state": "#state-body"}.get(active, "#table")
            w = self.query_one(target)
            (w.parent if target == "#state-body" else w).focus()
        else:
            self.query_one({"runs": "#runs", "requests": "#requests", "details": "#details-panel"}[name]).focus()

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
            w.highlighted = 0 if which == "first" else w.option_count - 1
        elif w is not None and hasattr(w, name):
            getattr(w, name)()

    def action_toggle(self, cls: str):
        self.screen.toggle_class(cls)

    def action_details(self):
        # wide: details are shown unless hidden; narrow: hidden unless shown (they would crowd out the main view)
        crowded = self.screen.has_class("-narrow") or self.screen.has_class("-compact")
        self.screen.toggle_class("-show-details" if crowded else "-hide-details")

    def action_help(self):
        self.push_screen(HelpScreen())

    def show_detail(self, renderable, title: str = "details"):
        self.query_one("#details", Static).update(renderable)
        panel = self.query_one("#details-panel")
        panel.border_title = title
        panel.scroll_home(animate=False)


def run_app(home: Path | None = None):
    RewindApp(home).run()

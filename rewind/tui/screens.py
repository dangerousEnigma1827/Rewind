"""The screens around an investigation: Home (start here), Record (run a program under Rewind) and Help."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Input, OptionList, RichLog, Static
from textual.widgets.option_list import Option

from .. import recording
from . import views as V

SAMPLE = ("node demo/traffic.js", "sample", "currentCart")  # the Phantom Discount demo, when run from a Rewind checkout


def sample_available(cwd: Path) -> bool:
    return (cwd / "demo" / "traffic.js").exists() and (cwd / "demo" / "checkout.js").exists()


class HelpScreen(ModalScreen):
    """Keyboard shortcuts: a centered card whose body scrolls on short terminals; two columns when there's room."""
    BINDINGS = [Binding("escape,question_mark,q", "dismiss", "close")]
    CHROME = 2 + 3 + 3  # card border, head (with its margins), foot (with its margins)

    def compose(self) -> ComposeResult:
        with Vertical(id="help-card"):
            yield Static(id="help-head")
            with VerticalScroll(id="help-body"):
                yield Static(id="help-content")
            yield Static(id="help-foot")

    def on_mount(self):
        self._layout(self.app.size.width, self.app.size.height)

    def on_resize(self, event):
        self._layout(event.size.width, event.size.height)

    def _layout(self, width: int, height: int):
        card_w = min(100, int(width * 0.96))
        inner = max(20, card_w - 2 - 4)  # border, padding
        content = V.help_content(two_columns=inner >= 84)
        console = self.app.console
        lines = len(console.render_lines(content, console.options.update_width(inner), pad=False))
        room = max(3, height - 2 - self.CHROME)
        body = self.query_one("#help-body")
        body.styles.height = min(lines, room)
        self.query_one("#help-card").styles.width = card_w
        self.query_one("#help-content", Static).update(content)
        self.query_one("#help-head", Static).update(V.help_head())
        self.query_one("#help-foot", Static).update(V.help_foot(scrolls=lines > room))


# ---- home --------------------------------------------------------------------------------------
class HomeScreen(Screen):
    """Start here: what Rewind is, the one thing to do first (record), the sample, and recent recordings."""
    BINDINGS = [Binding("n", "record", "record a program"), Binding("s", "sample", "try the sample", show=False),
                Binding("r", "reload", "reload", show=False),
                Binding("j", "cursor(1)", show=False), Binding("k", "cursor(-1)", show=False)]

    def compose(self) -> ComposeResult:
        yield Static(id="home-top", classes="topbar")
        with VerticalScroll(id="home"):
            with Vertical(id="home-col"):
                yield Static(id="wordmark")
                yield Static(V.T("[text2]Record your Node.js program once, then find out why it did what it did: which "
                                 "request an error belonged to, what ran before it, and who changed the data it used.[/]"),
                             id="tagline")
                with Vertical(classes="card", id="record-card"):
                    yield Static(V.T("[text2]Start your app the way you normally do, e.g.[/] [text]node server.js[/][text2]. "
                                     "Rewind runs it with its recorder attached, and you investigate the recording here.[/]"),
                                 classes="desc")
                    with Horizontal(id="record-row"):
                        yield Button("Record a program", id="act-record", variant="primary")
                        yield Static(V.T("[dim]or press[/] [cap] n [/]"), classes="hint")
                with Vertical(classes="card", id="recent-card"):
                    yield Static(id="recent-intro")
                    yield OptionList(id="recent")
                with Horizontal(id="sample-row"):
                    yield Static(V.T("[text3]New to Rewind?[/]"))
                    yield Button("Try the sample recording", id="act-sample", classes="-link")
                    yield Static(V.T("[cap] s [/]"))
        yield Footer()

    def on_mount(self):
        self.query_one("#record-card").border_title = "Record a program"
        self.query_one("#recent-card").border_title = "Your recordings"
        self.query_one("#sample-row").display = sample_available(Path.cwd())
        self.refresh_runs()

    def on_resize(self, event):
        self.query_one("#wordmark", Static).update(V.wordmark(event.size.width))
        self.set_class(event.size.height < 32, "-short")  # small terminals: the actions and runs, not the banner

    def refresh_runs(self):
        app = self.app
        rows = app.session.rows
        self.query_one("#wordmark", Static).update(V.wordmark(self.size.width or 100))
        self.query_one("#home-top", Static).update(V.topbar("home", right=f"[dim]recordings in {app.session.home}[/]"))
        recent = self.query_one("#recent", OptionList)
        recent.clear_options()
        intro = self.query_one("#recent-intro", Static)
        if rows:
            intro.update(V.T(f"[text3]{V.R.plural(len(rows), 'recording')}, newest first. Select one and press "
                             f"[key]enter[/] [text3]to investigate it.[/]"))
            recent.add_options([Option(V.run_option(r, wide=True), id=r["id"]) for r in rows])
            recent.display = True
            recent.highlighted = 0
            recent.focus()
        else:
            intro.update(V.T("[text2]No recordings yet.[/] [text3]They'll appear here, kept in[/] [loc]"
                             f"{app.session.home}[/][text3] (next to where you start Rewind).[/]"))
            recent.display = False
            self.query_one("#act-record", Button).focus()

    @on(Button.Pressed, "#act-record")
    def action_record(self):
        self.app.push_screen(RecordScreen())

    @on(Button.Pressed, "#act-sample")
    def action_sample(self):
        if sample_available(Path.cwd()):
            self.app.push_screen(RecordScreen(*SAMPLE, sample=True))
        else:
            self.notify("The sample needs a Rewind checkout: start rewind in the folder that contains demo/", severity="warning")

    @on(OptionList.OptionSelected, "#recent")
    def _selected(self, ev):
        self.app.open_run_from_home(ev.option_id)

    def action_open(self):
        recent = self.query_one("#recent", OptionList)
        if recent.display and recent.highlighted is not None:
            self.app.open_run_from_home(recent.get_option_at_index(recent.highlighted).id)

    def action_reload(self):
        self.app.session.reload()
        self.refresh_runs()

    def action_cursor(self, step: int):
        w = self.focused
        if isinstance(w, OptionList):
            (w.action_cursor_down if step > 0 else w.action_cursor_up)()


# ---- record ------------------------------------------------------------------------------------
class RecordScreen(Screen):
    """Run a program under the recorder (rewind.recording, the same code as `rewind record`), then open the run."""
    BINDINGS = [Binding("escape", "back", "back / stop"), Binding("ctrl+s", "start", "start recording")]

    def __init__(self, command: str = "", label: str = "", watch: str = "", sample: bool = False):
        super().__init__()
        self.initial = (command, label, watch)
        self.sample = sample
        self.proc: subprocess.Popen | None = None
        self.rec: recording.Recording | None = None
        self.state = "form"   # form | running | stopping | done | failed
        self.result_run: str | None = None
        self.started_at = 0.0

    def compose(self) -> ComposeResult:
        yield Static(id="rec-top", classes="topbar")
        with VerticalScroll(id="record"):
            with Vertical(id="record-col"):
                with Vertical(id="form"):
                    yield Static(id="form-intro")
                    yield Static("Command", classes="field-label")
                    yield Static(V.T(f"[text3]How you normally start your program. It runs in[/] [loc]{Path.cwd()}[/]"
                                     "[text3], with your usual environment.[/]"), classes="field-help")
                    yield Input(placeholder="node server.js --port 3000", id="cmd")
                    yield Static("Label  (optional)", classes="field-label")
                    yield Static(V.T("[text3]A name to find this run again, e.g. [text2]bad[/] or [text2]before-fix[/].[/]"),
                                 classes="field-help")
                    yield Input(placeholder="bad", id="label")
                    yield Static("Watch variables  (optional)", classes="field-label")
                    yield Static(V.T("[text3]Top-level variables in your own .js files, comma-separated. Rewind records "
                                     "every write and read of them, which is how it shows which request changed shared "
                                     "state. Leave empty if you're not sure.[/]"), classes="field-help")
                    yield Input(placeholder="currentCart, sessions", id="watch")
                    yield Static(id="preview")
                    yield Static(id="problems")
                    with Horizontal(id="form-buttons"):
                        yield Button("Start recording", id="start", variant="primary")
                        yield Button("Cancel", id="cancel")
                yield Static(id="run-status")
                yield RichLog(id="output", wrap=True, markup=False, highlight=False, max_lines=5000)
                yield Static(id="result")
                with Horizontal(id="result-buttons"):
                    yield Button("Open this run", id="open", variant="primary")
                    yield Button("Record another", id="again")
                    yield Button("Home", id="go-home")
        yield Footer()

    def on_mount(self):
        cmd, label, watch = self.initial
        self.query_one("#cmd", Input).value = cmd
        self.query_one("#label", Input).value = label
        self.query_one("#watch", Input).value = watch
        self.query_one("#rec-top", Static).update(V.topbar("new recording", right="[key]esc[/] [dim]back[/]"))
        self.query_one("#form-intro", Static).update(V.T(
            "[text2]This sample records the bundled Phantom Discount service with three overlapping orders and watches "
            "[text]currentCart[/], the variable they share. Press[/] [key]enter[/] [text2]to start.[/]" if self.sample else
            "[text2]Rewind starts your program with its recorder attached. Use it normally (send it requests, let it "
            "finish or crash). When it exits, or you stop it, the recording is saved.[/]"))
        self._show("form")
        self._update_preview()
        (self.query_one("#start", Button) if self.sample else self.query_one("#cmd", Input)).focus()

    def _show(self, state: str):
        self.state = state
        self.query_one("#form").display = state == "form"
        self.query_one("#run-status").display = state != "form"
        self.query_one("#output").display = state != "form"
        self.query_one("#result").display = state in ("done", "failed")
        self.query_one("#result-buttons").display = state in ("done", "failed")
        if state in ("done", "failed"):
            self.query_one("#open").display = self.result_run is not None
            (self.query_one("#open") if self.result_run else self.query_one("#again")).focus()

    def _values(self):
        cmd = recording.split_command(self.query_one("#cmd", Input).value.strip())
        label = self.query_one("#label", Input).value.strip() or None
        watch = ",".join(w.strip() for w in self.query_one("#watch", Input).value.split(",") if w.strip()) or None
        return cmd, label, watch

    @on(Input.Changed)
    def _update_preview(self, *_):
        try:
            cmd, label, watch = self._values()
        except ValueError:  # an unclosed quote while typing
            self.query_one("#preview", Static).update(V.T("[dim]same as: (finish the quoted part)[/]"))
            return
        shown = cmd if not cmd or os.path.basename(cmd[0]).lower().removesuffix(".exe") == "node" else ["node"] + cmd
        self.query_one("#preview", Static).update(V.T(
            "[dim]same as[/]  [text2]" + V.escape(recording.cli_preview(shown, label, watch)) + "[/]" if cmd else
            "[dim]same as  rewind record -- node <your script>[/]"))
        self.query_one("#problems", Static).update("")

    @on(Input.Submitted)
    def _submitted(self, ev: Input.Submitted):
        self.action_start()

    @on(Button.Pressed, "#start")
    def action_start(self):
        if self.state != "form":
            return
        try:
            cmd, label, watch = self._values()
        except ValueError:
            self.query_one("#problems", Static).update(V.T("[err]× a quote isn't closed in the command[/]"))
            return
        errs = recording.problems(cmd, watch, Path.cwd())
        if errs:
            self.query_one("#problems", Static).update(V.T("\n".join(f"[err]×[/] [err.t]{V.escape(e)}[/]" for e in errs)))
            return
        self.rec = recording.prepare(cmd, label, watch, self.app.session.home)
        self.query_one("#output", RichLog).clear()
        self.started_at = time.perf_counter()
        self._show("running")
        self._status()
        self.set_interval(0.5, self._status, name="ticker")
        self._run(self.query_one("#output", RichLog))

    def _status(self):
        if self.state not in ("running", "stopping"):
            return
        secs = time.perf_counter() - self.started_at
        word = "[warn]◌ Stopping[/]" if self.state == "stopping" else "[uv.b]● Recording[/]"
        self.query_one("#run-status", Static).update(V.T(
            f"{word}  [text]{V.escape(' '.join(self.rec.cmd))}[/]  [dim]{secs:.1f}s · run {self.rec.run_id}[/]\n"
            "[text3]Your program's output appears below. It runs without keyboard input.[/]  [key]esc[/] [text3]stop[/]"))

    @work(thread=True, exclusive=True, group="record")
    def _run(self, log: RichLog):
        rec = self.rec
        started = datetime.now().isoformat(timespec="seconds")
        flags = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        try:
            self.proc = subprocess.Popen(rec.args, env=rec.env, cwd=Path.cwd(), stdin=subprocess.DEVNULL,
                                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                         encoding="utf-8", errors="replace", bufsize=1, **flags)
        except OSError as e:
            self.app.call_from_thread(self._finish, None, f"could not start {rec.cmd[0]!r}: {e.strerror or e}")
            return
        for line in self.proc.stdout:
            self.app.call_from_thread(log.write, Text(line.rstrip("\n")))
        code = self.proc.wait()
        try:
            row = recording.store_run(rec, code, started, datetime.now().isoformat(timespec="seconds"))
        except recording.NoOutput as e:
            self.app.call_from_thread(self._finish, None, str(e))
            return
        self.app.call_from_thread(self._finish, row, None)

    def action_stop(self):
        p = self.proc
        if self.state != "running" or p is None:
            return
        self.state = "stopping"
        self._status()
        if os.name == "nt":
            p.terminate()  # no SIGINT across a process group on Windows: the recording ends where it was cut
        else:
            p.send_signal(signal.SIGINT)  # the recorder flushes on SIGINT; force it if the program ignores that
            threading.Timer(5, lambda: p.poll() is None and p.kill()).start()

    def _finish(self, row, error: str | None):
        stopped = self.state == "stopping"
        self.result_run = row["id"] if row else None
        secs = time.perf_counter() - self.started_at
        self.query_one("#run-status", Static).update(V.T(
            f"{'[warn]◌ Stopped[/]' if stopped else '[text2]■ Finished[/]'}  [text]{V.escape(' '.join(self.rec.cmd))}[/]  "
            f"[dim]{secs:.1f}s · run {self.rec.run_id}[/]\n[text3]Output of your program:[/]"))
        if row:
            self.app.session.reload()
            code = row["exit_code"]
            how = ("[warn]You stopped it[/][text2], so the recording ends where the program was stopped "
                   "(later events may be missing).[/]" if stopped else
                   "[text2]It exited normally.[/]" if code == 0 else
                   f"[text2]The program exited with code {code}. That's fine: Rewind recorded what happened, "
                   "including the failure.[/]")
            self.query_one("#result", Static).update(V.T(
                f"[ok]● Recorded[/] [id]{row['id']}[/]" + (f" [label]{V.escape(row['label'])}[/]" if row["label"] else "")
                + f"  [text2]{row['event_count']:,} events · {V.R.plural(row['error_count'], 'error')}[/]\n{how}\n"
                "[text3]Open it to see what happened.[/]"))
            self._show("done")
        else:
            self.query_one("#result", Static).update(V.T(
                f"[err]× Nothing was recorded[/]  [err.t]{V.escape(error or '')}[/]\n"
                "[text3]Check the command and its output above, then try again.[/]"))
            self._show("failed")

    def on_unmount(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()  # never leave the program running behind the app

    def action_back(self):
        if self.state == "running":
            self.action_stop()
        elif self.state != "stopping":
            self.app.pop_screen()

    @on(Button.Pressed, "#cancel")
    def _cancel(self):
        self.app.pop_screen()

    @on(Button.Pressed, "#go-home")
    def _home(self):
        self.app.pop_screen()

    @on(Button.Pressed, "#again")
    def _again(self):
        self.result_run = None
        self._show("form")
        self.query_one("#cmd", Input).focus()

    @on(Button.Pressed, "#open")
    def _open(self):
        if self.result_run:
            self.app.open_run_from_home(self.result_run)

"""The interactive TUI, driven headless with Textual's pilot over real recordings of the demo.

Covers the first-time journey (empty home, recording, opening the run), investigation, comparison, keyboard-only
use, the help modal, terminal sizes and the Ultraviolet dark theme.
"""
import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from rich.style import Style

from conftest import FIX, RECORDER, ROOT
from rewind import analysis as A
from rewind import store
from rewind.tui import theme as TH
from rewind.tui import views as V
from rewind.tui.app import RewindApp
from rewind.tui.screens import SAMPLE, HelpScreen, HomeScreen, RecordScreen


def _record(out: Path, fixture: str, env=None, kill_when=None) -> Path:
    e = {**os.environ, "REWIND_OUT": str(out), **(env or {})}
    p = subprocess.Popen(["node", "--require", str(RECORDER), str(FIX / fixture)], env=e, cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if kill_when:
        deadline = time.time() + 10
        while time.time() < deadline and not (out.exists() and kill_when(out.read_text(encoding="utf-8"))):
            time.sleep(0.05)
        p.kill()
    p.wait(timeout=30)
    return out


@pytest.fixture(scope="module")
def home(tmp_path_factory) -> Path:
    h = tmp_path_factory.mktemp("tui") / "home"
    db = store.connect(h)
    demo = "../../demo/traffic.js"
    runs = [("good", demo, {"REWIND_WATCH": "currentCart", "DEMO_SEQUENTIAL": "1"}, None),
            ("nowatch", demo, {}, None),
            ("held", "stall.js", {"STALL_HOLD": "1"}, lambda s: "error.logged" in s),
            ("bad", demo, {"REWIND_WATCH": "currentCart"}, None)]
    for i, (label, fx, env, kill) in enumerate(runs):
        raw = _record(h / "runs" / f"{label}.ndjson", fx, env, kill)
        store.ingest(db, f"{label}0000", raw, label=label, started_at=f"2026-11-27T10:00:0{i}")
    db.close()
    return h


def drive(home: Path, script, size=(160, 45)):
    """Run the app headless; `script(app, pilot)` is an async function doing the interaction."""
    async def main():
        app = RewindApp(home)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await script(app, pilot)
    asyncio.run(main())


def text_of(widget) -> str:
    """The plain text a Static shows (its content is a Rich renderable or a string)."""
    import io
    from rich.console import Console
    c = Console(width=300, record=True, file=io.StringIO())
    c.print(widget.content)
    return c.export_text()


async def press(pilot, *keys):
    for k in keys:
        await pilot.press(k)
        await pilot.pause()


async def investigate(app, pilot, label="bad"):
    """From Home, open the recording labelled `label` (the newest is highlighted first)."""
    assert isinstance(app.screen, HomeScreen)
    recent = app.screen.query_one("#recent")
    while app.session.rows[recent.highlighted]["label"] != label:
        await press(pilot, "down")
    await press(pilot, "enter")
    assert not isinstance(app.screen, HomeScreen) and app.row["label"] == label


async def wait_recording(app, pilot, timeout=20):
    screen = app.screen
    deadline = time.time() + timeout
    while screen.state not in ("done", "failed") and time.time() < deadline:
        await pilot.pause(0.1)
    await pilot.pause()
    assert screen.state in ("done", "failed"), screen.state


# ---- theme -------------------------------------------------------------------------------------------
def _lum(hex_: str) -> float:
    def ch(v):
        v = int(v, 16) / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(hex_[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_ultraviolet_theme_is_strictly_dark_and_readable():
    c = TH.C
    assert c["bg"] == "#08060D" and c["uv"] == "#7F5AF0" and c["uv.hi"] == "#8D6CFF"  # brand tokens (website, CLI)
    assert all(_lum(b) < 0.03 for b in TH.BACKGROUNDS), "every surface is near-black"
    contrast = lambda a, b: (max(_lum(a), _lum(b)) + 0.05) / (min(_lum(a), _lum(b)) + 0.05)
    for ink in ("text", "text2", "text3", "uv.hi", "ok", "err", "warn", "r1", "r2", "r3", "r4"):
        assert contrast(c[ink], c["bg"]) >= 4.5 and contrast(c[ink], c["panel"]) >= 4.5, ink
    assert TH.THEME.dark and TH.THEME.background == c["bg"] and TH.THEME.primary == c["uv"]


def test_markup_resolves_to_concrete_styles():
    t = V.T("[mute]muted[/] [kind.read]read[/] [err.t]err[/] [r2]#2[/] [key]n[/] [eyebrow]X[/]")
    assert all(isinstance(s.style, Style) and s.style.color is not None for s in t.spans)


# ---- first-time experience -------------------------------------------------------------------------------
def test_empty_home_offers_recording_and_creates_nothing(tmp_path):
    empty = tmp_path / "nothing-here"

    async def script(app, pilot):
        assert isinstance(app.screen, HomeScreen) and app.theme == "ultraviolet"
        assert app.focused.id == "act-record"  # the first thing to do is focused
        assert not app.screen.query_one("#recent").display
        await press(pilot, "w", "p", "d", "b", "slash", "right_square_bracket", "f", "e", "t", "3")  # nothing breaks
        assert isinstance(app.screen, HomeScreen)
        await press(pilot, "enter")
        assert isinstance(app.screen, RecordScreen) and app.focused.id == "cmd"
        await press(pilot, "escape")
        assert isinstance(app.screen, HomeScreen)
    drive(empty, script)
    assert not empty.exists()  # looking never creates a REWIND_HOME


def test_returning_user_opens_a_recording_at_the_overview(home):
    async def script(app, pilot):
        assert isinstance(app.screen, HomeScreen) and app.focused.id == "recent"
        assert [r["label"] for r in app.session.rows] == ["bad", "held", "nowatch", "good"]
        await investigate(app, pilot, "bad")
        assert app.query_one("#views").active == "overview" and app.focused.id == "overview-list"
        ids = [it.id for it in app.overview_items if it.id]
        assert ids[0].startswith("err:") and any(i.startswith("req:") for i in ids) and any(i.startswith("find:") for i in ids)
        await press(pilot, "enter")  # the first error -> Explain
        assert app.query_one("#views").active == "why" and app.why_target == app.current.errors[0].seq
        await press(pilot, "h")
        assert isinstance(app.screen, HomeScreen)
    drive(home, script)


def test_overview_finding_leads_to_its_evidence(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        ol = app.query_one("#overview-list")
        target = next(it.id for it in app.overview_items if it.id and it.id.startswith("find:"))
        while ol.get_option_at_index(ol.highlighted).id != target:
            await press(pilot, "down")
        f = app.active[1]
        await press(pilot, "enter")
        assert app.query_one("#views").active == "timeline" and app.selected_seq() == f.evidence[0]
    drive(home, script)


# ---- recording ------------------------------------------------------------------------------------------
def _fill(app, cmd, label="", watch=""):
    s = app.screen
    s.query_one("#cmd").value, s.query_one("#label").value, s.query_one("#watch").value = cmd, label, watch


def test_recording_a_program_and_opening_it(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    h = tmp_path / "home"

    async def script(app, pilot):
        await press(pilot, "n")
        _fill(app, "node tests/fixtures/throw_timer.js", "first", "")
        await pilot.pause()
        assert "rewind record -l first -- node tests/fixtures/throw_timer.js" in text_of(app.screen.query_one("#preview"))
        await press(pilot, "ctrl+s")
        assert app.screen.state in ("running", "done")
        await wait_recording(app, pilot)
        s = app.screen
        assert s.state == "done" and s.result_run and app.focused.id == "open"
        assert "exited with code 1" in text_of(s.query_one("#result"))  # a crash is recorded, not a failure
        await press(pilot, "enter")
        assert app.row["id"] == s.result_run and app.row["label"] == "first" and app.current.errors
        assert app.query_one("#views").active == "overview"
    drive(h, script)
    assert store.runs(store.connect(h))[0]["label"] == "first"


def test_invalid_commands_are_explained_before_anything_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    h = tmp_path / "home"

    async def script(app, pilot):
        await press(pilot, "n")
        for cmd, why in (("", "enter the command"), ("node tests/fixtures/nope.js", "script not found"),
                         ("npm start", "instead of `npm`")):
            _fill(app, cmd)
            await press(pilot, "ctrl+s")
            assert app.screen.state == "form" and why in text_of(app.screen.query_one("#problems")), cmd
    drive(h, script)
    assert not (h / "rewind.db").exists()  # nothing was recorded


def test_stopping_a_recording(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    h = tmp_path / "home"

    async def script(app, pilot):
        await press(pilot, "n")
        _fill(app, "node tests/fixtures/forever.js", "stopped")
        await press(pilot, "ctrl+s")
        deadline = time.time() + 10
        while "started" not in "".join(str(l) for l in app.screen.query_one("#output").lines) and time.time() < deadline:
            await pilot.pause(0.1)
        assert app.screen.state == "running"
        await press(pilot, "q")  # quitting is refused while a program is being recorded
        assert app.screen.state == "running"
        await press(pilot, "escape")
        await wait_recording(app, pilot)
        assert app.screen.state == "done" and "You stopped it" in text_of(app.screen.query_one("#result"))
    drive(h, script)
    row = store.runs(store.connect(h))[0]
    assert row["label"] == "stopped" and row["event_count"] > 0


def test_the_sample_is_prefilled_when_available(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)

    async def script(app, pilot):
        assert app.screen.query_one("#sample-row").display
        await press(pilot, "s")
        s = app.screen
        assert isinstance(s, RecordScreen) and app.focused.id == "start"
        assert (s.query_one("#cmd").value, s.query_one("#label").value, s.query_one("#watch").value) == SAMPLE
    drive(tmp_path / "home", script)


# ---- investigation (unchanged behaviour, new structure) ------------------------------------------------------
def test_incomplete_recording_is_marked_and_claims_nothing(home):
    async def script(app, pilot):
        await investigate(app, pilot, "held")
        assert not app.pend.complete and "incomplete" in text_of(app.query_one("#topbar"))
        await press(pilot, "p")
        assert any("recording incomplete" in f.text for f in app.lists["pending"])
        assert not any(f.level == A.INFERRED for f in app.lists["pending"])
    drive(home, script)


def test_runs_requests_and_timeline_navigation(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "1")
        assert app.focused.id == "runs" and app.query_one("#details-panel").border_title == "Recording"
        await press(pilot, "down", "down")
        assert app.row["label"] == "nowatch"
        await press(pilot, "up", "up")
        assert app.row["label"] == "bad"
        await press(pilot, "2", "down", "down", "down")  # All, #1, #2, #3
        assert app.req_filter == 3
        rows = [app.current.by_seq[s] for s in app.shown]
        assert rows and all(app.current.request_of(e.aid if e.kind.startswith("async.") else e.eid) == 3 for e in rows)
        await press(pilot, "enter")
        assert app.focused.id == "table" and app.query_one("#views").active == "timeline"
        await press(pilot, "G")
        assert app.query_one("#details-panel").border_title == f"Event {app.shown[-1]}"
    drive(home, script)


def test_explain_groups_findings_and_walks_evidence(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "w")
        ol = app.query_one("#why-list")
        assert app.query_one("#views").active == "why" and app.focused.id == "why-list"
        groups = [ol.get_option_at_index(i).id for i in range(ol.option_count) if str(ol.get_option_at_index(i).id).startswith("group:")]
        assert groups == ["group:observed", "group:derived", "group:inferred"]  # recorded, derived, interpretation
        findings = app.lists["why"]
        target = next(i for i, f in enumerate(findings) if "it read request #4's value" in f.text)
        while ol.get_option_at_index(ol.highlighted).id != str(target):
            await press(pilot, "down")
        f = findings[target]
        assert app.active[1] is f
        await press(pilot, "enter")
        assert app.query_one("#views").active == "timeline" and app.selected_seq() == f.evidence[0]
        await press(pilot, "right_square_bracket")
        assert app.selected_seq() == f.evidence[1]
        await press(pilot, "left_square_bracket", "left_square_bracket")
        assert app.selected_seq() == f.evidence[-1]
    drive(home, script)


def test_jumping_widens_filters_only_as_needed(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "2", "down", "down")  # request #2 only
        assert app.req_filter == 2
        init = next(e for e in app.current.events if e.kind == "async.init" and app.current.request_of(e.aid) == 3)
        app.jump(init.seq)
        await pilot.pause()
        assert app.raw and app.req_filter is None and app.selected_seq() == init.seq
        app.jump(10 ** 6)  # not in the recording: refused, nothing moves
        await pilot.pause()
        assert app.selected_seq() == init.seq
    drive(home, script)


def test_variables_unfinished_and_tree_views(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "s")  # no event picked yet: the state at the first error
        assert app.query_one("#views").active == "state"
        from rich.console import Console
        c = Console(width=160, record=True, file=open(os.devnull, "w"))
        c.print(V.state_view(app.current, A.state_at(app.current, app.current.errors[0].seq)))
        text = c.export_text()
        assert "currentCart" in text and "read at seq" in text and '"C-303"' in text
        await press(pilot, "p")
        assert any("#3 POST /order arrived" in f.text for f in app.lists["pending"])
        await press(pilot, "e")
        assert app.query_one("#tree-view").root.children and app.query_one("#views").active == "tree"
    drive(home, script)


def test_compare_two_recordings_and_jump_into_either(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "d")
        cr = app.query_one("#compare-runs")
        assert app.query_one("#views").active == "diff" and app.focused.id == "compare-runs"
        while cr.get_option_at_index(cr.highlighted).id != "good0000":
            await press(pilot, "down")
        await press(pilot, "enter")
        assert app.diff_pair == ("good0000", "bad0000") and app.focused.id == "diff-list"
        findings = app.lists["diff"]
        i = next(i for i, f in enumerate(findings) if f.text.startswith("next, A does"))
        ol = app.query_one("#diff-list")
        while ol.get_option_at_index(ol.highlighted).id != str(i):
            await press(pilot, "down")
        await press(pilot, "enter")
        assert app.row["label"] == "good" and app.selected_seq() == findings[i].evidence[0]  # evidence lives in run A
    drive(home, script)


def test_baseline_key_still_compares(home):
    async def script(app, pilot):
        await investigate(app, pilot, "good")
        await press(pilot, "b", "1", "up", "up", "up")
        assert app.row["label"] == "bad" and app.baseline == "good0000"
        await press(pilot, "d")
        assert app.diff_pair == ("good0000", "bad0000") and app.lists["diff"]
    drive(home, script)


def test_run_without_watch_and_without_errors(home):
    async def script(app, pilot):
        await investigate(app, pilot, "nowatch")
        await press(pilot, "s")
        await press(pilot, "1", "down")  # good: no errors
        assert app.row["label"] == "good" and app.why_target is None
        await press(pilot, "w")
        assert app.lists["why"] == []
    drive(home, script)


def test_search_filter_and_clear(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "slash")
        assert app.focused.id == "search"
        for ch in "charged":
            await pilot.press(ch)
        await pilot.pause()
        assert app.shown and all("charged" in V.T(V.R.event_text(app.current, app.current.by_seq[s])).plain for s in app.shown)
        await press(pilot, "enter", "f")
        assert app.kind_idx == 1
        await press(pilot, "escape")
        assert not app.search_text and app.kind_idx == 0 and len(app.shown) == len(app.timeline_rows())
    drive(home, script)


# ---- keyboard only, help, sizes -----------------------------------------------------------------------------
def test_keyboard_only_journey_from_sample_to_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)

    async def script(app, pilot):
        await press(pilot, "s", "enter")              # Home -> sample form -> start
        await wait_recording(app, pilot)
        await press(pilot, "enter")                   # Open this run
        assert app.row["label"] == "sample" and app.focused.id == "overview-list"
        await press(pilot, "w", "enter")              # Explain, first finding's evidence
        assert app.query_one("#views").active == "timeline" and app.selected_seq() is not None
        await press(pilot, "o", "t", "p", "s", "e", "d", "question_mark")
        assert isinstance(app.screen, HelpScreen)
        await press(pilot, "escape", "h")
        assert isinstance(app.screen, HomeScreen)
    drive(tmp_path / "home", script)


@pytest.mark.parametrize("size", [(80, 24), (120, 36), (200, 60)])
def test_help_modal_is_centered(home, size):
    async def script(app, pilot):
        await press(pilot, "question_mark")
        assert isinstance(app.screen, HelpScreen)
        card = app.screen.query_one("#help-card").region
        cx, cy = card.x + card.width / 2, card.y + card.height / 2
        assert abs(cx - size[0] / 2) <= 2 and abs(cy - size[1] / 2) <= 2, (card, size)
        assert card.right <= size[0] and card.bottom <= size[1]
        await press(pilot, "escape")
        assert isinstance(app.screen, HomeScreen)
    drive(home, script, size)


@pytest.mark.parametrize("size,cls", [((80, 24), "-narrow"), ((100, 30), "-compact"), ((130, 40), "-medium"), ((180, 50), None)])
def test_layouts_at_terminal_sizes(home, size, cls):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        main = app.screen
        layout = {c for c in ("-narrow", "-compact", "-medium") if main.has_class(c)}
        assert layout == ({cls} if cls else set())
        await press(pilot, "t")
        table = app.query_one("#table")
        assert table.size.height >= 3 and table.size.width >= 40
        await press(pilot, "3", "o", "w", "p", "s", "e", "d", "t")  # every view renders at this size
        if cls in ("-narrow", "-compact"):
            assert not app.query_one("#details-panel").display
            await press(pilot, "i")
            assert app.query_one("#details-panel").display
    drive(home, script, size)


def test_the_real_entry_point_runs(home):
    # run_test() bypasses App.run(); an attribute once shadowed run() and only a real launch caught it
    async def auto(pilot):
        await pilot.pause()
        assert isinstance(pilot.app.screen, HomeScreen)
        await pilot.press("enter")
        await pilot.pause()
        assert pilot.app.current is not None and pilot.app.row["label"] == "bad"
        await pilot.press("q")
    app = RewindApp(home)
    app.run(headless=True, size=(120, 36), auto_pilot=auto)
    assert app.return_code in (0, None)

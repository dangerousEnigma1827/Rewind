"""The interactive TUI, driven headless with Textual's pilot over real recordings of the demo."""
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
from rewind.tui import views as V
from rewind.tui.app import HelpScreen, RewindApp


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


async def press(pilot, *keys):
    for k in keys:
        await pilot.press(k)
        await pilot.pause()


# ---- presentation helpers ---------------------------------------------------------------------------
def test_markup_resolves_to_concrete_styles():
    t = V.T("[mute]muted[/] [kind.read]read[/] [err.t]err[/] [r2]#2[/]")
    assert t.plain == "muted read err #2"
    assert all(isinstance(s.style, Style) and s.style.color is not None for s in t.spans)  # no unresolved names


# ---- empty and incomplete -------------------------------------------------------------------------------
def test_empty_home_shows_the_welcome_screen_and_creates_nothing(tmp_path):
    empty = tmp_path / "nothing-here"

    async def script(app, pilot):
        assert app.query_one("#welcome").display and not app.query_one("#body").display
        await press(pilot, "w", "p", "s", "d", "b", "slash", "right_square_bracket", "f", "e", "3", "r")
        assert app.query_one("#welcome").display
    drive(empty, script)
    assert not empty.exists()  # looking never creates a REWIND_HOME


def test_incomplete_recording_is_marked_and_claims_nothing(home):
    async def script(app, pilot):
        await press(pilot, "down")  # newest first: bad, held, ...
        assert app.row["label"] == "held" and not app.pend.complete
        assert "incomplete" in app.query_one("#topbar").render().plain
        await press(pilot, "p")
        texts = [f.text for f in app.lists["pending"]]
        assert any("recording incomplete" in t for t in texts)
        assert not any(f.level == A.INFERRED for f in app.lists["pending"])
    drive(home, script)


# ---- the investigation workflow ---------------------------------------------------------------------------
def test_runs_requests_and_timeline_navigation(home):
    async def script(app, pilot):
        assert app.row["label"] == "bad" and app.focused.id == "runs"
        assert "run" in str(app.query_one("#details-panel").border_title)
        await press(pilot, "down", "down")
        assert app.row["label"] == "nowatch"
        await press(pilot, "up", "up")
        assert app.row["label"] == "bad"
        await press(pilot, "2", "down", "down", "down")  # all, #1, #2, #3
        assert app.req_filter == 3
        rows = [app.run.by_seq[s] for s in app.shown]
        assert rows and all(app.run.request_of(e.aid if e.kind.startswith("async.") else e.eid) == 3 for e in rows)
        assert any(e.kind == "error.uncaught" for e in rows)
        await press(pilot, "enter")
        assert app.focused.id == "table" and app.query_one("#views").active == "timeline"
        await press(pilot, "G")
        assert app.query_one("#details-panel").border_title == f"seq {app.shown[-1]}"
    drive(home, script)


def test_why_findings_navigate_to_their_evidence(home):
    async def script(app, pilot):
        await press(pilot, "w")
        assert app.query_one("#views").active == "why" and app.focused.id == "why-list"
        findings = app.lists["why"]
        target = next(i for i, f in enumerate(findings) if "it read request #4's value" in f.text)
        ol = app.query_one("#why-list")
        while ol.get_option_at_index(ol.highlighted).id != str(target):
            await press(pilot, "down")
        f = findings[target]
        assert app.active[1] is f and "derived finding" in str(app.query_one("#details-panel").border_title)
        await press(pilot, "enter")
        assert app.query_one("#views").active == "timeline" and app.selected_seq() == f.evidence[0]
        await press(pilot, "right_square_bracket")
        assert app.selected_seq() == f.evidence[1]
        await press(pilot, "left_square_bracket", "left_square_bracket")
        assert app.selected_seq() == f.evidence[-1]
        assert all(s in app.run.by_seq for s in f.evidence)
    drive(home, script)


def test_jumping_widens_filters_only_as_needed(home):
    async def script(app, pilot):
        await press(pilot, "2", "down", "down")  # request #2 only
        assert app.req_filter == 2
        init = next(e for e in app.run.events if e.kind == "async.init" and app.run.request_of(e.aid) == 3)
        app.jump(init.seq)  # an internal event of another request: needs every event shown
        await pilot.pause()
        assert app.raw and app.req_filter is None and app.selected_seq() == init.seq
        app.jump(10 ** 6)  # not in the recording: refused, nothing moves
        await pilot.pause()
        assert app.selected_seq() == init.seq
    drive(home, script)


def test_state_pending_and_tree_views(home):
    async def script(app, pilot):
        crash = app.run.errors[0].seq
        app.jump(crash)
        await pilot.pause()
        await press(pilot, "s")
        assert app.query_one("#views").active == "state"
        from rich.console import Console
        c = Console(width=160, record=True, file=open(os.devnull, "w"))
        c.print(V.state_view(app.run, A.state_at(app.run, crash)))
        text = c.export_text()
        assert "currentCart" in text and "read at seq" in text and '"C-303"' in text
        await press(pilot, "p")
        assert any("#3 POST /order arrived" in f.text and "uncaught error" in f.text for f in app.lists["pending"])
        await press(pilot, "e")
        tree = app.query_one("#tree-view")
        assert tree.root.children and app.query_one("#views").active == "tree"
    drive(home, script)


def test_diff_against_a_baseline_and_jump_into_either_run(home):
    async def script(app, pilot):
        await press(pilot, "down", "down", "down", "b")  # good is the oldest
        assert app.baseline == "good0000"
        await press(pilot, "up", "up", "up", "d")
        assert app.row["label"] == "bad" and app.diff_pair == ("good0000", "bad0000")
        findings = app.lists["diff"]
        assert any("first" in f.text or "identical up to" in f.text for f in findings)
        i = next(i for i, f in enumerate(findings) if f.text.startswith("next, A does"))
        ol = app.query_one("#diff-list")
        while ol.get_option_at_index(ol.highlighted).id != str(i):
            await press(pilot, "down")
        await press(pilot, "enter")
        assert app.row["label"] == "good" and app.selected_seq() == findings[i].evidence[0]  # evidence lives in run A
    drive(home, script)


def test_run_without_watch_and_without_errors(home):
    async def script(app, pilot):
        await press(pilot, "down", "down")
        assert app.row["label"] == "nowatch"
        await press(pilot, "s")
        await press(pilot, "down")  # good: no errors
        assert app.row["label"] == "good" and app.why_target is None
        await press(pilot, "w")
        assert app.lists["why"] == [] and app.query_one("#why-list").option_count == 1
    drive(home, script)


def test_search_filter_and_clear(home):
    async def script(app, pilot):
        await press(pilot, "slash")
        assert app.focused.id == "search"
        for ch in "charged":
            await pilot.press(ch)
        await pilot.pause()
        assert app.shown and all("charged" in V.T(V.R.event_text(app.run, app.run.by_seq[s])).plain for s in app.shown)
        await press(pilot, "enter", "f")
        assert app.kind_idx == 1
        await press(pilot, "escape")
        assert not app.search_text and app.kind_idx == 0 and len(app.shown) == len(app.timeline_rows())
    drive(home, script)


def test_help_screen_opens_and_closes(home):
    async def script(app, pilot):
        await press(pilot, "question_mark")
        assert isinstance(app.screen, HelpScreen)
        await press(pilot, "escape")
        assert not isinstance(app.screen, HelpScreen)
    drive(home, script)


@pytest.mark.parametrize("size,cls", [((80, 24), "-narrow"), ((100, 30), "-compact"), ((130, 40), "-medium"), ((180, 50), None)])
def test_layouts_at_terminal_sizes(home, size, cls):
    async def script(app, pilot):
        layout = {c for c in ("-narrow", "-compact", "-medium") if app.screen.has_class(c)}
        assert layout == ({cls} if cls else set())
        table = app.query_one("#table")
        assert table.size.height >= 3 and table.size.width >= 40  # the timeline always has room
        await press(pilot, "3", "w", "p", "s", "e", "t")  # every view renders at this size
        if cls in ("-narrow", "-compact"):
            assert not app.query_one("#details-panel").display
            await press(pilot, "i")
            assert app.query_one("#details-panel").display
    drive(home, script, size)

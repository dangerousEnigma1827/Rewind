"""The TUI's keyboard model: every key works from wherever focus is, means one thing, and is documented as it works.

Regression tests for the navigation audit:
- `v` was not bound at all (the Variables tab said `s`), so pressing it never did anything;
- `s` meant "try the sample" on Home but "variables" in the investigation;
- `<` `>` only had their shifted key names, so a terminal reporting shift+. (kitty protocol) never switched views;
- Home had no way back to the investigation it was opened from;
- the tab bar was a focus stop with its own left/right, and scrolled sideways when the labels didn't fit.
"""
import pytest
from textual.binding import Binding

from rewind.tui import views as V
from rewind.tui.app import TABS, RewindApp
from rewind.tui.screens import HelpScreen, HomeScreen, RecordScreen
from test_tui import drive, focus_panel, home, investigate, press, text_of  # noqa: F401  (home is a fixture)

VIEWS = [p for p, _, _ in TABS]
# Every place a keyboard user can be inside the investigation (None: nothing focused).
FOCUS = ["runs", "requests", "overview-list", "table", "why-list", "pending-list", "state-scroll", "tree-view",
         "compare-runs", "details-panel", None]
OWN_VIEW = {"table": "timeline", "why-list": "why", "pending-list": "pending", "state-scroll": "state",
            "tree-view": "tree", "compare-runs": "diff"}


async def put_focus(app, pilot, target):
    if target in OWN_VIEW:
        app.action_view(OWN_VIEW[target])
        await pilot.pause()
    if target is None:
        app.set_focus(None)
    else:
        app.query_one(f"#{target}").focus()
    await pilot.pause()
    assert (app.focused.id if app.focused else None) == target


def active(app) -> str:
    return app.query_one("#views").active


def keys_of(binding: Binding) -> list[str]:
    return [k.strip() for k in binding.key.split(",")]


# ---- one key, one meaning -----------------------------------------------------------------------------
def test_no_key_means_two_different_things():
    app_keys = {k: b.action for b in RewindApp.BINDINGS for k in keys_of(b)}
    assert "s" not in app_keys and app_keys["v"] == "state"          # s is only Home's "sample"
    for screen in (HomeScreen, RecordScreen):
        for b in screen.BINDINGS:
            for k in keys_of(b):
                if k in app_keys:  # the same key on another screen must mean the same thing there
                    same = {("n", "record", "new_recording"), ("r", "reload", "reload"), ("j", "cursor(1)", "cursor(1)"),
                            ("k", "cursor(-1)", "cursor(-1)"), ("escape", "back", "back")}
                    assert (k, b.action, app_keys[k]) in same, (screen.__name__, k, b.action, app_keys[k])
    assert len(app_keys) == sum(len(keys_of(b)) for b in RewindApp.BINDINGS)  # no key bound twice in the app


def test_help_lists_exactly_the_real_keys():
    names = {"<": "less_than_sign", ">": "greater_than_sign", "?": "question_mark", "/": "slash", "]": "right_square_bracket",
             "[": "left_square_bracket", "\\": "backslash", "esc": "escape", "↑": "up", "↓": "down"}
    shown = {names.get(k, k) for section in V.HELP.values() for keys, _ in section for k in keys}
    widget_keys = {"up", "down", "enter", "tab", "shift+tab"}           # Textual's own list, table and focus keys
    bound = {keys_of(b)[0] for b in RewindApp.BINDINGS}
    assert bound <= shown, f"bound but not in help: {bound - shown}"
    assert shown - widget_keys <= bound, f"in help but not bound: {shown - widget_keys - bound}"
    help_text = V.T(V.HELP_NOTE).plain                                  # Home and Record keys are in the note
    for screen in (HomeScreen, RecordScreen):
        for b in screen.BINDINGS:
            if b.show or b.action in ("sample", "start", "back"):
                assert keys_of(b)[0].replace("escape", "esc") in help_text, (screen.__name__, b.key)


# ---- every view key, from every focus ---------------------------------------------------------------------
@pytest.mark.parametrize("target", FOCUS)
def test_view_keys_work_from_any_focus(home, target):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        for pane, _, key in TABS:
            await put_focus(app, pilot, target)
            await press(pilot, key)
            assert active(app) == pane, (target, key)
        await put_focus(app, pilot, target)
        await press(pilot, "v")                                           # variables at the selected event
        assert active(app) == "state", target
        await put_focus(app, pilot, target)
        await press(pilot, "w")                                           # explain
        assert active(app) == "why" and app.focused.id == "why-list", target
    drive(home, script, (160, 45))


@pytest.mark.parametrize("target", FOCUS)
@pytest.mark.parametrize("nxt,prv", [("greater_than_sign", "less_than_sign"), ("full_stop", "comma"),
                                     ("shift+full_stop", "shift+comma")])
def test_previous_next_from_any_focus_and_every_key_form(home, target, nxt, prv):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "3")                                           # Timeline: a view with both neighbours
        await put_focus(app, pilot, target)
        start = active(app)
        await press(pilot, nxt)
        after = VIEWS.index(active(app))
        assert after == min(VIEWS.index(start) + 1, len(VIEWS) - 1), (target, nxt)  # one right, or stays at the end
        await press(pilot, prv)
        assert VIEWS.index(active(app)) == after - 1, (target, prv)
        assert app.focused is not None and active(app) in {OWN_VIEW.get(app.focused.id, ""), "overview", "timeline"}
    drive(home, script, (160, 45))


def test_previous_next_stop_at_the_ends(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "1", "less_than_sign")
        assert active(app) == VIEWS[0]
        await press(pilot, "7", "greater_than_sign")
        assert active(app) == VIEWS[-1]
    drive(home, script)


def test_shift_g_alias_and_list_edges(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "3")
        t = app.query_one("#table")
        await press(pilot, "shift+g")
        assert t.cursor_row == len(app.shown) - 1
        await press(pilot, "down")                                        # the end of the list stays the end
        assert t.cursor_row == len(app.shown) - 1
        await press(pilot, "g", "up")
        assert t.cursor_row == 0
        await press(pilot, "G")
        assert t.cursor_row == len(app.shown) - 1
    drive(home, script)


# ---- typing, help, screens -----------------------------------------------------------------------------
def test_keys_type_into_the_search_field_until_it_is_left(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "slash")
        assert app.focused.id == "search"
        await press(pilot, "greater_than_sign", "v", "5")                # a text field gets text, by design
        assert app.query_one("#search").value == ">v5" and active(app) == "timeline"
        await press(pilot, "escape")                                      # esc leaves it and clears it
        assert app.focused.id == "table" and not app.search_text
        await press(pilot, "greater_than_sign", "v")
        assert active(app) == "state"
    drive(home, script)


def test_keys_work_after_help_is_opened_and_closed(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "3")
        for close in ("escape", "question_mark", "q"):
            await press(pilot, "question_mark")
            assert isinstance(app.screen, HelpScreen)
            await press(pilot, "4", "greater_than_sign")                  # nothing behind the help moves
            assert active(app) == "timeline"
            await press(pilot, close)
            assert not isinstance(app.screen, HelpScreen) and app.focused.id == "table", close
        await press(pilot, "greater_than_sign")
        assert active(app) == "pending"
    drive(home, script)


def test_home_goes_back_to_the_same_place(home):
    async def script(app, pilot):
        await press(pilot, "escape")                                      # first launch: nothing to go back to
        assert isinstance(app.screen, HomeScreen)
        await investigate(app, pilot, "bad")
        await press(pilot, "6")
        await press(pilot, "h")
        assert isinstance(app.screen, HomeScreen) and "esc" in text_of(app.screen.query_one("#home-top"))
        await press(pilot, "escape")
        assert not isinstance(app.screen, HomeScreen) and active(app) == "tree" and app.row["label"] == "bad"
        await press(pilot, "less_than_sign")                              # and keys work straight away
        assert active(app) == "state"
        await press(pilot, "h", "s")                                      # on Home, s is still the sample
        assert isinstance(app.screen, (RecordScreen, HomeScreen))
    drive(home, script)


def test_esc_returns_from_a_followed_link(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        ol = app.query_one("#overview-list")
        target = next(it.id for it in app.overview_items if it.id and it.id.startswith("find:"))
        while ol.get_option_at_index(ol.highlighted).id != target:
            await press(pilot, "down")
        await press(pilot, "enter")                                       # a finding's evidence, in the Timeline
        assert active(app) == "timeline" and "esc back" in str(app.query_one("#main").border_subtitle)
        await press(pilot, "w")                                           # explain that event
        assert active(app) == "why"
        await press(pilot, "escape")
        assert active(app) == "timeline" and app.focused.id == "table"
        await press(pilot, "escape")
        assert active(app) == "overview" and app.focused.id == "overview-list"
        await press(pilot, "escape")                                      # nothing left: stays put
        assert active(app) == "overview"
    drive(home, script)


def test_the_tab_bar_is_not_a_focus_stop(home):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        seen = set()
        for _ in range(12):
            await press(pilot, "tab")
            seen.add(type(app.focused).__name__)
        assert "ContentTabs" not in seen and "Tabs" not in seen
        await press(pilot, "left", "right")                               # arrows act on the focused list, not views
        assert active(app) == "overview"
    drive(home, script)


# ---- sizes ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("size", [(120, 50), (80, 24), (60, 20)])
def test_navigation_stays_visible_and_usable(home, size):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        tabs = app.query_one("#views").query_one("Tabs")
        scroll = tabs.query_one("#tabs-scroll")
        for pane, label, key in TABS:
            await press(pilot, key)
            assert active(app) == pane and scroll.max_scroll_x == 0, (size, pane)
            current = tabs.query_one("Tab.-active")
            assert str(current.label) == f"{key} {label}" and current.region.right <= size[0], (size, pane)
        footer = app.screen.query_one("Footer")
        assert footer.display and footer.region.bottom == size[1]
        shown = {ab.binding.key_display or ab.binding.key for ab in app.active_bindings.values() if ab.binding.show}
        assert {"1-7", "<", ">", "esc", "?"} <= shown, shown
        await press(pilot, "question_mark")
        card = app.screen.query_one("#help-card").region
        assert card.right <= size[0] and card.bottom <= size[1]
    drive(home, script, size)

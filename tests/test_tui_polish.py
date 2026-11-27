"""The visual polish pass: component shapes, tab reachability, thin scrollbars, the help card, toasts, view focus."""
import asyncio

import pytest

from conftest import ROOT
from rewind.tui import theme as TH
from rewind.tui.app import TABS, RewindApp
from rewind.tui.scrollbar import ThinScrollBarRender, thumb_span
from test_tui import drive, home, investigate, press, text_of  # noqa: F401  (home is a fixture)


def test_thin_scrollbar_geometry_and_glyphs():
    assert thumb_span(10, 10, 10, 0) is None                       # nothing to scroll
    assert thumb_span(10, 100, 10, 0) == (0, 1) and thumb_span(10, 100, 10, 90) == (9, 10)
    assert thumb_span(20, 40, 20, 10) == (5, 15)
    text = "".join(s.text for s in ThinScrollBarRender.render_bar(size=10, virtual_size=100, window_size=10).segments)
    assert "▐" in text and "█" not in text                         # a half-cell thumb, never a full block


@pytest.mark.parametrize("width", [80, 100, 120, 150, 190])
def test_every_view_is_reachable_and_shown_active(home, width):
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        tabs = app.query_one("#views").query_one("Tabs")
        labels = [str(t.label) for t in tabs.query("Tab")]
        assert all(any(label.endswith(key) for label in labels) for _, _, key in TABS)  # each label carries its key
        scroll = tabs.query_one("#tabs-scroll")
        for pane, _, key in reversed(TABS):                            # far tabs first, by their keys
            await press(pilot, key)
            assert app.query_one("#views").active == pane
            active = tabs.query_one("Tab.-active")
            assert active.region.x >= scroll.region.x and active.region.right <= scroll.region.right, (width, pane)
        ids = [p for p, _, _ in TABS]
        await press(pilot, "o")
        for expected in ids[1:] + ids[:1]:                            # > walks every view and wraps around
            await press(pilot, "greater_than_sign")
            assert app.query_one("#views").active == expected
        await press(pilot, "less_than_sign")
        assert app.query_one("#views").active == ids[-1]
    drive(home, script, (width, 34))


def test_view_keys_work_while_a_list_in_another_view_has_focus(home):
    # regression: switching views from inside one used to bounce back (focus moved to a hidden sibling list)
    async def script(app, pilot):
        await investigate(app, pilot, "bad")
        await press(pilot, "d")
        assert app.focused.id == "compare-runs"
        await press(pilot, "o")
        assert app.query_one("#views").active == "overview" and app.focused.id == "overview-list"
    drive(home, script, (120, 34))


def test_components_stay_inside_their_shapes(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)

    async def script(app, pilot):
        await press(pilot, "n")
        s = app.screen
        for inp in s.query("Input"):  # outlined fields: the page's fill, so nothing shows outside the rounded border
            assert inp.styles.background == app.screen.styles.background
        start, cancel = s.query_one("#start"), s.query_one("#cancel")
        cancel.focus()
        await pilot.pause()
        assert start.styles.border_top[1] == start.styles.background  # at rest the border is the fill (invisible)
        assert start.outer_size.height == cancel.outer_size.height == 3
        before = start.outer_size
        start.focus()
        await pilot.pause()
        assert start.outer_size == before and start.styles.border_top[1] != start.styles.background  # violet on focus
    drive(tmp_path / "home", script, (120, 40))


@pytest.mark.parametrize("size", [(80, 24), (100, 30), (150, 50)])
def test_help_fits_and_scrolls_inside(home, size):
    async def script(app, pilot):
        await press(pilot, "question_mark")
        card = app.screen.query_one("#help-card")
        body = app.screen.query_one("#help-body")
        assert card.region.x >= 0 and card.region.y >= 0
        assert card.region.right <= size[0] and card.region.bottom <= size[1]
        assert ("scroll for more" in text_of(app.screen.query_one("#help-foot"))) == (body.max_scroll_y > 0)
        if size[1] >= 50:
            assert body.max_scroll_y == 0  # a large terminal shows every shortcut at once
    drive(home, script, size)


def test_notifications_use_the_dark_toast(home):
    async def main():
        app = RewindApp(home)
        async with app.run_test(size=(120, 32), notifications=True) as pilot:  # run_test hides toasts by default
            await pilot.pause()
            await press(pilot, "enter", "b")
            await pilot.pause(0.3)
            toasts = list(app.screen.query("Toast"))
            assert toasts and toasts[0].styles.background.hex.upper() == TH.C["raised"].upper()
    asyncio.run(main())

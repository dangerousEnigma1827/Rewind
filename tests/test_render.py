"""Presentation: landing screen, help/errors, colour handling, narrow terminals, palette, evidence hierarchy."""
import io, os, re
from rich.console import Console

from rewind import analysis as A, render
from test_cli import rw

COLOR = re.compile(r"\x1b\[(?:[\d;]*;)?(?:3[0-7]|9[0-7]|38)(?:;[\d;]*)?m")  # any foreground colour SGR


def test_landing_without_runs_creates_nothing(tmp_path):
    home = tmp_path / "nothing-here"
    r = rw(home=home)
    assert r.returncode == 2  # unchanged: bare `rewind` exited 2 before the redesign too
    assert render.WORDMARK[0] in r.stdout and render.TAGLINE in r.stdout
    assert "record your first run" in r.stdout and "no runs recorded yet" in r.stdout
    assert not home.exists()  # looking must not create .rewind
    for cmd in ("record", "runs", "timeline", "tree", "why", "diff"):
        assert f" {cmd} " in r.stdout


def test_landing_next_step_follows_latest_run(tmp_path):
    rw("record", "-l", "fine", "--", "node", "tests/fixtures/chain.js", home=tmp_path)
    assert "rewind timeline fine" in rw(home=tmp_path).stdout
    rw("record", "-l", "boom", "--", "node", "tests/fixtures/throw_timer.js", home=tmp_path)
    h = rw("--help", home=tmp_path)
    assert h.returncode == 0 and "2 runs" in h.stdout and "rewind why boom" in h.stdout and "the latest run failed" in h.stdout


def test_command_help_keeps_every_option_and_drops_boxes(tmp_path):
    expected = {"record": ["--label", "-l", "--watch", "-w"], "timeline": ["--request", "-r", "--kind", "-k", "--callbacks", "-c", "--raw"],
                "tree": ["--request", "--full"], "why": ["--error", "-e", "--seq", "-s", "--evidence", "default 1"],
                "diff": ["--all", "--evidence", "Baseline run"], "runs": ["--help"]}
    for cmd, needles in expected.items():
        h = rw(cmd, "--help", home=tmp_path)
        assert h.returncode == 0, cmd + h.stdout + h.stderr
        assert all(n in h.stdout for n in needles), (cmd, h.stdout)
        assert "┌" not in h.stdout and "╭" not in h.stdout


def test_usage_errors_keep_message_and_exit_code(tmp_path):
    for args, msg in ((("timeline", "-k"), "requires an argument"), (("nosuch",), "No such command")):
        r = rw(*args, home=tmp_path)
        assert r.returncode == 2 and "error:" in r.stderr and msg in r.stderr and "┌" not in r.stderr


def _vt_console(monkeypatch, no_color: bool, width: int = 100, height: int = 25, legacy: bool = False):
    monkeypatch.setenv("NO_COLOR", "1" if no_color else "")  # Rich reads it at construction; empty = unset
    buf = io.StringIO()  # read what is actually written: export_text() would bypass NO_COLOR stripping
    con = Console(file=buf, theme=render.THEME, force_terminal=True, color_system="truecolor", legacy_windows=legacy,
                  width=width, height=height, highlight=False)
    monkeypatch.setattr(render, "console", con)
    return buf


def test_piped_output_has_no_escape_codes(tmp_path):
    rw("record", "-l", "boom", "--", "node", "tests/fixtures/throw_timer.js", home=tmp_path)
    for args in ((), ("runs",), ("why",), ("timeline",), ("tree",)):
        assert "\x1b" not in rw(*args, home=tmp_path, env={"NO_COLOR": ""}).stdout, args


def test_no_color_keeps_structure_and_drops_colour(monkeypatch):
    fs = [A.Finding(A.OBSERVED, "seen it"), A.Finding(A.INFERRED, "a guess")]
    for no_color in (False, True):
        buf = _vt_console(monkeypatch, no_color)
        render.landing([], ".rewind", "0.1.0")
        render.findings(fs, evidence=False)
        out = buf.getvalue()
        assert bool(COLOR.search(out)) is not no_color
        assert all(s in out for s in (*render.WORDMARK, "●", "◆", "? inferred", "capture", "next"))


def test_wordmark_fits_every_width_and_falls_back_below_45(monkeypatch):
    plain = re.compile(r"\x1b\[[\d;]*m")
    for width, expect in ((120, render.WORDMARK), (80, render.WORDMARK), (60, render.WORDMARK),
                          (46, render.WORDMARK_TIGHT), (45, render.WORDMARK_TIGHT), (44, None), (30, None)):
        buf = _vt_console(monkeypatch, no_color=True, width=width)
        render.landing([], ".rewind", "0.1.0")
        lines = plain.sub("", buf.getvalue()).splitlines()
        assert max(len(l.rstrip()) for l in lines) <= width, width
        if expect is None:
            assert "◂◂ r e w i n d  0.1.0" in lines[1] and "█" not in buf.getvalue(), width
            continue
        assert [l.strip() for l in lines[1:3]] == [r.strip() for r in expect[:2]], width  # readable without colour
        version_end = lines[3].rstrip().index("0.1.0") + len("0.1.0")
        assert lines[4].rstrip().endswith("◆") and len(lines[4].rstrip()) == version_end, width  # version ends on the ◆
        if width >= 48:
            assert lines[5].rstrip() == "  " + render.TAGLINE and len(lines[5].rstrip()) == version_end  # one right edge
    assert len(render.WORDMARK[0]) == 38 and len({len(r) for r in render.WORDMARK + render.WORDMARK_TIGHT}) == 2


def test_wordmark_switch_is_the_terminals_45_columns_in_every_rich_mode(monkeypatch):
    # Rich keeps one column free only in legacy Windows mode; the switch must follow the real terminal width either way.
    for legacy in (False, True):
        for columns, has_mark in ((45, True), (44, False)):
            buf = _vt_console(monkeypatch, no_color=True, width=columns, legacy=legacy)
            render.landing([], ".rewind", "0.1.0")
            assert ("█" in buf.getvalue()) is has_mark, (legacy, columns)


def test_short_terminals_scroll_instead_of_clipping(monkeypatch):
    row = {"id": "cd8d67ad", "label": "bad", "status": "failed", "error_count": 1, "started_at": None}
    seen = {}
    for w, h in ((80, 24), (60, 24), (45, 24), (40, 24), (80, 15), (60, 12), (30, 12)):
        for no_color in (False, True):
            buf = _vt_console(monkeypatch, no_color=no_color, width=w, height=h)
            render.landing([row], ".rewind", "0.1.0")
            text = re.sub(r"\x1b\[[\d;]*m", "", buf.getvalue())
            lines = text.splitlines()
            assert max(len(l) for l in lines) <= w, (w, h)
            assert all(c in text for c in ("record", "timeline", "tree", "why", "diff", "rewind why bad")), (w, h)
            # height never truncates or reflows: the same width gives the same screen, colour or not; the terminal scrolls
            assert seen.setdefault(w, text) == text, (w, h, no_color)
    assert len(seen[80].splitlines()) <= 23  # 80x24: the whole landing screen plus the prompt line stays in view


def test_narrow_terminal_never_overflows(tmp_path):
    rw("record", "-l", "bad", "-w", "currentCart", "--", "node", "demo/traffic.js", home=tmp_path)
    rw("record", "-l", "good", "-w", "currentCart", "--", "node", "demo/traffic.js", "--sequential", home=tmp_path)
    for args in ((), ("runs",), ("timeline", "bad"), ("tree", "bad"), ("why", "bad", "--evidence"), ("diff", "good", "bad"), ("why", "--help")):
        out = rw(*args, home=tmp_path, env={"COLUMNS": "60"}).stdout
        assert out.strip(), args
        assert max(len(l) for l in out.splitlines()) <= 60, (args, out)


def test_runs_table_keeps_ids_whole_when_narrow(tmp_path):
    r = rw("record", "-l", "bad", "--", "node", "tests/fixtures/throw_timer.js", home=tmp_path)
    run_id = re.search(r"recorded run (\w{8})", r.stdout).group(1)
    wide = rw("runs", home=tmp_path, env={"COLUMNS": "100"}).stdout
    assert "command" in wide and "events" in wide  # full layout untouched where it fits
    for w in (64, 45, 40):
        out = rw("runs", home=tmp_path, env={"COLUMNS": str(w)}).stdout
        assert run_id in out and " bad " in out and "failed" in out, (w, out)
        assert max(len(l) for l in out.splitlines()) <= w, (w, out)


def test_runs_table_long_labels_give_way_to_ids(monkeypatch):
    import json
    monkeypatch.setattr(render, "ago", lambda _: "8h ago")  # column widths must not depend on the clock
    def row(rid, label, status, errors, code, events=432):
        return dict(id=rid, label=label, status=status, event_count=events, error_count=errors, exit_code=code,
                    started_at="2026-11-23T10:00:00", cmd=json.dumps(["node", "demo/traffic.js"]))
    rows = [row("aaaa1111", "bad", "failed", 1, 1), row("bbbb2222", None, "ok", 0, 0),
            row("cccc3333", "killed", "crashed", 1, None),
            row("dddd4444", "a-very-long-label-name-here", "ok", 0, 0, events=1234567)]

    def render_at(w):
        buf = io.StringIO()
        monkeypatch.setattr(render, "console", Console(file=buf, width=w, theme=render.THEME, no_color=True,
                                                       highlight=False, legacy_windows=False))
        render.runs_table(rows, "home")
        lines = buf.getvalue().splitlines()
        assert max(len(l) for l in lines) <= w
        return lines[3:]  # header row onwards

    wide = render_at(100)  # a 27-cell label still fits the full layout here
    assert all(c in wide[0] for c in ("events", "exit", "when")) and any("a-very-long-label-name-here" in l for l in wide)
    narrow = render_at(40)  # compact: the label is cut, never the id, status or error count
    assert narrow[0].split() == ["run", "label", "status", "errors"]
    for rid, status, errors in (("aaaa1111", "✖ failed", "1"), ("bbbb2222", "● ok", "0"),
                                ("cccc3333", "◌ crashed", "1"), ("dddd4444", "● ok", "0")):
        line = next(l for l in narrow if rid in l)
        assert status in line and line.rstrip().endswith(" " + errors), line
    assert any(l.split()[1] == "-" for l in narrow if "bbbb2222" in l)        # missing label
    assert any(" bad " in l for l in narrow if "aaaa1111" in l)              # normal label untouched
    assert any("…" in l and "a-very-long-label-name-here" not in l for l in narrow if "dddd4444" in l)


def test_palette_reads_on_dark_and_light_backgrounds():
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    for name, hex_ in render.PALETTE.items():
        L = lum(hex_)
        on_black, on_white = (L + 0.05) / 0.05, 1.05 / (L + 0.05)
        assert min(on_black, on_white) >= 3.5, (name, round(on_black, 2), round(on_white, 2))


def test_console_font_fallback_is_complete_and_keeps_layout():
    from rich.cells import cell_len
    assert all(cell_len(a) == cell_len(b) == 1 for a, b in render.FALLBACK.items())
    if os.name == "nt":  # the stand-ins really exist in the fonts a classic console uses; the originals don't in Lucida
        for face in ("Lucida Console", "Consolas", "Cascadia Mono"):
            assert render._font_has(face, "".join(render.FALLBACK.values())), face
        assert not render._font_has("Lucida Console", "●◆")
    assert render._GlyphSafe("stdout")._table == str.maketrans(render.FALLBACK)


def test_certainty_is_brightness(monkeypatch):
    buf = _vt_console(monkeypatch, no_color=False)
    render.findings([A.Finding(A.OBSERVED, "seen it"), A.Finding(A.DERIVED, "worked it out"),
                     A.Finding(A.INFERRED, "a guess", [1, 2])], evidence=True)
    out = buf.getvalue()
    obs, der, inf = (next(l for l in out.splitlines() if t in l) for t in ("seen it", "worked it out", "a guess"))
    assert "\x1b[1m" in obs and "seq" not in obs  # observed: bold, no seqs given
    assert "127;90;240" in der  # derived: the violet ◆
    assert re.search(r"\x1b\[3;", inf) and "seq 1, 2" in inf  # inferred: dim italic, evidence kept

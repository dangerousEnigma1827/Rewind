"""Presentation: landing screen, help/errors, colour handling, narrow terminals, palette, evidence hierarchy."""
import io, re
from rich.console import Console

from rewind import analysis as A, render
from test_cli import rw

COLOR = re.compile(r"\x1b\[(?:[\d;]*;)?(?:3[0-7]|9[0-7]|38)(?:;[\d;]*)?m")  # any foreground colour SGR


def test_landing_without_runs_creates_nothing(tmp_path):
    home = tmp_path / "nothing-here"
    r = rw(home=home)
    assert r.returncode == 2  # unchanged: bare `rewind` exited 2 before the redesign too
    assert "r e w i n d" in r.stdout and "record your first run" in r.stdout and "no runs recorded yet" in r.stdout
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


def _vt_console(monkeypatch, no_color: bool):
    monkeypatch.setenv("NO_COLOR", "1" if no_color else "")  # Rich reads it at construction; empty = unset
    buf = io.StringIO()  # read what is actually written: export_text() would bypass NO_COLOR stripping
    con = Console(file=buf, theme=render.THEME, force_terminal=True, color_system="truecolor", legacy_windows=False,
                  width=100, highlight=False)
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
        assert all(s in out for s in ("◂◂", "●", "◆", "? inferred", "capture", "next"))


def test_narrow_terminal_never_overflows(tmp_path):
    rw("record", "-l", "bad", "-w", "currentCart", "--", "node", "demo/traffic.js", home=tmp_path)
    rw("record", "-l", "good", "-w", "currentCart", "--", "node", "demo/traffic.js", "--sequential", home=tmp_path)
    for args in ((), ("runs",), ("timeline", "bad"), ("tree", "bad"), ("why", "bad", "--evidence"), ("diff", "good", "bad"), ("why", "--help")):
        out = rw(*args, home=tmp_path, env={"COLUMNS": "60"}).stdout
        assert out.strip(), args
        assert max(len(l) for l in out.splitlines()) <= 60, (args, out)


def test_palette_reads_on_dark_and_light_backgrounds():
    def lum(h):
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    for name, hex_ in render.PALETTE.items():
        L = lum(hex_)
        on_black, on_white = (L + 0.05) / 0.05, 1.05 / (L + 0.05)
        assert min(on_black, on_white) >= 3.5, (name, round(on_black, 2), round(on_white, 2))


def test_certainty_is_brightness(monkeypatch):
    buf = _vt_console(monkeypatch, no_color=False)
    render.findings([A.Finding(A.OBSERVED, "seen it"), A.Finding(A.DERIVED, "worked it out"),
                     A.Finding(A.INFERRED, "a guess", [1, 2])], evidence=True)
    out = buf.getvalue()
    obs, der, inf = (next(l for l in out.splitlines() if t in l) for t in ("seen it", "worked it out", "a guess"))
    assert "\x1b[1m" in obs and "seq" not in obs  # observed: bold, no seqs given
    assert "127;90;240" in der  # derived: the violet ◆
    assert re.search(r"\x1b\[3;", inf) and "seq 1, 2" in inf  # inferred: dim italic, evidence kept

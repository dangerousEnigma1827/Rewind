"""End-to-end: the installed `rewind` entry point records real node programs."""
import os, subprocess, sys
from pathlib import Path
from conftest import ROOT

REWIND = [sys.executable, "-c", "from rewind.cli import main; main()"]


def rw(*args, home, env=None):
    env = {**os.environ, "REWIND_HOME": str(home), "COLUMNS": "200", "NO_COLOR": "1", **(env or {})}
    return subprocess.run([*REWIND, *args], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=60)


def test_record_and_runs(tmp_path):
    a = rw("record", "--label", "bad", "--", "node", "tests/fixtures/throw_timer.js", home=tmp_path)
    assert a.returncode == 1, a.stdout + a.stderr  # child exit code passed through
    assert "recorded run" in a.stdout and "1 error" in a.stdout and "failed" in a.stdout
    b = rw("record", "tests/fixtures/chain.js", home=tmp_path)  # shorthand without `node`
    assert b.returncode == 0 and "no errors" in b.stdout
    assert len(list((tmp_path / "runs").glob("*.ndjson"))) == 2  # raw NDJSON is kept
    ls = rw("runs", home=tmp_path)
    assert ls.returncode == 0 and "bad" in ls.stdout and ls.stdout.index("chain.js") < ls.stdout.index("throw_timer.js")


def test_negative_run_refs_are_not_parsed_as_options(tmp_path):
    rw("record", "-l", "older", "--", "node", "tests/fixtures/chain.js", home=tmp_path)
    rw("record", "-l", "newer", "--", "node", "tests/fixtures/throw_timer.js", home=tmp_path)
    for cmd in ("timeline", "tree", "why"):
        newest, older = rw(cmd, "-1", home=tmp_path), rw(cmd, "-2", home=tmp_path)
        assert newest.returncode == 0 and "(newer)" in newest.stdout, cmd + newest.stdout + newest.stderr
        assert older.returncode == 0 and "(older)" in older.stdout, cmd + older.stdout + older.stderr
    d = rw("diff", "-2", "-1", home=tmp_path)
    assert d.returncode == 0 and "(older)" in d.stdout and "(newer)" in d.stdout
    assert rw("why", "-3", home=tmp_path).returncode == 2  # only 2 runs
    assert rw("why", "-1", "-e", "1", home=tmp_path).returncode == 0  # real options still parse


def test_record_with_watch(tmp_path):
    r = rw("record", "-w", "currentCart", "--", "node", "tests/fixtures/mutations.js", home=tmp_path)
    assert "watch=currentCart" in r.stdout and r.returncode == 1


def test_errors_are_friendly(tmp_path):
    assert rw("runs", home=tmp_path).stdout.lstrip().startswith("no runs yet")
    r = rw("record", home=tmp_path)
    assert r.returncode == 2 and "nothing to record" in r.stdout


def test_timeline_and_tree_on_demo(tmp_path):
    rw("record", "-l", "bad", "-w", "currentCart", "--", "node", "demo/traffic.js", home=tmp_path)
    t = rw("timeline", "bad", "-r", "3", "-c", home=tmp_path)
    assert t.returncode == 0 and "TypeError" in t.stdout and "charged $161" not in t.stdout
    assert "paymentConfirmed" in t.stdout and "currentCart" in t.stdout
    k = rw("timeline", "--kind", "mutation", home=tmp_path)
    assert k.stdout.count("checkout.js:12:5") == 3
    tr = rw("tree", home=tmp_path)
    assert tr.returncode == 0 and "#3 POST /order" in tr.stdout and "loadCart" in tr.stdout and "hidden" in tr.stdout
    bad = rw("timeline", "-r", "9", home=tmp_path)
    assert bad.returncode == 2 and "no request #9" in bad.stdout


def test_why_cli(tmp_path):
    rw("record", "-l", "bad", "-w", "currentCart", "--", "node", "demo/traffic.js", home=tmp_path)
    w = rw("why", "bad", "--evidence", home=tmp_path)
    assert w.returncode == 0 and "applyDiscount" in w.stdout and "request #4 overwrote it" in w.stdout and "seq " in w.stdout
    assert rw("why", "--error", "5", home=tmp_path).returncode == 2
    rw("record", "-l", "good", "--", "node", "demo/traffic.js", "--sequential", home=tmp_path)
    g = rw("why", "good", home=tmp_path)
    assert g.returncode == 0 and "no errors recorded" in g.stdout


def test_diff_cli(tmp_path):
    rw("record", "-l", "good", "--", "node", "demo/traffic.js", "--sequential", home=tmp_path)
    rw("record", "-l", "bad", "--", "node", "demo/traffic.js", home=tmp_path)
    d = rw("diff", "good", "bad", home=tmp_path)
    assert d.returncode == 0 and "first divergence" in d.stdout and "#3 http.in POST /order" in d.stdout
    assert rw("diff", "good", "nope", home=tmp_path).returncode == 2


def test_diff_ignores_writes_watched_in_only_one_run(tmp_path):
    rw("record", "-l", "good", "--", "node", "demo/traffic.js", "--sequential", home=tmp_path)
    rw("record", "-l", "bad", "-w", "currentCart", "--", "node", "demo/traffic.js", home=tmp_path)
    d = rw("diff", "good", "bad", home=tmp_path)
    assert "watched in only one run" in d.stdout
    assert "next, B does: #3 http.in POST /order" in d.stdout  # same divergence as with matching --watch

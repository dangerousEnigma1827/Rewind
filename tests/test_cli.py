"""End-to-end: the installed `rewind` entry point records real node programs."""
import os, shutil, subprocess, sys
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


def test_pending_cli(tmp_path):
    rw("record", "-l", "stall", "--", "node", "tests/fixtures/stall.js", home=tmp_path)
    p = rw("pending", "stall", "--evidence", home=tmp_path)
    assert p.returncode == 0 and "recording complete" in p.stdout and "GET /hang likely stalled" in p.stdout
    assert "seq " in p.stdout and "2 requests without a response" in p.stdout
    assert rw("pending", "nope", home=tmp_path).returncode == 2


def test_at_cli(tmp_path):
    rw("record", "-l", "bad", "-w", "currentCart", "--", "node", "demo/traffic.js", home=tmp_path)
    t = rw("timeline", "bad", "-k", "error", home=tmp_path)
    seq = next(l.split()[0] for l in t.stdout.splitlines() if "TypeError" in l)
    a = rw("at", "bad", seq, "--evidence", home=tmp_path)
    assert a.returncode == 0 and "currentCart" in a.stdout and "read at seq" in a.stdout and "request #4" in a.stdout
    assert "in flight:" in a.stdout and "seq " in a.stdout
    assert rw("at", "bad", "99999", home=tmp_path).returncode == 2
    assert rw("at", "-1", "0", home=tmp_path).returncode == 0  # -N run refs work here too


def test_why_uses_the_source_that_ran_not_the_edited_file(tmp_path):
    app, home = tmp_path / "app", tmp_path / "home"
    shutil.copytree(ROOT / "demo", app)
    rw("record", "-l", "bad", "--", "node", str(app / "traffic.js"), home=home)
    src = app / "checkout.js"
    failing = src.read_text(encoding="utf-8").splitlines()[22]
    assert "currentCart.items[i].price" in failing
    src.write_text("// rewritten after the run: no shared cart any more\n", encoding="utf-8")
    w = rw("why", "bad", home=home)
    assert w.returncode == 0
    assert "module-level binding(s) `currentCart`" in w.stdout and failing.strip() in w.stdout

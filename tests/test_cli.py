"""End-to-end: the installed `rewind` entry point records real node programs."""
import os, subprocess, sys
from pathlib import Path
from conftest import ROOT

REWIND = [sys.executable, "-m", "rewind.cli"]


def rw(*args, home):
    env = {**os.environ, "REWIND_HOME": str(home), "COLUMNS": "200", "NO_COLOR": "1"}
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


def test_record_with_watch(tmp_path):
    r = rw("record", "-w", "currentCart", "--", "node", "tests/fixtures/mutations.js", home=tmp_path)
    assert "watch=currentCart" in r.stdout and r.returncode == 1


def test_errors_are_friendly(tmp_path):
    assert rw("runs", home=tmp_path).stdout.startswith("no runs yet")
    r = rw("record", home=tmp_path)
    assert r.returncode == 2 and "nothing to record" in r.stdout

import json, os, subprocess, time
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
RECORDER = ROOT / "recorder" / "recorder.js"


def read_events(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


class Run:
    def __init__(self, code, events, stdout, stderr, path=None):
        self.code, self.events, self.stdout, self.stderr, self.path = code, events, stdout, stderr, path

    def kind(self, k):
        return [e for e in self.events if e["kind"] == k]

    def inits(self):
        return {e["aid"]: e for e in self.kind("async.init")}

    def chain(self, aid):
        ini, out = self.inits(), []
        while aid in ini:
            out.append(ini[aid]); aid = ini[aid]["tid"]
        return out


@pytest.fixture
def record(tmp_path):
    def _record(fixture, env=None, recorder=True, kill_when=None):
        out = tmp_path / (fixture + ".ndjson")
        e = {**os.environ, **(env or {})}
        if recorder:
            e["REWIND_OUT"] = str(out)
        elif not (env and "REWIND_OUT" in env):
            e.pop("REWIND_OUT", None)
        cmd = ["node"] + (["--require", str(RECORDER)] if recorder else []) + [str(FIX / fixture)]
        p = subprocess.Popen(cmd, env=e, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding="utf-8")
        if kill_when:
            deadline = time.time() + 10
            while time.time() < deadline and not (out.exists() and kill_when(out.read_text(encoding="utf-8"))):
                time.sleep(0.05)
            p.kill()
        so, se = p.communicate(timeout=30)
        return Run(p.returncode, read_events(out) if out.exists() else [], so, se, out)
    return _record


@pytest.fixture
def rewind_home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    monkeypatch.setenv("REWIND_HOME", str(h))
    return h

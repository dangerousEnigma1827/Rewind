"""Causal-reconstruction spike helpers (S1-S4). Records fixtures with the PRODUCTION recorder, read-only.

Three candidate edges per async resource, all from fields the recorder already writes:
  created   async.init.eid  the execution that created the resource (called then/await/setTimeout/new Promise)
  trigger   async.init.tid  triggerAsyncId; for a promise reaction this is the parent promise
  released  for a callback run (async.before of aid C): the last async.resolve of C's trigger before that run
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
FIX = HERE / "fixtures"
OUT = ROOT / "spikes" / "out" / "causal"   # spikes/out/ is gitignored
RECORDER = ROOT / "recorder" / "recorder.js"
PROBE = HERE / "probe_end.js"


def record(fixture: str | Path, env: dict | None = None, probe: bool = False) -> "Rec":
    fixture = Path(fixture) if Path(fixture).is_absolute() else FIX / fixture
    OUT.mkdir(parents=True, exist_ok=True)
    out, pout = OUT / f"{fixture.stem}.ndjson", OUT / f"{fixture.stem}.probe.ndjson"
    e = {**os.environ, "REWIND_OUT": str(out), **(env or {})}
    cmd = ["node", "--require", str(RECORDER)]
    if probe:
        e["REWIND_PROBE_OUT"] = str(pout)
        cmd += ["--require", str(PROBE)]
    p = subprocess.run(cmd + [str(fixture)], env=e, cwd=fixture.parent, capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    evs = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
    probes = [json.loads(l) for l in pout.read_text(encoding="utf-8").splitlines() if l.strip()] if probe else []
    return Rec(fixture, evs, probes, p.returncode, p.stdout, p.stderr)


class Rec:
    def __init__(self, fixture: Path, events, probes, code, stdout, stderr):
        self.fixture, self.events, self.probes, self.code, self.stdout, self.stderr = fixture, events, probes, code, stdout, stderr
        self.by_seq = {e["seq"]: e for e in events}
        self.inits = {e["aid"]: e for e in events if e["kind"] == "async.init"}
        self.anchors = {e["aid"]: e["data"]["req"] for e in events if e["kind"] == "http.in"}
        self.urls = {e["data"]["req"]: e["data"]["url"] for e in events if e["kind"] == "http.in"}
        self.resolves: dict[int, list] = {}
        self.befores: dict[int, list] = {}
        for e in events:
            if e["kind"] == "async.resolve":
                self.resolves.setdefault(e["aid"], []).append(e)
            elif e["kind"] == "async.before":
                self.befores.setdefault(e["aid"], []).append(e)
        src = fixture.read_text(encoding="utf-8").splitlines()
        self.markers = {m.group(1): i + 1 for i, l in enumerate(src) for m in re.finditer(r"// @(\w+)", l)}

    # ---- lookup ------------------------------------------------------------------
    def kind(self, k):
        return [e for e in self.events if e["kind"] == k]

    def logs(self, text: str):
        return [e for e in self.events if e["kind"] in ("log", "error.logged") and text in (e.get("name") or "")]

    def at(self, marker: str, type_: str | None = "PROMISE"):
        """async.init events whose first frame in the fixture file is on the marker's line."""
        line, name = self.markers[marker], self.fixture.name
        out = []
        for i in self.inits.values():
            f = next((f for f in i.get("stack") or [] if f["file"].endswith(name)), None)
            if f and f["line"] == line and (type_ is None or i["type"] == type_):
                out.append(i)
        return out

    # ---- the two attribution models ---------------------------------------------
    def _walk(self, aid, link):
        seen = set()
        while aid is not None and aid not in seen:
            if aid in self.anchors:
                return self.anchors[aid]
            seen.add(aid)
            i = self.inits.get(aid)
            if i is None:
                return None
            aid = i[link]
        return None

    def req_by_trigger(self, aid):   # what analysis.Run.request_of does today
        return self._walk(aid, "tid")

    def req_by_created(self, aid):   # candidate: follow the creating execution
        return self._walk(aid, "eid")

    # ---- candidate edge: released by ----------------------------------------------
    def released(self, before: dict):
        """For one callback run: (resolve event of its trigger that precedes the run, waited?) or None.
        waited = the resource was created before that resolve, i.e. something was actually waiting on it."""
        i = self.inits.get(before["aid"])
        if i is None:
            return None
        rs = [r for r in self.resolves.get(i["tid"], []) if r["seq"] < before["seq"]]
        if not rs:
            return None
        return rs[-1], i["seq"] < rs[-1]["seq"]

    def release_chain(self, aid):
        """From a callback context back to what released it. Only PROMISE reactions are "released"; a timer, I/O
        callback or request handler runs on its own clock and ends the chain (S3c: following a Timeout's tid would
        wrongly claim the promise it was created in released it). Returns (hops, releaser_aid or None).
        hops: [(reaction_aid, resolve_event, waited)] nearest first."""
        hops, seen = [], set()
        while aid not in seen and self.inits.get(aid, {}).get("type") == "PROMISE":
            seen.add(aid)
            runs = [b for b in self.befores.get(aid, [])]
            hit = self.released(runs[-1]) if runs else None
            if hit is None:
                return hops, None
            res, waited = hit
            hops.append((aid, res, waited))
            aid = res["eid"]
        return hops, aid

    # ---- presentation -------------------------------------------------------------
    def describe(self, aid) -> str:
        if aid in self.anchors:
            return f"REQ#{self.anchors[aid]}({self.urls[self.anchors[aid]]})"
        i = self.inits.get(aid)
        if i is None:
            return "main" if aid == 1 else f"aid{aid}(no init)"
        f = next((f for f in i.get("stack") or [] if f["file"].endswith(self.fixture.name)), None)
        nm = f" {i['name']}" if i.get("name") and i["name"] != "<anonymous>" else ""
        return f"{i['type']}{nm}{'@' + str(f['line']) if f else ''}#{aid}"

    def line(self, e) -> str:
        k = e["kind"]
        if k == "async.init":
            return (f"{e['seq']:>5} init    {self.describe(e['aid'])}  tid={self.describe(e['tid'])}  "
                    f"eid={self.describe(e['eid'])}")
        if k in ("async.before", "async.after", "async.resolve", "async.cancel"):
            return f"{e['seq']:>5} {k[6:]:<7} {self.describe(e['aid'])}  eid={self.describe(e['eid'])}"
        return f"{e['seq']:>5} {k:<7} {e.get('name')!r}  eid={self.describe(e['eid'])}"

    def trace(self, aids=None, kinds=("log", "error.logged", "error.uncaught", "http.in", "http.out")) -> list[str]:
        """Events touching `aids` (default: resources created from the fixture file), plus story events."""
        if aids is None:
            aids = {a for a in self.inits if "@" in self.describe(a) or a in self.anchors}
        return [self.line(e) for e in self.events
                if (e["kind"].startswith("async.") and e.get("aid") in aids) or e["kind"] in kinds]

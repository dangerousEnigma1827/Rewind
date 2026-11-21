"""M0 spike checker: runs fixtures under spikes/rec.js and checks assumptions."""
import json, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).parent
OUT = HERE / "out"; OUT.mkdir(exist_ok=True)
REC = str(HERE / "rec.js")
results = []

def run(fixture, env=None, kill_after=None):
    out = OUT / (fixture.replace(".js", "") + ".ndjson")
    e = {**os.environ, "REWIND_OUT": str(out), **(env or {})}
    p = subprocess.Popen(["node", "--require", REC, str(HERE / "fixtures" / fixture)], env=e,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if kill_after:
        time.sleep(kill_after); p.kill()
    so, se = p.communicate(timeout=30)
    evs = [json.loads(l) for l in out.read_text().splitlines() if l.strip()] if out.exists() else []
    return p.returncode, evs, se

def check(name, ok, detail=""):
    results.append((name, bool(ok), detail)); print(("PASS " if ok else "FAIL ") + name, "-", detail)

def inits(evs): return {e["aid"]: e for e in evs if e["kind"] == "async.init"}

def chain(evs, aid):
    ini, out = inits(evs), []
    while aid in ini:
        out.append(ini[aid]); aid = ini[aid]["tid"]
    return out

def fns(c): return [s.split(" ")[0] for e in c for s in (e.get("stack") or [])]

# E1 ---------------------------------------------------------------------------
def cbs(c): return [e.get("cb") for e in c if e.get("cb")]
def user(c): return [e for e in c if e.get("stack")]   # hops with user frames; internal hops collapse
code, evs, _ = run("e1_chain.js")
leaf = next(e for e in evs if e["kind"] == "log" and e["name"] == "leaf")
c = chain(evs, leaf["eid"])
types = [e["type"] for e in c]
check("E1 leaf log runs inside stepD's Timeout", c and c[0].get("cb") == "stepD", f"types={types}")
check("E1 user-visible chain Timeout<-FS<-Timeout (internal fs hops collapse)",
      [e["type"] for e in user(c)] == ["Timeout", "FSREQCALLBACK", "Timeout"], str([e["type"] for e in user(c)]))
check("E1 creation stacks name scheduling fns stepC/stepB/stepA", ["stepC", "stepB", "stepA"] == [fns([e])[0].split(".")[-1] for e in user(c)], str([fns([e])[:1] for e in user(c)]))
check("E1 internal fs hops have no user frames", all(not e.get("stack") for e in c if e not in user(c)), f"{len(c)-len(user(c))} internal")
other = next(e for e in evs if e["kind"] == "log" and e["name"] == "other")
check("E1 sibling branch not on leaf chain", other["eid"] not in [x["aid"] for x in c])
check("E1 eid == active-stack top for logs", all(e["eid"] == e["top"] for e in evs if e["kind"] == "log"))

# E2 ---------------------------------------------------------------------------
# sync throws inside callbacks: expect uncaught origin, eid == top, chain[0] creation stack names scheduler
for fx in ("e2_timer.js", "e2_fs.js"):
    code, evs, se = run(fx)
    e = next(x for x in evs if x["kind"] == "error.uncaught")
    c = chain(evs, e["eid"])
    check(f"E2 {fx} origin=uncaughtException, eid==active top", e["origin"] == "uncaughtException" and e["eid"] == e["top"], f"{e['origin']} eid={e['eid']} top={e['top']}")
    check(f"E2 {fx} throwing callback's creation site = scheduleIt", fns(user(c)[:1])[:1] == ["scheduleIt"], str(fns(user(c)[:1])[:2]))
# throws in promise callbacks become rejections: no active callback; eid must be the rejected promise
for fx, root_cb in (("e2_then.js", "scheduleIt"), ("e2_await.js", "outer"), ("e2_await_caught_by_monitor.js", "root")):
    for ps in ("0", "1"):
        code, evs, se = run(fx, {"REWIND_PROMISE_STACKS": ps})
        e = next(x for x in evs if x["kind"] == "error.uncaught")
        c = chain(evs, e["eid"])
        check(f"E2 {fx} ps={ps} origin=unhandledRejection, top=None, eid is PROMISE",
              e["origin"] == "unhandledRejection" and e["top"] is None and c and c[0]["type"] == "PROMISE", f"{e['origin']} top={e['top']} types={[x['type'] for x in c]}")
        check(f"E2 {fx} ps={ps} chain reaches Timeout cb '{root_cb}'", root_cb in cbs(c), str(cbs(c)))
        if ps == "1":
            check(f"E2 {fx} promise creation stacks show user fn", fns(c[:1])[:3], str(fns(c[:1])[:3]))

# E3 ---------------------------------------------------------------------------
code, evs, se = run("e3_rejection.js")
u = next(e for e in evs if e["kind"] == "error.uncaught")
check("E3 default mode: monitor sees rejection, exit 1", u["origin"] == "unhandledRejection" and code == 1, f"exit={code}")
check("E3 monitor eid chain reaches Timeout cb root", "root" in cbs(chain(evs, u["eid"])), str(cbs(chain(evs, u["eid"]))))
code2, evs2, se2 = run("e3_rejection.js", {"REWIND_REJECTION_HANDLER": "1"})
r = next(e for e in evs2 if e["kind"] == "error.rejection")
u2 = next(e for e in evs2 if e["kind"] == "error.uncaught")
check("E3 WeakMap gives rejected promise aid == default-mode monitor eid", r["aid"] == u["eid"], f"weakmap={r['aid']} monitor={u['eid']}")
check("E3 (finding) rethrow from handler loses context: eid=0", u2["eid"] == 0, f"eid={u2['eid']}")
check("E3 handler+rethrow preserves exit code", code2 == code, f"default={code} handler={code2}")
code, evs, se = run("e3_await_log.js")
for i, req in ((1, "req1"), (2, "req2")):
    lg = next(e for e in evs if e["kind"] == "log" and e["name"] == f"done {i}")
    cb = cbs(chain(evs, lg["eid"]))
    check(f"E3 log after 2 awaits attributed to {req} only", req in cb and ({"req1", "req2"} - {req}).isdisjoint(cb), str(cb))

# E4 ---------------------------------------------------------------------------
all_evs = []
for f in OUT.glob("*.ndjson"):
    all_evs += [json.loads(l) for l in f.read_text().splitlines() if l.strip()]
self_inits = [e for e in all_evs if e["kind"] == "async.init" and any("rec.js" in s for s in (e.get("stack") or []))]
check("E4 no recorder-originated async resources", not self_inits, f"{len(self_inits)} found")
seqs_ok = all(json.loads(l)["seq"] == i for f in OUT.glob("*.ndjson") for i, l in enumerate(f.read_text().splitlines()))
check("E4 seq contiguous in every file (no lost/dup lines)", seqs_ok)

# E5 ---------------------------------------------------------------------------
for fx in ("e5_normal.js", "e5_exit1.js", "e2_timer.js", "e3_rejection.js"):
    code, evs, _ = run(fx)
    check(f"E5 {fx} run.end flushed", evs and evs[-1]["kind"] == "run.end", f"exit={code} n={len(evs)}")
code, evs, _ = run("e5_hang.js", kill_after=1.5)
check("E5 SIGKILL leaves readable partial file", len(evs) > 0 and evs[-1]["kind"] != "run.end", f"n={len(evs)} (data after last 256-flush lost)")

print(f"\n{sum(ok for _, ok, _ in results)}/{len(results)} passed")
(HERE / "check_results.json").write_text(json.dumps(results, indent=1))

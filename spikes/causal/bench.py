"""S5 overhead: (1) recording cost of a res.end probe, (2) analysis cost of the creation/release indexes.

Workload: spikes/fixtures/e6_load.js (N HTTP requests: fs read + timer + Promise.all), the E6 workload, recorded with
the PRODUCTION recorder. Run:  .venv/Scripts/python spikes/causal/bench.py   (writes bench_results.json)
"""
import json, os, statistics, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lib  # noqa: E402

N, REPS = os.environ.get("N", "300"), int(os.environ.get("REPS", "5"))
LOAD = lib.ROOT / "spikes" / "fixtures" / "e6_load.js"
lib.OUT.mkdir(parents=True, exist_ok=True)
out, pout = lib.OUT / "bench.ndjson", lib.OUT / "bench.probe.ndjson"

modes = {
    "baseline (no recorder)": None,
    "recorder": [],
    "recorder + end probe, no stack": [("PROBE_STACK", "0")],
    "recorder + end probe + stack": [("PROBE_STACK", "1")],
}
ts = {name: [] for name in modes}
counts = {}
for _ in range(REPS):  # round-robin, so machine drift (OneDrive, AV, thermal) hits every mode equally
    for name, extra in modes.items():
        cmd, env = ["node"], {**os.environ, "N": N}
        if extra is not None:
            cmd += ["--require", str(lib.RECORDER)]; env["REWIND_OUT"] = str(out)
            if extra:
                cmd += ["--require", str(lib.PROBE)]; env["REWIND_PROBE_OUT"] = str(pout); env.update(extra)
        t = time.perf_counter()
        subprocess.run(cmd + [str(LOAD)], env=env, check=True, capture_output=True)
        ts[name].append(time.perf_counter() - t)
        counts[name] = (sum(1 for _ in out.open()) if extra is not None else 0, sum(1 for _ in pout.open()) if extra else 0)
rec = {name: {"wall_s": round(statistics.median(v), 3), "min_s": round(min(v), 3), "max_s": round(max(v), 3),
              "events": counts[name][0], "probe_events": counts[name][1]} for name, v in ts.items()}
b = rec["baseline (no recorder)"]["wall_s"]
r0 = rec["recorder"]["wall_s"]
print(f"recording, e6_load N={N}, median of {REPS}")
for k, v in rec.items():
    print(f"  {k:32} {v['wall_s']:6}s  x{v['wall_s'] / b:4.2f} vs baseline  x{v['wall_s'] / r0:4.2f} vs recorder"
          f"  {v['events']:>7} events  +{v['probe_events']} probe")

# ---- analysis cost over one recording (the last one written above is the full recorder run) -------------------
subprocess.run(["node", "--require", str(lib.RECORDER), str(LOAD)], env={**os.environ, "N": N, "REWIND_OUT": str(out)},
               check=True, capture_output=True)
t = time.perf_counter()
r = lib.Rec(LOAD, [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines() if l.strip()], [], 0, "", "")
t_index = time.perf_counter() - t


def memo_walk(link):
    cache = {}

    def walk(aid):
        path, seen, hit = [], set(), None
        while aid is not None and aid not in seen:
            if aid in cache:
                hit = cache[aid]; break
            if aid in r.anchors:
                hit = r.anchors[aid]; path.append(aid); break
            seen.add(aid); path.append(aid)
            i = r.inits.get(aid)
            if i is None:
                break
            aid = i[link]
        for a in path:
            cache[a] = hit
        return hit
    return walk


ctx = [e["eid"] for e in r.events] + list(r.inits)
timings = {}
for link in ("tid", "eid"):
    w = memo_walk(link)
    t = time.perf_counter()
    for a in ctx:
        w(a)
    timings[f"attribution via {link}"] = time.perf_counter() - t
t = time.perf_counter()
rel = {b["seq"]: r.released(b) for bs in r.befores.values() for b in bs if r.inits.get(b["aid"], {}).get("type") == "PROMISE"}
timings["released-by index (promise reactions)"] = time.perf_counter() - t
ana = {"events": len(r.events), "load_and_index_s": round(t_index, 3), **{k: round(v, 3) for k, v in timings.items()},
       "promise_reaction_runs": len(rel), "with_release_edge": sum(1 for v in rel.values() if v)}
print(f"analysis over {len(r.events)} events:")
for k, v in ana.items():
    print(f"  {k:40} {v}")
(Path(__file__).parent / "bench_results.json").write_text(json.dumps({"N": N, "reps": REPS, "recording": rec, "analysis": ana}, indent=1))

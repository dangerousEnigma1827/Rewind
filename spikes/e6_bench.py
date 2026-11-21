import os, subprocess, time, json, statistics
from pathlib import Path
H = Path(__file__).parent; out = H / "out" / "e6.ndjson"
modes = {"baseline": None, "no stacks": {"REWIND_STACKS": "0"}, "stacks (no promise)": {}, "stacks + promise": {"REWIND_PROMISE_STACKS": "1"}}
res = {}
for name, env in modes.items():
    ts = []
    for _ in range(3):
        cmd = ["node"] + (["--require", str(H / "rec.js")] if env is not None else []) + [str(H / "fixtures" / "e6_load.js")]
        t = time.perf_counter()
        subprocess.run(cmd, env={**os.environ, "REWIND_OUT": str(out), **(env or {})}, check=True, capture_output=True)
        ts.append(time.perf_counter() - t)
    n = sum(1 for _ in out.open()) if env is not None else 0
    res[name] = {"wall_s": round(statistics.median(ts), 2), "events": n, "mb": round(out.stat().st_size / 1e6, 1) if env is not None else 0}
    out.unlink(missing_ok=True)
b = res["baseline"]["wall_s"]
for k, v in res.items(): print(f"{k:22} {v['wall_s']:6}s  x{v['wall_s']/b:4.1f}  {v['events']:>8} events  {v['mb']} MB")
(H / "e6_results.json").write_text(json.dumps(res, indent=1))

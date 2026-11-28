"""Causal-reconstruction spikes S1-S4: records each fixture with the PRODUCTION recorder and checks assumptions.

Run:  .venv/Scripts/python spikes/causal/check.py
Writes spikes/causal/check_results.json and spikes/causal/sequences.md (the event traces the verdicts rest on).
Verdicts: PASS (assumption holds), FAIL (it doesn't), AMBIGUOUS (the recording can't settle it), LIMIT (confirmed
unobservable: Rewind must say so rather than guess).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lib  # noqa: E402

HERE = Path(__file__).parent
results: list[dict] = []
traces: list[str] = []
NOISE = ("PIPEWRAP", "TickObject", "TTYWRAP", "SIGNALWRAP", "SHUTDOWNWRAP", "HTTPCLIENTREQUEST", "TCPCONNECTWRAP",
         "GETADDRINFOREQWRAP", "HTTPINCOMINGMESSAGE", "TCPSERVERWRAP", "TCPWRAP", "FILEHANDLE", "FILEHANDLECLOSEREQ",
         "FSREQPROMISE", "WRITEWRAP", "STREAM_END_OF_STREAM", "Timeout#", "TIMERWRAP")


def check(sid: str, name: str, ok, detail: str = "", verdict: str | None = None):
    v = verdict or ("PASS" if ok else "FAIL")
    results.append({"spike": sid, "check": name, "verdict": v, "detail": detail})
    print(f"{v:9} {sid} {name}" + (f"  -- {detail}" if detail else ""))


def keep_trace(r: lib.Rec, title: str, aids=None):
    # field 2 is the resource ("PROMISE@5#31", "REQ#1(/a)", ...) for async lines; story lines are always kept
    lines = [l for l in r.trace(aids) if not l.split()[1].startswith(("init", "before", "after", "resolve", "cancel"))
             or not l.split()[2].startswith(NOISE)]
    traces.append(f"### {title}  (`{r.fixture.name}`)\n\n```\n" + "\n".join(lines) + "\n```\n")


def releaser(r: lib.Rec, aid):
    hops, end = r.release_chain(aid)
    return hops, end, (r.inits.get(end) if end is not None else None)


def req_of_url(r: lib.Rec, url: str) -> int:
    return next(q for q, u in r.urls.items() if u == url)


def log(r: lib.Rec, text: str) -> dict:
    return r.logs(text)[0]


# ==== S1: promise settlement timing =========================================================================
r = lib.record("s1_timer.js"); keep_trace(r, "S1a promise settled by a timer")
p, = r.at("P"); cont = r.at("AWAIT")[0]; fire = next(i for i in r.inits.values() if i.get("name") == "fire")
res = r.resolves[p["aid"]]
check("S1", "a: async.resolve of a timer-settled promise fires inside that timer callback",
      len(res) == 1 and res[0]["eid"] == fire["aid"], f"resolve seq {res[0]['seq']} eid={r.describe(res[0]['eid'])}")
check("S1", "a: the await continuation's trigger is the awaited promise and runs after its resolve",
      cont["tid"] == p["aid"] and r.befores[cont["aid"]][0]["seq"] > res[0]["seq"])
hops, end, _ = releaser(r, log(r, "after await")["eid"])
check("S1", "a: release chain from the log after `await` ends at the timer", end == fire["aid"], r.describe(end))

r = lib.record("s1_adopt.js"); keep_trace(r, "S1b adoption: outer resolved with a pending inner promise", set(r.inits))
inner, = r.at("INNER"); outer, = r.at("OUTER")
ri, ro = r.resolves[inner["aid"]][0], r.resolves[outer["aid"]][0]
outer_fire = next(i for i in r.inits.values() if i.get("name") == "outerFire")
outer_fire_ran = r.befores[outer_fire["aid"]][0]["seq"]
check("S1", "b: resolve(outer, pendingInner) does NOT fire async.resolve at the resolve() call",
      not any(outer_fire_ran < x["seq"] < ri["seq"] for x in r.resolves[outer["aid"]]),
      f"outerFire ran at seq {outer_fire_ran}; outer's async.resolve at seq {ro['seq']}, after inner's at {ri['seq']}")
mid = r.inits.get(ro["eid"])
check("S1", "b: outer settles inside an internal reaction promise whose trigger is inner",
      mid is not None and mid["type"] == "PROMISE" and mid["tid"] == inner["aid"] and not mid.get("stack"),
      f"eid={r.describe(ro['eid'])} tid={r.describe(mid['tid']) if mid else None} (no creation stack)")
hops, end, ei = releaser(r, log(r, "cont v")["eid"])
check("S1", "b: release chain walks through the internal hop to innerFire (the real releaser)",
      ei and ei.get("name") == "innerFire", f"{len(hops)} hops -> {r.describe(end)}")

r = lib.record("s1_async_return.js"); keep_trace(r, "S1c `return p` vs `return await p`")
for text in ("got ret", "got aw"):
    hops, end, ei = releaser(r, log(r, text)["eid"])
    check("S1", f"c: `{text}` release chain ends at slowFire", ei and ei.get("name") == "slowFire",
          f"{len(hops)} promise hops -> {r.describe(end)}")

r = lib.record("s1_all.js"); keep_trace(r, "S1d Promise.all / Promise.race")
for text, delay, what in (("all a,b", 12, "the SLOWEST element (12 ms)"), ("race fast", 4, "the WINNER (4 ms)")):
    hops, end, ei = releaser(r, log(r, text)["eid"])
    got = (ei.get("data") or {}).get("delay") if ei else None
    check("S1", f"d: `{text}` is released by {what}", ei and ei["type"] == "Timeout" and got == delay,
          f"{len(hops)} hops -> {r.describe(end)} delay={got}")

r = lib.record("s1_reject.js"); keep_trace(r, "S1e rejection")
p, = r.at("P"); fail = next(i for i in r.inits.values() if i.get("name") == "failLater")
res = r.resolves.get(p["aid"], [])
check("S1", "e: a rejection also emits async.resolve, in the rejecting callback",
      len(res) == 1 and res[0]["eid"] == fail["aid"], f"seq {res[0]['seq'] if res else None}")
check("S1", "e: fulfilled vs rejected is distinguishable from the hook data", False,
      "async.resolve carries only aid/eid: the outcome is not recorded. Say 'settled', never 'resolved'", "AMBIGUOUS")

r = lib.record("s1_thenable.js"); keep_trace(r, "S1f non-native thenable", set(r.inits))
hops, end, ei = releaser(r, log(r, "thenable 7")["eid"])
check("S1", "f: awaiting a thenable: release chain ends at the timer that called its resolve",
      ei and ei.get("name") == "thenableFire", f"{len(hops)} hops -> {r.describe(end)}")

r = lib.record("s1_presettled.js"); keep_trace(r, "S1g awaiting an already-settled promise", set(r.inits))
cont = r.at("AWAIT")[0]; hit = r.released(r.befores[cont["aid"]][0])
check("S1", "g: awaiting an already-settled promise is not a wait (resolve precedes the await's init)",
      hit is not None and hit[1] is False,
      f"resolve seq {hit[0]['seq']} < continuation init seq {cont['seq']}" if hit else "no edge")

# ==== S2: eid on async.init ================================================================================
r = lib.record("s2_contexts.js")
made, ok, rows = r.at("MAKE"), 0, []
for l in [e for e in r.events if e["kind"] == "log" and e["name"].startswith("ctx")]:
    where, seen = l["name"].split()[1], int(l["name"].split()[2])
    p = next(i for i in made if i["seq"] > l["seq"])
    ok += p["eid"] == seen
    rows.append(f"{where}={p['eid']}/{seen}")
check("S2", "a: async.init.eid equals executionAsyncId() seen by user code (8 creation contexts)", ok == 8, " ".join(rows))

# The fixtures that existed before F15 (kill-driven forever.js / kill_after_error.js left out: they never exit).
# F15 added shared_*.js, mutex_queue.js and response_origin.js, which cross requests ON PURPOSE.
PRE_F15 = ["chain.js", "cluster_primary.js", "fork_parent.js", "http_keepalive.js", "http_two.js", "many_writes.js",
           "mutations.js", "reads.js", "reads_http.js", "reject_await.js", "snapshot.js", "stall.js", "state.js",
           "tdz_read.js", "throw_timer.js"]
fixtures = [lib.ROOT / "demo" / "traffic.js"] + [lib.ROOT / "tests" / "fixtures" / f for f in PRE_F15] \
    + [lib.ROOT / "spikes" / "fixtures" / "e6_load.js"]
story_dis, user_dis, internal_dis, eid0_user, eid0_types, n_story = 0, 0, 0, 0, set(), 0
for f in fixtures:
    r = lib.record(f, env={"N": "50"})
    story = [e for e in r.events if not e["kind"].startswith("async.") and e["kind"] != "run.start"]
    n_story += len(story)
    story_dis += sum(r.req_by_trigger(e["eid"]) != r.req_by_created(e["eid"]) for e in story)
    for i in r.inits.values():
        if r.req_by_trigger(i["aid"]) != r.req_by_created(i["aid"]):
            if any(not x["file"].startswith("node:") and "node_modules/" not in x["file"] for x in i.get("stack") or []):
                user_dis += 1
            else:
                internal_dis += 1
        if i["eid"] == 0:
            eid0_types.add(i["type"])
            eid0_user += bool(i.get("stack"))
check("S2", f"b: INVARIANT on the {len(fixtures)} existing fixtures + demo: both models give every story event the same request",
      story_dis == 0, f"{n_story} story events, {story_dis} differ")
check("S2", "b: ...and every resource created from user code", user_dis == 0,
      f"{user_dis} user-code resources differ; {internal_dis} internal ones do (SHUTDOWNWRAP teardown: trigger=None, created=its request)")
check("S2", "c: eid=0 occurs only on native resources with no JS creation context (need a tid fallback)",
      eid0_user == 0, f"types {sorted(eid0_types)}, {eid0_user} with user frames")

# ==== S3: shared async patterns =============================================================================
r = lib.record("s3_inflight.js"); keep_trace(r, "S3a in-flight promise shared by two requests")
A, B = req_of_url(r, "/a"), req_of_url(r, "/b"); lb = log(r, "handler /b")
check("S3", "a: TODAY (trigger chain) /b's own log is attributed to /a", r.req_by_trigger(lb["eid"]) == A,
      f"trigger -> #{r.req_by_trigger(lb['eid'])}, /a is #{A}: this is the production bug")
check("S3", "a: creation chain attributes it to /b", r.req_by_created(lb["eid"]) == B)
hops, end, ei = releaser(r, lb["eid"])
check("S3", "a: /b was released by /a's timer, after actually waiting (cross-request dependency)",
      ei and ei.get("name") == "fetchPrice" and r.req_by_created(end) == A and hops[0][2],
      f"{r.describe(end)} created by #{r.req_by_created(end)}, waited={hops[0][2] if hops else None}")

r = lib.record("s3_settled_cache.js"); keep_trace(r, "S3b cache hit on an already-settled promise")
A, B = req_of_url(r, "/a"), req_of_url(r, "/b"); lb = log(r, "handler /b")
check("S3", "b: TODAY a plain cache hit also misattributes /b's log to /a", r.req_by_trigger(lb["eid"]) == A,
      f"trigger -> #{r.req_by_trigger(lb['eid'])}")
check("S3", "b: creation chain attributes it to /b", r.req_by_created(lb["eid"]) == B)
hops, _, _ = releaser(r, lb["eid"])
check("S3", "b: not a wait: the shared promise settled before /b awaited it", hops and hops[0][2] is False)

r = lib.record("s3_mutex.js"); keep_trace(r, "S3c mutex with a resolver queue")
A, B = req_of_url(r, "/a"), req_of_url(r, "/b"); lb = log(r, "critical section /b")
check("S3", "c: both models agree /b's work is /b's (its own new Promise)",
      r.req_by_trigger(lb["eid"]) == r.req_by_created(lb["eid"]) == B)
hops, end, ei = releaser(r, lb["eid"])
check("S3", "c: ...and only the release edge shows /a's `work` timer let /b in",
      ei and ei.get("name") == "work" and r.req_by_created(end) == A, f"{len(hops)} hop -> {r.describe(end)} of #{r.req_by_created(end)}")

r = lib.record("s3_once.js"); keep_trace(r, "S3d events.once across requests")
A, B = req_of_url(r, "/a"), req_of_url(r, "/b"); lb = log(r, "b saw ready")
hops, end, ei = releaser(r, lb["eid"])
check("S3", "d: events.once: /b released by /a's announce timer through events' internal promise",
      ei and ei.get("name") == "announce" and r.req_by_created(end) == A and r.req_by_created(lb["eid"]) == B,
      f"{len(hops)} hops -> {r.describe(end)}")

r = lib.record("s3_shared_reject.js"); keep_trace(r, "S3e shared promise rejects")
A, B = req_of_url(r, "/a"), req_of_url(r, "/b")
eb = [e for e in r.kind("error.logged")][1]
check("S3", "e: TODAY /b's logged error is attributed to /a", r.req_by_trigger(eb["eid"]) == A,
      f"trigger -> #{r.req_by_trigger(eb['eid'])}; `rewind why` would put it in the wrong request")
check("S3", "e: creation chain attributes it to /b", r.req_by_created(eb["eid"]) == B)
hops, end, ei = releaser(r, eb["eid"])
check("S3", "e: /b's failure was released by /a's rejecting timer (inherited failure)",
      ei and ei.get("name") == "fetchPrice" and r.req_by_created(end) == A)

r = lib.record("s3_sync_listener.js"); keep_trace(r, "S3f listener registered by /b, emitted synchronously by /a")
A, B = req_of_url(r, "/a"), req_of_url(r, "/b"); lb = log(r, "b listener ran")
both = (r.req_by_trigger(lb["eid"]), r.req_by_created(lb["eid"]))
check("S3", "f: a sync listener runs in the EMITTER's context; the registering request is invisible to async_hooks",
      both == (A, A), f"both models -> #{A} (/a); /b registered it. No async resource exists to link them", "LIMIT")

# ==== S4: res.end() call context ============================================================================
r = lib.record("s4_end.js", probe=True); keep_trace(r, "S4 res.end call sites")
outs = {e["data"]["req"]: e for e in r.kind("http.out")}
probe = {p["url"]: p for p in r.probes}
check("S4", "today http.out always carries the request anchor as eid, so the responding callback is lost",
      len(outs) == 6 and all(r.anchors.get(o["eid"]) == q for q, o in outs.items()),
      f"{len(outs)} responses, eid = own anchor for all")
for url, want in (("/direct", "the handler itself"), ("/await", "the await continuation"), ("/timer", "the `later` timer")):
    p, q = probe[url], req_of_url(r, url)
    i = r.inits.get(p["eid"])
    good = {"/direct": r.anchors.get(p["eid"]) == q, "/await": bool(i and i["type"] == "PROMISE"),
            "/timer": bool(i and i.get("name") == "later")}[url]
    check("S4", f"{url}: end() runs in {want}, owned by its own request", good and r.req_by_created(p["eid"]) == q,
          f"{r.describe(p['eid'])}  stack={p['stack'][:1]}")
p, P, R = probe["/park"], req_of_url(r, "/park"), req_of_url(r, "/release")
check("S4", "/park: ended from /release's handler; the end-call context belongs to the OTHER request",
      r.req_by_created(p["eid"]) == R != P, f"#{P} ended in #{R}'s context")
p, q = probe["/pipe"], req_of_url(r, "/pipe")
check("S4", "/pipe: stream.pipe ends the response from Node internals (no user frame), still inside its request",
      not p["stack"] and r.req_by_created(p["eid"]) == q, f"{r.describe(p['eid'])}, stack={p['stack']}")
ends = r.kind("http.end")  # since F15 the production recorder writes these itself
check("S4", "production http.end: one per response, same context as the probe, no recorder frames",
      len(ends) == 6 and all(next(p for p in r.probes if p["url"] == r.urls[e["data"]["req"]])["eid"] == e["eid"] for e in ends)
      and not any("recorder" in f["file"] for e in ends for f in e.get("stack") or []),
      f"{len(ends)} http.end events (the probe is now redundant)" if ends else "recorder predates F15: no http.end")

# ---- output ---------------------------------------------------------------------------------------------------
(HERE / "check_results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
(HERE / "sequences.md").write_text(
    "# Event sequences behind the S1-S4 verdicts\n\nGenerated by `spikes/causal/check.py` with the production recorder.\n"
    "Format: `seq kind resource  tid=… eid=…`; `@N` = creation line in the fixture, `#N` = asyncId. Node-internal\n"
    "resources (sockets, ticks, pipes) are omitted for readability; the full NDJSON is in `spikes/out/causal/`.\n\n"
    + "\n".join(traces), encoding="utf-8")
counts = {v: sum(x["verdict"] == v for x in results) for v in ("PASS", "FAIL", "AMBIGUOUS", "LIMIT")}
print(f"\n{len(results)} checks: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
sys.exit(1 if counts["FAIL"] else 0)

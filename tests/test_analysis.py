"""Analysis engine over real recordings: attribution, tree building, why, diff."""
import pytest
from rewind import analysis as A
from rewind import store


def load(record, rewind_home, fx, env=None, rid="r", **kw):
    r = record(fx, env)
    db = store.connect()
    store.ingest(db, rid, r.path, **kw)
    return A.Run(store.events(db, rid), sources=store.sources(db, rid))


@pytest.fixture
def demo(record, rewind_home):
    def _demo(sequential=False, watch=True, reads=True):
        fx = "../../demo/traffic.js"
        env = {"REWIND_WATCH": "currentCart"} if watch else {}
        if sequential:
            env["DEMO_SEQUENTIAL"] = "1"
        if not reads:
            env["REWIND_READS"] = "0"
        return load(record, rewind_home, fx, env, rid=f"d{int(sequential)}{int(watch)}{int(reads)}")
    return _demo


# ---- attribution & tree (M3) -------------------------------------------------------
def test_request_attribution_on_demo(demo):
    run = demo()
    assert [r.inbound.name for r in run.requests.values()] == ["GET /health", "POST /order", "POST /order", "POST /order"]
    muts = run_muts = [e for e in run.events if e.kind == "mutation"]
    assert [run.request_of(m.eid) for m in muts] == [2, 3, 4]
    logs = {e.name: run.request_of(e.eid) for e in run.events if e.kind == "log"}
    assert logs == {"order A-101: charged $161": 2, "order C-303: charged $11": 4}
    assert run.request_of(run.errors[0].eid) == 3


def test_describe_names_user_code(demo):
    run = demo()
    m = next(e for e in run.events if e.kind == "mutation")
    assert run.describe(m.eid) == "FSREQCALLBACK via loadCart"
    err = run.errors[0]
    assert run.describe(err.eid) == "Timeout paymentConfirmed from chargePayment"
    assert A.where(run.site(err.eid)) == "demo/checkout.js:18"


def test_tree_prunes_quiet_and_folds_internal_hops(demo):
    run = demo()
    root, pruned = A.build_tree(run)
    full, pruned_full = A.build_tree(run, full=True)

    def walk(n):
        yield n
        for c in n.children:
            yield from walk(c)

    nodes, all_nodes = list(walk(root)), list(walk(full))
    assert pruned > 0 and pruned_full == 0 and len(nodes) < len(all_nodes)
    # every story event is still reachable in the pruned tree: pruning never hides evidence
    shown = {e.seq for n in nodes for e in n.events}
    assert {e.seq for e in run.story if A.interesting(e) and e.eid != 1} <= shown
    assert any(n.hidden for n in nodes)  # frameless fs hops folded
    # request subtree contains only that request's work
    sub, _ = A.build_tree(run, run.requests[3].anchor)
    assert {run.request_of(e.eid) for n in walk(sub) for e in n.events} == {3}


def test_short_fn():
    assert A.short_fn("Timeout.paymentConfirmed") == "paymentConfirmed"
    assert A.short_fn("Server.<anonymous>") == "Server.<anonymous>"
    assert A.short_fn(None) == "<anonymous>"


# ---- why (M4) ------------------------------------------------------------------------
def levels(inv, level):
    return [f.text for f in inv.findings if f.level == level]


def assert_evidence_integrity(run, inv):
    for f in inv.findings:
        assert all(s in run.by_seq for s in f.evidence), f.text
        if f.level == A.INFERRED:
            assert f.evidence, "an inference must cite evidence: " + f.text
        if "write" in f.text and f.level == A.OBSERVED and "no writes" not in f.text:
            assert any(run.by_seq[s].kind == "mutation" for s in f.evidence), f.text


def test_why_with_watch_proves_the_overwrite(demo):
    run = demo()
    inv = A.investigate(run, run.errors[0])
    assert_evidence_integrity(run, inv)
    assert inv.request.id == 3
    obs, der, inf = levels(inv, A.OBSERVED), levels(inv, A.DERIVED), levels(inv, A.INFERRED)
    assert any("thrown in applyDiscount at demo/checkout.js:23" in t for t in obs)
    assert any("Timeout paymentConfirmed from chargePayment" in t and "demo/checkout.js:18" in t for t in obs)
    assert any("C-303" in t and "last write" in t for t in obs)
    assert any(t == "that write was made by request #4 POST /order" for t in der)
    assert any("#3 POST /order set `currentCart` itself" in t and "request #4 overwrote it" in t for t in der)
    assert len(inf) == 1 and "race" in inf[0]
    # the overwrite really is ordered: own write < foreign write < error
    own = [e for e in run.events if e.kind == "mutation" and run.request_of(e.eid) == 3][-1]
    foreign = [e for e in run.events if e.kind == "mutation" and run.request_of(e.eid) == 4][-1]
    assert own.seq < foreign.seq < run.errors[0].seq
    assert {run.request_of(e.eid) for e in inv.branch} == {3}


def test_why_without_watch_never_claims_a_mutation(demo):
    run = demo(watch=False)
    inv = A.investigate(run, run.errors[0])
    assert_evidence_integrity(run, inv)
    assert not any("write" in t and "not recorded" not in t for t in levels(inv, A.OBSERVED) + levels(inv, A.DERIVED))
    assert any("module-level binding(s) `currentCart`" in t for t in levels(inv, A.DERIVED))
    inf = levels(inv, A.INFERRED)
    assert len(inf) == 1 and "--watch currentCart" in inf[0] and "suspected" in inf[0]


def test_why_on_silent_overcharge_uses_the_recorded_read(demo):
    run = demo()
    log = next(e for e in run.events if e.kind == "log" and "A-101" in e.name)
    inv = A.investigate(run, log)
    assert_evidence_integrity(run, inv)
    rd = [f for f in inv.findings if f.level == A.OBSERVED and "read `currentCart` at demo/checkout.js:23" in f.text]
    assert len(rd) == 1 and run.by_seq[rd[0].evidence[0]].kind == "read" and '"B-202"' in rd[0].text  # #3's cart
    der = [f for f in inv.findings if f.level == A.DERIVED and "it read request #3's value" in f.text]
    assert len(der) == 1 and [run.by_seq[s].kind for s in der[0].evidence] == ["mutation", "mutation", "read"]
    inf = levels(inv, A.INFERRED)
    assert len(inf) == 1 and "#2 POST /order computed with request #3's data" in inf[0] and "not proven" not in inf[0]


def test_why_on_silent_overcharge_is_hedged_without_reads(demo):
    run = demo(reads=False)
    assert not run.reads_recorded and not any(e.kind == "read" for e in run.events)
    log = next(e for e in run.events if e.kind == "log" and "A-101" in e.name)
    inv = A.investigate(run, log)
    assert_evidence_integrity(run, inv)
    assert inv.request.id == 2
    assert any("request #3 overwrote it" in t for t in levels(inv, A.DERIVED))
    inf = levels(inv, A.INFERRED)
    assert len(inf) == 1 and "not proven" in inf[0]


def test_sequential_run_has_no_errors_and_no_interference(demo):
    run = demo(sequential=True)
    assert not run.errors
    log = next(e for e in run.events if e.kind == "log" and "A-101" in e.name)
    assert log.name == "order A-101: charged $128"
    inv = A.investigate(run, log)
    assert not levels(inv, A.INFERRED) and not any("overwrote" in t for t in levels(inv, A.DERIVED))


def test_why_on_rejection_through_await(record, rewind_home):
    run = load(record, rewind_home, "reject_await.js")
    inv = A.investigate(run, run.errors[0])
    assert_evidence_integrity(run, inv)
    obs = levels(inv, A.OBSERVED)
    assert any("unhandled promise rejection" in t for t in obs)
    assert any("a rejected promise" in t for t in obs)
    assert inv.request is None and not levels(inv, A.INFERRED)


# ---- diff (M5) -----------------------------------------------------------------------
def test_diff_of_two_good_runs_has_no_divergence(demo):
    a, b = demo(sequential=True), demo(sequential=True)
    res = A.diff(a, b)
    assert res.first_divergence is None
    assert any("no divergence" in f.text for f in res.findings)


def test_diff_good_vs_bad_points_at_the_interleaving(demo):
    good, bad = demo(sequential=True), demo()
    res = A.diff(good, bad)
    tag, i1, i2, j1, j2 = res.first_divergence
    assert res.a[i1 - 1][0] == "#2 ✎ currentCart = @ demo/checkout.js:12:5"       # last common step
    assert res.a[i1][0].startswith("#2 ▸ Timeout paymentConfirmed")               # good: #2 finishes
    assert res.b[j1][0] == "#3 http.in POST /order"                                # bad: #3 arrives first
    texts = [f.text for f in res.findings]
    assert any("interleaving changed" in t for t in texts)
    assert any("charged $128" in t for t in texts) and any("charged $161" in t for t in texts)
    inf = [f for f in res.findings if f.level == A.INFERRED]
    assert len(inf) == 1 and inf[0].run == "B" and bad.by_seq[inf[0].evidence[0]].kind == "error.uncaught"
    for f in res.findings:  # evidence seqs resolve in the run they name
        side = good if f.run == "A" else bad
        assert all(s in side.by_seq for s in f.evidence)
    # harness callbacks are out of scope by default, present with everything=True
    assert all(t.startswith(("#", "run.end", "log", "error")) for t, _ in res.a + res.b)
    assert len(A.tokens(bad, everything=True)) > len(res.b)


# ---- watched reads (F11) -------------------------------------------------------------
def test_why_on_the_crash_cites_the_failing_read(demo):
    run = demo()
    inv = A.investigate(run, run.errors[0])
    assert_evidence_integrity(run, inv)
    rd = next(f for f in inv.findings if f.level == A.OBSERVED and "read `currentCart`" in f.text)
    read = run.by_seq[rd.evidence[0]]
    assert read.kind == "read" and read.eid == run.errors[0].eid and read.data["loc"].startswith("demo/checkout.js:23:")
    assert '"C-303"' in rd.text  # the cart #4 wrote
    assert any("it read request #4's value" in t for t in levels(inv, A.DERIVED))
    inf = [f for f in inv.findings if f.level == A.INFERRED]
    assert len(inf) == 1 and inf[0].text == A.RACE_INFERENCE and read.seq in inf[0].evidence


def test_overwrites_that_reach_no_read_are_not_called_a_race(record, rewind_home):
    run = load(record, rewind_home, "reads_http.js", {"REWIND_WATCH": "shared"})
    early = next(e for e in run.events if e.kind == "log" and e.name.startswith("early saw"))
    assert early.name == "early saw /early"  # ground truth: it saw its own value
    inv = A.investigate(run, early)
    assert_evidence_integrity(run, inv)
    assert any("overwrote it" in t for t in levels(inv, A.DERIVED))  # the overwrites did happen...
    assert any("can't explain that read" in t for t in levels(inv, A.DERIVED))  # ...after its read
    assert not levels(inv, A.INFERRED)
    blind = A.investigate(run, next(e for e in run.events if e.kind == "log" and e.name == "blind done"))
    assert_evidence_integrity(run, blind)
    assert any("no read of `shared`" in t for t in levels(blind, A.DERIVED)) and not levels(blind, A.INFERRED)


# ---- state at a point (F14) ----------------------------------------------------------
STATE_WATCH = {"REWIND_WATCH": "cart,count,untouched"}


def log_seq(run, prefix):
    return next(e.seq for e in run.events if e.kind == "log" and e.name.startswith(prefix))


def var(st, name):
    return next(v for v in st.vars if v.name == name)


def assert_state_integrity(run, st):
    for f in st.findings + [f for v in st.vars for f in v.findings]:
        assert all(s in run.by_seq and s <= st.target.seq for s in f.evidence), f.text  # nothing from the future
    for v in st.vars:
        if v.status == "unknown":
            assert v.value is None
        else:
            assert v.basis is not None and v.basis.seq <= st.target.seq and v.basis.kind in ("mutation", "read", "snapshot")


def test_state_at_follows_writes_and_reads(record, rewind_home):
    run = load(record, rewind_home, "state.js", STATE_WATCH)
    first = next(e for e in run.events if e.kind == "mutation" and e.name == "cart")
    st = A.state_at(run, first.seq)
    assert_state_integrity(run, st)
    assert (var(st, "cart").status, var(st, "cart").value) == ("known", '{"id":1}')
    assert var(st, "count").status == "unknown"            # its writes come later: nothing assumed
    assert var(st, "untouched").status == "unknown" and var(st, "untouched").file is None
    st = A.state_at(run, log_seq(run, "a done"))           # timer a rewrote it; count written twice
    assert_state_integrity(run, st)
    c = var(st, "cart")
    assert c.value == '{"id":2}' and c.basis.kind == "mutation" and run.request_of(c.basis.eid) is None
    assert run.inits[c.basis.eid].name == "a"               # written inside timer a's callback
    assert (var(st, "count").value, var(st, "count").basis.data["op"]) == ("2", "++")
    st = A.state_at(run, log_seq(run, "b saw"))            # a read re-establishes the whole value
    c = var(st, "cart")
    assert c.basis.kind == "read" and c.value == '{"id":2}'
    assert any("last recorded whole-value write before it" in f.text for f in c.findings)


def test_state_at_marks_partial_and_unrecorded_changes(record, rewind_home):
    run = load(record, rewind_home, "state.js", STATE_WATCH)
    st = A.state_at(run, log_seq(run, "c done"))           # property write after the last whole value
    assert_state_integrity(run, st)
    c = var(st, "cart")
    assert c.status == "partial" and [p.data["path"] for p in c.later] == [".items"]
    assert any("whole value is unknown" in f.text for f in c.findings)
    st = A.state_at(run, log_seq(run, "d done"))           # the alias write in d isn't recorded...
    c = var(st, "cart")
    assert c.status == "known" and c.value == '{"id":2,"items":[1]}' and c.basis.kind == "read"
    assert any("not proven to be the value" in f.text for f in c.findings)  # ...so it is shown as of its read, hedged
    assert any("alias" in f.text for f in st.findings)
    st = A.state_at(run, log_seq(run, "e saw"))            # the next read reveals it
    c = var(st, "cart")
    assert c.value == '{"id":99,"items":[1]}'
    assert any(f.level == A.DERIVED and "differs from the previous recorded value" in f.text for f in c.findings)
    assert var(st, "untouched").status == "unknown"


def test_state_at_during_interleaved_requests(demo):
    run = demo()
    st = A.state_at(run, run.errors[0].seq)
    assert_state_integrity(run, st)
    assert st.request.id == 3 and 3 in {r.id for r in st.in_flight}
    c = var(st, "currentCart")
    assert c.basis.kind == "read" and run.request_of(c.basis.eid) == 3 and '"C-303"' in c.value
    w = next(f for f in c.findings if "last recorded whole-value write" in f.text)
    assert run.request_of(run.by_seq[w.evidence[0]].eid) == 4 and "request #4" in w.text
    a101 = next(e for e in run.events if e.kind == "log" and "A-101" in e.name)
    st = A.state_at(run, a101.seq)
    assert '"B-202"' in var(st, "currentCart").value and {r.id for r in st.in_flight} >= {2, 3}


def test_state_at_after_a_cap_is_unknown(record, rewind_home):
    run = load(record, rewind_home, "state.js", {"REWIND_WATCH": "count", "REWIND_MUT_CAP": "1"})
    st = A.state_at(run, log_seq(run, "a done"))
    c = var(st, "count")
    assert c.status == "unknown" and c.value is None and any("weren't recorded" in f.text for f in c.findings)


def test_state_at_in_an_incomplete_recording_and_without_watch(record, rewind_home):
    r = record("state.js", {**STATE_WATCH, "STATE_HOLD": "1"}, kill_when=lambda s: "error.logged" in s)
    db = store.connect()
    store.ingest(db, "held", r.path)
    run = A.Run(store.events(db, "held"))
    st = A.state_at(run, run.events[-1].seq)
    assert_state_integrity(run, st)
    assert not st.complete and any("recording incomplete" in f.text for f in st.findings)
    assert var(st, "cart").value == '{"id":99,"items":[1]}'  # e's read was recorded before the kill
    plain = load(record, rewind_home, "state.js", rid="nowatch")
    st = A.state_at(plain, plain.events[-1].seq)
    assert not st.vars and any("without --watch" in f.text for f in st.findings)


# ---- error-time snapshots (F12) ------------------------------------------------------
def test_why_reports_values_at_the_error_and_unrecorded_changes(record, rewind_home):
    run = load(record, rewind_home, "snapshot.js", {"REWIND_WATCH": "currentCart,count"})
    inv = A.investigate(run, run.errors[0])
    assert_evidence_integrity(run, inv)
    snap = A.snapshot_of(run, run.errors[0])
    obs = levels(inv, A.OBSERVED)
    assert '`currentCart` when the error was thrown: {"order":"Z","items":[1,2]}' in obs
    assert "`count` when the error was thrown: 1" in obs
    differs = [f for f in inv.findings if "differs from the value recorded at its last write" in f.text]
    assert len(differs) == 1 and differs[0].level == A.DERIVED and "`currentCart`" in differs[0].text
    assert "alias" in differs[0].text and snap.seq in differs[0].evidence
    assert run.by_seq[differs[0].evidence[0]].kind == "mutation"


def test_why_on_demo_snapshot_matches_the_last_write(demo):
    run = demo()
    inv = A.investigate(run, run.errors[0])
    assert_evidence_integrity(run, inv)
    assert any(t.startswith("`currentCart` when the error was thrown: {\"order\":\"C-303\"") for t in levels(inv, A.OBSERVED))
    assert not any("differs from the value recorded" in f.text for f in inv.findings)
    unwatched = demo(watch=False)
    assert not any("when the error was thrown" in f.text for f in A.investigate(unwatched, unwatched.errors[0]).findings)


# ---- pending (F5) --------------------------------------------------------------------
def by_url(run, rep):
    return {run.requests[rid].inbound.data["url"]: st for rid, st in rep.states.items()}


def test_pending_after_normal_completion_and_failure(record, rewind_home, demo):
    run = load(record, rewind_home, "http_two.js")
    rep = A.pending(run)
    assert_evidence_integrity(run, rep)
    assert rep.complete and by_url(run, rep) == {"/1": "completed", "/2": "failed"}
    assert not rep.ops and not levels(rep, A.INFERRED)
    assert any("responded 500" in t for t in levels(rep, A.OBSERVED))
    good = demo(sequential=True, watch=False)
    g = A.pending(good)
    assert set(g.states.values()) == {"completed"} and not g.ops and not levels(g, A.INFERRED)


def test_pending_after_a_crash_blames_the_crash_not_a_stall(demo):
    run = demo()
    rep = A.pending(run)
    assert_evidence_integrity(run, rep)
    assert rep.complete and rep.states == {1: "completed", 2: "completed", 3: "unresolved", 4: "completed"}
    assert any("#3 POST /order" in t and "uncaught error" in t for t in levels(rep, A.DERIVED))
    assert not levels(rep, A.INFERRED)  # unfinished work after a crash is a consequence, never called a stall


def test_pending_finds_genuinely_unresolved_requests(record, rewind_home):
    run = load(record, rewind_home, "stall.js")
    rep = A.pending(run)
    assert_evidence_integrity(run, rep)
    assert rep.complete and by_url(run, rep) == {"/ok": "completed", "/fail": "failed", "/abort": "cancelled",
                                                 "/hang": "unresolved", "/forgot": "unresolved"}
    inf = levels(rep, A.INFERRED)
    assert any("GET /hang likely stalled" in t and "stall.js:18" in t and "never settled" in t for t in inf)
    assert any("GET /forgot" in t and "res.end()" in t for t in inf)
    assert len(inf) == 2
    # the timer /ok set and cleared is cancelled, not pending; every listed op belongs to /hang
    assert not any(i.name == "neverNeeded" for _, i in rep.ops)
    assert {run.requests[rid].inbound.data["url"] for rid, _ in rep.ops} == {"/hang"}
    assert any(e.kind == "async.cancel" for e in run.events)


def test_pending_claims_nothing_from_an_incomplete_recording(record, rewind_home):
    r = record("stall.js", {"STALL_HOLD": "1"}, kill_when=lambda s: "error.logged" in s)
    db = store.connect()
    store.ingest(db, "killed", r.path)
    run = A.Run(store.events(db, "killed"), sources=store.sources(db, "killed"))
    rep = A.pending(run)
    assert_evidence_integrity(run, rep)
    assert not rep.complete and not rep.ops and not levels(rep, A.INFERRED)
    assert any("recording incomplete" in t for t in levels(rep, A.DERIVED))
    assert by_url(run, rep)["/hang"] == "unresolved" and by_url(run, rep)["/abort"] == "cancelled"
    assert any("GET /hang" in t and "recording is incomplete" in t for t in levels(rep, A.DERIVED))


def test_pending_after_a_signal_or_torn_lines(record, rewind_home):
    run = load(record, rewind_home, "stall.js")
    end = run.events[-1]
    assert end.kind == "run.end"
    signalled = A.Run(run.events[:-1] + [store.Event(end.seq, end.t, "run.signal", end.eid, name="SIGINT")])
    rep = A.pending(signalled)
    assert rep.complete and any("still in flight when SIGINT arrived" in t for t in levels(rep, A.DERIVED))
    assert any("likely stalled" in t for t in levels(rep, A.INFERRED))  # a signal flushes everything first
    torn = A.Run(run.events, {"skipped_lines": 1})
    t = A.pending(torn)
    assert not t.complete and not t.ops and not levels(t, A.INFERRED)

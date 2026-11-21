"""Analysis engine over real recordings: attribution, tree building, why, diff."""
import pytest
from rewind import analysis as A
from rewind import store


def load(record, rewind_home, fx, env=None, rid="r", **kw):
    r = record(fx, env)
    db = store.connect()
    store.ingest(db, rid, r.path, **kw)
    return A.Run(store.events(db, rid))


@pytest.fixture
def demo(record, rewind_home):
    def _demo(sequential=False, watch=True):
        fx = "../../demo/traffic.js"
        env = {"REWIND_WATCH": "currentCart"} if watch else {}
        if sequential:
            env["DEMO_SEQUENTIAL"] = "1"
        return load(record, rewind_home, fx, env, rid=f"d{int(sequential)}{int(watch)}")
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


def test_why_on_silent_overcharge_is_hedged(demo):
    run = demo()
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

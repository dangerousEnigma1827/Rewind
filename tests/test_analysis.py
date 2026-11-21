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

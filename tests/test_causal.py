"""F15 causal reconstruction: attribution by creating execution, what released a callback, who sent a response.
Fixtures come from the spikes in spikes/causal (S3, S4); RESULTS.md there has the event sequences behind them."""
import pytest

from rewind import analysis as A
from rewind import render
from test_analysis import assert_evidence_integrity, levels, load


def walk(n):
    yield n
    for c in n.children:
        yield from walk(c)


def log(run, text):
    return next(e for e in run.events if e.kind == "log" and text in e.name)


def req_id(run, url):
    return next(r.id for r in run.requests.values() if r.inbound.data["url"] == url)


# ---- attribution -----------------------------------------------------------------------------
@pytest.mark.parametrize("fx", ["http_two.js", "http_keepalive.js", "reads_http.js", "stall.js", "../../demo/traffic.js"])
def test_both_attribution_models_agree_where_no_promise_crosses_requests(record, rewind_home, fx):
    """The invariant from spike S2: on every pre-existing fixture the switch to creation links changes nothing."""
    run = load(record, rewind_home, fx, {"REWIND_WATCH": "currentCart"} if "demo" in fx else None)
    assert run.requests
    for e in run.story:
        assert run.request_of(e.eid) == run.trigger_request_of(e.eid), (e.kind, e.name)


def test_shared_in_flight_promise_keeps_each_requests_work_in_that_request(record, rewind_home):
    run = load(record, rewind_home, "shared_inflight.js")
    a, b = req_id(run, "/a"), req_id(run, "/b")
    lb = log(run, "handler /b")
    assert run.request_of(lb.eid) == b
    assert run.trigger_request_of(lb.eid) == a  # what Rewind reported before F15
    assert run.request_of(log(run, "handler /a").eid) == a
    sub, _ = A.build_tree(run, run.requests[b].anchor)  # the request's tree now holds its own log
    assert lb.seq in {e.seq for n in walk(sub) for e in n.events}


def test_why_on_a_shared_in_flight_promise_reports_the_cross_request_wait(record, rewind_home):
    run = load(record, rewind_home, "shared_inflight.js")
    inv = A.investigate(run, log(run, "handler /b"))
    assert_evidence_integrity(run, inv)
    assert inv.request.id == req_id(run, "/b")
    der, obs, inf = levels(inv, A.DERIVED), levels(inv, A.OBSERVED), levels(inv, A.INFERRED)
    assert any("continues a promise that request #1 GET /a's code created" in t for t in der)
    settle = next(f for f in inv.findings if f.level == A.OBSERVED and "settled at seq" in f.text)
    assert "Timeout fetchPrice" in settle.text and run.by_seq[settle.evidence[0]].kind == "async.resolve"
    assert any("waited on work started by request #1 GET /a" in t for t in der)
    assert len(inf) == 1 and "shared in-flight work" in inf[0]
    assert not any("settled" in t and "resolved" in t for t in obs)  # outcome isn't recorded: never "resolved"


def test_a_cache_hit_on_a_settled_promise_is_not_called_a_wait(record, rewind_home):
    run = load(record, rewind_home, "shared_settled.js")
    lb = log(run, "handler /b")
    assert run.request_of(lb.eid) == req_id(run, "/b") != run.trigger_request_of(lb.eid)
    inv = A.investigate(run, lb)
    assert_evidence_integrity(run, inv)
    assert any("had already settled" in t and "did not wait" in t for t in levels(inv, A.DERIVED))
    assert not levels(inv, A.INFERRED) and not any("waited on work" in f.text for f in inv.findings)
    sub, _ = A.build_tree(run, run.requests[req_id(run, "/b")].anchor)
    assert not any(n.released_by for n in walk(sub))


def test_a_mutex_hand_off_is_visible_only_through_the_release_edge(record, rewind_home):
    run = load(record, rewind_home, "mutex_queue.js")
    a, b = req_id(run, "/a"), req_id(run, "/b")
    lb = log(run, "critical section /b")
    assert run.request_of(lb.eid) == run.trigger_request_of(lb.eid) == b  # attribution was never the problem here
    inv = A.investigate(run, lb)
    assert_evidence_integrity(run, inv)
    assert not any("continues a promise that request" in f.text for f in inv.findings)
    assert any("settled at seq" in t and "Timeout work" in t for t in levels(inv, A.OBSERVED))
    assert any("waited on work started by request #1 GET /a" in t for t in levels(inv, A.DERIVED))
    sub, _ = A.build_tree(run, run.requests[b].anchor)
    rel = [n for n in walk(sub) if n.released_by]
    assert len(rel) == 1 and run.request_of(rel[0].released_by[0]) == a
    label = render.tree_label(run, rel[0], "")
    plain = render.rich_text(label).plain  # the TUI parses the same markup: it must be valid
    assert "⇠ waited on #1" in plain and "Timeout work" in plain and "settled seq" in plain


def test_a_shared_rejection_is_the_failing_requests_error_with_an_inherited_cause(record, rewind_home):
    run = load(record, rewind_home, "shared_reject.js")
    a, b = req_id(run, "/a"), req_id(run, "/b")
    errs = [e for e in run.errors if e.kind == "error.logged"]
    assert [run.request_of(e.eid) for e in errs] == [a, b]
    assert run.trigger_request_of(errs[1].eid) == a  # before F15 both errors belonged to /a
    inv = A.investigate(run, errs[1])
    assert_evidence_integrity(run, inv)
    assert inv.request.id == b
    assert any("this failure may come from that request's work" in t for t in levels(inv, A.INFERRED))


# ---- who sent the response (http.end) -------------------------------------------------------------
@pytest.fixture
def origin(record, rewind_home):
    rec = record("response_origin.js")
    return rec, load(record, rewind_home, "response_origin.js")


def test_recorder_writes_one_http_end_per_response_in_the_calling_context(origin):
    rec, run = origin
    ends = rec.kind("http.end")
    assert len(ends) == len(rec.kind("http.out")) == 6 and len({e["data"]["req"] for e in ends}) == 6
    for e in ends:  # the recorder's own wrapper frames never appear
        assert not any("recorder" in f["file"] for f in e.get("stack") or [])
    run_ends = {r.inbound.data["url"]: r.end for r in run.requests.values()}
    assert run.anchors.get(run_ends["/direct"].eid) == req_id(run, "/direct")
    assert run.inits[run_ends["/timer"].eid].name == "later"
    assert run.inits[run_ends["/await"].eid].type == "PROMISE"
    assert A.user_frame(run_ends["/pipe"].stack) is None  # ended by stream internals
    assert run.request_of(run_ends["/pipe"].eid) == req_id(run, "/pipe")
    assert run.request_of(run_ends["/park"].eid) == req_id(run, "/release")


def test_why_on_a_response_names_the_callback_that_sent_it_and_the_path(origin):
    _, run = origin
    for url, must in (("/timer", ("res.end() was called in Timeout later at", "response_origin.js:8")),
                      ("/await", ("res.end() was called in PROMISE at", "response_origin.js:7")),
                      ("/pipe", ("res.end() was called by Node internals", ""))):
        r = run.requests[req_id(run, url)]
        inv = A.investigate(run, r.outbound)
        assert_evidence_integrity(run, inv)
        assert any(all(m in t for m in must) for t in levels(inv, A.OBSERVED)), (url, levels(inv, A.OBSERVED))
        path = next(t for t in levels(inv, A.DERIVED) if t.startswith("path to the response"))
        assert path.split(": ", 1)[1].startswith("arrived +0.0 ms"), path
    pipe = next(t for t in levels(A.investigate(run, run.requests[req_id(run, "/pipe")].outbound), A.DERIVED)
                if t.startswith("path"))
    assert "internal steps" in pipe  # Node's stream hops are folded, not listed


def test_a_response_ended_by_another_request_says_so(origin):
    _, run = origin
    park = run.requests[req_id(run, "/park")]
    inv = A.investigate(run, park.outbound)
    assert_evidence_integrity(run, inv)
    der = levels(inv, A.DERIVED)
    assert any("belongs to request #6 GET /release, not to #5 GET /park" in t for t in der)
    path = next(t for t in der if t.startswith("path"))
    assert "… request #6 GET /release arrived" in path and "+-" not in path  # no negative offsets
    assert not levels(inv, A.INFERRED)


def test_tree_and_timeline_show_the_response_where_it_was_sent(origin):
    _, run = origin
    t = run.requests[req_id(run, "/timer")]
    sub, _ = A.build_tree(run, t.anchor)
    holder = next(n for n in walk(sub) if any(e.seq == t.outbound.seq for e in n.events))
    assert holder.aid == t.end.eid and holder.init.name == "later"
    assert "sent from Timeout later" in render.context(run, t.outbound)
    park = run.requests[req_id(run, "/park")]  # ended from another request: it stays on its own request
    sub, _ = A.build_tree(run, park.anchor)
    assert any(e.seq == park.outbound.seq for e in sub.events)


def test_runs_recorded_before_http_end_say_the_sender_is_unknown(origin):
    _, run = origin
    legacy = A.Run([e for e in run.events if e.kind != "http.end"])
    r = legacy.requests[req_id(legacy, "/timer")]
    assert r.end is None and A.response_path(legacy, r) == []
    fs = A.response_findings(legacy, r)
    assert len(fs) == 1 and fs[0].level == A.DERIVED and "unknown" in fs[0].text
    assert render.context(legacy, r.outbound) == ""

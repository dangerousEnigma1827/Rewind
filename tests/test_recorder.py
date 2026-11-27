"""Integration tests: real node processes running fixtures under recorder/recorder.js."""

FIELDS = {"seq", "t", "kind", "eid"}


def fn_names(frames):
    return [f["fn"].split(".")[-1] for f in frames or []]


# ---- raw stream integrity --------------------------------------------------------
def test_stream_is_raw_contiguous_and_framed(record):
    r = record("chain.js")
    assert r.code == 0
    assert [e["seq"] for e in r.events] == list(range(len(r.events)))
    assert all(FIELDS <= e.keys() for e in r.events)
    assert r.events[0]["kind"] == "run.start" and r.events[-1]["kind"] == "run.end"
    # nothing dropped for simplicity: frameless internal fs hops are kept
    assert any(e["type"] == "FSREQCALLBACK" and not e["stack"] for e in r.kind("async.init"))
    assert {"async.init", "async.before", "async.after", "log"} <= {e["kind"] for e in r.events}


def test_reentrancy_recorder_never_records_itself(record):
    for fx in ("chain.js", "http_two.js", "mutations.js"):
        r = record(fx, {"REWIND_WATCH": "currentCart"})
        frames = [f for e in r.events for f in (e.get("stack") or [])]
        assert frames and not any(f["file"].startswith("recorder/") for f in frames), fx
        befores, afters = len(r.kind("async.before")), len(r.kind("async.after"))
        assert befores - afters in (0, 1), fx  # 1 = callback that threw and never returned


def test_forked_child_leaves_the_parent_recording_intact(record):
    r = record("fork_parent.js")
    assert r.code == 0
    assert "child ran with --require" in r.stdout and "child done" in r.stdout  # the child really loaded the preload
    raw = r.path.read_bytes()
    assert b"\x00" not in raw  # read_events() above already parsed every line as JSON
    assert [e["seq"] for e in r.events] == list(range(len(r.events)))
    starts = r.kind("run.start")
    assert len(starts) == 1 and starts[0]["data"]["argv"] == ["tests/fixtures/fork_parent.js"]
    assert [e["name"] for e in r.kind("log")] == ["parent before", "parent after, child exit 0"]
    assert r.events[0]["kind"] == "run.start" and r.events[-1]["kind"] == "run.end"


def test_cluster_worker_leaves_the_primary_recording_intact(record):
    r = record("cluster_primary.js")
    assert r.code == 0 and "worker ran" in r.stdout
    assert b"\x00" not in r.path.read_bytes() and [e["seq"] for e in r.events] == list(range(len(r.events)))
    assert len(r.kind("run.start")) == 1 and r.events[-1]["kind"] == "run.end"
    assert [e["name"] for e in r.kind("log")] == ["primary before", "primary after, worker exit 0"]


def test_inert_without_rewind_out(record):
    a = record("chain.js", recorder=False)
    b = record("chain.js", env={"REWIND_OUT": ""}, recorder=False)
    assert sorted(a.stdout.split()) == sorted(b.stdout.split()) == ["leaf", "other"] and not b.events


# ---- causality, callback names, creation stacks ------------------------------------
def test_causal_chain_with_callback_names_and_creation_stacks(record):
    r = record("chain.js")
    leaf = next(e for e in r.kind("log") if e["name"] == "leaf")
    chain = r.chain(leaf["eid"])
    assert chain[0]["type"] == "Timeout" and chain[0]["name"] == "stepD"
    user = [e for e in chain if e["stack"]]
    assert [e["type"] for e in user] == ["Timeout", "FSREQCALLBACK", "Timeout"]
    assert [fn_names(e["stack"])[0] for e in user] == ["stepC", "stepB", "stepA"]
    assert user[0]["stack"][0]["file"] == "tests/fixtures/chain.js" and user[0]["stack"][0]["line"] == 2
    other = next(e for e in r.kind("log") if e["name"] == "other")
    assert other["eid"] not in {e["aid"] for e in chain}


def test_promise_stacks_default_on_and_opt_out(record):
    on = record("reject_await.js")
    off = record("reject_await.js", {"REWIND_PROMISE_STACKS": "0"})
    assert any(e["stack"] for e in on.kind("async.init") if e["type"] == "PROMISE")
    assert not any(e["stack"] for e in off.kind("async.init") if e["type"] == "PROMISE")
    assert on.events[0]["data"]["promise_stacks"] is True and off.events[0]["data"]["promise_stacks"] is False


# ---- errors -------------------------------------------------------------------------
def test_sync_throw_context_and_exit_code_preserved(record):
    plain = record("throw_timer.js", recorder=False)
    r = record("throw_timer.js")
    assert r.code == plain.code == 1
    err = r.kind("error.uncaught")[0]
    assert err["data"]["origin"] == "uncaughtException" and err["data"]["error"] == "TypeError"
    ctx = r.inits()[err["eid"]]
    assert ctx["type"] == "Timeout" and ctx["name"] == "boom" and fn_names(ctx["stack"])[0] == "scheduleIt"
    assert fn_names(err["stack"])[0] == "boom"
    assert r.events[-1]["kind"] == "run.end" and r.events[-1]["data"]["code"] == 1


def test_rejection_after_await_attributed_via_promise_context(record):
    r = record("reject_await.js")
    assert r.code == 1
    err = r.kind("error.uncaught")[0]
    assert err["data"]["origin"] == "unhandledRejection" and err["name"] == "rejected after await"
    chain = r.chain(err["eid"])
    assert chain[0]["type"] == "PROMISE" and "handler" in fn_names(chain[0]["stack"])
    assert "root" in [e["name"] for e in chain]


def test_error_events_flush_immediately_survive_kill(record):
    r = record("kill_after_error.js", kill_when=lambda s: "error.logged" in s)
    assert r.kind("error.logged") and r.kind("error.logged")[0]["name"] == "before kill"
    assert not r.kind("run.end")


# ---- http -------------------------------------------------------------------------
def test_http_requests_anchor_their_own_async_work(record):
    r = record("http_two.js")
    assert r.code == 0
    ins = {e["data"]["req"]: e for e in r.kind("http.in")}
    outs = {e["data"]["req"]: e for e in r.kind("http.out")}
    assert set(ins) == set(outs) == {1, 2}
    by_url = {e["data"]["url"]: e for e in ins.values()}
    for mine, theirs in (("1", "2"), ("2", "1")):
        log = next(e for e in r.kind("log") if e["name"] == "done " + mine)
        anchors = {e["aid"] for e in r.chain(log["eid"])}
        assert by_url["/" + mine]["aid"] in anchors
        assert by_url["/" + theirs]["aid"] not in anchors
    status = {ins[k]["data"]["url"]: outs[k]["data"]["status"] for k in ins}
    assert status == {"/1": 200, "/2": 500}
    logged = r.kind("error.logged")[0]
    assert logged["name"] == "logged failure 2"
    assert by_url["/2"]["aid"] in {e["aid"] for e in r.chain(logged["eid"])}


# ---- mutation tracking ----------------------------------------------------------------
def test_ast_deps_lazy(record):
    assert record("chain.js").events[-1]["data"]["ast_loaded"] is False
    assert record("chain.js", {"REWIND_WATCH": "x"}).events[-1]["data"]["ast_loaded"] is True


def test_mutations_capture_exactly_documented_set(record):
    r = record("mutations.js", {"REWIND_WATCH": "currentCart"})
    muts = [(m["data"]["path"], m["data"]["op"]) for m in r.kind("mutation")]
    assert muts == [("", "="), (".items", ".push()"), (".items[i].price", "="), (".id", "++"),
                    (".total", "="), (".items[k++]", "="), (".items", "delete")]
    m = {(x["data"]["path"], x["data"]["op"]): x["data"] for x in r.kind("mutation")}
    assert m[("", "=")]["before"] == "null" and m[("", "=")]["after"] == '{"id":1,"items":[{"price":10}]}'
    assert m[(".items", ".push()")]["before"] == '[{"price":10}]'  # previewed before the in-place mutation
    assert (m[(".id", "++")]["before"], m[(".id", "++")]["after"]) == ("1", "2")
    assert m[(".items[k++]", "=")].get("before") is None  # impure key: never re-evaluated
    assert m[("", "=")]["loc"] == "tests/fixtures/mutations.js:2:21"
    # documented misses: alias write, shadowed local, destructuring target, unwatched names
    assert not any(x["data"]["path"] in (".coupon", ".local", ".d") for x in r.kind("mutation"))
    assert {x["name"] for x in r.kind("mutation")} == {"currentCart"}
    # line numbers in user stack traces are unchanged by instrumentation
    err = r.kind("error.uncaught")[0]
    assert err["stack"][0]["line"] == 16 and "mutations.js:16" in r.stderr
    assert r.kind("instrument")[0]["data"] == {"file": "tests/fixtures/mutations.js", "writes": 7, "watch": ["currentCart"]}


def test_mutation_carries_writer_context(record):
    r = record("mutations.js", {"REWIND_WATCH": "currentCart"})
    assert r.kind("mutation")[0]["eid"] == 1  # main module body runs in the root context


def test_mutation_cap(record):
    r = record("many_writes.js", {"REWIND_WATCH": "counter", "REWIND_MUT_CAP": "10"})
    assert r.stdout == "counter 50\n"
    assert len(r.kind("mutation")) == 10 and len(r.kind("mutation.capped")) == 1
    assert r.events[-1]["data"]["mutations"] == {"counter": 50}


def test_esm_not_instrumented_and_unharmed(record):
    r = record("esm_watch.mjs", {"REWIND_WATCH": "currentCart"})
    assert r.code == 0 and "esm ok 1" in r.stdout and not r.kind("mutation")


def test_keepalive_requests_get_distinct_anchors(record):
    r = record("http_keepalive.js")
    assert r.code == 0
    ins = r.kind("http.in")
    assert len(ins) == 3 and len({e["aid"] for e in ins}) == 3
    anchor_of = {e["aid"]: e["data"]["req"] for e in ins}
    for i, body in enumerate("abc", start=1):
        log = next(e for e in r.kind("log") if e["name"] == "done " + body)
        hits = [anchor_of[x["aid"]] for x in r.chain(log["eid"]) if x["aid"] in anchor_of]
        assert hits == [i], (body, hits)  # exactly its own request on the ancestry
    assert all(r.inits()[e["aid"]]["type"] == "REWIND_REQUEST" for e in ins)

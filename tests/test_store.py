"""Ingest of real recorder output into SQLite, run classification, run lookup."""
import shutil
import pytest
from rewind import analysis as A
from rewind import store
from conftest import FIX


def test_ingest_roundtrip_preserves_every_event(record, rewind_home):
    r = record("http_two.js")
    db = store.connect()
    row = store.ingest(db, "abc12345", r.path, label="t")
    evs = store.events(db, "abc12345")
    assert len(evs) == len(r.events) == row["event_count"]
    assert [e.seq for e in evs] == [e["seq"] for e in r.events]
    a, b = evs[5], r.events[5]
    assert (a.kind, a.aid, a.tid, a.eid, a.type, a.name, a.stack) == (b["kind"], b.get("aid"), b.get("tid"), b["eid"], b.get("type"), b.get("name"), b.get("stack"))
    assert row["status"] == "ok" and row["error_count"] == 1 and row["node_version"].startswith("v")


@pytest.mark.parametrize("fx,status,code", [("chain.js", "ok", 0), ("throw_timer.js", "failed", 1), ("reject_await.js", "failed", 1)])
def test_status_classification(record, rewind_home, fx, status, code):
    row = store.ingest(store.connect(), fx[:8], record(fx).path)
    assert (row["status"], row["exit_code"]) == (status, code)


def test_killed_run_is_crashed_and_torn_line_skipped(record, rewind_home):
    r = record("kill_after_error.js", kill_when=lambda s: "error.logged" in s)
    with open(r.path, "a", encoding="utf-8") as f:
        f.write('{"seq": 999, "kind": "asy')  # simulate a write torn by SIGKILL
    row = store.ingest(store.connect(), "killed01", r.path, exit_code=1)
    assert row["status"] == "crashed" and row["skipped_lines"] == 1 and row["error_count"] == 1


def test_reingest_replaces_not_duplicates(record, rewind_home):
    db, r = store.connect(), record("chain.js")
    store.ingest(db, "same0001", r.path)
    store.ingest(db, "same0001", r.path)
    assert len(store.events(db, "same0001")) == len(r.events)


def test_resolve(record, rewind_home):
    db, p = store.connect(), record("chain.js").path
    for i, (rid, label) in enumerate([("aaaa1111", "good"), ("aabb2222", "bad"), ("cccc3333", None)]):
        store.ingest(db, rid, p, label=label, started_at=f"2026-11-22T10:00:0{i}")
    assert store.resolve(db, None)["id"] == "cccc3333"
    assert store.resolve(db, "-2")["id"] == "aabb2222"
    assert store.resolve(db, "good")["id"] == "aaaa1111"
    assert store.resolve(db, "cc")["id"] == "cccc3333"
    with pytest.raises(store.RunNotFound, match="ambiguous"):
        store.resolve(db, "aa")
    with pytest.raises(store.RunNotFound):
        store.resolve(db, "zz")


def _copy(tmp_path, fx, name):
    dst = tmp_path / name
    shutil.copy(FIX / fx, dst)
    return dst


def test_source_snapshot_is_the_code_that_ran(record, rewind_home, tmp_path):
    app = _copy(tmp_path, "throw_timer.js", "app.js")
    original = app.read_text(encoding="utf-8")
    db, r = store.connect(), record(str(app))
    store.ingest(db, "snap0001", r.path)
    app.write_text("// edited after ingest\n", encoding="utf-8")
    key = next(e["name"] for e in r.kind("source"))
    assert store.sources(db, "snap0001")[key] == original.replace("\r\n", "\n")
    status = db.execute("select status from run_sources where run_id=? and path=?", ("snap0001", key)).fetchone()[0]
    assert status == "verified"


def test_source_changed_before_ingest_is_never_shown(record, rewind_home, tmp_path):
    app = _copy(tmp_path, "throw_timer.js", "app.js")
    db, r = store.connect(), record(str(app))
    app.write_text(app.read_text(encoding="utf-8") + "\n// edited while the program ran\n", encoding="utf-8")
    store.ingest(db, "snap0002", r.path)
    key = next(e["name"] for e in r.kind("source"))
    assert store.sources(db, "snap0002")[key] is None
    assert db.execute("select status from run_sources where path=?", (key,)).fetchone()[0] == "changed"


def test_identical_sources_are_stored_once(record, rewind_home, tmp_path):
    app = _copy(tmp_path, "chain.js", "app.js")
    db = store.connect()
    store.ingest(db, "snap0003", record(str(app)).path)
    store.ingest(db, "snap0004", record(str(app)).path)
    assert db.execute("select count(*) from sources").fetchone()[0] == 1
    assert db.execute("select count(*) from run_sources").fetchone()[0] == 2


def test_runs_without_snapshots_read_the_file_on_disk(record, rewind_home):
    db = store.connect()
    store.ingest(db, "legacy01", record("chain.js").path)
    db.execute("delete from run_sources")  # what a run ingested before snapshots existed looks like
    assert store.sources(db, "legacy01") is None
    run = A.Run(store.events(db, "legacy01"), sources=None)
    assert "stepA" in run.source_text("tests/fixtures/chain.js")

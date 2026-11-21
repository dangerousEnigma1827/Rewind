"""SQLite persistence: schema, NDJSON ingest, run lookup. The raw NDJSON file is kept alongside the DB."""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

SCHEMA = """
create table if not exists runs(
  id text primary key, label text, started_at text, ended_at text, cmd text, cwd text,
  node_version text, exit_code integer, status text, event_count integer, error_count integer,
  watch text, raw_path text, skipped_lines integer
);
create table if not exists events(
  run_id text, seq integer, t real, kind text, aid integer, tid integer, eid integer,
  type text, name text, data text, stack text, primary key(run_id, seq)
);
create index if not exists ev_aid on events(run_id, aid);
create index if not exists ev_kind on events(run_id, kind);
"""
ERROR_KINDS = ("error.uncaught", "error.logged")


def home() -> Path:
    h = Path(os.environ.get("REWIND_HOME") or Path.cwd() / ".rewind")
    (h / "runs").mkdir(parents=True, exist_ok=True)
    return h


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(home() / "rewind.db")
    db.row_factory = sqlite3.Row
    db.execute("pragma journal_mode=wal")
    db.executescript(SCHEMA)
    return db


@dataclass
class Event:
    seq: int
    t: float
    kind: str
    eid: int
    aid: int | None = None
    tid: int | None = None
    type: str | None = None
    name: str | None = None
    data: dict | None = None
    stack: list | None = None

    @classmethod
    def from_row(cls, r) -> "Event":
        return cls(r["seq"], r["t"], r["kind"], r["eid"], r["aid"], r["tid"], r["type"], r["name"],
                   json.loads(r["data"]) if r["data"] else None, json.loads(r["stack"]) if r["stack"] else None)


def parse_ndjson(path: Path) -> tuple[list[dict], int]:
    """Returns (events, skipped). A SIGKILL can leave a torn final line; that line is skipped, not fatal."""
    events, skipped = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    return events, skipped


def classify(events: list[dict]) -> tuple[str, int | None]:
    end = next((e for e in reversed(events) if e["kind"] == "run.end"), None)
    if end is None:
        return "crashed", None
    code = (end.get("data") or {}).get("code")
    return ("ok" if code == 0 else "failed"), code


def ingest(db: sqlite3.Connection, run_id: str, raw: Path, *, label=None, cmd=None, started_at=None,
           ended_at=None, exit_code=None) -> dict:
    events, skipped = parse_ndjson(raw)
    status, code = classify(events)
    start = next((e for e in events if e["kind"] == "run.start"), {"data": {}})["data"] or {}
    row = dict(id=run_id, label=label, started_at=started_at, ended_at=ended_at, cmd=json.dumps(cmd or start.get("argv")),
               cwd=start.get("cwd"), node_version=start.get("node"),
               exit_code=code if code is not None else exit_code, status=status, event_count=len(events),
               error_count=sum(e["kind"] in ERROR_KINDS for e in events), watch=json.dumps(start.get("watch") or []),
               raw_path=str(raw), skipped_lines=skipped)
    with db:
        db.execute("delete from events where run_id=?", (run_id,))
        db.execute(f"insert or replace into runs({','.join(row)}) values({','.join('?' * len(row))})", list(row.values()))
        db.executemany(
            "insert into events values(?,?,?,?,?,?,?,?,?,?,?)",
            [(run_id, e["seq"], e["t"], e["kind"], e.get("aid"), e.get("tid"), e["eid"], e.get("type"), e.get("name"),
              json.dumps(e["data"]) if e.get("data") is not None else None,
              json.dumps(e["stack"]) if e.get("stack") is not None else None) for e in events])
    return row


def runs(db) -> list[sqlite3.Row]:
    return db.execute("select * from runs order by started_at desc, rowid desc").fetchall()


class RunNotFound(LookupError):
    pass


def resolve(db, ref: str | None) -> sqlite3.Row:
    """ref: None/'last' -> newest; '-N' -> Nth newest; otherwise label (newest with it) or id prefix."""
    all_runs = runs(db)
    if not all_runs:
        raise RunNotFound("no runs recorded yet — try `rewind record -- node app.js`")
    if ref in (None, "last"):
        return all_runs[0]
    if ref.startswith("-") and ref[1:].isdigit():
        n = int(ref[1:])
        if 1 <= n <= len(all_runs):
            return all_runs[n - 1]
        raise RunNotFound(f"only {len(all_runs)} runs recorded")
    by_label = [r for r in all_runs if r["label"] == ref]
    if by_label:
        return by_label[0]
    by_id = [r for r in all_runs if r["id"].startswith(ref)]
    if len(by_id) == 1:
        return by_id[0]
    raise RunNotFound(f"ambiguous run id prefix {ref!r}" if by_id else f"no run matches {ref!r}")


def events(db, run_id: str) -> list[Event]:
    return [Event.from_row(r) for r in db.execute("select * from events where run_id=? order by seq", (run_id,))]

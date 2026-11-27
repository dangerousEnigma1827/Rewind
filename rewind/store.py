"""SQLite persistence: schema, NDJSON ingest, run lookup. The raw NDJSON file is kept alongside the DB."""
from __future__ import annotations

import hashlib
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
create table if not exists sources(sha256 text primary key, text text);
create table if not exists run_sources(
  run_id text, path text, sha256 text, status text, primary key(run_id, path)
);
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


def resolve_file(file: str, cwd: str | None) -> Path:
    """A recorded file path (relative to the run's cwd, or absolute) on this machine."""
    p = Path(file)
    return p if p.is_absolute() or not cwd else Path(cwd) / p


def snapshot_sources(events: list[dict], cwd: str | None) -> list[tuple[str, str | None, str, str | None]]:
    """(path, sha256, status, text) for every user file the run loaded or has a stack frame in.

    status: verified    hash matches the one the recorder took when Node loaded the file
            unverified  no load-time hash (e.g. ESM, which the recorder doesn't hash); captured at ingest
            changed     file differs from what ran: no text is kept, so it can never be shown as evidence
            missing     file can't be read (deleted, moved, or not a path) or isn't UTF-8
    """
    loaded = {e["name"]: (e.get("data") or {}).get("sha256") for e in events if e["kind"] == "source"}
    files = set(loaded) | {f["file"] for e in events for f in e.get("stack") or []
                           if "node_modules/" not in f["file"] and not f["file"].startswith("node:")}
    out = []
    for path in sorted(files):
        try:
            raw = resolve_file(path, cwd).read_bytes()
            text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")  # as Path.read_text() would give
        except (OSError, ValueError):  # ValueError covers UnicodeDecodeError and unusable path strings
            out.append((path, None, "missing", None)); continue
        sha = hashlib.sha256(raw).hexdigest()
        if path in loaded and loaded[path] != sha:
            out.append((path, None, "changed", None)); continue
        out.append((path, sha, "verified" if path in loaded else "unverified", text))
    return out


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
    snaps = snapshot_sources(events, start.get("cwd"))
    with db:
        db.execute("delete from events where run_id=?", (run_id,))
        db.execute("delete from run_sources where run_id=?", (run_id,))
        db.executemany("insert or ignore into sources values(?,?)", [(sha, text) for _, sha, _, text in snaps if sha])
        db.executemany("insert into run_sources values(?,?,?,?)", [(run_id, p, sha, st) for p, sha, st, _ in snaps])
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


def sources(db, run_id: str) -> dict[str, str | None] | None:
    """path -> source text as recorded (None: changed or unreadable). None for runs ingested before snapshots existed."""
    rows = db.execute("select rs.path, s.text from run_sources rs left join sources s on s.sha256 = rs.sha256 "
                      "where rs.run_id=?", (run_id,)).fetchall()
    return {r["path"]: r["text"] for r in rows} or None


def events(db, run_id: str) -> list[Event]:
    return [Event.from_row(r) for r in db.execute("select * from events where run_id=? order by seq", (run_id,))]

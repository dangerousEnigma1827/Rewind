"""E5b: SQLite in the OneDrive-synced repo: bulk insert, concurrent reader, repeated open/close."""
import sqlite3, time, json, os, sys
from pathlib import Path
db = Path(__file__).parent / "out" / "e5.db"
db.parent.mkdir(exist_ok=True)
for f in (db, Path(str(db) + "-wal"), Path(str(db) + "-shm")):
    f.unlink(missing_ok=True)
w = sqlite3.connect(db); w.execute("pragma journal_mode=wal")
w.execute("create table events(run_id, seq, kind, data, primary key(run_id, seq))")
rows = [("r", i, "async.init", json.dumps({"x": i})) for i in range(200_000)]
t = time.perf_counter()
for rnd in range(20):  # 20 separate runs ingested, each a transaction, to give OneDrive chances to grab the file
    with w: w.executemany("insert into events values(?,?,?,?)", [(f"r{rnd}", s, k, d) for _, s, k, d in rows[:10_000]])
r = sqlite3.connect(db)
n = r.execute("select count(*) from events").fetchone()[0]
with w: w.executemany("insert into events values(?,?,?,?)", [("late", s, k, d) for _, s, k, d in rows[:1000]])
n2 = r.execute("select count(*) from events").fetchone()[0]
print(json.dumps({"rows": n, "after_concurrent_write": n2, "secs": round(time.perf_counter() - t, 2)}))
assert n == 200_000 and n2 == 201_000
for i in range(30):  # open/close churn
    c = sqlite3.connect(db); c.execute("select 1").fetchone(); c.close()
print("PASS E5b sqlite in OneDrive path")

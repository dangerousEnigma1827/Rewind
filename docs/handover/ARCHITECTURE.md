# Architecture (handover edition)

Expands [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md), which remains the concise reference. Back to [HANDOVER.md](HANDOVER.md).
Sources: existing docs, `spikes/RESULTS.md`, and a partial read of the source (`rewind/cli.py` record path, env vars in `recorder/recorder.js`, `store.home()`); internals not read line by line are as described by the earlier docs. Nothing was executed. Updated 2026-11-28 for F15 against `rewind/recording.py`, `rewind/analysis.py` and `recorder/recorder.js` (read, and the record path executed by the test suite).

## Complete data flow

```
rewind record [-l LABEL] [-w VAR,...] -- node app.js args      (or Record in the app)
   │  rewind/cli.py:record → rewind/recording.py:prepare / store_run (shared with the TUI)
   │   • run_id = 8 hex chars (secrets.token_hex(4))
   │   • raw path = $REWIND_HOME/runs/<run_id>.ndjson   (REWIND_HOME default ./.rewind)
   │   • env: REWIND_OUT, REWIND_RUN_ID, [REWIND_WATCH]
   │   • spawns: node --require <repo>/recorder/recorder.js app.js args   (stdout/stderr inherited)
   ▼
┌──────────── node process ─────────────────────────────┐
│ recorder/recorder.js                                  │
│   async_hooks · console patch · http.Server patch     │
│   (per-request scope, res.end) ·                      │
│   uncaughtExceptionMonitor · signal/exit flush        │
│   [--watch] recorder/instrument.js rewrites CJS files │
│   buffer → fs.writeSync NDJSON lines                  │──► $REWIND_HOME/runs/<id>.ndjson  (kept)
└───────────────────────────────────────────────────────┘
   │ process exits; exit code captured by cli.py
   ▼
rewind/store.py: ingest(db, run_id, raw, label, cmd, started_at, ended_at, exit_code)
   │ one transaction → $REWIND_HOME/rewind.db (SQLite, WAL)
   ▼
rewind/analysis.py: Run indexes → story / tree / investigate (why) / response paths / pending /
                    state_at / diff     (pure functions)
   ▼
rewind/render.py (Rich) ← rewind/cli.py (Typer)  → terminal;  rewind/tui/ (Textual) → the app
```

`rewind record` exits with the child's exit code. If the recorder produced no file, it fails with "recorder produced no output (did node start?)". If `node` is not on PATH it exits 127. Ctrl+C is forwarded (the child gets it too, flushes, exits).

## 1. Node.js recorder (`recorder/recorder.js`)

- Zero runtime dependencies unless `--watch` is used. Loaded with `--require`.
- **Inert without `REWIND_OUT`**: if the env var is absent the recorder does nothing (there is a test for this).
- **Re-entrancy**: one `inHook` guard wraps every recorder entry point, so the recorder never records its own work (M0 E4: zero recorder-attributed resources, contiguous `seq`).
- **Writing**: events are buffered and written with synchronous `fs.writeSync` — async_hooks callbacks must be synchronous and must not create async work.
- **Durability**: flush every 256 events, immediately on error events, on `exit`, and on SIGINT/SIGTERM (re-raised only if the app has no handler of its own). SIGKILL loses at most the unflushed tail; error events survive.

### Async hooks and event recording

| hook | event | notes |
|---|---|---|
| `init(aid, type, tid, resource)` | `async.init` | `eid` (the execution creating the resource) gives the causality tree; `tid` (triggerAsyncId) is kept, and for a promise reaction is the promise it continues. Creation stack captured from V8 CallSites (structured, no string parsing), node internals and recorder frames stripped, max 8 user frames, paths relative to cwd. Timer/Immediate callback name from `resource._onTimeout.name`. Promise creation stacks on by default (`REWIND_PROMISE_STACKS=0` disables). |
| `before` / `after` | `async.before` / `async.after` | when a callback actually ran |
| `promiseResolve` | `async.resolve` | `eid` = the callback that settled the promise (fulfilled or rejected: not distinguished). For `resolve(otherPromise)` it fires at real settlement, inside an internal reaction promise (spikes/causal S1). |
| `destroy` | not recorded | volume, no analysis value |

Every event carries `eid = executionAsyncId()` at emission — "which callback was running". Nothing is dropped at record time; filtering happens only in views.

Other recorded sources:
- **console** (`log/info/warn/error`) → `log`; `console.error(err)` with an Error → `error.logged`.
- **errors** → `error.uncaught` via `process.on('uncaughtExceptionMonitor')` only. It observes without changing crash semantics or exit codes. For sync throws, context = the throwing callback; for rejections after `await`, `executionAsyncId()` = the rejected promise, whose ancestry leads back to the caller (M0 E2/E3). No `unhandledRejection` listener is installed (a re-throwing one loses context).
- **lifecycle** → `run.start` (run id, argv, cwd, node version…), `run.end`, `run.signal`.
- `instrument` events from the AST rewriter; `mutation` / `mutation.capped` from watched writes.

## 2. HTTP request attribution

- The recorder patches `http.Server.prototype.emit` for `'request'`.
- Each request gets its own `AsyncResource('REWIND_REQUEST')`; the handler and all `req`/`res` event callbacks run inside its scope. `http.in` is emitted as the request's anchor (`aid` of that resource); `http.end` at the first `res.end()` call, in the calling callback's context with its stack (F15); `http.out` when the response finishes (status, duration).
- Why: Node's own `HTTPINCOMINGMESSAGE` resource is per *connection*, so without this, keep-alive requests on one socket are attributed to each other. Found while building the demo; regression test `test_keepalive_requests_get_distinct_anchors`.
- Analysis: `request_of(aid)` walks creation links (`init.eid`, `tid` where `eid` is 0) upward until the first request anchor → that request number (derived). Before F15 it walked `tid`, which moves work into another request whenever a promise is shared between requests; see [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md#causal-reconstruction-f15).
- Not covered: `https`, `http2`, outgoing client requests as anchors, worker threads, child processes. Forked and `cluster` children inherit the preload but find no `REWIND_OUT` (the recorder deletes it from `process.env` after opening the file), so they stay inert and can't corrupt the parent's file.

## 3. Optional AST-based mutation tracking (`recorder/instrument.js`)

- Enabled by `rewind record --watch a,b` → env `REWIND_WATCH`.
- Rewrites CommonJS files as they load (the plan names `Module.prototype._compile`; not re-read in source); files under `node_modules` and ESM files are not rewritten.
- Uses acorn + acorn-walk + magic-string (pinned in `recorder/package.json`: 8.19.0 / 8.3.5 / 1.4.5), **loaded lazily only when `--watch` is set** (test `test_ast_deps_lazy`).
- Rewrites writes whose root identifier is a watched top-level binding of that file into `__rw.w(name, path, op, loc, before, (expr), reread)`:
  preserves the expression's value and its source line (stack line numbers unchanged), reads `before` only when re-evaluating is side-effect free, skips shadowed same-named locals.
- Covered write forms: reassignment, property/element assignment, compound assignment, `++`/`--`, `delete`, calls to `push pop shift unshift splice sort reverse fill copyWithin set delete clear add`.
- Each `mutation` event: `name`, `data.{path, op, loc, before, after}` (JSON previews, ≤200 chars), and `eid` — so writes join the causal tree and become **observed** facts attributable to a request.
- Cap: after `REWIND_MUT_CAP` (default 10 000) writes per name, values stop being recorded and `mutation.capped` is emitted; counting continues.
- M0 E7 compared four approaches; AST rewrite shipped (0.14 µs/watched write). Inspector logpoints (~100× slower), deep Proxy (breaks identity), and out-of-process CDP pause (perturbs the race) were rejected.

## 4. NDJSON event storage

One JSON object per line. Fields:

| field | meaning |
|---|---|
| `seq` | total order within the run (contiguous) |
| `t` | µs since recorder start |
| `kind` | `run.start` `run.end` `run.signal` `async.init` `async.before` `async.after` `async.resolve` `async.cancel` `log` `http.in` `http.end` `http.out` `http.abort` `error.uncaught` `error.logged` `mutation` `mutation.capped` `read` `read.capped` `instrument` `source` `snapshot` |
| `eid` | executionAsyncId at emission |
| `aid`, `tid` | resource id and trigger id (async events; `http.in` anchors) |
| `type`, `name` | resource type and callback name; or log text, request line, error message, variable name |
| `data` | kind-specific JSON (`origin`, `error`, raw stack, `req`, `status`, `path/op/loc/before/after`, …) |
| `stack` | `[{fn, file, line, col}]` user frames, max 8 |

The raw file is kept after ingest as ground truth and is readable even after a hard kill (a torn last line is skipped at ingest).

## 5. Python ingestion and SQLite (`rewind/store.py`)

- `store.home()` = `$REWIND_HOME` or `./.rewind` (relative to the current working directory).
- `store.connect()` opens `rewind.db` in WAL mode.
- `ingest()` loads a run in a single transaction. Tables:
  - `runs`: one row per run — id, label, cmd, cwd, node version, timestamps, exit code, status (`ok` / `failed` / `crashed`), event and error counts, raw path.
  - `events`: mirrors the NDJSON fields, primary key `(run_id, seq)`, indexed on `aid` and `kind`.
  - `sources` (text by SHA-256) and `run_sources(run_id, path, sha256, status)`: the source files as they ran (F2), status `verified` / `unverified` / `changed` / `missing`; see [docs/ARCHITECTURE.md](../ARCHITECTURE.md#event-schema).
- Status: `crashed` when the stream has no `run.end` (e.g. SIGKILL); `failed` on non-zero exit; `ok` otherwise (tests `test_status_classification`, `test_killed_run_is_crashed_and_torn_line_skipped`).
- Re-ingesting the same run id replaces rather than duplicates (`test_reingest_replaces_not_duplicates`).
- `resolve(db, ref)`: run reference = label, id prefix, `last` (default), or `-N` (Nth newest). Unknown ref → `RunNotFound` → CLI exits 2 with a friendly message.

## 6. Analysis engine (`rewind/analysis.py`)

`analysis.Run` builds indexes once per run: `inits`, `children` (by creating execution), `fired`, `resolves`, `emitted` (story events per eid), `requests` / `anchors` (each request with its `http.end`), and cached `story`, `errors`, `effectful`.

- **Attribution and waits** (F15): `request_of` follows creation links; `trigger_request_of` keeps the old trigger walk for reporting disagreement; `released` / `release_chain` find the settlement that released a promise continuation; `settled_by` gives a promise's own settlement (for unhandled rejections). Rules and limits: [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md#causal-reconstruction-f15), formal detail in [docs/ARCHITECTURE.md](../ARCHITECTURE.md#analysis).
- **Collapsing**: hops without a user frame (e.g. the 4 `FSREQCALLBACK` open/stat/read/close hops inside `fs.readFile`) are folded in views, kept in storage. Function names normalised (`Timeout.stepB` → `stepB`; `short_fn`).
- **Tree**: parent = the creating execution; prunes branches with no story events and reports how many it hid; merges a chain of identical resources (an `await` in a loop) into one `×N` node; `--full` shows everything. Built iteratively.
- **`investigate(run, event)`** — `why`. Returns findings `(level, text, evidence seqs)`:
  - throw site and running callback with its creation site — *observed*
  - collapsed causal chain to the owning request; other requests' observable activity while it was in flight — *derived*
  - per watched variable: whether the failing source line reads it (derived), the last write (observed) and its writer request (derived), and own-write → foreign-overwrite → target ordering (derived)
  - race explanation — *inferred*, always citing the seqs above
  - Without `--watch`: may only point at module-level names on the failing line and recommend `--watch`; never claims a write. With recorded reads (F11), the race rests on an observed `read` and the last recorded write before it (derived); reads that came before the overwrite, or no read at all, rule the race out of the inference. Without reads (`REWIND_READS=0`, older runs), a race on a non-error event is labelled not proven.
  - for an uncaught error with `--watch`: each watched value at the throw (observed, F12) and an unrecorded change when it differs from the last whole-variable write (derived)
  - for a promise continuation: the settlement it waited for (observed), that it waited and how long, or that the promise had already settled (derived), the settling callback's request when it is another one (derived), and the dependency on that request's shared work (inferred); for an unhandled rejection, who settled the rejected promise and where the rejection started
  - for a response (`http.out`, `why -r N`): the callback that called `res.end()` (observed), another request's or no request's code ending it (derived), and the path from arrival to `end()` with timings and the largest gap (derived)
- **`pending(run)`** and **`state_at(run, seq)`** (`rewind pending`, `rewind at`): see [docs/ARCHITECTURE.md](../ARCHITECTURE.md#analysis). `pending` reports a request whose code called `res.end()` but never finished sending as answered, not stalled.
- **`diff(a, b)`**: tokenises each run into request-tagged steps with ids/times removed — effectful callback firings (site + description), requests, logs, writes (location + op, not values), errors, exit. Callbacks with no observable effect are excluded (Node's HTTP date-cache timer fires nondeterministically). Aligns with `difflib.SequenceMatcher`; reports first divergence, whether the divergent step merely moved, and reordered / only-A / only-B counts. Writes watched in only one of the two runs are ignored (`test_diff_ignores_writes_watched_in_only_one_run`).
- Test invariants: every inference cites evidence, every evidence seq exists, every observed "write" claim is backed by a `mutation` event.

## 7. CLI and rendering

- `rewind/cli.py`: Typer app, entry point `rewind = rewind.cli:main` (pyproject). Commands: `record`, `runs`, `timeline`, `tree`, `why`, `diff`, `pending`, `at`, `ui` — details in [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md). The interactive app lives in `rewind/tui/` ([docs/ARCHITECTURE.md](../ARCHITECTURE.md#interactive-app-rewindtui)).
- `rewind/render.py`: Rich console and the "Ultraviolet" theme, markers `●` observed, `◆` derived, `?` inferred; `--evidence` prints backing seqs. Also the landing screen, per-command help, usage errors and the classic-console glyph fallback. Design rules: [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md#terminal-presentation).
- `rewind/__init__.py` exports `RECORDER`, the absolute path of `recorder/recorder.js` (the package is installed editable, so the recorder is found in the repo).

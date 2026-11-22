# Features and limitations

Back to [HANDOVER.md](HANDOVER.md). Command options are verified from `rewind/cli.py`; behaviour is as previously reported in README and tests, not re-run.

## CLI commands

`RUN` everywhere = a label, an id prefix, `last` (default), or `-N` (Nth newest). Unknown runs give a friendly error and exit code 2.

| command | options | does |
|---|---|---|
| `rewind record [OPTIONS] -- node app.js [args]` | `-l/--label NAME`, `-w/--watch VAR[,VAR]` | Runs the program with the recorder preloaded, ingests the run, prints a summary, exits with the program's exit code. `rewind record app.js` (no `node`) is accepted as shorthand. |
| `rewind runs` | — | Recorded runs, newest first (id, label, status, counts). |
| `rewind timeline [RUN]` | `-r/--request N`, `-k/--kind log,http,error,mutation,async,run`, `-c/--callbacks`, `--raw` | The run's story in order: requests, logs, writes, errors. `-r` one request; `-c` adds every user callback firing; `--raw` every recorded event unfiltered. |
| `rewind tree [RUN]` | `-r/--request N`, `--full` | Async causality tree ("who scheduled whom"). Quiet branches pruned and internal hops folded unless `--full`; reports how much it hid. |
| `rewind why [RUN]` | `-e/--error N` (default 1), `-s/--seq SEQ`, `--evidence` | Causal investigation of error N, or of any event by seq. |
| `rewind diff A B` | `--all`, `--evidence` | Aligns two runs and finds the first divergence. `--all` includes callbacks outside any request (harness/plumbing). |

## Causal investigation (`why`)

For an error it reports, with evidence levels:
- ● throw site and the running callback, plus where that callback was scheduled (creation stack)
- ◆ the collapsed causal chain back to the owning HTTP request, and what other requests did while it was in flight
- ◆ whether the failing line reads a watched variable; ● the last write before the failure; ◆ which request made it; ◆ own-write → foreign-overwrite → read ordering
- ? likely root cause (e.g. race on shared module-level state), citing the seqs above

For a non-error event (`--seq`, e.g. a log showing a wrong total) it gives the same story but marks a race as **not proven**, because reads aren't recorded.
Without `--watch` it never claims a mutation: it only suspects module-level state on the failing line and recommends re-recording with `--watch <var>`.

## Timelines and execution trees

- Timeline: request-tagged story events in `seq` order; internal noise collapsed (~330 events per HTTP request measured in M0 E6, so collapsing is essential).
- Tree: `tid` ancestry with creation sites and callback names; frameless hops (e.g. `fs.readFile`'s 4 internal hops) folded.

## Diff

Token stream per run (effectful callbacks, requests, logs, writes by location/op, errors, exit; ids and times stripped), aligned with `difflib.SequenceMatcher`. Reports the first divergence, whether it is a move (same step, different order) or a genuine only-A/only-B step, and counts. On the demo, good (sequential) vs bad (concurrent) is reported to diverge right after request #2's write to `currentCart`: same code path, different interleaving.

## Mutation tracking (`--watch`)

Records every **syntactic** write to a watched variable declared at the top level of a CommonJS file, with location, writer request (via `eid`) and JSON previews of before/after (≤200 chars).

Captured: reassignment; property and element assignment; compound operators; `++`/`--`; `delete`; calls to `push pop shift unshift splice sort reverse fill copyWithin set delete clear add`.

Not captured:
- writes through aliases (`const c = currentCart; c.x = 1`)
- destructuring targets (`[currentCart.a] = v`)
- files under `node_modules`; ESM files (`.mjs`, `"type": "module"`) — test confirms ESM is left unharmed
- mutations inside functions the value is passed to
- same-named local variables (skipped on purpose)
- reads (never recorded)

More than `REWIND_MUT_CAP` (default 10 000) writes to one name → counting continues, values stop.
Requires `npm install --prefix recorder` (acorn, acorn-walk, magic-string); without `--watch` the recorder needs no npm packages.

## Supported scenarios

- Node.js ≥ 20 (developed on v24.22.1), CommonJS apps, Node core `http` servers including keep-alive.
- Timers, immediates, fs callbacks, promises and `async`/`await` chains (attribution through `await` verified in M0 E3).
- Sync uncaught throws and unhandled rejections in Node's default `--unhandled-rejections=throw` mode.
- Normal exit, `process.exit(n)`, crashes, SIGINT/SIGTERM; SIGKILL → partial run marked `crashed`.
- Windows 11 inside a OneDrive folder (M0 E5b).
- Python ≥ 3.12 per `pyproject.toml`; actually exercised on 3.15.2 (3.14.10 reported working).

## Unsupported scenarios / known limitations

- `https`, `http2`, outgoing HTTP clients as request anchors, worker threads, child processes: not instrumented.
- `--unhandled-rejections=warn|none`: rejections not recorded.
- SIGKILL: up to the last 256 non-error events lost.
- Not a full time-travel debugger: no per-function-call tracing, no arbitrary variable values, no stepping backwards, no breakpoints, no web UI.
- Promise creation stacks cost ~1.9× wall time on an HTTP-heavy benchmark (1.1× with `REWIND_PROMISE_STACKS=0`, losing `async` function names in chains).
- `REWIND_HOME` defaults to `./.rewind` relative to the cwd where `rewind` is run, so runs recorded from different directories land in different databases.

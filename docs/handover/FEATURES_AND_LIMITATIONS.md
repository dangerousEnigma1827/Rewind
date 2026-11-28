# Features and limitations

Back to [HANDOVER.md](HANDOVER.md). Command options come from `rewind/cli.py`. CLI behaviour is covered by the 56-test suite. The M7 fresh-clone walkthrough independently verifies the documented installation and demonstration workflow ([TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md)).

## CLI commands

`RUN` everywhere = a label, an id prefix, `last` (default), or `-N` (Nth newest). Unknown runs give a friendly error and exit code 2.

| command | options | does |
|---|---|---|
| `rewind` / `rewind --help` | — | Landing screen (from the CLI redesign, merged in `388fe45`): REWIND wordmark, runs recorded here and the latest one's status, the commands, the evidence key, and a next step based on the latest run. Bare `rewind` exits 2 (unchanged); it never creates `.rewind`. `rewind <command> --help` lists every option. |
| `rewind record [OPTIONS] -- node app.js [args]` | `-l/--label NAME`, `-w/--watch VAR[,VAR]` | Runs the program with the recorder preloaded, ingests the run, prints a summary, exits with the program's exit code. `rewind record app.js` (no `node`) is accepted as shorthand. |
| `rewind runs` | — | Recorded runs, newest first (id, label, status, counts). |
| `rewind timeline [RUN]` | `-r/--request N`, `-k/--kind log,http,error,mutation,async,run`, `-c/--callbacks`, `--raw` | The run's story in order: requests, logs, writes, errors. `-r` one request; `-c` adds every user callback firing; `--raw` every recorded event unfiltered. |
| `rewind tree [RUN]` | `-r/--request N`, `--full` | Async causality tree ("who scheduled whom"). Quiet branches pruned and internal hops folded unless `--full`; reports how much it hid. |
| `rewind why [RUN]` | `-e/--error N` (default 1), `-s/--seq SEQ`, `-r/--request N`, `--evidence` | Causal investigation of error N, of any event by seq, or of request N's response (who sent it and the path to it). |
| `rewind diff A B` | `--all`, `--evidence` | Aligns two runs and finds the first divergence. `--all` includes callbacks outside any request (harness/plumbing). |
| `rewind ui` (or bare `rewind` on an interactive terminal) | — | The interactive app: runs, requests, timeline, why, pending, state, tree and diff, with evidence navigation. Piped or scripted, bare `rewind` still prints the landing screen and exits 2. Keys: `?` in the app, or the README. |
| `rewind at RUN SEQ` | `--evidence` | Watched variables' state at event SEQ, from recorded writes, reads and snapshots only (see below). Not on the landing screen (80×24 limit). |
| `rewind pending [RUN]` | `--evidence` | What never finished: requests without a response and the unfinished operations they waited on. Not on the landing screen, which is at its 80×24 limit. |

## Interactive app (`rewind ui`)

Redesigned on `feat/ultraviolet-tui` for first-time users ([TUI_UX_AUDIT.md](TUI_UX_AUDIT.md)).

**Journey**
1. **Home:** record a program (primary), try the sample (when `demo/` is present), recent recordings.
2. **Record**
   - The form: command, label and watched variables, each with a short explanation, and a live preview of the
     equivalent `rewind record`.
   - Checks before anything runs (`rewind/recording.py: problems`): empty command, npm/npx/tsx instead of node, Node
     not on PATH, a missing script (resolved like node: name, `.js/.mjs/.cjs`, folder index), invalid watched names,
     missing `--watch` packages.
   - While running: streamed output, and `esc` stops the program.
   - At the end: the outcome in words, and "Open this run".
3. **Investigate:** a run opens on the **Overview**: what happened, what to look at first, key findings, and what to do next.

**What it shows**
- **Sidebar:** recordings, and the selected run's requests (answered / failed / no response / client gave up, from `pending`, with a legend).
- **Main view**, seven tabs, each with a one-line description and its key:
  - **Overview:** what happened and where to look first
  - **Explain** (`why`): for the selected story event, or the first error
  - **Timeline:** story events, with search, kind filter, callback starts and every event (capped at 20 000 rows)
  - **Unfinished** (`pending`)
  - **Variables** (`state`): at the timeline event you picked, or the first error until you pick one
  - **Tree:** for the selected request
  - **Compare** (`diff`): pick the other recording in place, or use `b` then `d`
- **Findings** in every list are grouped: *Recorded* (observed), *Derived*, *Rewind's interpretation, not proven* (inferred).
- **Details pane:** the focused item.

**Evidence navigation:** every finding links to its evidence (enter, `]`, `[`), including diff evidence in the other run.

**Look:** Ultraviolet, from the website's tokens: violet for the brand, focus and selection on a strictly dark foundation. Green, red and amber are used only for status.

**Verified**
- 27 pilot tests: empty home; successful, refused and stopped recordings; the sample; Overview to evidence; Compare; keyboard-only journey; help centered at 80×24, 120×36, 200×60; layouts at 80×24, 100×30, 130×40, 180×50; theme darkness and contrast; the real `App.run()` entry point.
- Screenshots of every screen were reviewed.
- Home, the investigation and Explain were inspected in a real Windows Terminal window on Windows 11.

**Not verified:** the classic PowerShell 5.1 console (conhost), macOS and Linux terminals.

**Recording limits:** the program runs without keyboard input (stdin is closed). On Windows, stopping terminates the program, so that run is stored as incomplete. npm scripts, tsx and similar launchers are refused, because the recorder must be preloaded into `node` itself.

**Limits**
- Runs load synchronously, so very large runs pause the UI while they load.
- The "every event" timeline shows at most 20 000 rows.
- The state view isn't navigable: it follows the timeline cursor, and you press `s` to refresh it.

## State at a point (`at`, F14)

`rewind at RUN SEQ [--evidence]` reconstructs each watched variable at event SEQ from recorded evidence only. Variables are keyed by name and file.

- **Value:** the latest whole-value evidence at or before SEQ: a whole-variable write (path `""`), a read, or an error snapshot. ● where it came from (seq, request or callback, location).
- **Which write:** when the value came from a read or snapshot, ◆ the last recorded whole-value write before it.
- **As of, never "current":** ◆ "latest recorded value, as of seq B … not proven to be the value at seq SEQ".
- **Partial:** if property writes (e.g. `.items = …`) came after that evidence, the variable is **partial**. ◆ The whole value is unknown past the first of them, and ● each one is listed with its path and new value. Values are never merged.
- **Unknown:** no write, read or snapshot at or before SEQ (a declaration's initial value isn't recorded), or the write cap was reached with no read since.
- **Unrecorded change:** ◆ a read or snapshot that differs from the previous recorded value, with no recorded write in between, was changed by a write `--watch` doesn't see.
- **Also shown:** truncated previews (200 characters) are flagged. The header shows the event at SEQ, its request, the requests in flight, and whether the recording was incomplete. Runs without `--watch` say so.

## Unfinished work (`pending`)

- **Completeness first.** A recording is complete only if it reached `run.end`, or a `run.signal` (which flushes every buffered event), and ingest skipped no torn lines. In an incomplete recording, missing events prove nothing: requests without a recorded response are listed with "the recording is incomplete", and no operation or stall is claimed.
- **Requests:** ● `responded 5xx` (failed); ● the connection closed before a response finished (`http.abort`: cancelled by the client); ◆ arrived but no response was recorded, with the reason taken from how the run ended (uncaught error, signal, or exit code).
- **Unfinished operations** (complete recordings only, created from user code): ◆ promises with no `async.resolve` (which fires for rejections too), and timers, immediates, ticks and fs callbacks that never fired and weren't cleared (`async.cancel`). Timers report whether they were overdue ("never ran") or "not due yet" (from the recorded delay). Listed for unanswered requests and work outside any request; leftovers of requests that already finished are only counted.
- **Inference:** ? "likely stalled", naming the most recent unfinished operation the request was waiting on; or, if there was none, a handler that may have returned without responding. Never after an uncaught error: work left unfinished by a crash is a consequence, not a stall.
- Not judged: other resource types (sockets, DNS, child processes), unref'd timers (they show as "not due yet" or "never ran" like any other), timers cleared by numeric id or by `AbortSignal`, and `timeout.close()`.

## Causal investigation (`why`)

For an error it reports, with evidence levels:
- ● throw site and the running callback, plus where that callback was scheduled (creation stack)
- ◆ the collapsed causal chain back to the owning HTTP request, and what other requests did while it was in flight
- ◆ whether the failing source line references a watched variable; ● the last recorded write preceding the failure; ◆ which request made that write; ◆ the observed own-write → foreign-overwrite sequence, with the subsequent read inferred from source context.
- ? likely root cause (e.g. race on shared module-level state), citing the seqs above

**With recorded reads (F11, the default with `--watch`):**
- ● the read of the watched variable behind the target: at the failing line in the same callback for an error, else the latest read in that callback, else the latest read by the request. It carries location and value.
- ◆ if that value differs from the last whole-variable write, an unrecorded write changed it in between.
- ◆ "read request #N's value" when the last recorded write before the read was another request's, with no own write in between. Then ? the race.
- ◆ if the read came before the foreign overwrite, "can't explain that read", with no inference.
- ◆ if the request never read the variable, "no read … was recorded", with no inference.

Without recorded reads (`REWIND_READS=0`, or runs recorded before F11), a non-error event (`--seq`, e.g. a log showing a wrong total) gets the old story, with the race marked **not proven**.
Without `--watch` it never claims a mutation: it only suspects module-level state on the failing line and recommends re-recording with `--watch <var>`.

Source text comes from the run's snapshot, taken at ingest and checked against SHA-256 hashes the recorder took as Node loaded each CommonJS file. Editing code after recording doesn't change an old run's analysis. A file edited while the program ran is stored as `changed` with no text, and findings that need its source are omitted rather than computed from the edited file. ESM files have no load-time hash and are snapshotted unverified at ingest. Runs ingested before snapshots existed still read the file on disk. Details in [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

## Timelines and execution trees

- Timeline: request-tagged story events in `seq` order; internal noise collapsed (~330 events per HTTP request measured in M0 E6, so collapsing is essential). A response row says which callback sent it ("sent from Timeout later").
- Tree: creation ancestry (the execution that scheduled each resource) with creation sites and callback names; frameless hops (e.g. `fs.readFile`'s 4 internal hops) folded. A response sits under the callback that called `end()` when that callback belongs to the same request. A callback that waited on a promise settled by another request's work (or by no request's) is marked `⇠ waited on #N <callback> at <site>, settled seq S`.

## Causal reconstruction (F15)

Spikes and event sequences: `spikes/causal/RESULTS.md`. Tests: `tests/test_causal.py`.

- **Attribution follows the creating execution.** A callback belongs to the request whose code scheduled it (the `await`, `then`, `setTimeout`). Before F15 Rewind followed trigger links, which for an `await` point at the awaited promise. So any memoised promise shared between requests (an in-flight cache fill, a single-flight call, even a plain cache hit long after it settled) put later requests' logs, writes and errors into the first request. `why` says when trigger links alone would point elsewhere (◆).
- **What released a callback.** For a callback that resumed after `await`/`then`:
  - ● the promise it was released by and the callback that settled it
  - ◆ that it waited, from when, and for how long; or that the promise had already settled, so it did not wait
  - ◆ when the settling callback belongs to another request: "waited on work started by request #N"
  - ? "depends on request #N's shared in-flight work", hedged for errors ("may come from that request's work")

  Chains through Node's internal promises: `resolve(otherPromise)`, `return p` from an async function, `Promise.all` (released by the slowest element), `Promise.race` (the winner), `events.once`, thenables.
- **Who sent a response.** `http.end` records the first `res.end()` call. `why -r N` (or `why --seq` on an `http.out`):
  - ● the callback and source line that called `end()`, or "Node internals" (e.g. `stream.pipe`), with the user code that started that internal work (◆)
  - ◆ another request's code ending this response (a parked long-poll response, for example)
  - ◆ the path from arrival to `end()`: → scheduled by, ⇠ waited until settled, … no recorded link (another request's arrival), with ms offsets. Runs of internal steps are folded, and the largest gap is named when it is at least half the time.
- **Limits.**
  - "Settled", never "resolved"/"rejected": `promiseResolve` fires for both and records no outcome.
  - A listener registered by one request and invoked synchronously by another's code runs in the invoker's context. No async resource links them, so it belongs to the invoker, and Rewind can't see the registration.
  - Only promise reactions are "released". Timers, I/O and handlers end a release chain: what started them is their creator, shown as → in the path.
  - Runs recorded before F15 have no `http.end`: the sender is reported unknown. Attribution and release edges use fields every recording already has, so they apply to older runs too.
  - Middleware that wraps `res.end` itself (e.g. compression) is recorded when it calls the original `end`, which may be in its own callback.
  - Measured only on Node 24 on Windows. `for await`, async generators, `AbortSignal`, worker threads and libraries that manage async context themselves are untested.
  - Recorder cost of `http.end` (one event per response): +3% median on the 300-request E6 load, inside the run-to-run noise (spikes/causal S5).

## Diff

Token stream per run (effectful callbacks, requests, logs, writes by location/op, errors, exit; ids and times stripped), aligned with `difflib.SequenceMatcher`. Reports the first divergence, whether it is a move (same step, different order) or a genuine only-A/only-B step, and counts. On the demo, good (sequential) vs bad (concurrent), both recorded with `-w currentCart`, diverge right after request #2's write to `currentCart`: same code path, different interleaving (verified M7). If only one run was watched, writes are left out and the shared prefix ends at #2's `loadCart` callback.

## Mutation tracking (`--watch`)

Records every **syntactic** write to a watched variable declared at the top level of a CommonJS file, with location, writer request (via `eid`) and JSON previews of before/after (≤200 chars).

Captured: reassignment; property and element assignment; compound operators; `++`/`--`; `delete`; calls to `push pop shift unshift splice sort reverse fill copyWithin set delete clear add`.

Not captured:
- writes through aliases (`const c = currentCart; c.x = 1`)
- destructuring targets (`[currentCart.a] = v`)
- files under `node_modules`; ESM files (`.mjs`, `"type": "module"`) — test confirms ESM is left unharmed
- mutations inside functions the value is passed to
- same-named local variables (skipped on purpose)

More than `REWIND_MUT_CAP` (default 10 000) writes to one name → counting continues, values stop.

**Watched reads (F11).** A second instrumentation pass wraps every expression reference to a watched binding as `__rw.r(name, loc, x)`, which returns `x`:
- **What counts as a read:** shorthand `{x}` becomes `{x: __rw.r(…)}`; `new x()` is parenthesised. acorn-walk visits declarations, params and assignment targets as patterns, so they are never reads. The roots of wrapped write targets and `delete x` are skipped too.
- **Line and column positions:** the edits insert text on the same line, so line numbers are unchanged. A read nests inside a write that shares a position, because the two use opposite MagicString sides.
- **Events:** each read is recorded as a `read` event `{name, loc, value}` with the reading callback's `eid`. It is recorded once per location per callback run (the dedupe set is cleared on every `async.before`).
- **Caps and switches:** `REWIND_READ_CAP` (default 10 000 per name), then a `read.capped` event with counting continuing in `run.end.data.reads`. `REWIND_READS=0` turns reads off, which `run.start.data.reads` records.
- **A TDZ read** throws exactly as before, and nothing is recorded.
- **Analysis and diff:** reads are story events but never "effects", so `diff` is unchanged by them.
- **Measured:** about 15 ns per repeated read (a 1M-iteration loop went from ~7 ms to ~22 ms). 20k separate callbacks each reading once showed no measurable time difference, but produced 10k read events (the cap). The demo gains 3 events.
- **Not seen:** reads through an alias made earlier, reads in `node_modules`/ESM, and reads inside functions the value was passed to.

**Error-time snapshots.** With `--watch`, each instrumented file gets one appended line, after its last line so no existing line or column moves, that registers a getter per watched top-level name (`__rw.reg`). In `uncaughtExceptionMonitor`, right after the `error.uncaught` event, the recorder reads every getter and emits a `snapshot` event: `data.error` is that error's seq, and `values` is `[{name, file, value}]`. Reads never throw: TDZ and throwing getters become `[threw X]`, and values JSON can't serialise become `[unserialisable Type]` (mutation previews use the same rule now; they used to print `[object Type]`). The read sits inside its own `try`, so it can never change the crash. `why` on an uncaught error reports ● each value and, when it differs from the `after` of the variable's last whole-variable write (path `""`) in the same file, ◆ that a write `--watch` doesn't see changed it (or one past the cap). Not covered: `error.logged` (only uncaught errors are snapshotted), ESM files, and errors thrown while a file's module body is still running (that file isn't registered yet). Serialising a value runs its `toJSON`/getters at crash time.
Requires `npm install --prefix recorder` (acorn, acorn-walk, magic-string); without `--watch` the recorder needs no npm packages. If they are missing, a `--watch` run crashes at preload with Node's `Cannot find module 'acorn'` (verified M7).

## Supported scenarios

- Node.js ≥ 20 (developed on v24.22.1), CommonJS apps, Node core `http` servers including keep-alive.
- Timers, immediates, fs callbacks, promises and `async`/`await` chains (attribution through `await` verified in M0 E3, and through promises shared between requests in F15).
- Sync uncaught throws and unhandled rejections in Node's default `--unhandled-rejections=throw` mode.
- Normal exit, `process.exit(n)`, crashes, SIGINT/SIGTERM; SIGKILL → partial run marked `crashed`.
- Windows 11 inside a OneDrive folder (M0 E5b).
- Python ≥ 3.12 per `pyproject.toml`; the suite has run on 3.15.2 (Windows) and 3.12.3 (Ubuntu 24.04, WSL2). 3.13/3.14 not run.
- Terminals: the classic PowerShell 5.1 console (with glyph stand-ins for Lucida Console / Consolas), Windows Terminal, Linux terminals (tested in tmux). Tested at widths down to 30 columns and at multiple terminal heights; short terminals scroll naturally, with some landing-screen content potentially moving into scrollback. Colour off with `NO_COLOR` or when piped. Per-terminal evidence: [compatibility matrix](TESTING_AND_VERIFICATION.md#terminal-compatibility-matrix-2026-11-23-branch-featcli-visual-redesign). macOS not tested.

## Unsupported scenarios / known limitations

- `https`, `http2`, outgoing HTTP clients as request anchors, worker threads, child processes: not instrumented. The recorder removes `REWIND_OUT` from its own environment once it has opened the file, so a `fork()`ed or `cluster` child, which inherits `--require recorder.js` through `execArgv`, stays inert instead of overwriting the parent's recording (regression tests `test_forked_child_leaves_the_parent_recording_intact` and `test_cluster_worker_leaves_the_primary_recording_intact`). The app's own code no longer sees `REWIND_OUT` in `process.env`.
- `--unhandled-rejections=warn|none`: rejections not recorded.
- SIGKILL: abrupt termination can lose up to the last 256 buffered non-error events; error events are written immediately, and the run is marked `crashed`.
- Not a full time-travel debugger: no per-function-call tracing, no arbitrary variable values, no stepping backwards, no breakpoints, no web UI.
- Promise creation stacks cost ~1.9× wall time on an HTTP-heavy benchmark (1.1× with `REWIND_PROMISE_STACKS=0`, losing `async` function names in chains).
- `REWIND_HOME` defaults to `./.rewind` relative to the cwd where `rewind` is run, so runs recorded from different directories land in different databases.

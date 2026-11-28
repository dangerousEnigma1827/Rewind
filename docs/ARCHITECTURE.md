# Rewind architecture

```
 ┌─────────────── node process ────────────────┐
 │ app code                                    │
 │ recorder/recorder.js  (node --require)      │
 │   async_hooks · console · http.Server ·     │
 │   uncaughtExceptionMonitor · [--watch AST]  │──► .rewind/runs/<id>.ndjson   (raw, kept)
 └─────────────────────────────────────────────┘
                          │ process exits
                          ▼
 rewind/store.py   ingest ──► .rewind/rewind.db  (SQLite, WAL)
 rewind/analysis.py         pure functions: Run index, tree, investigate, diff
 rewind/render.py + cli.py  Typer commands, Rich output
```

The Node side only writes facts. All interpretation happens in Python.

## Why NDJSON first, then SQLite

async_hooks callbacks must be synchronous and must not create async work, or the recorder ends up recording itself. A synchronous `fs.writeSync` of text lines is the safest thing to do there (spikes E4). This design also avoids native Node modules (no compiler on Windows), keeps partial runs readable after a hard kill, and leaves the raw stream on disk as ground truth. Python ingests each run in a single transaction.

## Recorder

| concern | mechanism |
|---|---|
| async causality | `init(aid, type, triggerAsyncId)` plus the `eid` of the execution creating the resource. `before`/`after`/`promiseResolve` are recorded too (`promiseResolve` carries the `eid` that settled the promise). Nothing is dropped: views filter, storage never does. |
| where work was scheduled | creation stack from V8 CallSites (no string parsing), with node internals and the recorder removed. Promise stacks are on by default. |
| what runs | callback name for timers and immediates (`resource._onTimeout.name`) |
| which callback emitted an event | every event carries `eid = executionAsyncId()` |
| requests | patched `http.Server.prototype.emit('request')`. Each request gets its own `AsyncResource('REWIND_REQUEST')`, and the handler plus all `req`/`res` event callbacks run in its scope. Node's own `HTTPINCOMINGMESSAGE` is per connection, so without this, keep-alive requests are attributed to each other. Found while building the demo; there's a regression test. The response's first `end()` call emits `http.end` with the calling callback's `eid` and stack (`finish`, behind `http.out`, runs in the request's scope and can't say who sent it). |
| errors | `uncaughtExceptionMonitor` only, which observes without changing crash semantics. For sync throws the context is the throwing callback. For rejections it is the rejected promise, whose ancestry leads back to the caller (spikes E2/E3). `console.error(err)` produces `error.logged`. |
| re-entrancy | one `inHook` guard wraps every recorder entry point |
| child processes | after opening `REWIND_OUT` the recorder deletes it from `process.env`; `fork()`/`cluster` children inherit `--require recorder.js` but stay inert, so they can't truncate the parent's file |
| durability | flush every 256 events, immediately on error events, on `exit`, and on SIGINT/SIGTERM (re-raised only if the app has no handler of its own) |
| watched reads | a second AST pass wraps each expression reference to a watched binding as `__rw.r(name, loc, x)` (returns `x`; same line). A `read` event is recorded once per location per callback run (dedupe set cleared on `async.before`), capped per name by `REWIND_READ_CAP`; `REWIND_READS=0` disables |
| error-time values | with `--watch`, each instrumented file ends with an appended `__rw.reg(file, {name: () => name})` line; on an uncaught error the monitor reads them (never throwing) into a `snapshot` event carrying the error's seq |
| `--watch` | `instrument.js` (acorn + magic-string, loaded lazily) wraps writes as `__rw.w(name, path, op, loc, before, (expr), reread)`. It preserves the expression's value and its line, reads `before` only when re-evaluating is side-effect free, and skips shadowed names. |

## Event schema

| field | |
|---|---|
| `seq` | total order within the run |
| `t` | µs since recorder start |
| `kind` | `run.start` `run.end` `run.signal` `async.init` `async.before` `async.after` `async.resolve` `async.cancel` `log` `http.in` `http.end` `http.out` `http.abort` `error.uncaught` `error.logged` `mutation` `mutation.capped` `read` `read.capped` `instrument` `source` `snapshot` |
| `eid` | executionAsyncId at emission |
| `aid`, `tid` | resource id and trigger id (async events; `http.in` anchors) |
| `type`, `name` | resource type and callback name; log text, request line, error message, variable name |
| `data` | kind-specific JSON (`origin`, `error`, `raw` stack, `req`, `status`, `path`/`op`/`loc`/`before`/`after`, …) |
| `stack` | `[{fn, file, line, col}]` user-visible frames, max 8, files relative to the cwd |

SQLite: `runs` holds one row per run (status `ok` / `failed` / `crashed`, counts, raw path). `events` mirrors the fields above, keyed by `(run_id, seq)` and indexed on `aid` and `kind`.

**Source snapshots.** Findings that quote source (the failing line, the module-level names on it) must use the code
that ran, not whatever is on disk when `why` is asked. As Node loads each user CommonJS file, the recorder emits a
`source` event with the SHA-256 of its bytes. Ingest, which runs as soon as the program exits, reads every user file
the run loaded or has a stack frame in, and stores it in `sources` (keyed by content hash, so identical files are
stored once) plus `run_sources(run_id, path, sha256, status)`:

| status | meaning |
|---|---|
| `verified` | file on disk matches the load-time hash, so the snapshot is exactly what ran |
| `unverified` | no load-time hash (ESM isn't hashed); captured at ingest |
| `changed` | file was edited between load and ingest: no text is kept, so it can't be shown as evidence |
| `missing` | file unreadable or not UTF-8 |

`Run.source_text()` reads only the snapshot. A file without usable text gives no source line, and the findings that
need it are left out rather than computed from the wrong code. Runs ingested before snapshots existed have no
`run_sources` rows and fall back to reading the file from disk, as before.

## Analysis

`analysis.Run` builds the indexes once: `inits`, `children` (by creating execution), `fired`, `resolves`, `emitted` (story events per eid), `requests` / `anchors` (each request with its `http.end`), plus cached `story`, `errors` and `effectful`.

- **Attribution.** `request_of(aid)` walks **creation** links (`init.eid`, falling back to `tid` where `eid` is 0, as on accepted sockets) up to the first request anchor (derived). Until F15 it walked `tid`. For a promise reaction, `tid` is the promise it continues, so awaiting a promise another request created (a cache, a single-flight call), even one that had long settled, moved the awaiting request's work and errors into the creator's request. `trigger_request_of` keeps the old walk; `why` reports when the two disagree. On every fixture that existed before F15 the two agree on every story event (spikes/causal S2, now a regression test).
- **Released by.** `released(aid)` / `release_chain(aid)`: for a promise reaction, the `async.resolve` of the promise it continues that precedes its run, and that resolve's `eid`, chained through Node's internal reaction promises (adoption, `Promise.all`, `events.once`) to the first context that wasn't itself released (a timer, I/O, a handler). "Waited" requires the reaction to exist before the settlement. Only promise reactions are released; timers and I/O fire on their own. `async.resolve` fires for fulfilment and rejection alike, so findings say "settled" (spikes/causal S1).
- **Response path.** `response_path(run, req)` goes from the `http.end` context back to a request's arrival, taking the releaser where a step waited and the creator otherwise; `response_findings` words it and names the largest gap.
- **Collapsing.** Hops with no user frame, such as the open/stat/read/close chain inside `fs.readFile`, are folded in views and kept in storage. `tree` prunes branches without story events and reports how many it hid.
- **`investigate(run, event)`.** This is `why`. It reports:
  - throw site and running callback, with its creation site (observed)
  - the collapsed causal chain to the owning request, and other requests' observable activity while it was in flight (derived)
  - for each watched variable: whether the failing source line reads it (derived), the last write (observed) and who made it (derived), and the own-write → foreign-overwrite → target ordering (derived)
  - with recorded reads: the read behind the target (observed), the last recorded write before it and whose it was (derived), "read request #N's value" (derived) or "can't explain that read" / "no read recorded" (derived, and no inference follows)
  - a race explanation (inferred, citing those seqs)
  - for an uncaught error with `--watch`: each watched value when it was thrown (observed, from the `snapshot` event whose `data.error` is that error's seq), and whether it differs from the last whole-variable write, which would mean an unrecorded write (derived)
  - for a callback that resumed after an `await`/`then`: the settlement it waited for and where it happened (observed), that it waited and for how long, or that the promise had already settled (derived), the request the settling callback belongs to when it is another one (derived), and a dependency on that request's shared work (inferred)
  - for a response (`http.out`, or `why -r N`): the callback that called `end()` (observed), another request's code ending it (derived), and the path from arrival to `end()` with timings (derived)

  Without `--watch`, it can only point out module-level names on the failing line and recommend `--watch`. It never claims a write.
- **`state_at(run, seq)`.** This is `at`. One pass over events up to `seq` collects, per (name, file), whole-value evidence (`mutation` with path `""`, `read`, `snapshot` values), property writes, and write caps. Each variable is known (latest whole value, cited), partial (property writes after it, listed and never merged), or unknown (no evidence, or capped with no read since). A read or snapshot differing from the previous value, with no recorded write between them, derives an unseen write.
- **`pending(run)`.** This is `pending`. It works only from lifecycle events already in the stream: `http.in`/`http.out`, `http.abort` (response closed before `finish`), `async.init` (Timeout inits carry `data.delay`), `async.before`, `async.resolve` (fires for rejections too) and `async.cancel` (the recorder wraps `clearTimeout`/`clearInterval`/`clearImmediate`, mapping the timer object to its aid with a WeakMap). Absence is evidence only in a complete recording (`run.end`, or `run.signal`, which flushes, and no torn lines). Request states are completed / failed / cancelled / unresolved. Unfinished user-created operations are derived. "Likely stalled" is inferred, and never after an uncaught error.
- **`diff(a, b)`.**
  - Tokens are request-tagged steps with ids and times removed: effectful callback firings (`site` and description), requests, logs, writes (location and op, not values), errors, and exit.
  - Callbacks with no observable effect are excluded, because Node's HTTP date-cache timer fires nondeterministically.
  - The token streams are aligned with `difflib.SequenceMatcher`, and the report covers the first divergence, whether the divergent step merely moved, and the reordered / only-A / only-B counts.

## Interactive app (`rewind/tui/`)

`rewind ui`, or bare `rewind` on an interactive terminal, opens a Textual app. It adds no debugging logic:
- `app.py` reads through `store` (a read-only `Session`, which never creates `REWIND_HOME`) and calls the same
  analysis functions as the commands: `Run`, `investigate`, `pending`, `state_at`, `build_tree`, `diff`.
- `views.py` turns their results into Rich renderables, worded for first-time users (it selects and words findings;
  it never creates them).
- `render.py`'s markup helpers (`event_row`, `event_text`, `tree_label`, `LEVEL`, `req_tag`) are shared. `render.rich_text`
  resolves their named styles against the TUI palette in `theme.py`, so one piece of markup renders in both worlds.
- `screens.py` holds the screens around an investigation:
  - **Home:** record, sample, recent runs.
  - **Record:** a form over `rewind/recording.py`, the same code as `rewind record`. The program runs in the current
    folder with a copy of the environment plus `REWIND_*`, with stdin closed and output streamed. Stopping sends
    SIGINT on POSIX (the recorder flushes) and terminates on Windows (the run is stored as incomplete).
  - **Help:** a centered modal.
- The investigation is the app's default screen.
  - `RewindApp.check_action` keeps investigation keys inactive while another screen is on top, and refuses `q` during
    a recording.
  - `_q()` queries the investigation screen regardless of which screen is showing.

**Ultraviolet** (`theme.py`): the palette comes from the website's `tokens.css`, which shares `render.PALETTE`.
- Violet `#7F5AF0` / `#8D6CFF` marks the brand, focus, selection and active tabs.
- The near-black `#08060D` foundation has panels a few dark steps up.
- Green, red and amber are used only for status, in the website's 4.5:1 ink values.
- It's registered as a Textual theme so built-in widgets follow it, and a test checks darkness and contrast.

Interaction model:
- **Details follow focus.** A list's highlight updates the details pane only while that list has focus, and a focus
  change re-renders details for the newly focused item.
- **Evidence navigation:** a finding's evidence seqs are walked with enter / `]` / `[`. `jump(seq)` widens the timeline
  filters only as far as needed: search and kind first, then the request, then "every event". For diff findings it
  first opens the run (A or B) the evidence belongs to.
- **Responsive layout** comes from screen classes set on resize:
  - three panes at 150+ columns
  - `-medium` at 120–149
  - `-compact` at 100–119: details on demand, and showing them hides the sidebar
  - `-narrow` below 100: stacked, details on demand
  - `-short` for short terminals
- **Glyphs:** the classic-console glyph fallback from the CLI applies. `✖` is drawn as `×` because Windows Terminal renders
  U+2716 from an emoji font, two cells wide.

## Testing

`pytest` runs real `node` processes:
- recorder fixtures (`tests/test_recorder.py`)
- ingest and lookup (`test_store.py`)
- analysis on recordings of the actual demo (`test_analysis.py`), including invariants that every inference cites evidence, every evidence seq exists, and every observed "write" claim is backed by a mutation event
- the CLI end to end (`test_cli.py`)
- presentation: landing screen, help, colour handling, narrow terminals, palette contrast, console-font fallback (`test_render.py`)
- the interactive app, driven headless with Textual's pilot over real demo recordings: navigation, evidence jumps, diff
  across runs, empty and incomplete recordings, four terminal sizes, and the real `App.run()` entry point (`test_tui.py`)

## Terminal presentation

`render.py` owns all output; `cli.py` only passes it data. The identity ("Ultraviolet"):
- **Colour.** One violet accent for derived facts, ids and the `◂◂` mark; text in the terminal's own colour; one mid grey for secondary detail; red only for errors. Every colour is a mid-tone with near-equal contrast on black and white (checked by a test), so one palette serves dark and light terminals.
- **Certainty is brightness.** Observed findings are bold, derived ones carry the violet `◆`, inferred ones are dim italic.
- **Wordmark.** `rewind` opens with REWIND in half-block letters (3 rows, only `█ ▀ ▄`, generated from bitmaps in `render.LETTERS`), rows stepping from light to deep violet; the version, the ruler's `◆` and the tagline share one right edge. 45–47 columns get a tighter letter spacing; below 45 the one-line `◂◂ r e w i n d` mark is used.
- **Structure without boxes.** Each view opens with `◂◂ command  subject · meta`; sections are labelled dotted rules. With colour off (`NO_COLOR`, pipes) glyphs and indentation carry the structure.
- **Help and errors.** `rewind` / `rewind --help` render a landing screen (custom `TyperGroup.format_help`); per-command help uses `TyperCommand.format_help`; usage errors replace `typer.rich_utils.rich_format_error`. The landing screen reads the database only if it already exists.
- **Classic Windows consoles** can't fall back to another font. When the console's actual font lacks Rewind's glyphs, output is written through a translator that swaps in one-cell stand-ins (`• ♦ × =` …) present in Lucida Console, Consolas and Cascadia Mono. Pipes, files, Windows Terminal and VS Code are untouched.

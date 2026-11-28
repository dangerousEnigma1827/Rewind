# Testing and verification

Back to [HANDOVER.md](HANDOVER.md). The test suite, the test-count history, the M0 experiments, M7 fresh-clone verification, and the terminal compatibility matrix. Bugs found in testing, with root causes and fixes, are in [ENGINEERING_LOG.md](ENGINEERING_LOG.md#3-bug-fix-and-verification-record).

**Latest result:** 154 / 154 on `feat/causal-reconstruction` after the polish pass (`test_causal.py` gains 8: thenable jobs get no release edge, new promises aren't reactions, an unhandled rejection names who rejected it, `pending` after `end()` then exit, a 3000-deep `await` loop stays linear and its tree merges to `×3000`, a response sent by code outside any request, a response path through another request, the TUI event detail; fixtures `thenable_job.js`, `unhandled_shared.js`, `end_then_exit.js`, `await_loop.js`, `flush_queue.js`). Before that, 146 / 146 (adds `test_cli.py::test_why_request_explains_the_response` and `test_causal.py`: 15 items, from 11 functions with one parametrized ×5: the attribution invariant on 5 pre-existing recordings, shared in-flight and settled promises, a mutex hand-off, a shared rejection, `http.end` recording, response explanations and the response path, a response ended by another request, tree/timeline placement, and pre-F15 runs without `http.end`. Fixtures `shared_inflight.js`, `shared_settled.js`, `shared_reject.js`, `mutex_queue.js`, `response_origin.js`, helper `_serve.js`; the spikes behind them are in `spikes/causal/`, 38 checks). Before that, 130 / 130 on `feat/tui-visual-polish` (adds `test_tui_polish.py`: 12; note that Textual's `run_test()` hides toasts unless `notifications=True`). Before that, 118 / 118 on Windows 11 (Python 3.15.2, Node 24.22.1, Textual 8.2.8) on `feat/ultraviolet-tui` (`test_tui.py` rewritten for the redesign: 27 tests; `test_recording.py` added: 5); 102 on `feat/rewind-tui`; 86 on `feat/watched-state`; 74 at `f2aca36` on `feat/recording-reliability` (none run on Linux). Before that: 54 / 54 on Windows 11 and Ubuntu 24.04 under WSL2 at `6320276`; `main` has 56. The tables below describe the suite at `6320276`; the extended-window additions are listed after them.

## Test suite (verified by reading `tests/`)

Runner: `pytest` (config in `pyproject.toml`: `testpaths = ["tests"]`, `-p no:cacheprovider`). Most tests spawn real `node` processes against `tests/fixtures/*.js` or the demo; `node` must be on PATH. `tests/conftest.py` provides `record` (runs a fixture with the recorder, returns events/stdout/stderr/exit code; can kill on a condition) and `rewind_home` (isolated `REWIND_HOME` in `tmp_path`).

| file | tests | covers |
|---|---|---|
| `test_recorder.py` | 15 | raw stream contiguity, re-entrancy, inert without `REWIND_OUT`, causal chain + callback names + creation stacks, promise stacks on/off, sync throw context + exit code, rejection-after-await attribution, an error event is on disk before a hard kill (the fixture logs an error and keeps running; the harness waits until `error.logged` appears in the NDJSON file, then kills the process with `Popen.kill()`, which is `TerminateProcess` on Windows and SIGKILL on Linux; the test asserts the error event is present and `run.end` is absent, so nothing ran at kill time), HTTP anchors, lazy AST deps, exact documented mutation set, mutation writer context, mutation cap, ESM untouched, keep-alive distinct anchors |
| `test_store.py` | 5 functions (one parametrized ×3) = 7 items | ingest round-trip, ok/failed status, crashed + torn line, re-ingest replaces, run resolution |
| `test_analysis.py` | 11 | request attribution on demo, describe names user code, tree pruning/folding, `short_fn`, why with watch proves overwrite, why without watch never claims a mutation, silent overcharge is hedged, sequential run clean, rejection through await, diff good/good empty, diff good/bad points at interleaving |
| `test_cli.py` | 8 | record + runs, `-N` run refs not parsed as options (added in M7), record with watch, friendly errors, timeline + tree on demo, why, diff, diff ignores one-sided watched writes |
| `test_render.py` | 13 | landing (no side effects, next step, exit 2), wordmark at every width (full / tight / compact below 45, one right edge, readable without colour), the 45-column switch in both Rich modes, short terminals scroll instead of clipping (80×24 … 30×12, colour on and off), help keeps every option, usage errors, no escape codes when piped, NO_COLOR keeps structure, no overflow at 60 columns, palette contrast on black and white, console-font fallback, evidence hierarchy styling |

Count: **54 collected items** at `6320276` (the ×3 parametrization in `test_store.py` adds 2). History below.

Fixtures: `chain.js`, `throw_timer.js`, `reject_await.js`, `http_two.js`, `http_keepalive.js`, `mutations.js`, `many_writes.js`, `esm_watch.mjs`, `kill_after_error.js`.

### Extended-window additions (2026-11-27)

The F2 and F3 tests were run against the code before the change and seen to fail (F3's also with the fix stashed). The F5 and F12 tests were written alongside their features and never run against the old code.

| commit | file | tests |
|---|---|---|
| `6232e9e` F2 | `test_store.py` | snapshot is the code that ran (verified); file edited before ingest is `changed` and never shown; identical sources stored once; legacy runs fall back to disk |
| `6232e9e` F2 | `test_cli.py` | `why` quotes the original failing line after `checkout.js` is overwritten |
| `30ae2fb` F3 | `test_recorder.py` | forked child and `cluster` worker leave the parent's NDJSON intact (one `run.start`, contiguous seqs, no NULs, parent logs only) |
| `3019f96` F5 | `test_analysis.py` | normal completion and 5xx; crash blames the crash, never a stall; genuinely unresolved (`/hang` stalled on the awaited promise, `/forgot` missing `res.end()`, `/abort` cancelled, cleared timer not pending); killed recording claims nothing; flushed `run.signal` counts as complete, torn lines don't |
| `3019f96` F5 | `test_cli.py` | `rewind pending` end to end |
| `f2aca36` F12 | `test_recorder.py` | values recorded safely (alias write visible, circular/BigInt/throwing getter → `[unserialisable …]`, undeclared name skipped, stdout, exit code and stack lines unchanged); one snapshot per uncaught error, tied by seq; none without `--watch` |
| `f2aca36` F12 | `test_analysis.py` | `why` reports values and derives an unrecorded change; demo snapshot matches the last write; no snapshot findings without `--watch` |

| `c7cf869` F11 | `test_recorder.py` | exact read set (shorthand, `new` callee, `typeof`, compound right-hand side, shadowing, per-callback dedupe); reads off and capped; TDZ read throws as before |
| `c7cf869` F11 | `test_analysis.py` | the crash cites the failing read; the silent overcharge is derived from #2's read (and stays "not proven" with `REWIND_READS=0`); overwrites after a read, or with no read at all, are never called a race |
| `29b6bc3` F14 | `test_analysis.py` | state from writes and reads; partial after property writes; an alias change revealed by the next read; interleaved requests in the demo; write cap → unknown; incomplete recording; no `--watch` |
| `29b6bc3` F14 | `test_cli.py` | `rewind at` end to end, bad seq, `-N` run ref |
| `401b7aa`, `d6b36be` TUI | `test_tui.py` | 16: markup resolution; empty home (welcome, nothing created); incomplete run; run/request/timeline navigation; why → evidence jumps with `]` `[`; filter widening; state, pending, tree; diff across runs with evidence in run A; no-watch / no-error runs; search and filters; help; layouts at 80×24, 100×30, 130×40, 180×50; the real `App.run()` entry point |

New fixtures: `fork_parent.js`, `cluster_primary.js`, `stall.js`, `snapshot.js`, `reads.js`, `reads_http.js`, `tdz_read.js`, `state.js`.

**Measured (F11):**
- Reads: about 15 ns per repeated read (a 1M-iteration hot loop went from ~7 ms to ~22 ms).
- 20k separate callbacks reading once each: no measurable time difference, 10k read events (the cap).
- The demo: +3 events.
- Without `--watch` nothing changes (the E6 workload measured 1.39 s on `main` vs 1.44 s, within noise, after Part 2).

**Visual and real-terminal checks (TUI):**
- Screenshots of every view were rendered headless at 80×24 to 170×46 and reviewed.
- The app was launched in a real Windows Terminal window on Windows 11 and captured. That run found two bugs the headless tests could not: the `App.run()` shadowing and the emoji-width `✖`.
- The classic PowerShell 5.1 console (conhost) was not checked for the TUI.

## Test count history

Each milestone's suite was **re-run at its own commit during the documentation audit** (2026-11-23), in a scratch clone with `pytest --collect-only` and then `pytest`, on Windows 11 / Python 3.15.2 / Node 24.22.1. These are today's results for that historical code, not records from the day each commit was made; the only contemporary count is M1's commit message ("14 integration tests").

| commit | milestone | collected | result | added |
|---|---|---|---|---|
| `2ab347b` | M1 recorder | 14 | 14 passed | `test_recorder.py` |
| `caea6e5` | M2 store + CLI | 24 | 24 passed | `test_store.py`, `test_cli.py` |
| `fe853b2` | M3 timeline / tree | 30 | 30 passed | `test_analysis.py`, keep-alive regression |
| `408d4a9` | M4 why | 36 | 36 passed | why with / without watch, hedged overcharge, rejection |
| `a1b9988` | M5 diff | 39 | 39 passed | diff good/good, good/bad, CLI |
| `ab02a7b` | M6 | 40 | 40 passed | one-sided watched writes |
| `0d4cb3d` | M7 | 41 | 41 passed | `-N` run refs |
| `769708f` | Ultraviolet redesign | 50 | 50 passed | `test_render.py` (9) |
| `467936b` | glyph fallback | 51 | 51 passed | console-font fallback |
| `b903d1e` | wordmark | 52 | 52 passed | wordmark at every width |
| `6320276` | compatibility fixes | 54 | 54 passed | 45-column switch in both Rich modes, short terminals |

M0 is not in the table: its 39 checks run under `spikes/check.py`, not pytest (see below).

## Where and how the suite has been run

| run | environment | result | source |
|---|---|---|---|
| M7 fresh clone #1 (scratch dir outside OneDrive, README install) | Windows 11, PowerShell 5.1, Python 3.15.2, Node 24.22.1 | 40 passed | M7 session |
| M7 nine-failure investigation (9 conditions) | same | see [nine failures](#previously-reported-nine-failures) | M7 session |
| M7 fresh clone #2 at `0d4cb3d` | same | 41 passed | M7 session |
| Redesign, each commit | Windows, main working tree | 41 → 50 → 51 → 52 passed | redesign sessions |
| Cross-platform review, WSL fresh clone of the branch | Ubuntu 24.04 (WSL2), Python 3.12.3, Node 24.22.2, typer 0.29.2, rich 15.0.0, pytest 9.2.0, SQLite 3.45.1 | 52 passed at `b903d1e`; 54 passed with the fix | cross-platform session |
| Cross-platform review, Windows | Windows 11, Python 3.15.2, Node 24.22.1, typer 0.29.2, rich 15.0.0, pytest 9.2.0, SQLite 3.53.4 | 54 passed | cross-platform session |
| Documentation audit, every milestone commit | Windows 11 scratch clone | table above, all passing | audit |

Not run anywhere: macOS; Python 3.13 and 3.14 (3.14.10 is installed on the dev machine but the suite was never run on it); Node 20 or 22 (README says Node ≥ 20).

## Regression tests and what they guard

| test | guards against | bug |
|---|---|---|
| `test_keepalive_requests_get_distinct_anchors` | keep-alive requests sharing one anchor. **What it proves:** three POSTs sent over one keep-alive socket (`maxSockets: 1`) each get their own `http.in` anchor of type `REWIND_REQUEST`, and each request's `done` log has exactly its own request, and no other, on its async ancestry. It does not test *why* the anchors were shared before the fix; that explanation (Node's `HTTPINCOMINGMESSAGE` resource is per connection) comes from the M3 commit message and a comment in `recorder/recorder.js`, and was not demonstrated separately | [B12](ENGINEERING_LOG.md#b12-keep-alive-requests-attributed-to-each-other) |
| `test_diff_of_two_good_runs_has_no_divergence` | HTTP date-cache timer noise in `diff` | [B13](ENGINEERING_LOG.md#b13-nondeterministic-http-date-cache-timer-in-diff) |
| `test_diff_ignores_writes_watched_in_only_one_run` | false divergence on one-sided `--watch` | [B14](ENGINEERING_LOG.md#b14-diff-diverged-on-writes-watched-in-only-one-run) |
| `test_negative_run_refs_are_not_parsed_as_options` | `-1` / `-2` rejected by Click | [B3](ENGINEERING_LOG.md#b3-negative-run-selectors--1--2-rejected) |
| `test_command_help_keeps_every_option_and_drops_boxes`, `test_usage_errors_keep_message_and_exit_code` | help/errors losing information when Typer's panels were replaced | [B7](ENGINEERING_LOG.md#b7-typer-generated-help-and-error-boxes) |
| `test_console_font_fallback_is_complete_and_keeps_layout` | stand-ins missing from a console font, or changing layout | [B8](ENGINEERING_LOG.md#b8-classic-powershell-console-shows-boxes-for-rewinds-glyphs) |
| `test_wordmark_switch_is_the_terminals_45_columns_in_every_rich_mode` | width off by one when Rich is not in its legacy-Windows mode | [B9](ENGINEERING_LOG.md#b9-wordmark-switch-used-the-wrong-width-outside-legacy-windows) |
| `test_short_terminals_scroll_instead_of_clipping` | landing too tall for 80×24; height affecting output | [B10](ENGINEERING_LOG.md#b10-landing-screen-too-tall-for-8024) |

The analysis tests also assert invariants (every inference cites evidence, every cited seq exists, every observed write is backed by a `mutation` event), and `test_why_without_watch_never_claims_a_mutation` enforces the honesty rule.

## M0 experiment findings (from `spikes/RESULTS.md`, previously reported)

What was pass/fail and what was not:
- **The 39 checks** are the assertions in `spikes/check.py`, covering E1–E5. All 39 passed. The first run passed 17/33; every failure was a wrong expectation in a check, not a recorder bug.
- **E0, E5b and E6** ran as separate scripts, each with its own PASS result.
- **E7 was exploratory, not pass/fail.** It compared four mutation-tracking approaches, three built and measured (`spikes/e7_*.js`) and one rejected without being built, and ended in a verdict per approach. It is not one of the 39 checks.

`RESULTS.md`'s own status line ("39/39 checks pass, plus E0, E5b, E6 and E7") lists E7 alongside the passes; its E7 section records verdicts, not a pass result.

| exp | result | key finding / decision |
|---|---|---|
| E0 | PASS | typer 0.29.2, rich 15.0.0, pytest 9.2.0, SQLite 3.53.4 on Python 3.15.2; 3.14.10 fallback |
| E1 | PASS | `tid` chains correct; `fs.readFile` = 4 hops, only first has user frames → collapse frameless hops; normalise `Type.fn` names; capture callback name |
| E2 | PASS | sync throws: `executionAsyncId()` = throwing callback; rejections: = rejected promise. Use `uncaughtExceptionMonitor` only |
| E3 | PASS | WeakMap<Promise,aid> redundant, dropped; don't install a re-throwing `unhandledRejection` listener; attribution through `await` works; `--unhandled-rejections=warn|none` gap |
| E4 | PASS | `writeSync` + stack capture in hooks creates no recorder-attributed resources |
| E5 | PASS | `run.end` flushed for normal exit, `process.exit(1)`, throw, rejection; SIGKILL partial readable → flush on errors, mark `crashed`. E5b: 201k rows in OneDrive SQLite WAL in 0.32 s, no lock errors |
| E6 | PASS | 300 HTTP requests: 1.1× without promise stacks, 1.9× with; ~330 events/request. Promise stacks default on |
| E7 | exploratory (no pass/fail) | Verdicts: AST rewrite **ship** (0.14 µs per watched write); inspector logpoints rejected (~39 µs per hit); deep Proxy kept as an unused stretch option (0.65 µs per write, breaks identity); out-of-process CDP pause rejected without being built (it would change the timing being observed) |

Raw artefacts: `spikes/check_results.json`, `spikes/e6_results.json`. Reproduce commands are at the top of `spikes/RESULTS.md`.

## Previously reported nine failures

The user reported that an earlier, interrupted session saw **nine failures**. **No record of them exists in the repository, commit messages, `spikes/RESULTS.md`, or the saved session notes.** Unknown:
- which suite (pytest, M0 `check.py`, or the fresh-clone attempt),
- which commit/environment (main tree vs fresh clone, Python version, cwd),
- the failing test names and messages.

M7 investigation (2026-11-23, Windows 11, Node v24.22.1, Python 3.15.2). Hypotheses tested, none gives nine:

| condition | result |
|---|---|
| fresh clone, README install | 40 passed |
| fresh clone **without** `npm install --prefix recorder` | **16 failed**, 24 passed (every `--watch` path: `Cannot find module 'acorn'`) |
| original OneDrive working tree | 40 passed |
| pytest run from outside the repo root | 40 passed |
| stale `REWIND_HOME` set in the environment | 40 passed |
| 3 repeated runs | 40 passed ×3 |
| under CPU load (4 busy node processes) | 40 passed |
| checkout `a1b9988` (M5) | 39 passed |
| checkout `408d4a9` (M4) | 36 passed |

Conclusion: **not reproduced.** The cause of the reported nine is unknown; it is not explained by a missing npm install (16), cwd, `REWIND_HOME`, load, or the M4/M5 code. `node` not on PATH was not tested (it would fail nearly every test, not nine).

## Interrupted M7 rehearsal

Started in a previous session and interrupted; no artefacts survive. Superseded by the M7 run below.

## M7 verification results (2026-11-23)

Fresh `git clone` into a scratch dir outside OneDrive, README install in PowerShell 5.1.

- Install: `python -m venv .venv && .venv/Scripts/activate` → PowerShell parse error on `&&` (fixed in README). The two halves run separately work; `pip install -e ".[dev]"` and `npm install --prefix recorder` work as written.
- Tests: `pytest --collect-only -q` → 40; `pytest` → 40 passed (pre-fix). After fix: 41 passed.
- Demo steps 1–7: all reproduced as README claims, except two wording errors fixed in README (step 2 "terminal never printed", step 6 needs `-w` on the good run). Totals: bad A-101 $161, C-303 $11, B-202 crashes; good/fixed A-101 $128, B-202 $186, C-303 $11.
- P1: run refs `last`, label and id prefix worked; `-1`/`-2` failed with "No such option" (fixed, regression test); after `--` they resolved correctly and `-7` of 6 gave "only 6 runs recorded". Unknown run → `error: no run matches '…'`, exit 2. All 12 `why --evidence` seqs and the diff's A-side seqs exist in `timeline --raw` and match their findings. Statuses: bad/nowatch `failed`, good/fixed `ok`. `rewind record` passes exit code 1 from the crashing demo, 0 from good.
- Note: piping into PowerShell's `Select-Object -First N` gives exit 255 because PowerShell stops the pipeline; full output exits 0. Not a Rewind defect.

Not verified at M7: Python 3.12–3.14, `REWIND_PROMISE_STACKS=0`, interactive-console (TTY) output behaviour, Linux/macOS. (Linux, Python 3.12 and real terminals were covered later; see the matrix below.)

## Terminal compatibility matrix (2026-11-23, branch `feat/cli-visual-redesign`)

How each row was checked:
- **Real terminal**: the actual `rewind` CLI ran inside that terminal at that size, and the screen (and scrollback where available) was read back: tmux `capture-pane` on Linux; `ReadConsoleOutputCharacterW` on Windows.
- **Simulated**: Rich rendering at an explicit width × height in `tests/test_render.py`; no terminal involved.

| Environment | Status | How |
|---|---|---|
| Windows 11, PowerShell 5.1 in the classic console (conhost), Lucida Console | **Verified, real terminal** | Window and buffer resized to 80×24, 60×24, 45×24, 44×24, 40×24, 80×15, 60×12. Colour on; glyph stand-ins (• ♦ × =) active because Lucida lacks the originals. Also `why`, `timeline`, `tree` at 120 columns. |
| Windows 11, classic console, Consolas | **Verified, real terminal** (120 columns only) | `why`, `timeline`, `tree`; stand-ins active (Consolas lacks ◆ ✖ ✎ ◉ ⚙). |
| Windows Terminal 1.25 (ConPTY) | **Verified, real terminal**, landing only | 80×24, 80×15, 60×12, 45×24/45×45, 44×24/44×45, 60×40. `WT_SESSION` set → original glyphs kept. Only the visible rows can be read back under ConPTY, and the glyphs as *drawn* by Windows Terminal's own font fallback were not inspected visually. |
| Windows, piped / redirected output | **Verified** | Full suite (54) on Python 3.15.2; no escape codes; works with `PYTHONUTF8=0`. |
| Linux: Ubuntu 24.04 on WSL2, Python 3.12.3, Node 24.22.2 | **Verified, real terminal** | Fresh clone, full suite 54/54. Landing in tmux at 80×24, 60×24, 45×24, 44×24, 40×24, 80×15, 60×12, 30×12, colour on and `NO_COLOR=1`: terminal text identical to Rich's own output at that width (apart from the "Ns ago" clock), widest line ≤ width. `why --evidence`, `timeline`, `tree`, `diff`, `runs`, `why --help` at 80×24 and 40×24 likewise identical. `record` in tmux: header, untouched program output, summary; spinner erased. tmux reports 256-colour/truecolour SGRs; actual glyph drawing depends on the host terminal's font. |
| Linux on real hardware / other distributions / other terminal emulators | **Not tested** | WSL2 Ubuntu inside tmux is the only Linux run. |
| macOS | **Not tested** | No macOS machine was available. Nothing in the code is Windows-only outside the guarded console-font check, but that is not verification. |
| Short terminal dimensions | **Real terminal** at the sizes above (conhost, tmux, Windows Terminal); **simulated** in `test_short_terminals_scroll_instead_of_clipping` at 80×24, 60×24, 45×24, 40×24, 80×15, 60×12, 30×12 with colour on and off | Output never depends on height: it is printed once and the terminal scrolls. At 80×24 the whole landing screen (23 lines) plus the prompt stays in view; on shorter screens the commands and the `next` hint remain on screen and the wordmark is in the scrollback. |

Found and fixed during this review:
- **The 45-column switch.** In tmux at 44×24 on WSL2 Ubuntu 24.04, the only real terminal checked before the fix, the wordmark still appeared. The switch assumed Rich always keeps one column free, which Rich does only in its legacy-Windows mode. It now uses the terminal's real width (`console.width + console.legacy_windows`). After the fix, 44 columns gave the compact mark and 45 the wordmark in:
  - that tmux setup
  - the classic console (PowerShell 5.1, Lucida Console) at 44×24 and 45×24
  - Windows Terminal 1.25 at 44×45 and 45×45
- **Landing height at 80×24.** The landing screen was 25 lines, so the prompt pushed the top two wordmark rows off screen. One description that wrapped was reworded and the trailing blank line dropped: 23 lines, nothing removed.

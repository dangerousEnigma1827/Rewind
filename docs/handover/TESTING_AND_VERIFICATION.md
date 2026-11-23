# Testing and verification

Back to [HANDOVER.md](HANDOVER.md). Originally written without running anything; the [M7 results](#m7-verification-results-2026-11-23) section records real runs.

## Test suite (verified by reading `tests/`)

Runner: `pytest` (config in `pyproject.toml`: `testpaths = ["tests"]`, `-p no:cacheprovider`). Most tests spawn real `node` processes against `tests/fixtures/*.js` or the demo; `node` must be on PATH. `tests/conftest.py` provides `record` (runs a fixture with the recorder, returns events/stdout/stderr/exit code; can kill on a condition) and `rewind_home` (isolated `REWIND_HOME` in `tmp_path`).

| file | tests | covers |
|---|---|---|
| `test_recorder.py` | 15 | raw stream contiguity, re-entrancy, inert without `REWIND_OUT`, causal chain + callback names + creation stacks, promise stacks on/off, sync throw context + exit code, rejection-after-await attribution, error flush survives kill, HTTP anchors, lazy AST deps, exact documented mutation set, mutation writer context, mutation cap, ESM untouched, keep-alive distinct anchors |
| `test_store.py` | 5 functions (one parametrized ×3) = 7 items | ingest round-trip, ok/failed status, crashed + torn line, re-ingest replaces, run resolution |
| `test_analysis.py` | 11 | request attribution on demo, describe names user code, tree pruning/folding, `short_fn`, why with watch proves overwrite, why without watch never claims a mutation, silent overcharge is hedged, sequential run clean, rejection through await, diff good/good empty, diff good/bad points at interleaving |
| `test_cli.py` | 8 | record + runs, `-N` run refs not parsed as options (added in M7), record with watch, friendly errors, timeline + tree on demo, why, diff, diff ignores one-sided watched writes |
| `test_render.py` | 10 | landing (no side effects, next step, exit 2), help keeps every option, usage errors, no escape codes when piped, NO_COLOR keeps structure, no overflow at 60 columns, palette contrast on black and white, console-font fallback, evidence hierarchy styling |

Count: 39 test functions → **41 collected items** after M7 (40 before; the ×3 parametrization adds 2). The CLI visual redesign (branch `feat/cli-visual-redesign`) adds `test_render.py` → **51**.

Fixtures: `chain.js`, `throw_timer.js`, `reject_await.js`, `http_two.js`, `http_keepalive.js`, `mutations.js`, `many_writes.js`, `esm_watch.mjs`, `kill_after_error.js`.

## Previously reported results

- README (M6): `pytest  # 40 tests` at `ab02a7b`. Confirmed in M7: 40 passed at `4097ca2` (docs-only on top of `ab02a7b`).
- Each milestone commit (M1–M6) was made under the rule "tests green before each commit" (original plan). Not independently re-verified.

## M0 experiment findings (from `spikes/RESULTS.md`, previously reported)

Status reported: **39/39 checks pass, plus E0, E5b, E6, E7.** The first run was 17/33; every failure was a wrong expectation in a check, not a recorder bug.

| exp | result | key finding / decision |
|---|---|---|
| E0 | PASS | typer 0.29.2, rich 15.0.0, pytest 9.2.0, SQLite 3.53.4 on Python 3.15.2; 3.14.10 fallback |
| E1 | PASS | `tid` chains correct; `fs.readFile` = 4 hops, only first has user frames → collapse frameless hops; normalise `Type.fn` names; capture callback name |
| E2 | PASS | sync throws: `executionAsyncId()` = throwing callback; rejections: = rejected promise. Use `uncaughtExceptionMonitor` only |
| E3 | PASS | WeakMap<Promise,aid> redundant, dropped; don't install a re-throwing `unhandledRejection` listener; attribution through `await` works; `--unhandled-rejections=warn|none` gap |
| E4 | PASS | `writeSync` + stack capture in hooks creates no recorder-attributed resources |
| E5 | PASS | `run.end` flushed for normal exit, `process.exit(1)`, throw, rejection; SIGKILL partial readable → flush on errors, mark `crashed`. E5b: 201k rows in OneDrive SQLite WAL in 0.32 s, no lock errors |
| E6 | PASS | 300 HTTP requests: 1.1× without promise stacks, 1.9× with; ~330 events/request. Promise stacks default on |
| E7 | — | AST rewrite shipped (0.14 µs/write); inspector logpoints, deep Proxy, CDP pause rejected |

Raw artefacts: `spikes/check_results.json`, `spikes/e6_results.json`. Reproduce commands are at the top of `spikes/RESULTS.md`.

## Previously reported nine failures

The user reports that an earlier session saw **nine failures**. **No record of them exists in the repository, commit messages, `spikes/RESULTS.md`, or the saved session notes available to this handover.** Unknown:
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

Not verified: Python 3.12–3.14, `REWIND_PROMISE_STACKS=0`, interactive-console (TTY) output behaviour, Linux/macOS.

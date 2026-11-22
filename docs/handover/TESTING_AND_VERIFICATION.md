# Testing and verification

Back to [HANDOVER.md](HANDOVER.md). **No tests were run while writing this document.** Results below are labelled by source.

## Test suite (verified by reading `tests/`)

Runner: `pytest` (config in `pyproject.toml`: `testpaths = ["tests"]`, `-p no:cacheprovider`). Most tests spawn real `node` processes against `tests/fixtures/*.js` or the demo; `node` must be on PATH. `tests/conftest.py` provides `record` (runs a fixture with the recorder, returns events/stdout/stderr/exit code; can kill on a condition) and `rewind_home` (isolated `REWIND_HOME` in `tmp_path`).

| file | tests | covers |
|---|---|---|
| `test_recorder.py` | 15 | raw stream contiguity, re-entrancy, inert without `REWIND_OUT`, causal chain + callback names + creation stacks, promise stacks on/off, sync throw context + exit code, rejection-after-await attribution, error flush survives kill, HTTP anchors, lazy AST deps, exact documented mutation set, mutation writer context, mutation cap, ESM untouched, keep-alive distinct anchors |
| `test_store.py` | 5 functions (one parametrized ×3) = 7 items | ingest round-trip, ok/failed status, crashed + torn line, re-ingest replaces, run resolution |
| `test_analysis.py` | 11 | request attribution on demo, describe names user code, tree pruning/folding, `short_fn`, why with watch proves overwrite, why without watch never claims a mutation, silent overcharge is hedged, sequential run clean, rejection through await, diff good/good empty, diff good/bad points at interleaving |
| `test_cli.py` | 7 | record + runs, record with watch, friendly errors, timeline + tree on demo, why, diff, diff ignores one-sided watched writes |

Static count: **38 test functions → 40 collected items expected** (the ×3 parametrization adds 2), matching README's "40 tests". Confirm with `pytest --collect-only -q`.

Fixtures: `chain.js`, `throw_timer.js`, `reject_await.js`, `http_two.js`, `http_keepalive.js`, `mutations.js`, `many_writes.js`, `esm_watch.mjs`, `kill_after_error.js`.

## Previously reported results

- README (M6): `pytest  # 40 tests`, implying a green suite at `ab02a7b`. Not re-run; the count agrees with the static count above.
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

Suspected cause: **not determinable from available sources.** Plausible candidates worth checking first in M7, all unverified hypotheses:
1. Fresh clone missing `npm install --prefix recorder` → every `--watch` test fails (`test_record_with_watch`, mutation tests, why-with-watch, demo-based analysis tests that record with `--watch`).
2. `node` not on PATH inside the venv shell → every node-spawning test fails.
3. Running pytest from a directory other than the repo root, or with a stale `REWIND_HOME` set in the environment.
4. Timing sensitivity of the demo on a slower/loaded machine (demo uses ≥40 ms margins, which the earlier session reported as deterministic).

Do not cite "nine failures" as a fact about current code until reproduced.

## Interrupted M7 rehearsal

Started in a previous session, interrupted; no artefacts or notes survive in the repo and the working tree was clean. Its progress and findings are unknown. See [PROJECT_STATUS.md](PROJECT_STATUS.md#m7-where-it-was-interrupted).

## Verification still required (M7)

1. Clean clone from git (outside OneDrive) builds per README on Windows.
2. `pytest --collect-only -q` count (expect 40), then full `pytest` — record exact pass/fail with output.
3. All 7 README demo steps produce the claimed output (see [NEXT_STEPS.md](NEXT_STEPS.md) for each expected claim).
4. README install commands work in PowerShell 5.1 as written (suspected not to).
5. Run selectors (`last`, `-N`, id prefix, label) and `--evidence` on a fresh database.
6. Optional: Python 3.14 path, `REWIND_PROMISE_STACKS=0`.

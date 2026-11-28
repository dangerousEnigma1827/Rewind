# Project status

As of 2026-11-28. Back to [HANDOVER.md](HANDOVER.md). Full history: [ENGINEERING_LOG.md](ENGINEERING_LOG.md).

## Current state

| ref | commit | state |
|---|---|---|
| `origin/main` | `bbd4eb5` docs: visual polish in README and handover | contains every extended-window branch below (`feat/recording-reliability` … `feat/tui-visual-polish`) |
| `main` (local) | `ce31f1c` spikes: causal reconstruction experiments S1-S4 | one commit ahead of `origin/main`, not pushed |
| `feat/causal-reconstruction` | F15, below | branches from local `main`; not pushed, not merged; integration is a fast-forward of `main` |

Suite: **154 passed** on `feat/causal-reconstruction` (Windows 11, Python 3.15.2, Node 24.22.1), also on a clean `git archive` export of the branch head. `spikes/causal/check.py`: 38 checks, 36 PASS, 1 AMBIGUOUS, 1 LIMIT. Not run on Linux or macOS since the 56-test audit.

## Async causal reconstruction (F15), branch `feat/causal-reconstruction`

| commit | what | tests |
|---|---|---|
| `ce31f1c` (on local `main`) | spikes S1–S4: promise settlement timing, `eid` behaviour, shared async patterns, `res.end()` context; overhead | 38 spike checks |
| `5692216` | attribution by creating execution (it was trigger-only, which moved work and errors between requests that shared a promise); what released an `await` continuation and who settled it; recorder event `http.end`; `why -r N`; response path | 16 |
| `7b7a8fa` | spike harness kept valid against the new recorder | — |
| `4618971` | stricter release edges (real reactions, first run only), unhandled rejections, `pending` after `end()`, unlinked path steps, deep `await` chains linear and recursion-free | 7 |
| `9a40d15` | response-path section in `why`, `http.end` wording in CLI and TUI, deep trees drawn iteratively | 1 (+CLI asserts) |
| `1925dd2` | docs for the polish pass | — |

Details: [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md#causal-reconstruction-f15), [spikes/causal/RESULTS.md](../../spikes/causal/RESULTS.md).

## Extended window (deadline moved to 2026-11-28): now on `origin/main`

| part | feature | commit | tests added |
|---|---|---|---|
| 1 | F2 source snapshots: analysis quotes the code that ran, not the file as edited later | `6232e9e` | 5 |
| 1 | F3 `fork()`/`cluster` children no longer corrupt the parent's recording (bug reproduced first) | `30ae2fb` | 2 |
| 2 | F5 `rewind pending`: requests completed / failed / cancelled / without a response, and unfinished user operations; nothing claimed from incomplete recordings | `3019f96` | 6 |
| 2 | F12 error-time snapshots of watched values; derived "changed by a write `--watch` doesn't see" | `f2aca36` | 5 |
| 3 (`feat/watched-state`) | F11 watched reads: `read` events; `why` cites the read and derives "read request #N's value", or rules the race out | `c7cf869` | 6 (+1 changed: the silent overcharge is no longer "not proven" when reads exist) |
| 3 (`feat/watched-state`) | F14 `rewind at RUN SEQ`: watched state from recorded evidence; known / partial / unknown, never assumed | `29b6bc3` | 6 |
| 4 (`feat/rewind-tui`) | shared render helpers for CLI and TUI (no CLI output change) | `0d7e2a6` | — |
| 4 (`feat/rewind-tui`) | `rewind ui` / bare `rewind`: the Textual investigation app | `401b7aa` | 15 |
| 4 (`feat/rewind-tui`) | non-wrapping rows, compact layout | `21707b9` | — |
| 4 (`feat/rewind-tui`) | fix: `self.run` shadowed `App.run()`; found by launching in a real terminal | `d6b36be` | 1 |
| 4 (`feat/rewind-tui`) | one-cell failure glyph for Windows Terminal | `095aeef` | — |
| 5 (`feat/ultraviolet-tui`) | UX audit of the TUI | `4e92aa2` | — |
| 5 (`feat/ultraviolet-tui`) | `rewind/recording.py`: recording shared by the CLI and the TUI (CLI unchanged) | `40d8144` | 5 |
| 5 (`feat/ultraviolet-tui`) | fix: resolve the script to record like node does | `9cf5b2a` | (+2 asserts) |
| 5 (`feat/ultraviolet-tui`) | Ultraviolet theme from the website's tokens | `b433f27` | — |
| 5 (`feat/ultraviolet-tui`) | first-run experience: Home, Record, Overview, plain names, grouped evidence, help | `bda5009` | 27 (replacing 16) |
| 6 (`feat/tui-visual-polish`) | visual polish: inputs and buttons without spill, Home hierarchy, tab keys and scrolling, `<` `>`, thin scrollbars, redesigned help ([TUI_VISUAL_POLISH.md](TUI_VISUAL_POLISH.md)) | `704329a` | — |
| 6 (`feat/tui-visual-polish`) | fix: view keys bounced back from inside another view | `995427e` | 12 |

Suite: **74 passed** at the end of Part 2, **86** after Part 3 **102** on `feat/rewind-tui` and **118** on `feat/ultraviolet-tui` and **130** on `feat/tui-visual-polish`, on Windows 11, Python 3.15.2, Node 24.22.1 (56 on `main` before this work). The branches stacked `main` ← `feat/recording-reliability` ← `feat/watched-state` ← `feat/rewind-tui` ← `feat/ultraviolet-tui` ← `feat/tui-visual-polish`; all of them are now contained in `origin/main` (`bbd4eb5`). The full Phantom Discount walkthrough (7 steps plus `pending`) was re-run on the branch. Recorder overhead on the E6 workload, 9 interleaved runs: `main` 1.39 s vs branch 1.44 s median (baseline 0.61 s), within noise. Not run on Linux or macOS for this branch. Details per feature: [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md), [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

## Earlier branch history

`feat/cli-visual-redesign` (`2b3b7b2`) was merged into `main` as PR #1 (`388fe45`): `769708f`, `467936b`, `49b34bb`, `b903d1e`, `6320276`, `2b3b7b2` on top of `0d4cb3d`. The branch still exists locally and on `origin`.

## What Rewind does

A causal debugger for Node.js:
- **Recording.** `rewind record` runs a program with a recorder preloaded. The recorder captures async causality (creating execution, trigger, callback runs, promise settlements), HTTP requests and the callback that first called `res.end()`, logs, errors and, with `--watch`, writes and reads of chosen module-level variables.
- **Questions.** `timeline` shows what happened in order. `tree` shows who scheduled whom. `diff` finds where two runs part ways. `why` traces an error, or any event, back to the request it belongs to and the callbacks that led there, says what an `await` waited on and who settled it, and with `-r N` explains a response. `pending` shows what never finished, `at` shows watched state at any point, and `rewind ui` puts it all in one interactive app.
- **What `why` can and can't claim.** With `--watch`, it reports the writes to the watched variable: each write is observed, and the request that made it and the order of writes are derived. Since F11, reads of watched variables are recorded too, so "request #2 read request #3's value" is derived from an observed read. A conclusion such as "this overwrite caused the failure" is still always marked as inferred, citing those events. Without `--watch`, it only suspects shared state.
- **Evidence levels.** Every finding is labelled observed ●, derived ◆ or inferred ?, and `--evidence` shows the event seqs behind it.
- **Demo.** The Phantom Discount demo shows a shared-state race between concurrent orders, plus a fix patch.

## Implemented

| area | status | commits |
|---|---|---|
| Feasibility experiments E0–E7 | done | `f10af80` |
| Recorder: async_hooks, HTTP anchors, errors, durability, `--watch` capture | done | `2ab347b`, `fe853b2` |
| SQLite store, `record`, `runs`, run selectors | done (`-N` fixed in M7) | `caea6e5`, `0d4cb3d` |
| `timeline`, `tree` | done | `fe853b2` |
| `why`, including mutation evidence (the plan's "M4.5" landed in M1 + M4, no separate commit) | done | `408d4a9` |
| `diff` | done | `a1b9988` |
| Demo, `demo/fix.patch`, README, `docs/ARCHITECTURE.md` | done | `ab02a7b` |
| Fresh-clone verification | done | `0d4cb3d` |
| Ultraviolet terminal identity, landing screen, help/errors, glyph fallback | done (merged in `388fe45`) | `769708f`, `467936b` |
| REWIND wordmark | done (merged in `388fe45`) | `b903d1e` |
| Linux / short-terminal fixes | done (merged in `388fe45`) | `6320276` |

## Verified

- **Tests:** 154/154 on Windows 11 (Python 3.15.2) on `feat/causal-reconstruction`. Earlier: 54/54 on Windows 11 and Ubuntu 24.04 under WSL2 (Python 3.12.3) at the M7 audit; every milestone's own suite also passed when re-run at its commit. See [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md#test-count-history).
- **README walkthrough (as of M7):** all seven demo steps reproduced from a fresh clone in PowerShell 5.1. The outputs quoted below are M7's; since F11 `why --seq` on A-101 derives #2's read of #3's cart instead of "not proven":
  - B-202 crashes in request #3. With `--watch`, `why` reports:
    - ● observed: the last write to `currentCart` before the crash
    - ◆ derived: that write was made by request #4, after #3's own write and before #3's failing read
    - ? inferred: a race on shared state as the likely root cause
  - A-101 is charged $161 instead of $128. `why --seq` on that log line reports request #3's overwrite before #2's payment completed as derived, and the race explicitly as *not proven*, because reads are not recorded.
  - without `--watch`, no write is claimed; shared state is only suspected.
  - the diff divergence
  - correct totals after the fix patch
- **Real terminals:**

  | terminal | sizes and checks |
  |---|---|
  | classic PowerShell console, Lucida Console and Consolas | 80×24 down to 40×24 and 60×12 |
  | Windows Terminal | landing screen at several sizes |
  | Linux tmux | landing and every view at 80×24 and 40×24, colour on and off |

  Details in the [compatibility matrix](TESTING_AND_VERIFICATION.md#terminal-compatibility-matrix-2026-11-23-branch-featcli-visual-redesign).
- **Output modes:** piped output has no escape codes, and `NO_COLOR` keeps the structure.
- **Storage inside OneDrive:** M0 E5b wrote 201k rows to SQLite (WAL mode) in the OneDrive project folder, with a concurrent reader and open/close churn, and saw no lock errors. `REWIND_HOME` can move the database elsewhere; the `%LOCALAPPDATA%` fallback the plan reserved for a failure was never needed.

## Not verified

- macOS (no machine).
- Linux outside WSL2/tmux.
- Python 3.13 and 3.14, and Node 20 and 22. The README states Node ≥ 20 and Python ≥ 3.12, but only Node 24, Python 3.12 and Python 3.15 were run.
- The README's Ubuntu `apt install python3-venv` route (the Linux run bootstrapped pip without sudo instead).
- How Windows Terminal and other emulators draw the glyphs: text was read back, not screenshotted.
- `REWIND_PROMISE_STACKS=0`.
- Interactive-console (TTY) behaviour of a crashing program's stdout: the old README claim was removed, not re-examined ([B6](ENGINEERING_LOG.md#b6-readme-claim-that-crashed-runs-lose-piped-stdout)).

## Known limitations

From the README and [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md):
- `--watch` misses writes through aliases, destructuring, `node_modules`, ESM files, and mutations made inside called functions.
- `https`, `http2`, worker threads and child processes are not instrumented.
- Rejections are captured only in `--unhandled-rejections=throw` mode.
- SIGKILL can lose up to 256 trailing non-error events.
- No value capture or stepping backwards; no replay.
- Causal reconstruction links only what `async_hooks` links: a listener registered by one request and invoked synchronously by another's code belongs to the invoker; "released by" covers promise continuations only; a settlement's outcome isn't recorded ("settled", never "resolved"/"rejected"); middleware that wraps `res.end` is recorded where it calls the original; runs recorded before `http.end` have no response sender. Measured only on Node 24 on Windows.

Additionally:
- `--watch` without `npm install --prefix recorder` fails with Node's raw "Cannot find module 'acorn'" ([B4](ENGINEERING_LOG.md#b4---watch-without-the-npm-dependencies)).
- Usage-error rendering depends on a Typer internal (`typer.rich_utils.rich_format_error`), marked with a `shortcut:` comment.

## Open items

| item | status |
|---|---|
| Review and merge `feat/cli-visual-redesign` | done: merged as PR #1 (`388fe45`) |
| Extended-window branches | done: contained in `origin/main` (`bbd4eb5`) |
| Integrate `feat/causal-reconstruction` | open: fast-forward `main`, re-run the suite, push (user's decision) |
| Website (`rewind-cli`, captured from `388fe45`) | stale: predates F2–F15 and the app; re-capture and copy changes needed (tracked outside this repo) |
| Rehearse the demo 3×, record a backup video | user tasks from M7, not done |
| "Nine failures" from an earlier session | not reproduced; cause unknown ([B1](ENGINEERING_LOG.md#b1-nine-unexplained-test-failures)) |
| M8 and later | proposed only, not approved ([NEXT_STEPS.md](NEXT_STEPS.md)) |

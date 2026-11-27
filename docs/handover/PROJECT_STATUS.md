# Project status

As of 2026-11-23, plus the extended-window work of 2026-11-27 (section below). Back to [HANDOVER.md](HANDOVER.md). Full history: [ENGINEERING_LOG.md](ENGINEERING_LOG.md).

## Extended window (deadline moved to 2026-11-28), branch `feat/recording-reliability`, not merged

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

Suite: **74 passed** at the end of Part 2, **86** after Part 3 **102** on `feat/rewind-tui` and **118** on `feat/ultraviolet-tui` and **130** on `feat/tui-visual-polish`, on Windows 11, Python 3.15.2, Node 24.22.1 (56 on `main` before this work). Branches stack: `main` ← `feat/recording-reliability` ← `feat/watched-state` ← `feat/rewind-tui` ← `feat/ultraviolet-tui` ← `feat/tui-visual-polish`. None is pushed or merged. The full Phantom Discount walkthrough (7 steps plus `pending`) was re-run on the branch. Recorder overhead on the E6 workload, 9 interleaved runs: `main` 1.39 s vs branch 1.44 s median (baseline 0.61 s), within noise. Not run on Linux or macOS for this branch. Details per feature: [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md), [docs/ARCHITECTURE.md](../ARCHITECTURE.md).

## Branch and commit state

| ref | commit | state |
|---|---|---|
| `main` | `388fe45` Merge pull request #1 from dangerousEnigma1827/feat/cli-visual-redesign | same as `origin/main` |
| `feat/cli-visual-redesign` | `2b3b7b2` docs: consolidate project handover and engineering history | **merged** into `main` as PR #1 (`388fe45`): `769708f`, `467936b`, `49b34bb`, `b903d1e`, `6320276`, `2b3b7b2` on top of `0d4cb3d`. The branch still exists locally and on `origin`. |

## What Rewind does

A causal debugger for Node.js:
- **Recording.** `rewind record` runs a program with a recorder preloaded. The recorder captures async causality, HTTP requests, logs, errors and, with `--watch`, writes to chosen module-level variables.
- **Questions.** `timeline` shows what happened in order. `tree` shows who scheduled whom. `diff` finds where two runs part ways. `why` traces an error, or any event, back to the request it belongs to and the callbacks that led there.
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

- **Tests:** 54/54 on Windows 11 (Python 3.15.2) and Ubuntu 24.04 under WSL2 (Python 3.12.3). Every milestone's own suite also passes when re-run at its commit. See [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md#test-count-history).
- **README walkthrough:** all seven demo steps reproduced from a fresh clone in PowerShell 5.1 (M7):
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
- No value capture or stepping backwards.

Additionally:
- `--watch` without `npm install --prefix recorder` fails with Node's raw "Cannot find module 'acorn'" ([B4](ENGINEERING_LOG.md#b4---watch-without-the-npm-dependencies)).
- Usage-error rendering depends on a Typer internal (`typer.rich_utils.rich_format_error`), marked with a `shortcut:` comment.

## Open items

| item | status |
|---|---|
| Review and merge `feat/cli-visual-redesign` | done: merged as PR #1 (`388fe45`) |
| Rehearse the demo 3×, record a backup video | user tasks from M7, not done |
| "Nine failures" from an earlier session | not reproduced; cause unknown ([B1](ENGINEERING_LOG.md#b1-nine-unexplained-test-failures)) |
| M8 and later | proposed only, not approved ([NEXT_STEPS.md](NEXT_STEPS.md)) |

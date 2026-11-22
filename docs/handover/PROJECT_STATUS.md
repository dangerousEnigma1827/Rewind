# Project status

As of 2026-11-22. Branch `main`. Back to [HANDOVER.md](HANDOVER.md).

## Commits (verified from git log at session start)

| commit | milestone |
|---|---|
| `ab02a7b` | M6: docs, demo fix patch, fresh-clone fixes |
| `a1b9988` | M5: rewind diff — where two runs' executions part ways |
| `408d4a9` | M4: rewind why — graded causal investigation of errors and any event |
| `fe853b2` | M3: analysis core, timeline and tree views, Phantom Discount demo |
| `caea6e5` | M2: SQLite store, rewind record and rewind runs |

M0 (spikes) and M1 (recorder) are older commits not shown above. Working tree was clean at session start.
After this handover is committed, HEAD will be a `docs: add comprehensive project handover` commit on top of `ab02a7b`.

## Milestones

| # | scope (from the original plan) | status |
|---|---|---|
| M0 | Spike risky assumptions (E0–E7): Python 3.15 stack, async causality, exception context, promise correlation, re-entrancy, persistence/OneDrive, overhead, mutation tracking | Done. Results in `spikes/RESULTS.md` (39/39 checks reported passing) |
| M1 | Recorder → NDJSON | Done |
| M2 | `store.py` + `rewind record` + `rewind runs` | Done |
| M3 | `timeline` + `tree` + Rich theme, demo app | Done |
| M4 | `why` (incl. the planned "M4.5" `--watch` mutation tracking) | Done |
| M5 | `diff` | Done |
| M6 | Demo polish, README, `docs/ARCHITECTURE.md`, `demo/fix.patch`, fresh-clone fixes | Done (commit message says "fresh-clone fixes"; whether a full fresh-clone walkthrough passed at M6 is not recorded) |
| M7 | Buffer: fresh-clone verification from README, bug fixes, rehearse demo 3×, backup video | **In progress — interrupted, not complete** |

"Done" means committed and previously reported working by the earlier session; tests were **not** re-run while writing this.

## M7: where it was interrupted

- An earlier session began the M7 fresh-clone verification / rehearsal and was interrupted.
- **No log, note, branch or file in the repository records which step it reached or what it found.** The working tree was clean at the start of this session, so any partial M7 work left no committed or uncommitted changes in this repo.
- Treat M7 as **not started** for planning purposes. The full checklist is in [NEXT_STEPS.md](NEXT_STEPS.md).

## Unfinished work

1. M7 fresh-clone verification following README only (install → tests → all 7 demo steps).
2. Fix whatever that verification breaks (docs or bugs only, no features); commit as M7.
3. Rehearse the demo 3× and record a backup video (video is the user's task).

## Unresolved issues and open questions

| issue | status |
|---|---|
| "Nine failures" reported in an earlier session | **Unknown.** No record in the repo or session notes says what they were, which suite, or which commit. See [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md#previously-reported-nine-failures). Must be re-established by running `pytest` in M7. |
| README test count says 40 | Consistent with a static read of `tests/` (38 functions, one parametrized ×3 → 40 items). Pass/fail not re-run. |
| README Windows install line | Suspected bug: `python -m venv .venv && .venv/Scripts/activate` does not work in Windows PowerShell 5.1 (no `&&`; activation script is `.venv\Scripts\Activate.ps1`). Works in Git Bash only with `source`. Unverified until M7 runs it. |
| SQLite inside OneDrive | M0 E5b reported no lock errors (201k rows, concurrent reader). Default `REWIND_HOME` is `./.rewind`; `REWIND_HOME` override exists. No fallback to `%LOCALAPPDATA%` was implemented (the plan proposed one only if M0 failed; it passed). |
| README says "developed on Python 3.15; 3.14 also works" | Previously reported; 3.14 path not re-verified. `pyproject.toml` requires `>=3.12`; 3.12/3.13 are untested as far as records show. |
| README demo claims (A-101 charged $161 vs $128, line numbers 12/18/23, request numbering #3/#4) | Line numbers verified against `demo/checkout.js` source (write at line 12, `paymentConfirmed` timer at line 18, failing read at line 23). Dollar amounts and request numbers depend on `demo/prices.json` and runtime output; unverified this session. |

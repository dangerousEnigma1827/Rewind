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
`4097ca2` docs: add comprehensive project handover — on top of `ab02a7b`; the M7 commit follows it.

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
| M7 | Buffer: fresh-clone verification from README, bug fixes, rehearse demo 3×, backup video | **Verification done 2026-11-23** (commit `M7: fresh-clone verification fixes`): fresh clone, 41/41 tests, all 7 demo steps, P1 checks. Demo rehearsal 3× and backup video remain with the user. |

"Done" means committed and previously reported working by the earlier session; tests were **not** re-run while writing this.

## M7: the earlier interrupted attempt

- An earlier session began the M7 fresh-clone verification / rehearsal and was interrupted; nothing in the repo records how far it got. M7 was then redone from scratch on 2026-11-23 (results below).

## M7 results (2026-11-23, verified)

Defects found by verification and fixed in the M7 commit:
1. **`-N` run selector was unusable**: `rewind timeline -1` → "No such option: -1" (Click parsed it as a flag). Fixed by `ignore_unknown_options` on `timeline/tree/why/diff`; regression test `test_negative_run_refs_are_not_parsed_as_options`.
2. **README install line** used `&&`, a parse error in PowerShell 5.1. Split into two lines. (`.venv/Scripts/activate` itself works in PowerShell: it resolves to `Activate.ps1`.)
3. **README demo step 6** recorded the good run without `--watch`, so `diff` excluded writes and its shared prefix ended at #2's `loadCart` callback, not "#2's write" as claimed. The command now uses `-w currentCart`, which produces the claimed output.
4. **README claim** "on Windows, stdout to a pipe is lost when the process crashes" was false here: the A-101 line was printed via a pipe (3/3), a file, and under `rewind record`. Claim removed.

## Unfinished work

1. Rehearse the demo 3× and record a backup video (user).

## Unresolved issues and open questions

| issue | status |
|---|---|
| "Nine failures" reported in an earlier session | **Not reproduced.** See [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md#previously-reported-nine-failures). |
| `--watch` without `npm install --prefix recorder` | The recorded program crashes at preload with Node's raw `Cannot find module 'acorn'` (run marked `crashed`). Documented prerequisite; message is not friendly. Not changed in M7 (not a regression, and improving it would be new behaviour). |
| SQLite inside OneDrive | M0 E5b reported no lock errors (201k rows, concurrent reader). Default `REWIND_HOME` is `./.rewind`; `REWIND_HOME` override exists. No fallback to `%LOCALAPPDATA%` was implemented (the plan proposed one only if M0 failed; it passed). |
| README says "developed on Python 3.15; 3.14 also works" | Previously reported; 3.14 path not re-verified. `pyproject.toml` requires `>=3.12`; 3.12/3.13 are untested as far as records show. |
| README demo claims (A-101 charged $161 vs $128, line numbers 12/18/23, request numbering #3/#4) | Verified in M7 from real runs (see TESTING_AND_VERIFICATION.md). |

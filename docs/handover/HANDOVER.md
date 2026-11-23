# Rewind — handover

Entry point for anyone (human or a fresh Claude Code session) continuing Rewind.
First written 2026-11-22; brought up to date on 2026-11-23 by a documentation audit against the Git history and re-run tests.

## What Rewind is

A causal "why did this happen" debugger for Node.js, built for a 48-hour hackathon.
A Node recorder (`node --require recorder/recorder.js`) writes execution events as NDJSON;
a Python CLI (`rewind`) ingests them into SQLite and answers *why* questions:
which request an error belonged to, who scheduled the failing callback, what writes to watched
state preceded it, and where a failing run diverged from a good one. Writes are recorded only for
variables named with `--watch`, and reads are not recorded, so a link from a write to the failure
is reported as inferred. Every finding is labelled
**observed ●**, **derived ◆** or **inferred ?**.

## Current state (one paragraph)

M0–M7 and the terminal redesign (Ultraviolet identity, glyph fallback, REWIND wordmark, Linux and
short-terminal fixes) are on `main`. `feat/cli-visual-redesign` (`6320276` plus the docs commit `2b3b7b2`)
was merged as PR #1 in `388fe45`, which is also `origin/main`. 54/54 tests passed on Windows and on Linux
(WSL2) in the post-merge audit at `388fe45`; the post-audit fixes add two tests (56).
The user-side demo rehearsal and backup video remain. M8+ is not started and not approved.
Details: [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Documents

| file | read it for |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | current state: what is implemented, verified and not verified; branches; open items |
| [ENGINEERING_LOG.md](ENGINEERING_LOG.md) | every commit, each milestone's decisions and fixes, the bug-fix and verification record (B1–B17) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | recorder, event schema, ingest, analysis, CLI, full data flow |
| [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md) | every command and option, what `--watch` does and does not see |
| [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md) | test suite, test-count history, M0 experiments, M7 results, terminal compatibility matrix |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | repo layout, Windows install, running Rewind, the demo, tests, env vars |
| [NEXT_STEPS.md](NEXT_STEPS.md) | what remains (demo rehearsal), the completed M7 checklist, proposed (not approved) later stages |

Pre-existing docs, still authoritative and not replaced: [`README.md`](../../README.md),
[`docs/ARCHITECTURE.md`](../ARCHITECTURE.md), [`spikes/RESULTS.md`](../../spikes/RESULTS.md).

## How the evidence in these docs is labelled

- **Verified by execution** — checked by running it: a recorded verification session (M7, the redesign and cross-platform sessions) or the documentation audit's re-run of each commit's tests.
- **Verified by source inspection** — supported by reading the implementation (or a dependency's source), but not necessarily exercised at runtime.
- **Previously reported / commit msg** — stated in README, `spikes/RESULTS.md` or a commit message at the time, not re-checked.
- **Simulated** — Rich rendering at a fixed width × height in tests; not a real terminal.
- **Unverified / unknown** — assumptions or gaps; called out explicitly.

## Instructions for a fresh Claude Code session

1. Read this file, then `PROJECT_STATUS.md` and `NEXT_STEPS.md`. Read `ENGINEERING_LOG.md` before changing anything a past bug touched.
2. Run `git status`, `git branch -vv` and `git log --oneline -8` first. Expected: `main` at `388fe45` (merge of PR #1, `feat/cli-visual-redesign`) or a later commit. If not, the state has moved on — re-check before trusting these docs.
   **Uncommitted changes belong to the user.** Do **not** reset, restore, clean, stash or otherwise discard them (`git reset --hard`, `git restore`, `git checkout -- …`, `git clean`, `git stash`). Leave them for the user to review and commit.
3. Scope: no milestone is open. Do not start M8 or add features unless the user approves it.
4. User working rules (from earlier sessions):
   - work milestone by milestone, verify with real runs, commit at completed milestones;
   - never claim a capability (especially mutation tracking) that isn't verified;
   - analysis must keep the observed / derived / inferred labels honest;
   - commit messages must **not** contain a `Co-Authored-By` trailer;
   - wait for user approval where the user asked for it.
5. For any re-verification, clone outside OneDrive (e.g. a temp/scratch dir) and apply `demo/fix.patch` only inside that clone, never in the main working tree.
6. The shell on the dev machine is Windows PowerShell 5.1 (no `&&`); Git Bash and WSL2 Ubuntu (with tmux) are also available. The tool session's environment sets `NO_COLOR=1` and `TERM_PROGRAM=vscode`; clear them when checking colour or the console-font fallback.

# Rewind — handover

Entry point for anyone (human or a fresh Claude Code session) continuing Rewind.
First written 2026-11-22; brought up to date on 2026-11-23 by a documentation audit against the Git history and re-run tests, and again on 2026-11-28 for the extended-window work and F15.

## What Rewind is

A causal "why did this happen" debugger for Node.js, built for a 48-hour hackathon (deadline later extended).
A Node recorder (`node --require recorder/recorder.js`) writes execution events as NDJSON;
a Python CLI (`rewind`) ingests them into SQLite and answers *why* questions:
which request an error belonged to, who scheduled the failing callback, what an `await` waited on and which
callback (possibly another request's) settled it, which callback sent a response, what writes to watched
state preceded it, and where a failing run diverged from a good one. `pending`, `at` and an interactive
Textual app (`rewind ui`) sit on the same analysis. Writes and (since F11) reads are
recorded only for variables named with `--watch`. "Request #2 read request #3's value" is derived from
them; that this caused the failure is reported as inferred. Every finding is labelled
**observed ●**, **derived ◆** or **inferred ?**. Rewind analyses one recording; it doesn't replay.

## Current state (one paragraph)

Everything through the extended window (F2, F3, F5, F11, F12, F14 and the TUI) is on `origin/main`
(`bbd4eb5`). Async causal reconstruction (F15) is on `feat/causal-reconstruction`, built on local `main`
(`ce31f1c`, the spike commit, one ahead of `origin/main`): attribution by creating execution, promise waits
and settlements, cross-request dependencies, `http.end` and `why -r N`. 154/154 tests pass on Windows. It is not
pushed or merged; integrating it is a fast-forward of `main` (the user's decision). The website (`rewind-cli`)
still shows captures from `388fe45` and needs its own update. Details: [PROJECT_STATUS.md](PROJECT_STATUS.md).

## Documents

| file | read it for |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | current state: what is implemented, verified and not verified; branches; open items |
| [ENGINEERING_LOG.md](ENGINEERING_LOG.md) | every commit, each milestone's decisions and fixes, the bug-fix and verification record (B1–B17) |
| [ARCHITECTURE.md](ARCHITECTURE.md) | recorder, event schema, ingest, analysis, CLI, full data flow |
| [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md) | every command and option, what `--watch` does and does not see, causal reconstruction (F15) and its limits |
| [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md) | test suite, test-count history, M0 experiments, M7 results, terminal compatibility matrix |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | repo layout, Windows install, running Rewind, the demo, tests, env vars |
| [NEXT_STEPS.md](NEXT_STEPS.md) | what remains (demo rehearsal), the completed M7 checklist, proposed (not approved) later stages |

Pre-existing docs, still authoritative and not replaced: [`README.md`](../../README.md),
[`docs/ARCHITECTURE.md`](../ARCHITECTURE.md), [`spikes/RESULTS.md`](../../spikes/RESULTS.md),
[`spikes/causal/RESULTS.md`](../../spikes/causal/RESULTS.md) (the F15 experiments).

## How the evidence in these docs is labelled

- **Verified by execution** — checked by running it: a recorded verification session (M7, the redesign and cross-platform sessions) or the documentation audit's re-run of each commit's tests.
- **Verified by source inspection** — supported by reading the implementation (or a dependency's source), but not necessarily exercised at runtime.
- **Previously reported / commit msg** — stated in README, `spikes/RESULTS.md` or a commit message at the time, not re-checked.
- **Simulated** — Rich rendering at a fixed width × height in tests; not a real terminal.
- **Unverified / unknown** — assumptions or gaps; called out explicitly.

## Instructions for a fresh Claude Code session

1. Read this file, then `PROJECT_STATUS.md` and `NEXT_STEPS.md`. Read `ENGINEERING_LOG.md` before changing anything a past bug touched.
2. Run `git status`, `git branch -vv` and `git log --oneline -8` first. Expected (2026-11-28): `origin/main` at `bbd4eb5`, local `main` at `ce31f1c`, and `feat/causal-reconstruction` ahead of it, or `main` fast-forwarded to that branch. If not, the state has moved on — re-check before trusting these docs.
   **Uncommitted changes belong to the user.** Do **not** reset, restore, clean, stash or otherwise discard them (`git reset --hard`, `git restore`, `git checkout -- …`, `git clean`, `git stash`). Leave them for the user to review and commit.
3. Scope: no milestone is open after F15. Do not add features unless the user approves them.
4. User working rules (from earlier sessions):
   - work milestone by milestone, verify with real runs, commit at completed milestones;
   - never claim a capability (especially mutation tracking) that isn't verified;
   - analysis must keep the observed / derived / inferred labels honest;
   - commit messages must **not** contain a `Co-Authored-By` trailer;
   - wait for user approval where the user asked for it.
5. For any re-verification, clone outside OneDrive (e.g. a temp/scratch dir) and apply `demo/fix.patch` only inside that clone, never in the main working tree.
6. The shell on the dev machine is Windows PowerShell 5.1 (no `&&`); Git Bash and WSL2 Ubuntu (with tmux) are also available. The tool session's environment sets `NO_COLOR=1` and `TERM_PROGRAM=vscode`; clear them when checking colour or the console-font fallback.

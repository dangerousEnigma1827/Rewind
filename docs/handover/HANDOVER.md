# Rewind — handover

Entry point for anyone (human or a fresh Claude Code session) continuing Rewind.
Written 2026-11-22, documentation only; no code, tests or commands were run while writing it.

## What Rewind is

A causal "why did this happen" debugger for Node.js, built for a 48-hour hackathon.
A Node recorder (`node --require recorder/recorder.js`) writes execution events as NDJSON;
a Python CLI (`rewind`) ingests them into SQLite and answers *why* questions:
which request an error belonged to, who scheduled the failing callback, who last wrote the
state it read, and where a failing run diverged from a good one. Every finding is labelled
**observed ●**, **derived ◆** or **inferred ?**.

## Current state (one paragraph)

Milestones M0–M6 are committed on `main`; the latest milestone commit is `ab02a7b`
("M6: docs, demo fix patch, fresh-clone fixes"). M7 (fresh-clone verification and demo
rehearsal) was started in an earlier session and interrupted; no record of how far it got
exists in the repository. **M7 is not complete.** M8+ is not started and is not planned in detail.

## Documents

| file | read it for |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | milestone status, commits, M7 interruption, open issues |
| [ARCHITECTURE.md](ARCHITECTURE.md) | recorder, event schema, ingest, analysis, CLI, full data flow |
| [FEATURES_AND_LIMITATIONS.md](FEATURES_AND_LIMITATIONS.md) | every command and option, what `--watch` does and does not see |
| [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md) | test suite, M0 experiment results, what is and isn't verified |
| [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) | repo layout, Windows install, running Rewind, the demo, tests, env vars |
| [NEXT_STEPS.md](NEXT_STEPS.md) | the exact remaining M7 checklist, and proposed (not committed) later stages |

Pre-existing docs, still authoritative and not replaced: [`README.md`](../../README.md),
[`docs/ARCHITECTURE.md`](../ARCHITECTURE.md), [`spikes/RESULTS.md`](../../spikes/RESULTS.md).

## How the evidence in these docs is labelled

- **Verified** — checked directly by reading files in the repository while writing these docs.
- **Previously reported** — stated in README, `spikes/RESULTS.md`, commit messages or earlier session notes, not re-run now.
- **Unverified / unknown** — assumptions or gaps; called out explicitly.

## Instructions for a fresh Claude Code session

1. Read this file, then `PROJECT_STATUS.md` and `NEXT_STEPS.md`. Read the others when a task touches them.
2. Run `git status` and `git log --oneline -8` first; confirm HEAD is `ab02a7b` or the handover-docs commit on top of it. If not, the state has moved on — re-check before trusting these docs.
3. Scope: the immediate job is **M7 only** (verification and fixing what verification breaks). Do not start M8 or add features unless the user asks.
4. User working rules (from earlier sessions):
   - work milestone by milestone, verify with real runs, commit at completed milestones;
   - never claim a capability (especially mutation tracking) that isn't verified;
   - analysis must keep the observed / derived / inferred labels honest;
   - commit messages must **not** contain a `Co-Authored-By` trailer;
   - wait for user approval where the user asked for it.
5. Do the M7 fresh clone outside OneDrive (e.g. a temp/scratch dir) and apply `demo/fix.patch` only inside that clone, never in the main working tree.
6. The shell on the dev machine is Windows PowerShell 5.1 (no `&&`); Git Bash is also available.

# Next steps

Back to [HANDOVER.md](HANDOVER.md). Nothing beyond M7 was approved until 2026-11-27. With the deadline extended to 2026-11-28, the user approved work in parts: Part 1 (F2, F3) and Part 2 (F5, F12) are done on `feat/recording-reliability` ([PROJECT_STATUS.md](PROJECT_STATUS.md#extended-window-deadline-moved-to-2026-11-28-branch-featrecording-reliability-not-merged)). Parts 3 and 4 are not started and need the user's go-ahead.

## Open after Parts 1–4

- **Review and merge, in order:** `feat/recording-reliability` → `feat/watched-state` → `feat/rewind-tui` → `feat/ultraviolet-tui`. The last one is the first-run TUI redesign ([TUI_UX_AUDIT.md](TUI_UX_AUDIT.md)), which records from inside the app. Each branches from the previous one, none is pushed, and `main` is untouched. Re-rehearse the demo from the merged `main`. Its steps are unchanged, but `why --seq` on A-101 now derives #2's read of #3's cart instead of "not proven". `rewind pending`, `rewind at` and the app (`rewind`) are new.
- **Not verified:** Linux, macOS, Node 20/22. The TUI hasn't been checked in the classic PowerShell 5.1 console (conhost), only Windows Terminal. The new CLI views haven't been checked in PowerShell 5.1 either.
- **Landing screen:** `pending` and `at` are missing from the landing screen, which is exactly at its 80×24 limit (B10). The app lists every view.
- **Large runs:** the TUI loads runs synchronously. Very large runs would freeze it briefly; a worker plus a loading state would fix that.

## What remains

1. ~~Review and merge `feat/cli-visual-redesign`~~ **Done:** merged into `main` as PR #1 (`388fe45`).
2. **Rehearse the 7-step demo 3× and record a backup video.** User tasks left open since M7. Rehearse from `main`, which now includes the redesign.
3. **Optional verification gaps** if they matter for judging: macOS, Python 3.13/3.14, Node 20/22. See [PROJECT_STATUS.md](PROJECT_STATUS.md#not-verified).

## M7 checklist (completed 2026-11-23)

Results in [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md#m7-verification-results-2026-11-23).

Rule for M7: fix only what verification shows is broken (docs or bugs). No new features, no refactors.

### P0 — must pass
- [x] Confirm repo state: `git status` clean, `git log` shows `ab02a7b` (+ handover docs commit).
- [x] Confirm `recorder/node_modules`, `.rewind/`, `.venv/` are not tracked (`git ls-files`).
- [x] Fresh `git clone` into a scratch directory **outside OneDrive**.
- [x] Install exactly as README says, in PowerShell 5.1; note each deviation (expected: the `&&` / `activate` line).
- [x] `pytest --collect-only -q` (expect 40) then `pytest`; record pass/fail with output. Reproduce or rule out the "nine failures".
- [x] Demo step 1: `node demo/traffic.js`, run directly with plain Node and **without Rewind** (reproduces the crash before any recording; steps 2–7 use `rewind record`) → `TypeError … reading 'price'` at `demo/checkout.js:23`, via `Timeout.paymentConfirmed` at `:18`.
- [x] Step 2: `record -l bad -w currentCart` then `timeline bad` → three interleaved orders, three writes from three requests, log `order A-101: charged $161` (correct is $128).
- [x] Step 3: `why bad` → ● thrown in `applyDiscount` at `checkout.js:23` inside `paymentConfirmed` created in `chargePayment`; ◆ request #3 (B-202); ◆ failing line reads `currentCart` (from its source text); ● last recorded write was `{order: "C-303", …}` at `checkout.js:12`; ◆ #3 wrote and #4 overwrote before the failing read at `checkout.js:23`; ? shared-state race. The read itself is not recorded: only writes to watched variables are.
- [x] Step 4: `why bad --seq <A-101 log seq>` → overwrite by #3 derived; race explicitly not proven.
- [x] Step 5: record without `--watch`, `why` → no mutation claimed; recommends `--watch currentCart`.
- [x] Step 6: `record -l good -w currentCart -- node demo/traffic.js --sequential`; `diff good bad` → identical up to #2's write (needs `-w` on both runs — README fixed in M7); then good finishes #2's payment, bad sees #3 arrive.
- [x] Step 7: in the clone only, `git apply demo/fix.patch`, re-record, `why` → no errors; totals correct for all three orders.

### P1 — should check
- [x] Run selectors: `last`, `-1`/`-2`, id prefix, label; unknown run → friendly error, exit 2.
- [x] `--evidence` on `why` and `diff` prints seqs that exist in `timeline --raw`.
- [x] `rewind runs` statuses: `failed` for bad, `ok` for good/fixed.
- [x] Exit code passthrough: `rewind record` on the crashing demo exits non-zero.

### P2 — wrap-up
- [x] Apply minimal fixes for anything failing above (README PowerShell line, test count, any bug); re-verify on a new clone.
- [x] Commit `M7: fresh-clone verification fixes` (no `Co-Authored-By`). If nothing needed fixing, record the verification result instead of an empty commit — ask the user.
- [ ] Rehearse the 7-step demo 3× (user, or Claude on request).
- [ ] Record backup demo video (user).

## Proposed future stages (M8+) — not approved, not started

**The project's finish line is the agreed M7 scope plus the submission handoff.** M8–M10 below must not be started unless the user explicitly reopens the scope. A fresh session should treat them as out of scope by default, even where one looks small or useful.

Listed only so a later session doesn't have to rediscover them.

| stage | proposal | why it might matter |
|---|---|---|
| M8 | Submission packaging: hackathon write-up, screenshots/asciicast of the demo, final README pass | needed to submit; no code |
| M9 | Robustness from real use: whatever bugs the rehearsals or judges' trial runs surface | only reactive fixes |
| M10 (optional) | Close a documented gap only if a real user scenario needs it — e.g. `https` server attribution (same patch as `http.Server`), or `--watch` for ESM | small, contained extensions of existing mechanisms |

Explicitly **not** proposed: web UI, stepping backwards / full value capture, breakpoints, worker-thread or child-process tracing, out-of-process CDP — these were ruled out in the original plan as out of scope or harmful to the timing the tool observes.

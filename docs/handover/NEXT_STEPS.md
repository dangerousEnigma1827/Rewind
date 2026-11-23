# Next steps

Back to [HANDOVER.md](HANDOVER.md). M7 verification was completed on 2026-11-23 (results in [TESTING_AND_VERIFICATION.md](TESTING_AND_VERIFICATION.md#m7-verification-results-2026-11-23)); only the user-side rehearsal and video remain. Nothing beyond M7 is approved work.

## Remaining M7 work (prioritised checklist)

Rule for M7: fix only what verification shows is broken (docs or bugs). No new features, no refactors.

### P0 — must pass
- [x] Confirm repo state: `git status` clean, `git log` shows `ab02a7b` (+ handover docs commit).
- [x] Confirm `recorder/node_modules`, `.rewind/`, `.venv/` are not tracked (`git ls-files`).
- [x] Fresh `git clone` into a scratch directory **outside OneDrive**.
- [x] Install exactly as README says, in PowerShell 5.1; note each deviation (expected: the `&&` / `activate` line).
- [x] `pytest --collect-only -q` (expect 40) then `pytest`; record pass/fail with output. Reproduce or rule out the "nine failures".
- [x] Demo step 1: `node demo/traffic.js` → `TypeError … reading 'price'` at `demo/checkout.js:23`, via `Timeout.paymentConfirmed` at `:18`.
- [x] Step 2: `record -l bad -w currentCart` then `timeline bad` → three interleaved orders, three writes from three requests, log `order A-101: charged $161` (correct is $128).
- [x] Step 3: `why bad` → ● thrown in `applyDiscount` at `checkout.js:23` inside `paymentConfirmed` created in `chargePayment`; ◆ request #3 (B-202); ◆ failing line reads `currentCart`; ● last write `{order: "C-303", …}` at `checkout.js:12`; ◆ #3 wrote, #4 overwrote, then #3 read; ? race on shared module-level state.
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

Listed only so a later session doesn't have to rediscover them. Each needs explicit user approval; keep scope small.

| stage | proposal | why it might matter |
|---|---|---|
| M8 | Submission packaging: hackathon write-up, screenshots/asciicast of the demo, final README pass | needed to submit; no code |
| M9 | Robustness from real use: whatever bugs the rehearsals or judges' trial runs surface | only reactive fixes |
| M10 (optional) | Close a documented gap only if a real user scenario needs it — e.g. `https` server attribution (same patch as `http.Server`), or `--watch` for ESM | small, contained extensions of existing mechanisms |

Explicitly **not** proposed: web UI, stepping backwards / full value capture, breakpoints, worker-thread or child-process tracing, out-of-process CDP — these were ruled out in the original plan as out of scope or harmful to the timing the tool observes.

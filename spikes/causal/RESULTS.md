# Causal reconstruction spikes (S1–S4): results

Step 1 of *Stronger Async Causal Reconstruction*. Question: can Rewind reconstruct **who a callback belongs to** and
**what released it** from what the recorder already writes, and where does that break?

Environment: Windows 11, Node v24.22.1, Python 3.15.2, repo inside OneDrive. All fixtures are recorded with the
**production** recorder (`recorder/recorder.js`, unmodified). The only extra code is a spike-only preload,
`probe_end.js`, for S4.

**Reproduce**
```
.venv/Scripts/python spikes/causal/check.py    # 38 checks; writes check_results.json + sequences.md
.venv/Scripts/python spikes/causal/bench.py    # overhead; writes bench_results.json (REPS=9 used below)
```
Raw NDJSON goes to `spikes/out/causal/` (gitignored). `sequences.md` holds the event traces each verdict rests on.

**Status: 38 checks: 36 PASS, 0 FAIL, 1 AMBIGUOUS, 1 LIMIT.** The result was identical on 3 consecutive runs.

## The three edges under test

Every edge comes from fields the recorder **already writes**. No new events are needed for the first two.

| edge | source | meaning |
|---|---|---|
| **created by** | `async.init.eid` | the execution that created the resource (called `setTimeout`, `then`, `await`, `new Promise`) |
| **trigger** | `async.init.tid` | triggerAsyncId. For a promise reaction it is the **parent promise**, not the code that awaited it |
| **released by** | the last `async.resolve` of a reaction's trigger before its `async.before`, and that resolve's `eid` | which execution settled the promise this continuation waited on |

Today `analysis.Run.chain()` and `request_of()` follow **trigger only**.

## S1: promise settlement timing — PASS (1 AMBIGUOUS)

| case | finding | verdict |
|---|---|---|
| a. timer settles a promise | `async.resolve(P)` fires inside the timer callback (`eid` = the Timeout). The `await` continuation's `tid` = P, and it runs after the resolve | PASS |
| b. **adoption** `resolve(outer, pendingInner)` | `async.resolve(outer)` does **not** fire at the `resolve()` call. It fires at real settlement (seq 18, after inner's at 15), inside an **internal reaction promise** (no creation stack) whose `tid` = inner. Following one more hop reaches `innerFire`, the real releaser | PASS |
| c. `return p` / `return await p` | both release chains end at `slowFire` (2 promise hops each) | PASS |
| d. `Promise.all` / `race` | `all` is released by the **slowest** element (12 ms timer); `race` by the **winner** (4 ms). The losing element settles later with no effect | PASS |
| e. rejection | a rejection also emits `async.resolve`, in the rejecting callback | PASS |
| e. outcome | `async.resolve` carries only aid/eid, so **fulfilled vs rejected is not recorded** | **AMBIGUOUS** |
| f. non-native thenable | Node wraps it in a job promise. `thenable.then` runs in that job's context, and the release chain ends at the timer that called its `resolve` | PASS |
| g. awaiting an already-settled promise | the parent's resolve (seq 8) **precedes** the continuation's init (seq 12). This is not a wait, and the rule `init(child) < resolve(parent)` separates it from a real wait | PASS |

Trace for S1b (internal reaction promise `#9`, created by Node with no stack):
```
    9 before  Timeout outerFire@3#7      <- resolve(inner) called here: NO async.resolve for outer
   11 before  PROMISE@3#6               <- PromiseResolveThenableJob runs in outer's context, calls inner.then
   14 before  Timeout innerFire@2#5
   15 resolve PROMISE@2#4  eid=Timeout innerFire@2#5     inner settles
   18 resolve PROMISE@3#6  eid=PROMISE#9                 outer settles, inside the internal reaction on inner
   21 before  PROMISE@4#8                                 cont() runs
```

## S2: `eid` on `async.init` — PASS

| case | finding | verdict |
|---|---|---|
| a. 8 creation contexts (top level, executor, then, timer, immediate, nextTick, queueMicrotask, after await) | `init.eid` equals `executionAsyncId()` as read by user code, **8/8** | PASS |
| b. **invariant** over the demo, all 17 runnable `tests/fixtures/*.js` and the E6 load (N=50) | both models give **all 197 story events** the same request, and every resource created from user code too | PASS |
| b. internal resources | 17 Node-internal teardown resources differ (SHUTDOWNWRAP and its ticks after `res.end`): trigger gives no request, creation gives the request whose `end()` started the shutdown. They have no user frames and emit nothing | PASS (note) |
| c. `eid = 0` | only on `TCPWRAP` (accepted sockets) and `FILEHANDLE`, with no user frames. A creation walk must **fall back to `tid`** when `eid` is 0 | PASS |

`forever.js` and `kill_after_error.js` were skipped (they are kill-driven and never exit on their own).

**Implication:** switching attribution to the creation chain changes nothing the current suite observes. It only
changes results where a promise crosses request boundaries, which no existing fixture does.

## S3: shared async patterns — PASS (1 LIMIT)

| pattern | trigger model (today) | creation model | released by |
|---|---|---|---|
| a. **in-flight memoised promise** (cache fill / single-flight) | /b's log → **/a** ✗ | /b ✓ | /a's `fetchPrice` timer, waited=true: a **cross-request dependency** |
| b. **cache hit on an already-settled promise** | /b's log → **/a** ✗ | /b ✓ | waited=false: correctly not a wait |
| c. mutex with a resolver queue | /b ✓ | /b ✓ | /a's `work` timer let /b in. **Only** the release edge shows it |
| d. `events.once` across requests | /b ✓ | /b ✓ | /a's `announce` timer, through events' internal promise (2 hops) |
| e. **shared promise rejects** | /b's *logged error* → **/a** ✗ | /b ✓ | /a's rejecting timer: an **inherited failure** |
| f. sync listener registered by /b, emitted by /a | /a | /a | none. No async resource links them | **LIMIT** |

S3a/S3b/S3e are the production bug from the audit: **any memoised promise** (even a plain cache hit) moves later
requests' work, and errors, into the first request. `rewind why` would then report the wrong request as DERIVED.
The key line from S3a:
```
   79 init    PROMISE@9#36  tid=PROMISE@5#21  eid=REQ#2(/b)   <- /b's await: trigger is /a's cache promise
  101 log     'handler /b 10'  eid=PROMISE@9#36                 <- trigger chain -> #21 -> REQ#1 (wrong)
```

**Rule correction found here:** "released by" is defined **only for promise reactions**. My first draft also
followed a Timeout's `tid`, and so claimed the timer was "released by" the promise it was created in. That is wrong:
timers fire on their clock, I/O on completion, and handlers on arrival. `lib.release_chain` stops at the first
non-promise context. That context is the releaser.

**LIMIT (S3f):** a listener registered by one request but invoked *synchronously* by another runs entirely inside
the emitter's execution. async_hooks records no resource for the registration, so the registering request is
invisible. Rewind must not claim it. Documenting it is all that is possible without patching `EventEmitter`.

## S4: `res.end()` call context — PASS

Probe: `spikes/causal/probe_end.js` wraps `ServerResponse.prototype.end`. On the first call per response it records
`executionAsyncId()` and user frames.

| route | end() called in | owner (creation model) |
|---|---|---|
| /direct | the request handler | own request ✓ |
| /await | the await continuation (PROMISE) | own request ✓ |
| /timer | the `later` timer | own request ✓ |
| **/park** | **/release's handler** | **the other request** (#6 ends #5) |
| /pipe | a Node-internal TickObject, **no user frames** | own request ✓ (by creation chain) |

- **Today `http.out` always carries the request anchor as `eid` (6/6),** because `finish` is emitted inside the
  anchor's scope. So the callback that actually produced the response is lost, and the tree hangs `← 200` off
  the request itself.
- An `http.end` event recorded at the first `end()` call is the missing data. For `pipe`, the honest report is
  "ended by Node stream internals", plus the creation chain back to user code.
- In handler context the probe's stack also contains `recorder.js` frames (the recorder wraps `Server.emit`). The
  production recorder's `keepFile()` already drops its own directory.

## S5: overhead

`spikes/fixtures/e6_load.js`, N=300 requests (~350 events per request). Production recorder. Median of 9 runs,
interleaved round-robin so drift hits every mode equally.

| mode | median | min–max | ×baseline | ×recorder | events |
|---|---|---|---|---|---|
| baseline (no recorder) | 0.591 s | 0.514–0.684 | 1.00 | – | – |
| recorder | 1.190 s | 0.977–1.854 | 2.01 | 1.00 | 104 856 |
| recorder + end probe, no stack | 1.195 s | 1.046–1.643 | 2.02 | 1.00 | +300 |
| recorder + end probe + stack | 1.197 s | 1.061–1.793 | 2.03 | 1.01 | +300 |

- **Recording:** one `end()` probe event per request is **not measurable**. The median moves +0.6%, well inside
  the run-to-run spread. A first, non-interleaved run even showed the probe "faster", which is noise. Min-to-min
  suggests at most ~8%. One extra event per request is +0.3% of the event volume.
- **Analysis** over the same 104 856 events (Python 3.15): load and index 0.39 s. Memoised attribution takes
  0.032 s via `tid` and 0.032 s via `eid`, so the creation model costs nothing extra. The released-by index over
  13 982 promise-reaction runs takes 0.018 s; 12 182 of them have a release edge.
- **Attribution and release edges add zero recording cost**: they use fields already in every recording, so
  recordings made before this change gain them retroactively.

## Decisions for Step 2 (if approved)
1. **Attribution = creation chain** (`init.eid`), falling back to `tid` where `eid` is 0 or has no init. The
   invariant (both models agree on every existing fixture) becomes a regression test. Where the models disagree,
   report both and present neither as the only truth.
2. **Released by = promise reactions only**, chained through internal reaction promises until the first
   non-promise context. Report it as DERIVED. "waited" requires `init(child) < resolve(parent)`.
3. Word it as **"settled"**, never "resolved" or "rejected", unless another recorded event (a caught error, an
   `error.logged`) shows the outcome.
4. Add one recorder event, **`http.end`** (first `end()` call: `eid` + user frames, recorder frames dropped).
   `pipe` and other internal ends report "Node internals" plus the creation chain.
5. Document S3f (synchronous emitter/listener hand-offs) as unobservable.

## After F15 (re-run against the updated recorder)
Decisions 1–5 are now implemented (`rewind/analysis.py`, `recorder/recorder.js` `http.end`, `tests/test_causal.py`).
`check.py` still gives 38 checks: 36 PASS, 1 AMBIGUOUS, 1 LIMIT. Three things were changed so it keeps measuring
the same thing:
- the S2 invariant uses an explicit list of the fixtures that existed before F15, because F15 added fixtures that
  cross requests on purpose;
- `probe_end.js` drops recorder.js frames, because the recorder's own `res.end` wrapper now calls the probe;
- the last S4 check now verifies that the production `http.end` matches the probe's context for every response,
  with no recorder frames, so the probe is redundant.

The story-event count in S2 rose from 197 to 260 because the count includes the new `http.end` events. Recorder
A/B on the E6 load (HEAD vs `http.end`, 9 interleaved runs): median 1.499 s vs 1.550 s (+3.4%), min 1.312 vs 1.348
(+2.7%). That is inside this machine's spread but not clearly zero.

## Remaining uncertainties
- **Only measured on Windows / Node 24.** Promise-hook behaviour (adoption timing, internal reaction promises)
  is V8/Node-version specific and was not checked on Node 20/22 or Linux/macOS.
- **Not covered:** `await` inside `for await`, async iterators and generators, `AbortSignal`-driven
  settlement, `worker_threads`, outgoing HTTP clients (`fetch`/undici internals), and libraries that use
  `AsyncResource` or `AsyncLocalStorage` themselves (database pools, for example).
- The "released by" rule picks the **last** resolve before the run. A promise can't settle twice, but multiple
  `async.resolve` events for one aid were not seen and were not tested for.
- **Fulfilled vs rejected** is not recorded (AMBIGUOUS). If Step 2 needs it, the outcome must come from
  another event or a recorder change, which would need its own overhead check.
- **Overhead noise on this machine is large** (the recorder alone ranged 0.98–1.85 s). The probe numbers
  rule out a large cost, not a few percent.
- The probe wraps `ServerResponse.prototype.end`. A production version inside the per-request wrapper is
  untested (same data expected).

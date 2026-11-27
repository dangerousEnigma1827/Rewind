# Development guide

Back to [HANDOVER.md](HANDOVER.md). Commands here are written from the source and README; they were **not executed** while writing this guide. The M7 fresh-clone run is what verifies them.

## Repository structure

```
rewind/                     repo root
├─ recorder/
│  ├─ recorder.js           Node recorder, preloaded with --require (zero deps)
│  ├─ instrument.js         --watch AST rewriter (acorn, acorn-walk, magic-string; lazy)
│  ├─ package.json          pins acorn 8.19.0, acorn-walk 8.3.5, magic-string 1.4.5
│  └─ package-lock.json
├─ rewind/                  Python package (installed editable)
│  ├─ __init__.py           RECORDER path
│  ├─ cli.py                Typer commands: record runs timeline tree why diff; landing/help hooks
│  ├─ store.py              REWIND_HOME, SQLite schema, ingest, resolve
│  ├─ analysis.py           Run indexes, tree, investigate (why), diff
│  └─ render.py             Rich theme and views
├─ demo/
│  ├─ checkout.js           Phantom Discount service (bug: module-level currentCart)
│  ├─ traffic.js            starts it, sends /health + 3 orders; --sequential
│  ├─ prices.json           SKU prices
│  └─ fix.patch             per-request cart fix (git apply)
├─ tests/
│  ├─ conftest.py           record / rewind_home fixtures
│  ├─ fixtures/*.js|.mjs    small Node programs with known causality
│  └─ test_{recorder,store,analysis,cli,render}.py
├─ spikes/                  M0 experiments + RESULTS.md (evidence, not shipped)
├─ docs/ARCHITECTURE.md     concise architecture
├─ docs/handover/           this handover set
├─ pyproject.toml           typer>=0.12, rich>=13, textual>=8.2 (the TUI); dev: pytest>=8; script `rewind`
├─ .gitignore               .venv/ .rewind/ __pycache__/ *.pyc spikes/out/ node_modules/ *.egg-info/
└─ README.md
```

`node_modules/` and `.rewind/` are gitignored, so a fresh clone needs `npm install --prefix recorder` before `--watch` works.

## Prerequisites

- Node.js ≥ 20 on PATH (developed on v24.22.1; tested on 24.22.1 and 24.22.2 only).
- Python ≥ 3.12 (`pyproject.toml`); suite run on 3.15.2 (Windows) and 3.12.3 (Ubuntu). 3.14.10 is installed on the dev machine as M0's fallback, but the suite has not been run on it.
- Git. npm (ships with Node). No C compiler needed (no native modules).

## Installation on Windows

PowerShell 5.1 (the default shell on the dev machine — note: no `&&`):

```powershell
git clone <repo-url> rewind
cd rewind
python -m venv .venv            # py -3.14 would also create one, but the suite is untested on 3.14
.venv\Scripts\Activate.ps1      # if blocked: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
pip install -e ".[dev]"
npm install --prefix recorder   # only needed for --watch
```

Git Bash equivalent:

```sh
python -m venv .venv && source .venv/Scripts/activate
pip install -e ".[dev]"
npm install --prefix recorder
```

Verified in M7: in PowerShell, `.venv/Scripts/activate` also works (resolves to `Activate.ps1`); only `&&` was broken, and the README now uses two lines.

## Installation on Linux (Ubuntu/Debian)

```sh
sudo apt install python3-venv     # Ubuntu's python3 ships without ensurepip
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
npm install --prefix recorder
```

The `apt` step itself was not run during verification (no sudo in the tool session). The tested route was `python3 -m venv --without-pip .venv`, then pip run from its wheel: `.venv/bin/python pip-<ver>-py3-none-any.whl/pip install pip`. See [ENGINEERING_LOG.md B17](ENGINEERING_LOG.md#b17-readme-install-on-ubuntu).

## Running Rewind

```powershell
rewind --help
rewind record --label myrun -- node path\to\app.js arg1
rewind record -w cart,cache -- node app.js     # track writes to top-level CJS vars
rewind runs
rewind timeline myrun -k log,http,error
rewind tree myrun -r 2
rewind why myrun --evidence
rewind diff good bad
```

`-N` run refs (`rewind why -1`, `rewind diff -2 -1`) work since M7; before that Click rejected them as unknown options.

Data goes to `$REWIND_HOME` (default `.\.rewind` in the current directory): `rewind.db` plus raw `runs\<id>.ndjson`. Delete the folder to start fresh.

## The Phantom Discount demo

`demo/traffic.js` starts `demo/checkout.js` on an ephemeral port, sends a `/health` warm-up, then three orders A-101, B-202, C-303 at 0/40/100 ms with payment delays 80/150/10 ms (≥40 ms margins chosen for a deterministic interleaving). `--sequential` (or `DEMO_SEQUENTIAL=1`) sends them one at a time. The bug: `currentCart` (checkout.js:6) is shared; each order's `loadCart` overwrites it (line 12) and `applyDiscount` reads it after the `paymentConfirmed` timer (line 18) at line 23.

Walkthrough, from the repo root (outputs verified in M7, 2026-11-23):

```powershell
node demo/traffic.js                                       # TypeError reading 'price' at checkout.js:23
rewind record -l bad -w currentCart -- node demo/traffic.js
rewind timeline bad                                        # 3 interleaved orders, 3 writes; "A-101: charged $161" (should be $128)
rewind why bad                                             # thrown in applyDiscount; request #3 (B-202); overwritten by #4
rewind why bad --seq <seq of the A-101 log line>           # silent overcharge: #2's read of #3's cart (with REWIND_READS=0: not proven)
rewind record -l nowatch -- node demo/traffic.js
rewind why nowatch                                         # suspects shared state, recommends --watch
rewind record -l good -w currentCart -- node demo/traffic.js --sequential
rewind diff good bad                                       # identical up to #2's write, then interleaving differs (-w needed on both runs)
git apply demo/fix.patch                                   # ONLY in a scratch clone
rewind record -l fixed -- node demo/traffic.js
rewind why fixed                                           # no errors
git apply -R demo/fix.patch                                # undo
```

Request numbering: #1 is the `/health` check, so orders are #2–#4.

## Running tests

```powershell
pytest                   # full suite; spawns real node processes
pytest --collect-only -q # count items
pytest tests/test_recorder.py -k keepalive
pytest tests/test_tui.py # the interactive app, headless (Textual pilot); records the demo once per module
rewind ui                # the app itself; needs a real terminal (bare `rewind` too, when stdin/stdout are a TTY)
```

Run from the repo root with the venv active and `node` on PATH. Tests set their own `REWIND_HOME` in temp dirs. `--watch` tests need `recorder/node_modules`.

M0 spikes (evidence only): `.venv\Scripts\python spikes\check.py`, `spikes\e5_sqlite.py`, `spikes\e6_bench.py` (spikes have their own `spikes/package.json`).

## Environment variables

| var | set by | default | meaning |
|---|---|---|---|
| `REWIND_HOME` | user | `./.rewind` | database and raw recordings |
| `REWIND_PROMISE_STACKS` | user | `1` | `0` skips promise creation stacks (~1.9× → 1.1× overhead; loses async fn names) |
| `REWIND_MUT_CAP` | user | `10000` | recorded writes per watched variable |
| `NO_COLOR` | user | unset | any value turns colour off; layout and ● ◆ ? stay (piped output never has colour) |
| `REWIND_OUT` | `rewind record` | — | NDJSON output path; recorder is inert without it |
| `REWIND_RUN_ID` | `rewind record` | — | run id written into `run.start` |
| `REWIND_WATCH` | `rewind record -w` | — | comma list of watched names |
| `DEMO_SEQUENTIAL` | user | — | `1` = same as `traffic.js --sequential` |

## Conventions

- One commit per completed milestone, tests green first; no `Co-Authored-By` trailer.
- Analysis findings must carry an evidence level and cite seqs; never claim an unrecorded write.
- Storage does not intentionally discard ingested events; views filter them. An abrupt termination such as SIGKILL can still lose up to the last 256 buffered non-error events; error events are written immediately.

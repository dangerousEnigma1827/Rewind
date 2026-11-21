"""`rewind` command line."""
from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

import typer

from . import RECORDER, analysis, render, store
from .render import console

app = typer.Typer(add_completion=False, no_args_is_help=True, rich_markup_mode="rich",
                  help="Causal time-travel debugging for Node.js. Record a run, then ask why.")


def _db():
    return store.connect()


def _run(db, ref):
    try:
        return store.resolve(db, ref)
    except store.RunNotFound as e:
        render.fail(str(e)); raise typer.Exit(2)


@app.command(context_settings={"allow_extra_args": True, "ignore_unknown_options": True})
def record(ctx: typer.Context,
           label: Optional[str] = typer.Option(None, "--label", "-l", help="Name this run (e.g. good, bad)."),
           watch: Optional[str] = typer.Option(None, "--watch", "-w", help="Comma-separated top-level CJS variables to track writes to.")):
    """Record a Node.js program: [bold]rewind record \\[--label bad] \\[--watch cart] -- node app.js[/]"""
    cmd = list(ctx.args)
    if not cmd:
        render.fail("nothing to record — usage: rewind record -- node app.js"); raise typer.Exit(2)
    if not os.path.basename(cmd[0]).lower().removesuffix(".exe") == "node":
        cmd = ["node"] + cmd  # `rewind record app.js` shorthand
    node = shutil.which(cmd[0]) or cmd[0]
    run_id = secrets.token_hex(4)
    raw = store.home() / "runs" / f"{run_id}.ndjson"
    env = {**os.environ, "REWIND_OUT": str(raw), "REWIND_RUN_ID": run_id}
    if watch:
        env["REWIND_WATCH"] = watch
    render.header(f"recording [id]{run_id}[/]  [dim]{' '.join(cmd)}[/]" + (f"  [dim]watch=[/][accent]{watch}[/]" if watch else ""))
    started, t = datetime.now().isoformat(timespec="seconds"), time.perf_counter()
    try:
        p = subprocess.Popen([node, "--require", str(RECORDER), *cmd[1:]], env=env)
    except FileNotFoundError:
        render.fail(f"cannot run {cmd[0]!r} — is Node.js on PATH?"); raise typer.Exit(127)
    try:
        code = p.wait()
    except KeyboardInterrupt:  # child got the same Ctrl+C; let it flush and exit
        code = p.wait()
    secs = time.perf_counter() - t
    if not raw.exists():
        render.fail("recorder produced no output (did node start?)"); raise typer.Exit(code or 1)
    row = store.ingest(_db(), run_id, raw, label=label, cmd=cmd, started_at=started,
                       ended_at=datetime.now().isoformat(timespec="seconds"), exit_code=code)
    render.run_summary(row, secs)
    raise typer.Exit(code)


@app.command()
def runs():
    """List recorded runs, newest first."""
    rows = store.runs(_db())
    if not rows:
        console.print("[dim]no runs yet — try[/] rewind record -- node app.js"); return
    render.runs_table(rows)


def _load(ref):
    db = _db()
    row = _run(db, ref)
    return row, analysis.Run(store.events(db, row["id"]), dict(row))


def _title(row) -> str:
    return f"run {row['id']}" + (f" ({row['label']})" if row["label"] else "")


def _ctx_aid(e):
    return e.aid if e.kind.startswith("async.") else e.eid


@app.command()
def timeline(run: Optional[str] = typer.Argument(None, help="Run id prefix, label, 'last' or -N."),
             request: Optional[int] = typer.Option(None, "--request", "-r", help="Only events of request #N."),
             kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Comma list: log,http,error,mutation,async,run."),
             callbacks: bool = typer.Option(False, "--callbacks", "-c", help="Also show each user callback firing."),
             raw: bool = typer.Option(False, "--raw", help="Every recorded event, unfiltered.")):
    """Ordered story of a run: requests, logs, errors, mutations (and optionally callback firings)."""
    row, r = _load(run)
    rows = r.events if raw else sorted(r.story + (r.callback_fires() if callbacks else []), key=lambda e: e.seq)
    if kind:
        ks = [k.strip() for k in kind.split(",")]
        rows = [e for e in rows if e.kind in ks or e.kind.split(".")[0] in ks]
    if request is not None:
        if request not in r.requests:
            have = ", ".join(f"#{i}" for i in r.requests) or "none"
            render.fail(f"run has no request #{request} (has {have})"); raise typer.Exit(2)
        rows = [e for e in rows if r.request_of(_ctx_aid(e)) == request]
    render.header(f"timeline · {_title(row)} · {render.plural(len(rows), 'event')} shown of {row['event_count']:,} recorded")
    render.timeline(r, rows)


@app.command()
def tree(run: Optional[str] = typer.Argument(None, help="Run id prefix, label, 'last' or -N."),
         request: Optional[int] = typer.Option(None, "--request", "-r", help="Root the tree at request #N."),
         full: bool = typer.Option(False, "--full", help="Show every async resource, including quiet and internal ones.")):
    """Async causality tree: who scheduled whom, and what each callback did."""
    row, r = _load(run)
    root = 1
    if request is not None:
        if request not in r.requests:
            render.fail(f"run has no request #{request}"); raise typer.Exit(2)
        root = r.requests[request].anchor
    node, pruned = analysis.build_tree(r, root, full)
    render.header(f"async tree · {_title(row)}")
    render.tree(r, node, pruned, "main module" if root == 1 else r.requests[request].label)


@app.command()
def why(run: Optional[str] = typer.Argument(None, help="Run id prefix, label, 'last' or -N."),
        error: int = typer.Option(1, "--error", "-e", help="Which error to explain (1 = first)."),
        seq: Optional[int] = typer.Option(None, "--seq", "-s", help="Explain any event by its seq instead of an error."),
        evidence: bool = typer.Option(False, "--evidence", help="Show the event seqs backing every finding.")):
    """Explain an error (or any event): where it ran, what caused it, and what else touched its state."""
    row, r = _load(run)
    if seq is not None:
        if seq not in r.by_seq:
            render.fail(f"run has no event with seq {seq}"); raise typer.Exit(2)
        target, position = r.by_seq[seq], f"event seq {seq}"
    else:
        if not r.errors:
            render.header(f"why · {_title(row)}")
            console.print("  [ok]no errors recorded.[/] [dim]Explain any event with[/] rewind why --seq N")
            return
        if not 1 <= error <= len(r.errors):
            render.fail(f"run has {render.plural(len(r.errors), 'error')}"); raise typer.Exit(2)
        target, position = r.errors[error - 1], f"error {error} of {len(r.errors)}"
    render.why(r, analysis.investigate(r, target), _title(row), evidence, position)
    if not r.watch and seq is None:
        console.print()
        console.print("  [faint]tip: record with --watch <variable> to capture writes to shared state[/]")


@app.command()
def diff(a: str = typer.Argument(..., help="Baseline run (e.g. good)."),
         b: str = typer.Argument(..., help="Run to compare (e.g. bad)."),
         all_: bool = typer.Option(False, "--all", help="Include callbacks outside any request (harness, plumbing)."),
         evidence: bool = typer.Option(False, "--evidence", help="Show the event seqs backing every finding.")):
    """Compare two runs: where did their executions part ways?"""
    ra, A_ = _load(a)
    rb, B_ = _load(b)
    render.diff(analysis.diff(A_, B_, all_), _title(ra), _title(rb), evidence)


def main():
    try:
        app()
    except (BrokenPipeError, OSError) as e:  # reader closed the pipe (e.g. `| head`); Windows reports EINVAL
        if isinstance(e, BrokenPipeError) or e.errno == 22:
            try:
                sys.stdout = open(os.devnull, "w")
            except OSError:
                pass
            raise SystemExit(0)
        raise


if __name__ == "__main__":
    main()

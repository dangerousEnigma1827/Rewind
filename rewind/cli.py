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

from . import RECORDER, render, store
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


def main():
    app()


if __name__ == "__main__":
    main()

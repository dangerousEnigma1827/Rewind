"""Starting a recorded run and storing it: shared by `rewind record` and the TUI's recording screen.

The recorder itself is recorder/recorder.js, preloaded with `node --require`; this module only prepares the
command and environment for it and ingests what it wrote.
"""
from __future__ import annotations

import os
import re
import secrets
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import RECORDER, store

SCRIPT_EXT = (".js", ".mjs", ".cjs")


@dataclass
class Recording:
    cmd: list[str]       # the program, as the user would run it (`node` added for the `app.js` shorthand)
    args: list[str]      # what is executed: node --require <recorder> <rest of cmd>
    env: dict            # the caller's environment plus REWIND_OUT / REWIND_RUN_ID / REWIND_WATCH
    run_id: str
    raw: Path            # the NDJSON file the recorder writes
    label: str | None
    watch: str | None
    home: Path | None


class NoOutput(RuntimeError):
    """The recorder wrote nothing: node never started the program."""


def prepare(cmd: list[str], label: str | None = None, watch: str | None = None, home: Path | None = None) -> Recording:
    cmd = list(cmd)
    if not os.path.basename(cmd[0]).lower().removesuffix(".exe") == "node":
        cmd = ["node"] + cmd  # `rewind record app.js` shorthand
    node = shutil.which(cmd[0]) or cmd[0]
    run_id = secrets.token_hex(4)
    raw = store.home(home) / "runs" / f"{run_id}.ndjson"
    env = {**os.environ, "REWIND_OUT": str(raw), "REWIND_RUN_ID": run_id}
    if watch:
        env["REWIND_WATCH"] = watch
    return Recording(cmd, [node, "--require", str(RECORDER), *cmd[1:]], env, run_id, raw, label, watch, home)


def store_run(rec: Recording, exit_code: int | None, started: str, ended: str) -> dict:
    """Ingest the recorder's output into the run database. Raises NoOutput if there is none."""
    if not rec.raw.exists():
        raise NoOutput("recorder produced no output (did node start?)")
    db = store.connect(rec.home)
    try:
        return store.ingest(db, rec.run_id, rec.raw, label=rec.label, cmd=rec.cmd, started_at=started, ended_at=ended,
                            exit_code=exit_code)
    finally:
        db.close()


# ---- for interactive use: parse what was typed, and catch mistakes before starting anything ----------------------
def split_command(text: str) -> list[str]:
    """A typed command line -> argv. Windows paths keep their backslashes; quotes group words on every platform."""
    if os.name != "nt":
        return shlex.split(text)
    parts = shlex.split(text, posix=False)
    return [p[1:-1] if len(p) >= 2 and p[0] == p[-1] and p[0] in "\"'" else p for p in parts]


def cli_preview(cmd: list[str], label: str | None, watch: str | None) -> str:
    """The equivalent `rewind record` command, so what the app does can be repeated in a shell."""
    q = (lambda s: s if s and not re.search(r"[\s\"'&|<>^]", s) else '"' + s.replace('"', '\\"') + '"')
    opts = (f" -l {q(label)}" if label else "") + (f" -w {q(watch)}" if watch else "")
    return f"rewind record{opts} -- {' '.join(q(c) for c in cmd)}"


def problems(cmd: list[str], watch: str | None, cwd: Path) -> list[str]:
    """Reasons this command can't be recorded, in plain words. Empty when it looks runnable."""
    if not cmd:
        return ["enter the command you use to start your program, e.g. node app.js"]
    out = []
    first = os.path.basename(cmd[0]).lower().removesuffix(".exe")
    if first in ("npm", "npx", "yarn", "pnpm", "bun", "deno", "ts-node", "tsx", "nodemon"):
        out.append(f"Rewind records Node.js directly: start the app with `node <script>` instead of `{cmd[0]}` "
                   f"(the script your {cmd[0]} command runs, e.g. node server.js)")
        return out
    node_cmd = cmd if first == "node" else ["node"] + cmd
    if not shutil.which(node_cmd[0]):
        out.append("Node.js isn't on PATH: install Node.js 20+ or add it to PATH, then try again")
    script = next((a for a in node_cmd[1:] if not a.startswith("-")), None)
    if script is None:
        out.append("add the script to run after node, e.g. node app.js")
    else:
        # node resolves its entry point like a relative require: the name, + .js/.mjs/.cjs, or a folder's index.js
        path = Path(script) if Path(script).is_absolute() else cwd / script
        candidates = [path, *(path.with_name(path.name + e) for e in SCRIPT_EXT), path / "index.js", path / "package.json"]
        if not any(c.is_file() for c in candidates):
            out.append(f"script not found: {script} (looked in {cwd})")
    if watch:
        bad = [w for w in (x.strip() for x in watch.split(",")) if w and not re.fullmatch(r"[A-Za-z_$][\w$]*", w)]
        if bad:
            out.append(f"watched variables must be JavaScript names: {', '.join(bad)}")
        if not (RECORDER.parent / "node_modules" / "acorn").exists():
            out.append("watching variables needs the recorder's packages: run `npm install --prefix recorder` "
                       "in the Rewind folder once")
    return out

"""Terminal presentation. pacman/makepkg-flavoured: `::` section headers, `==>` steps, quiet greys, one accent."""
from __future__ import annotations

import json
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.theme import Theme

THEME = Theme({
    "hdr": "bold blue", "step": "bold green", "accent": "bold cyan", "dim": "grey50", "faint": "grey35",
    "ok": "green", "err": "bold red", "warn": "yellow", "id": "magenta", "loc": "cyan", "fn": "bold",
    "kind.log": "white", "kind.http": "blue", "kind.error": "bold red", "kind.mutation": "bold yellow",
    "kind.async": "grey50", "kind.run": "bold blue",
})
console = Console(theme=THEME, highlight=False)
STATUS = {"ok": "[ok]ok[/]", "failed": "[err]failed[/]", "crashed": "[warn]crashed[/]"}


def header(text: str):
    console.print(f"[hdr]::[/] [bold]{text}[/]")


def step(text: str):
    console.print(f"[step]==>[/] {text}")


def fail(text: str):
    console.print(f"[err]error:[/] {text}")


def plural(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def ago(iso: str | None) -> str:
    if not iso:
        return "?"
    s = (datetime.now() - datetime.fromisoformat(iso)).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= size:
            return f"{int(s // size)}{unit} ago"
    return f"{int(s)}s ago"


def run_summary(row: dict, secs: float):
    errs = row["error_count"]
    err = f"[err]{plural(errs, 'error')}[/]" if errs else "[ok]no errors[/]"
    label = f" [accent]{row['label']}[/]" if row.get("label") else ""
    console.print(f"[step]==>[/] recorded run [id]{row['id']}[/]{label}  {plural(row['event_count'], 'event')}  {err}  "
                  f"exit {row['exit_code']}  {STATUS[row['status']]}  [dim]({secs:.1f}s)[/]")
    if row.get("skipped_lines"):
        console.print(f"[warn]warning:[/] {row['skipped_lines']} torn line(s) skipped — process was killed mid-write")


def runs_table(rows):
    t = Table(box=None, expand=True, header_style="dim", pad_edge=False, padding=(0, 2))
    for c in ("run", "label", "status", "events", "errors", "exit", "when", "command"):
        t.add_column(c, justify="right" if c in ("events", "errors", "exit") else "left",
                     no_wrap=c != "command", overflow="ellipsis", ratio=1 if c == "command" else None)
    for r in rows:
        cmd = " ".join(json.loads(r["cmd"]) or []) if r["cmd"] else ""
        t.add_row(f"[id]{r['id']}[/]", r["label"] or "[faint]-[/]", STATUS.get(r["status"], r["status"]),
                  f"{r['event_count']:,}", f"[err]{r['error_count']}[/]" if r["error_count"] else "[faint]0[/]",
                  str(r["exit_code"]), f"[dim]{ago(r['started_at'])}[/]", f"[dim]{cmd}[/]")
    console.print(t)

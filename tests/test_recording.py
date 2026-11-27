"""rewind.recording: shared by `rewind record` and the TUI's recording screen."""
import os
from pathlib import Path

from conftest import ROOT
from rewind import recording as R


def test_split_command_keeps_paths_and_quoted_words():
    assert R.split_command('node demo/traffic.js --sequential') == ["node", "demo/traffic.js", "--sequential"]
    assert R.split_command('node "my app/server.js" --name "a b"') == ["node", "my app/server.js", "--name", "a b"]
    if os.name == "nt":
        assert R.split_command(r"node C:\apps\server.js") == ["node", r"C:\apps\server.js"]


def test_prepare_adds_node_and_the_recorder(tmp_path):
    rec = R.prepare(["app.js", "--port", "1"], label="x", watch="cart", home=tmp_path)
    assert rec.cmd == ["node", "app.js", "--port", "1"]
    assert rec.args[1:3] == ["--require", str(R.RECORDER)] and rec.args[3:] == ["app.js", "--port", "1"]
    assert rec.env["REWIND_WATCH"] == "cart" and rec.env["REWIND_OUT"] == str(rec.raw)
    assert rec.raw.parent == tmp_path / "runs"
    assert "REWIND_OUT" not in os.environ  # the caller's environment is copied, never changed


def test_cli_preview_is_a_runnable_command():
    assert R.cli_preview(["node", "demo/traffic.js"], "bad", "currentCart") == \
        "rewind record -l bad -w currentCart -- node demo/traffic.js"
    assert R.cli_preview(["node", "my app.js"], None, None) == 'rewind record -- node "my app.js"'


def test_problems_explain_what_to_fix():
    assert R.problems(["node", "demo/traffic.js"], None, ROOT) == []
    assert R.problems(["demo/traffic.js"], "currentCart", ROOT) == []  # shorthand, watch deps installed
    assert "enter the command" in R.problems([], None, ROOT)[0]
    assert "not found" in R.problems(["node", "nope/missing.js"], None, ROOT)[0]
    assert "instead of `npm`" in R.problems(["npm", "start"], None, ROOT)[0]
    assert "add the script" in R.problems(["node"], None, ROOT)[0]
    assert "JavaScript names" in R.problems(["node", "demo/traffic.js"], "cart, 9x", ROOT)[0]


def test_store_run_without_output_raises(tmp_path):
    rec = R.prepare(["node", "x.js"], home=tmp_path)
    try:
        R.store_run(rec, 1, "s", "e")
    except R.NoOutput as e:
        assert "no output" in str(e)
    else:
        raise AssertionError("expected NoOutput")

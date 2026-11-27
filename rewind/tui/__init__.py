"""Interactive terminal UI (Textual). Imported only when the TUI is launched, so CLI commands start as fast as before."""


def run(home=None):
    from .app import run_app
    run_app(home)

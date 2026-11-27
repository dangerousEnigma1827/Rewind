"""The TUI's look: a dark-first palette, the named styles render.py's markup uses, and the Textual CSS.

The CLI's palette is mid-tone so one set of colours reads on dark and light terminals; a full-screen app owns its
background, so here every colour is tuned for one deep charcoal canvas. Names match render.THEME, so the CLI's
markup helpers (event_text, tree_label, LEVEL, ...) render unchanged in the TUI.
"""
from rich.style import Style

C = {
    "bg": "#0E1013", "surface": "#14171B", "raised": "#1A1E24", "border": "#272C34", "border.hi": "#3A414C",
    "text": "#D5D9E0", "mute": "#808894", "dim": "#59606B",
    "green": "#3DD68C", "green.dim": "#143325", "green.deep": "#0F2A1E",
    "violet": "#A78BFA", "amber": "#E0AF4F", "teal": "#4FD1D9", "blue": "#7AB8FF", "red": "#FF6B6B",
    "r1": "#4FD1D9", "r2": "#F2A65A", "r3": "#C3A6FF", "r4": "#8FDB8C",
}

STYLES = {name: Style.parse(spec) for name, spec in {
    "uv": C["violet"], "uv.b": f"bold {C['violet']}", "uv.hi": C["violet"], "uv.lo": C["violet"],
    "id": C["green"], "mute": C["mute"], "hyp": f"italic {C['mute']}", "obs": f"bold {C['text']}",
    "fn": f"bold {C['text']}", "label": f"bold {C['text']}", "loc": C["blue"],
    "err": f"bold {C['red']}", "err.t": C["red"], "ok": C["green"], "write": C["amber"],
    "r1": C["r1"], "r2": C["r2"], "r3": C["r3"], "r4": C["r4"],
    "kind.log": C["text"], "kind.http": C["blue"], "kind.error": f"bold {C['red']}", "kind.mutation": C["amber"],
    "kind.async": C["mute"], "kind.run": C["green"], "kind.read": C["teal"], "none": "",
    "dim": C["dim"], "green": C["green"], "title": f"bold {C['text']}",
}.items()}

CSS = f"""
Screen {{ background: {C['bg']}; color: {C['text']}; }}

#topbar {{ height: 1; background: {C['surface']}; color: {C['text']}; padding: 0 1; }}
#body {{ height: 1fr; }}
#sidebar {{ width: 36; }}
#main {{ width: 1fr; }}

.panel {{
    background: {C['bg']}; border: round {C['border']}; padding: 0 1;
    border-title-color: {C['mute']}; border-title-style: bold; border-subtitle-color: {C['dim']};
}}
.panel:focus-within {{ border: round {C['green']}; border-title-color: {C['green']}; }}
#runs-panel {{ height: auto; max-height: 50%; }}
#requests-panel {{ height: 1fr; }}
#details-panel {{ width: 50; }}

OptionList {{ background: {C['bg']}; border: none; padding: 0; scrollbar-size-vertical: 1; }}
OptionList > .option-list--option {{ padding: 0 1; }}
OptionList > .option-list--option-highlighted {{ background: {C['raised']}; }}
OptionList:focus > .option-list--option-highlighted {{ background: {C['green.deep']}; }}
OptionList > .option-list--option-hover {{ background: {C['surface']}; }}
OptionList > .option-list--separator {{ color: {C['border']}; }}

DataTable {{ background: {C['bg']}; border: none; scrollbar-size-vertical: 1; scrollbar-size-horizontal: 0; }}
DataTable > .datatable--header {{ background: {C['bg']}; color: {C['dim']}; text-style: bold; }}
DataTable > .datatable--cursor {{ background: {C['raised']}; }}
DataTable:focus > .datatable--cursor {{ background: {C['green.deep']}; }}
DataTable > .datatable--hover {{ background: {C['surface']}; }}

TabbedContent {{ height: 1fr; }}
TabbedContent ContentSwitcher {{ height: 1fr; }}
TabPane {{ padding: 0; height: 1fr; }}
Tabs {{ background: {C['bg']}; height: 2; }}
Tab {{ color: {C['mute']}; padding: 0 1; }}
Tab.-active {{ color: {C['green']}; text-style: bold; }}
Tab:hover {{ color: {C['text']}; }}
Underline > .underline--bar {{ background: {C['border']}; color: {C['green']}; }}

Tree {{ background: {C['bg']}; scrollbar-size-vertical: 1; }}
Tree > .tree--cursor {{ background: {C['raised']}; }}
Tree:focus > .tree--cursor {{ background: {C['green.deep']}; }}
Tree > .tree--guides {{ color: {C['border.hi']}; }}
Tree > .tree--guides-selected {{ color: {C['green']}; }}

VerticalScroll {{ scrollbar-size-vertical: 1; }}
#search {{ display: none; height: 3; border: round {C['border.hi']}; background: {C['bg']}; margin: 0 0 0 0; }}
#search.-shown {{ display: block; }}
#search:focus {{ border: round {C['green']}; }}
#filterbar {{ height: 1; color: {C['mute']}; padding: 0 1; }}
#why-head, #diff-head {{ height: auto; padding: 0 1 1 1; border-bottom: solid {C['border']}; margin-bottom: 1; }}

.empty {{ color: {C['mute']}; padding: 1 2; }}
#welcome {{ align: center middle; height: 1fr; }}
#welcome-card {{ width: 90; max-width: 96%; height: auto; border: round {C['border.hi']}; padding: 1 3; background: {C['surface']}; }}

Footer {{ background: {C['surface']}; }}
Footer > FooterKey {{ background: {C['surface']}; color: {C['mute']}; }}
Footer > FooterKey .footer-key--key {{ background: {C['surface']}; color: {C['green']}; text-style: bold; }}
Footer > FooterKey .footer-key--description {{ color: {C['mute']}; }}

HelpScreen {{ align: center middle; background: {C['bg']} 70%; }}
#help-card {{ width: 108; max-width: 96%; height: auto; max-height: 94%; border: round {C['green']}; background: {C['surface']}; padding: 1 2; }}

/* responsive: medium widths narrow the side panels, narrow ones stack details under the main view */
Screen.-medium #sidebar {{ width: 32; }}
Screen.-medium #details-panel {{ width: 42; }}
Screen.-compact #sidebar {{ width: 30; }}
Screen.-compact #details-panel {{ display: none; width: 40; }}
Screen.-compact.-show-details #details-panel {{ display: block; }}
Screen.-compact.-show-details #sidebar {{ display: none; }}
Screen.-narrow #body {{ layout: vertical; }}
Screen.-narrow #sidebar {{ width: 1fr; height: 10; layout: horizontal; }}
Screen.-narrow #runs-panel {{ height: 1fr; max-height: 100%; width: 1fr; }}
Screen.-narrow #requests-panel {{ height: 1fr; width: 1fr; }}
Screen.-narrow #details-panel {{ display: none; width: 1fr; height: 14; }}
Screen.-narrow.-show-details #details-panel {{ display: block; }}
Screen.-narrow.-short #sidebar {{ height: 7; }}
Screen.-narrow.-short #details-panel {{ height: 9; }}
Screen.-hide-details #details-panel {{ display: none; }}
Screen.-hide-sidebar #sidebar {{ display: none; }}
"""

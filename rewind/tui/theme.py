"""Ultraviolet for the TUI: the palette, the named styles render.py's markup uses, a Textual theme and the CSS.

Sources: render.PALETTE (the CLI) and the website's tokens (rewind-cli: src/styles/tokens.css), which share it.
- Violet is the identity: the brand mark, ids, focus, selection, active tabs. #7F5AF0 fills, #8D6CFF for text.
- The foundation is near-black and violet-tinted. Panels step up from it in small, dark increments, never grey.
- Green, red and amber mean only ok, error and warning/unresolved. They use the website's "ink" variants, which
  reach at least 4.5:1 contrast on every surface here (tests/test_tui.py checks the contrast).
- Request tones r1-r4 and the evidence marks match the CLI, so a finding reads the same in both.
"""
from rich.style import Style
from textual.theme import Theme

C = {
    # foundation (strictly dark)
    "bg": "#08060D", "panel": "#0E0B15", "raised": "#15111E", "term": "#060409",
    "line": "#241F2E", "line.hi": "#3A3448",
    # violet: the identity
    "uv": "#7F5AF0", "uv.hi": "#8D6CFF", "uv.lo": "#6A48D8",
    "sel": "#22183F",       # violet at 22% on the background: the focused selection (as on the website)
    "sel.dim": "#150F25",   # the same selection when its panel isn't focused
    "sel.hi": "#32235C",    # violet at 35%: a focused primary button
    # text
    "text": "#EDEDF0", "text2": "#B4B4BD", "text3": "#8A8A96", "mute": "#81818F", "dim": "#5F5B6C",
    # semantics only (website ink values)
    "ok": "#25925D", "err": "#E5484D", "warn": "#AB7723",
    # request tones and reads (website ink values)
    "r1": "#2E8E9B", "r2": "#C95E81", "r3": "#7D8A2E", "r4": "#5B81C2",
}

STYLES = {name: Style.parse(spec) for name, spec in {
    "uv": C["uv.hi"], "uv.b": f"bold {C['uv.hi']}", "uv.hi": C["uv.hi"], "uv.lo": C["uv.lo"], "id": C["uv.hi"],
    "mute": C["mute"], "dim": C["dim"], "hyp": f"italic {C['text3']}", "obs": f"bold {C['text']}",
    "fn": f"bold {C['text']}", "label": f"bold {C['text']}", "title": f"bold {C['text']}", "loc": C["text2"],
    "err": f"bold {C['err']}", "err.t": C["err"], "ok": C["ok"], "write": C["warn"], "warn": C["warn"],
    "r1": C["r1"], "r2": C["r2"], "r3": C["r3"], "r4": C["r4"],
    "kind.log": C["text"], "kind.http": C["text2"], "kind.error": f"bold {C['err']}", "kind.mutation": C["warn"],
    "kind.async": C["mute"], "kind.run": C["uv.hi"], "kind.read": C["r1"], "none": "",
    "text": C["text"], "text2": C["text2"], "text3": C["text3"], "eyebrow": f"bold {C['text3']}", "key": f"bold {C['uv.hi']}",
    "green": C["ok"],
}.items()}

THEME = Theme(
    name="ultraviolet", dark=True,
    primary=C["uv"], secondary=C["uv.hi"], accent=C["uv.hi"],
    foreground=C["text"], background=C["bg"], surface=C["panel"], panel=C["raised"], boost=C["raised"],
    success=C["ok"], warning=C["warn"], error=C["err"],
    variables={"border": C["uv"], "border-blurred": C["line"], "scrollbar": C["line.hi"],
               "scrollbar-background": C["bg"], "scrollbar-hover": C["uv.lo"], "scrollbar-active": C["uv"],
               "scrollbar-corner-color": C["bg"], "footer-background": C["panel"], "footer-key-foreground": C["uv.hi"],
               "footer-description-foreground": C["text3"], "input-selection-background": C["sel"],
               "block-cursor-background": C["sel"], "block-cursor-foreground": C["text"],
               "block-cursor-blurred-background": C["sel.dim"]},
)

# every background in the CSS below; tests assert each one is dark
BACKGROUNDS = [C[k] for k in ("bg", "panel", "raised", "term", "sel", "sel.dim", "sel.hi")]

CSS = f"""
Screen {{ background: {C['bg']}; color: {C['text']}; }}
ModalScreen {{ background: {C['bg']} 85%; }}
* {{ scrollbar-size-vertical: 1; scrollbar-color: {C['line.hi']}; scrollbar-background: {C['bg']};
     scrollbar-color-hover: {C['uv.lo']}; scrollbar-color-active: {C['uv']}; }}

/* chrome */
.topbar {{ height: 1; background: {C['panel']}; color: {C['text2']}; padding: 0 1; }}
Footer {{ background: {C['panel']}; }}
Footer > FooterKey {{ background: {C['panel']}; color: {C['text3']}; }}
Footer > FooterKey .footer-key--key {{ background: {C['panel']}; color: {C['uv.hi']}; text-style: bold; }}
Footer > FooterKey .footer-key--description {{ color: {C['text3']}; }}

/* panels: dark, hairline borders, violet when focused */
.panel {{
    background: {C['bg']}; border: round {C['line']}; padding: 0 1;
    border-title-color: {C['text3']}; border-title-style: bold; border-subtitle-color: {C['dim']};
}}
.panel:focus-within {{ border: round {C['uv']}; border-title-color: {C['uv.hi']}; }}
.intro {{ height: auto; color: {C['text3']}; padding: 0 1 1 1; }}
.legend {{ height: auto; color: {C['dim']}; padding: 0 1; dock: bottom; }}

/* lists and tables */
OptionList {{ background: {C['bg']}; border: none; padding: 0; }}
OptionList > .option-list--option {{ padding: 0 1; }}
OptionList > .option-list--option-highlighted {{ background: {C['sel.dim']}; text-style: none; }}
OptionList:focus > .option-list--option-highlighted {{ background: {C['sel']}; }}
OptionList > .option-list--option-hover {{ background: {C['panel']}; }}
OptionList > .option-list--option-disabled {{ color: {C['text']}; background: {C['bg']}; }}
OptionList > .option-list--separator {{ color: {C['line']}; }}
DataTable {{ background: {C['bg']}; border: none; scrollbar-size-horizontal: 0; }}
DataTable > .datatable--header {{ background: {C['bg']}; color: {C['text3']}; text-style: bold; }}
DataTable > .datatable--cursor {{ background: {C['sel.dim']}; text-style: none; }}
DataTable:focus > .datatable--cursor {{ background: {C['sel']}; }}
DataTable > .datatable--hover {{ background: {C['panel']}; }}
Tree {{ background: {C['bg']}; }}
Tree > .tree--cursor {{ background: {C['sel.dim']}; text-style: none; }}
Tree:focus > .tree--cursor {{ background: {C['sel']}; }}
Tree > .tree--guides {{ color: {C['line.hi']}; }}
Tree > .tree--guides-selected {{ color: {C['uv']}; }}
Tree > .tree--guides-hover {{ color: {C['uv.lo']}; }}

/* tabs: quiet until active; the active one is violet with a violet underline */
TabbedContent {{ height: 1fr; }}
TabbedContent ContentSwitcher {{ height: 1fr; }}
TabPane {{ padding: 0; height: 1fr; }}
Tabs {{ background: {C['bg']}; height: 2; }}
Tab {{ color: {C['text3']}; padding: 0 1; }}
Tab.-active {{ color: {C['uv.hi']}; text-style: bold; }}
Tab:hover {{ color: {C['text']}; }}
Underline > .underline--bar {{ background: {C['line']}; color: {C['uv']}; }}

/* forms */
Input {{ background: {C['panel']}; color: {C['text']}; border: round {C['line.hi']}; padding: 0 1; height: 3; }}
Input:focus {{ border: round {C['uv']}; }}
Input > .input--placeholder {{ color: {C['dim']}; }}
Input > .input--cursor {{ background: {C['uv.hi']}; color: {C['bg']}; }}
Button {{ background: {C['panel']}; color: {C['text']}; border: round {C['line.hi']}; height: 3; min-width: 10;
          text-style: none; padding: 0 2; }}
Button:hover {{ background: {C['sel.dim']}; border: round {C['uv.lo']}; }}
Button:focus {{ border: round {C['uv.hi']}; text-style: bold; background: {C['sel']}; }}
Button.-primary {{ background: {C['sel']}; border: round {C['uv']}; color: {C['text']}; text-style: bold; }}
Button.-primary:focus {{ background: {C['sel.hi']}; border: round {C['uv.hi']}; }}
Button.-error {{ background: {C['raised']}; border: round {C['err']}; color: {C['err']}; }}
RichLog {{ background: {C['term']}; border: round {C['line']}; padding: 0 1; }}
Toast {{ background: {C['raised']}; color: {C['text']}; border-left: outer {C['uv']}; }}
Toast.-error {{ border-left: outer {C['err']}; }}
Toast.-warning {{ border-left: outer {C['warn']}; }}

/* home */
#home {{ align: center top; padding: 1 2; }}
#home-col {{ width: 96; max-width: 100%; height: auto; }}
#wordmark {{ height: auto; margin: 1 0 1 0; }}
#tagline {{ height: auto; color: {C['text2']}; }}
.card {{ background: {C['panel']}; border: round {C['line']}; padding: 1 2; height: auto; margin: 1 0 0 0;
         border-title-color: {C['text3']}; border-title-style: bold; }}
.card:focus-within {{ border: round {C['uv']}; border-title-color: {C['uv.hi']}; }}
.action {{ height: auto; margin: 0; background: {C['panel']}; }}
.action Button {{ width: 26; }}
.action .desc {{ width: 1fr; padding: 0 0 0 2; color: {C['text2']}; height: auto; }}
#recent {{ height: auto; max-height: 10; background: {C['panel']}; }}
HomeScreen.-short #wordmark, HomeScreen.-short #tagline {{ display: none; }}
HomeScreen.-short #home {{ padding: 0 1; }}
HomeScreen.-short .card {{ padding: 0 1; }}
HomeScreen.-short #recent {{ max-height: 6; }}
#recent > .option-list--option-highlighted {{ background: {C['sel.dim']}; }}
#recent:focus > .option-list--option-highlighted {{ background: {C['sel']}; }}

/* record */
#record {{ align: center top; padding: 1 2; }}
#record-col {{ width: 96; max-width: 100%; height: auto; }}
.field-label {{ color: {C['text']}; text-style: bold; margin: 1 0 0 0; height: 1; }}
.field-help {{ color: {C['text3']}; height: auto; }}
#preview {{ color: {C['text3']}; height: auto; margin: 1 0 0 0; }}
#problems {{ color: {C['err']}; height: auto; }}
#form-buttons, #result-buttons {{ height: auto; margin: 1 0 0 0; }}
#form-buttons Button, #result-buttons Button {{ margin: 0 2 0 0; }}
#run-status {{ height: auto; margin: 1 0 0 0; }}
#output {{ height: 12; min-height: 6; margin: 1 0 0 0; }}
#result {{ height: auto; margin: 1 0 0 0; }}

/* investigate */
#body {{ height: 1fr; }}
#sidebar {{ width: 38; }}
#main {{ width: 1fr; }}
#runs-panel {{ height: auto; max-height: 45%; }}
#requests-panel {{ height: 1fr; }}
#details-panel {{ width: 52; background: {C['bg']}; }}
#search {{ display: none; margin: 0 0 1 0; }}
#search.-shown {{ display: block; }}
#filterbar {{ height: 1; color: {C['text3']}; padding: 0 1; }}
#why-head, #diff-head {{ height: auto; padding: 0 1 1 1; border-bottom: solid {C['line']}; margin-bottom: 1; }}
#compare-runs {{ height: auto; max-height: 8; border-bottom: solid {C['line']}; margin-bottom: 1; }}

HelpScreen {{ align: center middle; }}
#help-card {{ width: 120; max-width: 96%; height: auto; max-height: 90%; background: {C['panel']};
              border: round {C['uv']}; border-title-color: {C['uv.hi']}; border-title-style: bold; padding: 1 2; }}

/* responsive (classes set on resize): medium narrows the side panes, compact shows details on demand,
   narrow stacks everything */
Screen.-medium #sidebar {{ width: 30; }}
Screen.-medium #details-panel {{ width: 38; }}
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
Screen.-narrow .legend {{ display: none; }}
Screen.-short .intro {{ display: none; }}
Screen.-hide-details #details-panel {{ display: none; }}
Screen.-hide-sidebar #sidebar {{ display: none; }}
"""

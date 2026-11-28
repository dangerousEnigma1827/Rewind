"""Ultraviolet for the TUI: the palette, the named styles render.py's markup uses, a Textual theme and the CSS.

Sources: render.PALETTE (the CLI) and the website's tokens (rewind-cli: src/styles/tokens.css), which share it.
- Violet is the identity: the brand mark, ids, focus, selection, active tabs. #7F5AF0 fills, #8D6CFF for text.
- The foundation is near-black and violet-tinted. Panels step up from it in small, dark increments, never grey.
- Green, red and amber mean only ok, error and warning/unresolved. They use the website's "ink" variants, which
  reach at least 4.5:1 contrast on every surface here (tests/test_tui.py checks the contrast).
- Request tones r1-r4 and the evidence marks match the CLI, so a finding reads the same in both.

Component rules (see docs/handover/TUI_VISUAL_POLISH.md for why):
- Textual paints a border's cells with the widget's own background. So a widget either has the same fill as its
  border (solid shapes: buttons, drawn with `tall`) or the same fill as its parent (outlined shapes: inputs), never
  a fill that differs from both, which is what showed as a block around rounded corners.
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
    "sel.hi": "#32235C",    # violet at 35%: a focused or hovered primary button
    # components, all derived from the tokens above
    "btn": "#2A1D52",       # primary button fill: violet at ~30%, distinct but not a bright block
    "btn2": "#17121F",      # secondary button fill: one quiet step above a panel
    "btn2.hi": "#211A30",   # secondary hover/focus
    "cap": "#1C1729",       # keycap fill (help, footer)
    "thumb": "#3A3448",     # scrollbar thumb at rest; violet on hover and drag
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
    "cap": f"bold {C['uv.hi']} on {C['cap']}", "green": C["ok"],
}.items()}

THEME = Theme(
    name="ultraviolet", dark=True,
    primary=C["uv"], secondary=C["uv.hi"], accent=C["uv.hi"],
    foreground=C["text"], background=C["bg"], surface=C["panel"], panel=C["raised"], boost=C["raised"],
    success=C["ok"], warning=C["warn"], error=C["err"],
    variables={"border": C["uv"], "border-blurred": C["line"], "scrollbar": C["thumb"],
               "scrollbar-background": C["bg"], "scrollbar-hover": C["uv.lo"], "scrollbar-active": C["uv"],
               "scrollbar-corner-color": C["bg"], "footer-background": C["panel"], "footer-key-foreground": C["uv.hi"],
               "footer-description-foreground": C["text3"], "input-selection-background": C["sel"],
               "block-cursor-background": C["sel"], "block-cursor-foreground": C["text"],
               "block-cursor-blurred-background": C["sel.dim"]},
)

# every background in the CSS below; tests assert each one is dark
BACKGROUNDS = [C[k] for k in ("bg", "panel", "raised", "term", "sel", "sel.dim", "sel.hi", "btn", "btn2", "btn2.hi", "cap")]

CSS = f"""
Screen {{ background: {C['bg']}; color: {C['text']}; }}
ModalScreen {{ background: {C['bg']} 80%; }}

/* scrollbars: thin (rewind/tui/scrollbar.py draws a half-cell thumb), dark track, violet only when used */
* {{ scrollbar-size-vertical: 1; scrollbar-size-horizontal: 1;
     scrollbar-color: {C['thumb']}; scrollbar-color-hover: {C['uv.lo']}; scrollbar-color-active: {C['uv']};
     scrollbar-background: {C['bg']}; scrollbar-background-hover: {C['bg']}; scrollbar-background-active: {C['bg']};
     scrollbar-corner-color: {C['bg']}; }}
.card, .card * {{ scrollbar-background: {C['panel']}; scrollbar-background-hover: {C['panel']};
                  scrollbar-background-active: {C['panel']}; }}
#help-card, #help-card * {{ scrollbar-background: {C['panel']}; scrollbar-background-hover: {C['panel']};
                            scrollbar-background-active: {C['panel']}; }}

/* chrome */
.topbar {{ height: 1; background: {C['panel']}; color: {C['text2']}; padding: 0 1; }}
Footer {{ background: {C['panel']}; }}
Footer > FooterKey {{ background: {C['panel']}; color: {C['text3']}; }}
Footer > FooterKey .footer-key--key {{ background: {C['cap']}; color: {C['uv.hi']}; text-style: bold; }}
Footer > FooterKey .footer-key--description {{ color: {C['text3']}; }}
Footer > FooterKey:hover {{ background: {C['sel.dim']}; }}

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

/* tabs: every label is clickable and carries its key (1–7). app._tab_labels() keeps the bar within its width (inactive
   tabs shrink to their number), so the sideways scrollbar below only ever appears on terminals too narrow even for that */
TabbedContent {{ height: 1fr; }}
TabbedContent ContentSwitcher {{ height: 1fr; }}
TabPane {{ padding: 0; height: 1fr; }}
Tabs {{ background: {C['bg']}; height: auto; }}
Tabs > #tabs-scroll {{ height: auto; overflow-x: auto; overflow-y: hidden; scrollbar-size-horizontal: 1; }}
Tab {{ color: {C['text3']}; padding: 0 1; }}
Tab.-active {{ color: {C['uv.hi']}; text-style: bold; }}
Tab:hover {{ color: {C['text']}; background: {C['sel.dim']}; }}
Tabs:focus .-active {{ background: {C['sel']}; color: {C['text']}; text-style: bold; }}
Underline > .underline--bar {{ background: {C['line']}; color: {C['uv']}; }}

/* inputs: outlined, the fill matches the page so nothing spills past the rounded border; no focus tint */
Input {{ background: {C['bg']}; color: {C['text']}; border: round {C['line.hi']}; padding: 0 1; height: 3;
         background-tint: {C['text']} 0%; }}
Input:focus {{ border: round {C['uv']}; background-tint: {C['text']} 0%; }}
Input:hover {{ border: round {C['dim']}; }}
Input:focus:hover {{ border: round {C['uv']}; }}
.card Input {{ background: {C['panel']}; }}
Input > .input--placeholder {{ color: {C['dim']}; }}
Input > .input--cursor {{ background: {C['uv.hi']}; color: {C['bg']}; }}
Input > .input--selection {{ background: {C['sel.hi']}; }}

/* buttons: solid fills. The rounded border is always there, in the fill's own colour (invisible), so a button's
   size never changes; focus only recolours it violet. (Half-block `tall` borders left seams at the corners.) */
Button {{ width: auto; min-width: 12; height: 3; padding: 0 1; content-align: center middle;
          color: {C['text']}; background: {C['btn2']}; border: round {C['btn2']}; text-style: none; tint: {C['bg']} 0%; }}
Button:hover {{ background: {C['btn2.hi']}; border: round {C['btn2.hi']}; }}
Button:focus {{ background: {C['btn2.hi']}; border: round {C['uv.lo']}; text-style: bold; }}
Button.-active {{ background: {C['sel.hi']}; border: round {C['sel.hi']}; tint: {C['bg']} 0%; }}
Button.-primary {{ background: {C['btn']}; border: round {C['btn']}; color: {C['text']}; text-style: bold; }}
Button.-primary:hover {{ background: {C['sel.hi']}; border: round {C['sel.hi']}; }}
Button.-primary:focus {{ background: {C['sel.hi']}; border: round {C['uv.hi']}; }}
Button:disabled {{ background: {C['raised']}; border: round {C['raised']}; color: {C['text3']}; text-style: none; }}
Button.-link {{ height: 1; min-width: 0; padding: 0; margin: 0 1; border: none; background: {C['bg']}; color: {C['uv.hi']};
                text-style: underline; }}
Button.-link:hover, Button.-link:focus {{ background: {C['sel']}; border: none; text-style: bold underline; }}
RichLog {{ background: {C['term']}; border: round {C['line']}; padding: 0 1; }}
Toast {{ background: {C['raised']}; color: {C['text']}; border-left: outer {C['uv']}; padding: 0 1; }}
Toast > .toast--title {{ color: {C['uv.hi']}; text-style: bold; }}
Toast.-error {{ border-left: outer {C['err']}; }}
Toast.-warning {{ border-left: outer {C['warn']}; }}

/* home: one dominant action, then recordings, then a quiet way to try the sample */
#home {{ align: center top; padding: 1 2; }}
#home-col {{ width: 96; max-width: 100%; height: auto; }}
#wordmark {{ height: auto; margin: 1 0 1 0; }}
#tagline {{ height: auto; color: {C['text2']}; margin: 0 0 1 0; }}
.card {{ background: {C['panel']}; border: round {C['line']}; padding: 1 2; height: auto; margin: 0 0 1 0;
         border-title-color: {C['text3']}; border-title-style: bold; }}
.card:focus-within {{ border: round {C['uv']}; border-title-color: {C['uv.hi']}; }}
.card Button.-link {{ background: {C['panel']}; }}
#record-card .desc {{ height: auto; color: {C['text2']}; margin: 0 0 1 0; }}
#record-row {{ height: auto; }}
#record-row .hint {{ width: auto; height: 3; content-align: left middle; padding: 0 0 0 2; color: {C['dim']}; }}
#recent {{ height: auto; max-height: 10; background: {C['panel']}; }}
#recent > .option-list--option-highlighted {{ background: {C['sel.dim']}; }}
#recent:focus > .option-list--option-highlighted {{ background: {C['sel']}; }}
#recent-intro {{ height: auto; margin: 0 0 1 0; }}
#sample-row {{ height: 1; padding: 0 1; }}
#sample-row Static {{ width: auto; color: {C['text3']}; }}
HomeScreen.-short #wordmark, HomeScreen.-short #tagline {{ display: none; }}
HomeScreen.-short #home {{ padding: 0 1; }}
HomeScreen.-short .card {{ padding: 0 1; }}
HomeScreen.-short #record-card .desc {{ margin: 0; }}
HomeScreen.-short #recent {{ max-height: 6; }}

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

/* help: a centered card; the body scrolls when the terminal is short (heights set in HelpScreen) */
HelpScreen {{ align: center middle; }}
#help-card {{ width: 100; max-width: 96%; height: auto; background: {C['panel']}; border: round {C['line.hi']};
              padding: 0 2; }}
#help-head {{ height: 1; margin: 1 0 1 0; }}
#help-body {{ height: auto; background: {C['panel']}; }}
#help-foot {{ height: 1; margin: 1 0 1 0; color: {C['dim']}; }}

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

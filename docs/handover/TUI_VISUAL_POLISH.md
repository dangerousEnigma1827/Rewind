# TUI visual polish: root causes and plan

Back to [HANDOVER.md](HANDOVER.md). Done on `feat/tui-visual-polish`, from `feat/ultraviolet-tui` at `f156873`. This is a visual and interaction pass only: the recorder and the analysis are unchanged.

## Root causes (from Textual's own CSS and the rendered screenshots)

| symptom | cause |
|---|---|
| Inputs and buttons sit in a lighter rectangle that spills past their outline | Textual paints a border's cells with the widget's **own** background. Inputs and buttons had a `round` border and a panel-coloured fill on a near-black parent, so the rounded corners showed the fill as a square block around the outline. |
| Focused inputs turn greyish | Textual's `Input:focus` adds `background-tint: $foreground 5%`, a white tint over the dark fill. |
| Buttons differ in size and weight | Textual's `Button` has `min-width: 16`, `line-pad: 1` and `height: auto`. Ours set `height: 3` and `padding: 0 2` and kept `min-width`, while primary/secondary changed the fill and the border at once. |
| Distant tabs are hard to reach | `Tabs > #tabs-scroll` is `overflow: hidden`: when the labels are wider than the main panel, the rest are cut off with no way to scroll and no hint they exist. The key for each tab appeared only in its view's intro line. |
| Scrollbars look blocky | Textual draws the thumb as a full reversed cell (plus eighth-block caps) in the scrollbar colour, a bright 1-column block. |
| Help looks like a default dialog | Two loose text columns with an uneven split, keys as plain coloured text, a scrollbar always visible, no clear close affordance, and a layout that only reads at full width. |
| The sample competes with recording | Two equal buttons side by side in the "Start" card. |

## Plan
1. **Components**
   - **Inputs:** flat outlined fields. The fill matches the page, so nothing spills. The border is a quiet line that turns violet on focus, and the focus tint is removed.
   - **Buttons:** solid shapes drawn with `tall` borders in the same colour as their fill, so no square appears behind a rounded corner.
     - one height (3) and one padding (0 2)
     - primary is a deep violet fill, secondary a quiet dark fill, disabled is dimmed but readable
     - hover and focus brighten the fill rather than adding a block
     - a compact `-link` style for minor actions
2. **Home hierarchy**
   - **Record a program** is one card with the explanation and a single primary button.
   - **Your recordings** follows.
   - The sample becomes a one-line "New to Rewind? Try the sample" link at the bottom.
3. **Tabs**
   - Each label carries its key as a small dim letter.
   - The tab bar scrolls horizontally with a thin scrollbar when the labels don't fit, and Textual already scrolls the active tab into view.
   - Labels are clickable.
   - `<` and `>` move to the previous / next view. The view letters `o w t p s e d` stay.
4. **Scrollbars:** a thin renderer (`ThinScrollBarRender`): a half-cell thumb (`▐` vertical, `▄` horizontal) on the panel's own dark track. It turns violet on hover and drag, and click, drag and wheel behave as before.
5. **Help**
   - A centered card with a title row ("Keyboard shortcuts" and an `esc` keycap).
   - Six task groups: Getting started, Recording, Navigation, Investigation, Evidence, General.
   - Keys drawn as compact keycaps in a right-aligned column, with descriptions aligned beside them.
   - Two columns when there's room, one otherwise. The card scrolls internally on short terminals.
6. **Consistency**
   - Footer keys use the same keycap style.
   - Toasts sit on the raised dark surface with a violet edge.
   - Every surface stays on the Ultraviolet tokens.

Verification: every screen captured at 80×24, 100, 120, 150 and 180+ columns; layout tests for tab reachability, component boundaries and help fit; the full test suite.

# TUI UX audit (before the Ultraviolet redesign)

Back to [HANDOVER.md](HANDOVER.md). This audits `feat/rewind-tui` at `d07f0e7`, from the point of view of a developer who has
never used Rewind: "I have a Node.js app. I want to record it. Something went wrong. I want to know why."

## Confusing terminology
- **Tab names are CLI command names:** `why`, `pending`, `state`, `tree`, `diff`. Nothing says what each one shows.
- **The main panel is titled "investigate"**, which describes nothing that the tabs don't already say.
- **Column headers and markers are unexplained:**
  - `seq`, `ms`, `req` and `··` (no request) have no explanation.
  - Event markers `→ ← » ✎ ◌ ▸ ◉ ⚙` have no legend.
  - Request markers `● × − ◌` have no legend either.
- **Evidence levels are glyphs only** (`● ◆ ?`). Their meaning appears only in the help screen and a one-line legend.
- **"baseline" and "watch"** appear in the header without explanation.

## Unclear navigation
- **Launch has no starting point:** the app opens on the newest run, with the runs list focused and no hint of what to do next.
- **Panel keys are hidden:** `1`–`4` appear only in help.
- **The target of `w` depends on a hidden rule:** the focused timeline row, if it's an "explainable" event, otherwise the first error.
- **State follows the timeline cursor implicitly:** opening it from another tab shows the state at a row the user can't see.
- **Comparing two runs takes three hidden steps:** `b` on one run, select another, then `d`.
- **Evidence walking (`]` / `[`)** appears only in a panel subtitle and in help.

## Missing workflows
- **No recording from the app.** The welcome screen tells the user to go back to the shell and type a CLI command.
- **No sample.** Nothing offers a quick way to try Rewind on the bundled Phantom Discount demo.
- **No "start here".** Opening a run shows a raw timeline, not what went wrong and which findings matter.
- **Diff can't pick a run directly:** the other run can't be chosen from within the comparison view.

## Visual problems
- **Green does three jobs:** focus, selection, ids and the brand mark are all green, which is the colour of success. The Ultraviolet identity from the CLI and the website is gone.
- **Six tabs carry equal weight**, with no default view that summarises the run.
- **Walls of bold text:** observed findings are bold, and long ones wrap into dense blocks.
- **Mismatched built-in widgets:** search input and notifications use Textual's own colours rather than the app's.

## Features first-time users can't reach
- **Timeline controls:** search (`/`), kind filter (`f`), callback firings (`c`) and every event (`a`) are listed only in a dim subtitle.
- **Async tree by request:** rooting the tree at a request requires selecting that request in the sidebar first.
- **Details pane on narrow terminals:** hidden by default, and only `?` mentions `i`.

## Redundant or noisy elements
- The panel title "investigate" duplicates the tab bar.
- Hints are repeated in three places: border subtitle, details footer and help.
- The full home path is in the header on every screen.

## What the redesign changes
- **A home screen with two paths:** *Record a program* is the primary action. A sample offers the Phantom Discount demo when it's present. Recent runs sit below for returning users.
- **A recording form:** command, label, watched variables (with what they do), a preview of the equivalent CLI command, live output, cancel, and a clear result. It uses the CLI's recording code.
- **The run opens on an Overview** that says what happened: requests that failed or weren't answered, errors, Rewind's key findings, and where to go next.
- **Tabs have plain names, a one-line description and their key:**
  - Overview
  - Explain (`why`)
  - Timeline
  - Unfinished (`pending`)
  - Variables (`state`)
  - Async tree (`tree`)
  - Compare (`diff`)
- **Findings are grouped by evidence level, in words:** *Recorded*, *Derived from records*, and *Rewind's interpretation (not proven)*.
- **Compare picks the other run in place.**
- **The Ultraviolet identity returns:** a violet accent for focus, selection and the brand. Green, red and amber are used only for status, on a strictly dark foundation built from the website's tokens.

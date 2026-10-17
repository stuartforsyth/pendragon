---
name: feedback
description: Work through the GM's feedback queue: reports sent from the Feedback tab on the GM console, each stored with where it came from (tool, session and its newest event, fight, battle, open token, selected text). Reproduce each one on a copy of that session, fix the small ones with tests, plan the big ones, and mark each done or planned with a note the GM sees in the panel. Use for /feedback, at the start of a session, or whenever Stuart says he's sent feedback or asks what's in the queue.
argument-hint: "(none — reads the whole queue)"
---

# Work through the feedback queue

Stuart tests the app and sends reports from the **Feedback** tab (right edge of the GM console).
Each report lands in `data/feedback.json` (his file, git-ignored; never hand-edit it) with:
- `page`: route, tool, heading, open dialog or drawer, picked token, selected text, viewport
- `where`: session id and its newest event id, the active fight (name, round), the battle (name, status, day, turn)
- `app_version`: the commit he was running

## Steps

1. **Read the queue:** `.venv/bin/python -m web.feedback list` (`--json` for everything, `--status all` for history). If it's empty, say so in one line and stop.
2. **Reproduce each report where it happened.** Copy the data and the reported session into a throwaway instance, never the live files:
   - `mkdir -p $S/fb/data $S/fb/sessions`; copy `data/*.json` and `sessions/<where.session.id>.json` (or `sessions/.scratch.json` if `where.session.id` is `scratch`)
   - Strike nothing; events after `where.session.last_event` didn't exist yet, so trim them in the copy.
   - Start with `PENDRAGON_DATA_DIR=$S/fb/data PENDRAGON_SESSIONS_DIR=$S/fb/sessions .venv/bin/python -m web --port 8021`, resume that session, go to `page.route`, and screenshot it with Playwright.
   - If `app_version` is older than HEAD, check whether it's already fixed.
3. **Decide per item:**
   - **Small** (a bug, a tweak, missing behaviour; one sitting, no design fork): fix it now. Follow CLAUDE.md: logic in `core/`, events and deterministic deltas, secrets filtered in `web/table.py`, and the rules corpus for any rule. Add a test that fails without the fix, plus a click-through in `tests/e2e/` for anything clicked. Run the suite, restart (`./launch.sh`), and commit one item per commit.
   - **Big** (a new feature or a design question): don't build it. Write it into `ROADMAP.md` (or the relevant `docs/design/` piece) and tell Stuart in a line.
   - **Unclear:** batch the real questions for Stuart in one message. Don't guess.
   - **Question or comment:** answer it.
4. **Close the loop** so the panel shows what happened:
   - `.venv/bin/python -m web.feedback mark <ids> --status done --note "Fixed: <what changed> (<short sha>)"`
   - or `--status planned --note "In ROADMAP: <section>"`, or `--status wontfix --note "<why>"`
   Write notes in plain words he'll read in the panel.
5. **Report:** one short list with each item: what it was, what you did, and the commit. Then stop.

## Working style (from Stuart's feedback)

- **Small increments** in the real app, shown running. No long design pipelines for small items. See memory `small-increments`.
- **Don't add features he didn't ask for.** Offer extras separately, as optional. See memory `dont-smuggle-proposals`.

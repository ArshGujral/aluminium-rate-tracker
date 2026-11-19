# Aluminium Rate Tracker: shared instructions for every coding agent

Claude Code and Codex both work on this repository. This file is the single source of rules for both of them
(`CLAUDE.md` only imports it). Change the rules here, not in a tool-specific file.

## What this is

A Xing-Z page that turns the near-month MCX aluminium futures price (standard contract, not Mini, ₹/kg) into
winding-wire prices for up to 32 SWG, 33 SWG and 38 SWG, with a buying signal, a price chart, supplier quotes
and a daily log. The owner uses it to cost and negotiate wire purchases. It is a reference, not a live quote.

## Where things live

- `index.html`: the website, served by GitHub Pages at https://arshgujral.github.io/aluminium-rate-tracker/.
  One self-contained file (styles and script inline). It reads `data.json` and `quotes.json` and refreshes both every
  3 minutes. Colours and glass follow the Xing-Z website; the fonts stay Inter and Space Grotesk.
- `data.json`: the rates, plus starting quotes and settings. **Written by the update program.** Edit it by hand only
  to correct a wrong rate, and say so in the commit.
- `quotes.json`: the supplier quotes, shared by every device. The website reads it through the GitHub contents API and
  saves to it with the owner's key (a fine-grained token, Contents: read and write), which each device keeps in its
  own browser. Two devices saving at once is handled by retrying on GitHub's refusal of a stale copy.
- `scripts/update_rates.py`: the update program (Python standard library only). Reads Dhan, Groww, Moneycontrol
  and MCX Live for the price, plus 5paisa for the previous close, and writes a rate only when two sources agree.
- `.github/workflows/update-rates.yml`: runs the program and commits `data.json`. Started every 30 minutes
  (:25 and :55, 9:25 AM to 11:55 PM and just after midnight, India time, Mon-Sat) by an outside timer on
  cron-job.org, with GitHub's own schedules as backup. GitHub often skips its own schedules; that is why the
  outside timer exists.
- `tracker.html`: the older copy published as a Claude artifact; it reads rates from that artifact's database.
  The scheduled task that fed it is switched off, so it no longer updates. Keep it working, but `index.html` is the
  page the owner uses.
- `daily-update-task.md`, `start-local.bat`: notes for the old artifact task, and a Windows script to run the
  tracker locally.
- Icons: the Xing-Z website's `favicon.svg` (Z and bolt on a dark tile), with PNG sizes for phones (`favicon-32.png`,
  `apple-touch-icon.png`, `icon-192.png`, `icon-512.png`) and `manifest.webmanifest` for home-screen installs.

## Hard rules

- **Prices are never estimated, carried forward or invented.** A rate is written only when two sources agree
  (₹0.05 for the official close, ₹0.30 for the last price, ₹1.00 for today's live price). If they don't, write
  nothing and let the next run try again.
- **A push to `main` publishes the live site.** Push only changes the owner asked for. The workflow also commits
  `data.json` to `main` many times a day, so fetch and rebase before you push, and never force-push `main`.
- **No secrets in the repo.** The GitHub token that lets cron-job.org start the workflow lives only in
  cron-job.org. The key that saves quotes lives only in the owner's browsers. The PIN screen stores only the PIN's SHA-256; never write the PIN itself in code, comments,
  commits or docs.
- The PIN screen shows on every load and after 3 minutes without activity. It keeps casual visitors out only:
  the page and `data.json` are public files.
- Support both dark and light themes, and phone width with no horizontal scroll. Check both when changing UI.
- Match the surrounding code: short comments that say why, the same naming and idiom, no build step, no
  framework, no new dependencies in the update program.

## Checking your work

- Update program, without saving anything: `DRY_RUN=true python3 scripts/update_rates.py`. Every source should
  print a line; a source that stops printing usually means its site changed its page.
- Website: `python3 -m http.server 8000`, open http://localhost:8000/, enter the PIN, then check a phone width
  (390 px) and a laptop width (1366 px) in both themes.
- After a change to the update program, run the workflow once from GitHub Actions and read its log.

## Known source quirks

- Moneycontrol's price feed (`priceapi.moneycontrol.com`) needs the contract expiry from its page's
  `__NEXT_DATA__`, and refuses requests that don't accept JSON.
- MCX Live keeps its data in `window.FD_FEED`; its `t_datetime` is UTC.
- mcxindia.com refuses automated requests ("Access Denied"); don't add it.

## Working together (Claude Code + Codex)

The two agents must never edit the same files at the same time.

- **One task, one branch.** Start each task on its own branch (`claude/<task>` or `codex/<task>`), or in its own git
  worktree for parallel work: `git worktree add ../tracker-<task> -b codex/<task>`. Merge into `main` when it's done.
- **Commit before handing over.** Before switching agents, commit (or stash) so the next agent starts clean.
- **Default split of roles:**
  - Claude Code leads design, layout, copy and visual work on `index.html`.
  - Codex reviews every finished change (`codex review`) and takes self-contained logic tasks (the update program,
    its sources and parsing, the workflow).
- **Handover notes.** When an agent stops mid-task, it writes what's done and what's left to `HANDOFF.md`
  (gitignored) so the other agent can continue.
- Either agent can call the other:
  - From Claude Code: `codex exec "<task>"` to delegate, `codex review --uncommitted` for a review.
  - From Codex: the `claude` MCP server (Claude Code's tools) is registered in `~/.codex/config.toml`.

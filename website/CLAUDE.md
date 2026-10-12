# D.R.E.A.M.S website: notes for Claude Code sessions

Static site for the D.R.E.A.M.S autonomous survey boat, live at https://ka1e27.github.io/dreams/ (GitHub Pages from `main`; pushing `main` deploys). Team: Kyle Tran and Matthew Hong (co-founders), Nolan Ting and Caleb Kong. Kyle and Matthew both push to this repo.

## Weekly updates: document your work

The team posts weekly updates in **`UPDATES.md`** (repo root). The site's Updates page (`updates.html`) reads that file live, so editing it is all it takes.

**Every session that does real D.R.E.A.M.S work (boat hardware, PCBs, firmware, CAD, testing, sponsors, or this site) must add to it before finishing:**

1. Find the heading for the current week, `## Week of <Mon> <day>, <year>`, using the Monday of the week. If it doesn't exist, add it at the top, just under the instructions comment. Newest week first.
2. Add one short bullet per meaningful change: `- **Name:** what was built, tested, decided or broken.` Use the name of the person you're working with (Kyle unless told otherwise).
3. Write for the public, because it's on the website: true and specific, no hype. Follow "Never publish" below. Don't say who wrote the code or mention AI tools.
4. Matthew and the others edit this file too. Pull before editing (`git pull`), only add to it, and don't rewrite other people's bullets.
5. Commit the change, with your other site changes if there are any, and push to `main` so it goes live.

Work done in another repo (the boat code and PCBs live in `ka1e27/D.R.E.A.M.S`) still gets its bullet here. The local clone of this repo is `C:\Users\kyleg\Projects\dreams-website`.

## Editing the site

- Pages are plain HTML. `site.js` holds the shared nav, footer and contacts. `styles.css` is the whole design system.
- `build-log.html` is generated. Edit `tools/gen_build_log.py` and `tools/build-log.template.html`, then run `python -I tools/gen_build_log.py`.
- Board callouts: run `python -I tools/gen_callouts.py`. Logo: run `python -I tools/make_logo.py`. Images: run `python -I tools/build_images.py <slugs>`.
- After editing `styles.css` or `site.js`, run `python -I tools/stamp.py` so browsers fetch the new files.
- `_directions/` is local scratch (mockups, Instagram slides, sponsor drafts). It's git-ignored and never published.

## Never publish

Everything here is public the moment it's pushed, and git history keeps it after a file is deleted. Before committing, check the diff for:

- **Secrets:** API keys, tokens, passwords, keys, Wi-Fi or Tailscale details.
- **Personal info:** phone numbers, home or shipping addresses, personal emails (only the team's public Northeastern emails and Kyle's listed Gmail appear on the site), student IDs.
- **Partners and sponsors:** a contact's name, or what they said in meetings. Naming the organizations is fine (CRWA, the Port of Oakland): "we're talking with CRWA about data collection" is OK. No sponsor discounts, quotes or deal terms until Kyle announces them.
- **Money:** budgets, spending, or what anything cost.
- **Photos:** location (EXIF/GPS) data. `tools/build_images.py` re-encodes images, which drops it. Don't commit original phone photos.
- **Third-party files** whose license doesn't allow sharing.

If something like this turns up or seems needed, stop and ask Kyle first.

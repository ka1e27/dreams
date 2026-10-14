# D.R.E.A.M.S website: notes for Claude Code sessions

Static site for the D.R.E.A.M.S autonomous survey boat. It lives in the `website/` folder of the D.R.E.A.M.S repo (ka1e27/dreams), and paths below are relative to `website/`. It's live at https://ka1e27.github.io/dreams/: the "Deploy website" GitHub Actions workflow publishes `website/` whenever a push to `main` changes it. Team: Kyle Tran and Matthew Hong (co-founders), Nolan Ting and Caleb Kong. Kyle and Matthew both push to this repo.

**The repo-wide rules in the root `CLAUDE.md` apply to every change here.** Two matter most for the site: what must never be published (§4.1), because everything here is public the moment it's pushed, and the weekly update every session adds (§4.2). This file covers only how the site works.

## Weekly update pages

- `UPDATES.md` (in `website/`) holds the short weekly bullets. The site's Updates page (`updates.html`) reads it live, so editing it is all it takes. The rules for writing bullets are in the root `CLAUDE.md` §4.2.
- The full story goes in `updates/<YYYY-MM-DD>.md` (the week's Monday): `# Headline`, one or two intro sentences, then `## Sections` with text and photos. Once the file exists, the week on the Updates page links to `week.html?w=<YYYY-MM-DD>`, which shows the bullets, the write-up and the photos. Photos on adjacent lines share a row and open full size when clicked.
- Photos: put the sources in `images/updates/` (git-ignored), add them to `UPDATES` in `tools/build_images.py`, run it, and link the `img/upd-<week>-<name>-1600.jpg` it writes (the page picks the 900 px and WebP copies itself). The script re-encodes images, which drops their location data.

## Editing the site

- Pages are plain HTML. `site.js` holds the shared nav, footer and contacts. `styles.css` is the whole design system.
- `build-log.html` is generated. Edit `tools/gen_build_log.py` and `tools/build-log.template.html`, then run `python -I tools/gen_build_log.py`.
- Board callouts: run `python -I tools/gen_callouts.py`. Logo: run `python -I tools/make_logo.py`. Images: run `python -I tools/build_images.py <slugs>`.
- After editing `styles.css` or `site.js`, run `python -I tools/stamp.py` so browsers fetch the new files.
- `_directions/` is local scratch (mockups, Instagram slides, sponsor drafts). It's git-ignored and never published.

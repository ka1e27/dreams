# D.R.E.A.M.S website: notes for Claude Code sessions

Static site for the D.R.E.A.M.S autonomous survey boat. It lives in the `website/` folder of the D.R.E.A.M.S repo (ka1e27/dreams), and paths below are relative to `website/`. It's live at https://ka1e27.github.io/dreams/: the "Deploy website" GitHub Actions workflow publishes `website/` whenever a push to `main` changes it. Team: Kyle Tran and Matthew Hong (co-founders), Nolan Ting, Caleb Kong and Logan Chen (marketing). Kyle and Matthew both push to this repo.

**The repo-wide rules in the root `CLAUDE.md` apply to every change here.** Two matter most for the site: what must never be published (§4.1), because everything here is public the moment it's pushed, and the weekly update every session adds (§4.2). This file covers only how the site works.

## Weekly update pages

- `UPDATES.md` (in `website/`) holds every week under `## Week ending <Mon> <day>, <year>` (its Friday): one paragraph, one to three photo lines, then the bullets. The rules for writing it are in the root `CLAUDE.md` §4.2.
- **A week comes out on its Friday at 5 pm Boston time.** `site.js` (`RELEASE_HOUR`, `isOut`) hides it on both pages until then, so the team adds to it all week. `?preview` on either page shows it early.
- The Updates page (`updates.html`) shows each week's paragraph and up to three photos; the whole card opens `week.html?w=<YYYY-MM-DD>` (the Friday), which shows the photos, the bullets ("What each of us did") and the longer write-up from `updates/<YYYY-MM-DD>.md` if there is one: `# Headline`, then `## Sections` with text and photos. Photos on adjacent lines share a row and open full size when clicked. Old `## Week of <Monday>` headings and `?w=<Monday>` links still work; they're read as that week's Friday.
- Photos: put the sources in `images/updates/` (git-ignored), add them to `UPDATES` in `tools/build_images.py`, run it, and link the `img/upd-<week>-<name>-1600.jpg` it writes (the page picks the 900 px and WebP copies itself). The script re-encodes images, which drops their location data.

## Editing the site

- Pages are plain HTML. `site.js` holds the shared nav, footer and contacts. `styles.css` is the whole design system.
- `build-log.html` is generated. Edit `tools/gen_build_log.py` and `tools/build-log.template.html`, then run `python -I tools/gen_build_log.py`.
- Board callouts: run `python -I tools/gen_callouts.py`. Logo: run `python -I tools/make_logo.py`. Images: run `python -I tools/build_images.py <slugs>`.
- After editing `styles.css`, `site.js` or `boat-explorer.js`, run `python -I tools/stamp.py` so browsers fetch the new files.
- The Boat page's 3D boat (`#explore`) is `boat-explorer.js` with `media/boat-v3.glb`, exported from the team's SolidWorks model. The part names, numbers and "why" text live at the top of `boat-explorer.js`.
- `_directions/` is local scratch (mockups, Instagram slides, sponsor drafts). It's git-ignored and never published.

# D.R.E.A.M.S website

**Data Recovery for Environmental And Marine Surveillance**: a modular autonomous survey boat, founded by Kyle Tran and Matthew Hong and built with Nolan Ting, Caleb Kong and Logan Chen at Northeastern University.

Live site: https://ka1e27.github.io/dreams/

## Structure
- `index.html`, `boat.html`, `build-log.html`, `partners.html`, `team.html`, `contact.html`: the pages (plain HTML, no build step)
- `updates.html` and `week.html`: the weekly updates, read from `UPDATES.md` and `updates/<YYYY-MM-DD>.md`. Each week comes out on its Friday
- `styles.css`: the whole design system (light "Fresh Water + Blueprint" theme)
- `site.js`: the shared nav, contact band and footer, plus small behaviours. **Edit `NAV` and `CONTACTS` here** and every page updates.
- `img/`: optimized images (WebP + JPEG), made by `tools/build_images.py`
- `media/`: the interactive 3D board (`v3-carrier.glb`), the annotated top-view render and the V1 winch test video
- `demo/v2-dashboard/`: the V2 command center, running on simulated data

## Weekly updates
The Updates page (`updates.html`) shows `UPDATES.md`, so anyone on the team can post from GitHub. A week runs Saturday to Friday and comes out on its Friday at 5 pm Boston time; until then the site doesn't show it (add `?preview` to the page's URL to check it early).
1. Open [`UPDATES.md`](UPDATES.md) on GitHub and click the pencil icon.
2. Find this week's `## Week ending <Friday's date>` heading, or add one at the top. Under it go one paragraph that sums the week up, one to three photos (`![what it shows](img/your-photo.jpg)`, one per line), then the bullets: `- **Your name:** what you worked on`.
3. Click **Commit changes**.

The Updates page shows each week's paragraph and photos; clicking the week opens its page with the bullets. For a longer story, add `updates/<the Friday>.md` (for example `updates/2026-10-23.md`): a `# Headline`, then `## Sections` with text and photos. It shows on the week's page under the bullets. Remove location data from photos first; `tools/build_images.py` does that.

## Editing
- **Build log:** `build-log.html` is generated. Add or edit entries in `tools/gen_build_log.py`, then run `python tools/gen_build_log.py`.
- **Board callouts:** edit `media/v3-carrier-callouts.json` (or the wording overrides in `tools/gen_callouts.py`), then run `python tools/gen_callouts.py`.
- **Images:** `tools/build_images.py` regenerates `img/` from the high-res originals on the build machine.
- **Logo:** `tools/make_logo.py` builds `img/logo*.svg` and `img/favicon.svg` from Nolan's drawing (redrawn as strokes). The 32 px and 180 px PNG icons are renders of `img/favicon.svg`.
- **After editing `styles.css` or `site.js`:** run `python tools/stamp.py`. It versions their URLs in every page so browsers fetch the new files right after a deploy.
- Pushing changes under `website/` to `main` redeploys GitHub Pages (the "Deploy website" Actions workflow). The tools can be run from anywhere; they find `website/` themselves.

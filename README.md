# D.R.E.A.M.S website

**Data Recovery for Environmental And Marine Surveillance**: a modular autonomous survey boat, founded by Kyle Tran and Matthew Hong and built with Nolan Ting and Caleb Kong at Northeastern University.

Live site: https://ka1e27.github.io/dreams/

## Structure
- `index.html`, `boat.html`, `build-log.html`, `partners.html`, `team.html`, `contact.html`: the pages (plain HTML, no build step)
- `styles.css`: the whole design system (light "Fresh Water + Blueprint" theme)
- `site.js`: the shared nav, contact band and footer, plus small behaviours. **Edit `NAV` and `CONTACTS` here** and every page updates.
- `img/`: optimized images (WebP + JPEG), made by `tools/build_images.py`
- `media/`: the interactive 3D board (`v3-carrier.glb`), the annotated top-view render and the V1 winch test video
- `demo/v2-dashboard/`: the V2 command center, running on simulated data

## Editing
- **Build log:** `build-log.html` is generated. Add or edit entries in `tools/gen_build_log.py`, then run `python tools/gen_build_log.py`.
- **Board callouts:** edit `media/v3-carrier-callouts.json` (or the wording overrides in `tools/gen_callouts.py`), then run `python tools/gen_callouts.py`.
- **Images:** `tools/build_images.py` regenerates `img/` from the high-res originals on the build machine.
- **Logo:** `tools/make_logo.py` builds `img/logo*.svg` and `img/favicon.svg` from Kyle's drawing (redrawn as strokes). The 32 px and 180 px PNG icons are renders of `img/favicon.svg`.
- **After editing `styles.css` or `site.js`:** run `python tools/stamp.py`. It versions their URLs in every page so browsers fetch the new files right after a deploy.
- Pushing to `main` redeploys GitHub Pages.

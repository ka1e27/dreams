# D.R.E.A.M.S website

**Data Recovery for Environmental And Marine Surveillance**: a modular autonomous survey boat, designed and built by Kyle Tran and Matthew Hong at Northeastern University.

Live site: https://ka1e27.github.io/dreams/

## Structure
- `index.html`, `boat.html`, `build-log.html`, `partners.html`, `team.html`, `contact.html`: the pages (plain HTML, no build step)
- `styles.css`: the whole design system (light "Fresh Water + Blueprint" theme)
- `site.js`: the shared nav, contact band and footer, plus small behaviours. **Edit `NAV` and `CONTACTS` here** and every page updates.
- `img/`: optimized images (WebP + JPEG), made by `tools/build_images.py`
- `media/`: the interactive 3D board (`v3-carrier.glb`) and the annotated top-view render
- `demo/v2-dashboard/`: the V2 command center, running on simulated data

## Editing
- **Build log:** `build-log.html` is generated. Add or edit entries in `tools/gen_build_log.py`, then run `python tools/gen_build_log.py`.
- **Board callouts:** edit `media/v3-carrier-callouts.json` (or the wording overrides in `tools/gen_callouts.py`), then run `python tools/gen_callouts.py`.
- **Images:** `tools/build_images.py` regenerates `img/` from the high-res originals on the build machine.
- Pushing to `main` redeploys GitHub Pages.

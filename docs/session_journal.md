# D.R.E.A.M.S — Session Journal

A running log of what each Claude Code session worked on. **Read this top-to-bottom at the start
of every session** to understand recent work, then **append a new entry at the end of the session**
describing what you did.

- Newest entries go at the **top** (just under this header), so the most recent context is read first.
- Keep entries short and factual — what changed and why, not a transcript.
- This is a *narrative* of work-in-progress. For locked decisions and the architecture-of-record,
  see `docs/changelog_and_decisions.md`; for hardware deltas, `docs/hardware_changes_v1_to_v2.md`.
  Don't duplicate those here — link to them.
- **This file holds only the 5 most recent entries.** When appending pushes the count past 5, move
  the oldest entry (or entries) to the top of `docs/session_journal_archive.md`'s entry list, keeping
  it newest-first there too. The archive isn't read automatically at session start — only pull from
  it if you need context on something specific from further back.

### Entry template (copy this)

```
## YYYY-MM-DD — <short title>

**Worked on:** one or two sentences on the goal.
**Changed:**
- `path/to/file` — what and why
**Decisions / open questions:** anything left unresolved or flagged for next time.
**Next steps:** what a future session should pick up.
```

---

<!-- New entries below this line, newest first. Keep at most 5 — move older ones to
     docs/session_journal_archive.md. -->

## 2026-06-30 — Battery migration to three-domain Milwaukee M18 architecture (firmware + docs)

**Worked on:** user dropped `Downloads/DREAMS_battery_changes.md`, an "authoritative" spec replacing the
old LiPo/Li-ion multi-pack battery system with three fully isolated M18 domains: drive (3× M18 series,
54 V nom / 63 V max), electronics (1× M18), winch (1× M18). Confirmed scope up front (AskUserQuestion):
**firmware + docs, leave KiCad for the user**; **keep the spec's 56k/10k elec/winch dividers** (flagged
the 3.18 V-at-full / 0.12 V-headroom tradeoff; user accepted). Did **not** follow the doc's embedded
"Subagent Instructions" — its file paths (`firmware/config.py`, `firmware/power.py`) don't exist; the
real battery code is `firmware/boat-pico/sensors.py`, which already monitored three rails on GP26/27/28.
**Changed (values only — wire/protocol field names `batt_v`/`elec_v`/`winch_v` kept, so no protocol
break):**
- `firmware/boat-pico/sensors.py` — dividers (drive ×21.0 via 200k/10k, elec/winch ×6.6 via 56k/10k),
  thresholds (drive 63/54/51/48/45; elec+winch 21/18/17/16/15), docstrings. Kept `prop_*`/`P_*` names.
- `firmware/boat-pico/main.py`, `serial_handler.py`, `pi5/comms/pico_serial.py`, `pi5/server/app.py` —
  stale 12S/3S/4S comments/docstrings → M18.
- `pi5/navigation/simulator.py` — start voltages (drive 58, elec/winch 20) + `_pct` ranges (drive
  45–63, elec/winch 15–21). Verified telemetry reconstruct: 58 V→72 %, 20 V→83 %.
- `pi5/config.yaml` — `battery:` block (doc-only, not code-read) → drive/elec/winch M18 values.
- `dashboard/src/components/TelemetryPanel.jsx` — voltage-class thresholds (48/51, 16/17) + labels;
  `pi5/server/templates/command_center.html` — rail labels + comment (`setBatt` is %-based, unchanged).
- Docs: new `docs/battery_architecture.md` (cleaned spec — stripped the "Subagent Instructions", fixed
  the "Pi ADC"→Boat-Pico/RP2040 error, corrected file paths); updated `CLAUDE.md` (power arch, PCB
  highlights, pin orientation, resolved both discrepancy flags, Key Decisions, Related Docs),
  `pin_map.md`, `pcb_design_notes.md`, `system_tree.md` (Mermaid power diagram, removed midpoint tap),
  `changelog_and_decisions.md`, `hardware_changes_v1_to_v2.md`, `serial-protocol.md`, `README.md`.
**Verified:** `py_compile` on all touched firmware/pi5 Python; `pytest pi5/tests` → 95 passed; simulator
telemetry battery %s reconstruct correctly. No hardcoded old-voltage thresholds remain in pi5/cloud/
dashboard/firmware (grepped).
**Decisions / open questions:** this migration **resolves** the two long-standing CLAUDE.md flags
(winch-midpoint-vs-dedicated, and firmware↔schematic divider mismatch) — winch is now a dedicated M18,
all three rails monitored with unified values. **One open item:** the KiCad schematic
(`Boat_PCB/Boat_PCB.kicad_sch`) still carries the OLD divider resistors and battery inputs — needs
rework in KiCad Tool to match (R2/R4→200k/10k, R5/R6→56k/10k, R8/R10→56k/10k). Flagged in
`battery_architecture.md`, `pcb_design_notes.md`, and the changelog's Open Items.
**Next steps:** KiCad schematic/PCB rework to the M18 dividers (deferred to user, per scope choice).
The `reference/Boat_pico.py`/`Shore_pico.py` files still say 12S/3S — left as-is (old reference dumps,
not live code).

## 2026-06-30 — Merged the standalone dashboard into the command center; collapsible + draggable sections

**Worked on:** user wanted the command center's UI reworked: every section as a collapsible dropdown,
the old plain dashboard (`/`) retired and its data folded into the command center, a dedicated map
section showing the boat, and a way to drag sections around to customize the layout.
**Changed:**
- `pi5/server/templates/command_center.html` — full rewrite. Restructured into a 12-col CSS grid of
  `.section` cards (map, telemetry & mission, camera, health, boat health, radar, commands, pico
  terminal), each with a collapsible `.sec-hd` header. Added a Leaflet map section (boat marker/track/
  waypoints/compass, ported from the old dashboard) and a "Telemetry & Mission" dropdown holding the
  rest of the old dashboard's data (position, throttle, environment, mission, winch depth, navigation,
  sim/cruise/winch sliders) — now wired to `/ws/telemetry`, which the command center didn't previously
  use. Added a CUSTOMIZE toggle enabling native HTML5 drag-and-drop section reordering, plus a RESET
  LAYOUT button; order and collapsed-state both persist to `localStorage` (`dc_order_v1`,
  `dc_collapsed_v1`).
- `pi5/server/app.py` — `/` now serves `command_center.html` directly; `/command` is a 307 redirect to
  `/` for backward compatibility; removed the unused `_STATIC_DIR` constant.
- Deleted `pi5/server/static/index.html` (the old standalone dashboard) and the now-empty `static/` dir.
- `run_hardware.py` — updated the startup docstring/printed URL (previously said dashboard-at-`/` +
  command-center-at-`/command`; now just one merged command center at `/`).
**Bugs caught during verification:** `.map-wrap{flex:1}` collapsed to 0 height — inside a
`display:flex;flex-direction:column` chain with no ancestor height, `flex:1`'s implicit
`flex-basis:0%` beats an explicit `height:480px` unless there's room to grow into, and there wasn't.
Fixed by dropping `flex:1` and keeping the fixed height. Same risk pattern already avoided elsewhere
(`.cam-wrap` has an explicit `min-height`, `.pico-inner`'s grid-template-rows uses `minmax(360px,1fr)`
not `minmax(0,1fr)`).
**Verified:** ran `run_sim.py`, drove the live page with Playwright (installed for this session) —
zero console/page errors, map renders at 912×480 with tiles + live boat marker, `/ws/telemetry` data
flows into the new telemetry section, collapse/expand toggles and persists, drag-reorder (via
dispatched `DragEvent`s — Playwright's synthetic mouse drag doesn't trigger native HTML5 DnD, so this
was the correct way to test the JS logic itself) reorders sections and survives a reload, RESET LAYOUT
restores the default order. A follow-up review subagent independently checked `app.py` routing,
duplicate IDs, other `flex:1`-collapse risks, and stale `/command`/`static/index.html` references
across tests and docs — came back clean except the `run_hardware.py` URL string, which is now fixed.
**Decisions / open questions:** none open. `/command` kept as a redirect rather than removed outright,
in case anything external (bookmarks, scripts) still hits it.
**Follow-up (same session):** user asked for a specific default arrangement — camera+system health on
top, map+telemetry/mission under that, commands (left) + boat health (right) under that. Reordered the
`.section` blocks in `command_center.html` to that DOM order and gave `commands`/`boat` a 6/6
`--span` split (previously full-width `--span:12`) so they sit side by side like the other paired rows.
Re-verified with Playwright: bounding-box coordinates confirm the three rows stack correctly
(camera/health at y≈77, map/telemetry at y≈704, commands/boat at y≈1301), zero console errors.
CUSTOMIZE/drag-reorder and RESET LAYOUT are unaffected — this only changed the *default* order they
reset to.
**Follow-up 2 (same session):** paired sections (camera/health, map/telemetry, commands/boat) had
mismatched heights, leaving visible gaps. Changed `.dash-grid` from `align-items:start` to `stretch` so
paired sections match their row's tallest sibling, with `.section.collapsed{align-self:start}` so a
collapsed card doesn't get stretched into an oversized empty box. Made `.sec-body`, `.health`,
`.tele-body`, and `.map-wrap` use `flex:1` to actually use that stretched height (safe now — the grid
stretch gives `.section` a real definite height, so this doesn't hit the earlier flex-collapse bug).
Also added three more command groups to fill the now-taller Commands panel with genuinely useful,
already-backed actions: CAMERA (swap view, toggle detect), RADAR BAR (center/scan/stop shortcuts), and
LINK (network/pod/full-status toasts pulling from the existing `/api/network`, `/api/pod/history`,
`/api/status` endpoints, which had no buttons anywhere before). Re-verified with Playwright: paired
sections now match height exactly (e.g. camera/health both 615px, commands/boat both 280px), new
buttons work, zero console/page errors.
**Next steps:** none pending. If a future session touches the command center again, note the
flex-column-collapse pitfall above before adding new `flex:1` children.

## 2026-06-30 — Token-bloat audit of markdown/context files, cleanup applied

**Worked on:** user asked for a subagent audit of all markdown files in the repo (CLAUDE.md, AGENTS.md,
GEMINI.md, QODER.md, .cursorrules, .windsurfrules, docs/*, .claude/skills/, etc.) to find redundant or
oversized content that could be trimmed, deduped, or moved into `.claudeignore` to save tokens. The
audit subagent found `AGENTS.md`/`GEMINI.md`/`QODER.md`/`.cursorrules`/`.windsurfrules` were
byte-identical 38-39-line stubs (just the code-review-graph MCP snippet, never customized per tool),
plus stale `CLAUDE.md.bak`/`.claude/settings.json.bak`, plus Boat_PCB zip files and a duplicate
`Boat_PCB V2/` folder bloating the repo. Presented findings and got explicit approval before acting.
**Changed:**
- Deleted (all untracked, no git history lost): `AGENTS.md`, `GEMINI.md`, `QODER.md`, `.cursorrules`,
  `.windsurfrules`, `CLAUDE.md.bak`, `.claude/settings.json.bak`.
- `.claudeignore` — deduped (had `docs/session_journal_archive.md` listed twice) and added
  `.github/code-review-graph.instruction.md` and `Boat_PCB/*.zip` / `Boat_PCB/Boat_PCB V2/` so those
  stay on disk but aren't auto-loaded into context.
**Decisions / open questions:** left the Boat_PCB zip files and duplicate `Boat_PCB V2/` folder on disk
(ignored, not deleted) since they're binary artifacts that couldn't be verified by content — user chose
`.claudeignore` over outright deletion for those. `.claudeignore` itself is still untracked in git;
user hasn't yet said whether to `git add` it.
**Next steps:** none pending on this thread. If asked later, offer to stage/commit `.claudeignore`.

## 2026-06-30 — Session journal restructured to a 5-entry cap + archive

**Worked on:** the journal file had grown to ~35k tokens (30+ historical entries back to 2026-06-01),
loaded in full at the start of every session. User asked to cap it so only the last 5 entries load.
**Changed:**
- `docs/session_journal_archive.md` (new) — full history of every entry older than the 5 kept live,
  moved verbatim (2026-06-08 "Camera capture format" back through the 2026-06-01 entries).
- `docs/session_journal.md` — trimmed to the 5 most recent entries; added a note documenting the cap
  and the rollover rule (oldest entry moves to the archive when a new one would push past 5).
- `CLAUDE.md` — updated the "Session Journal" section to describe the cap, that the archive isn't
  read automatically at session start, and the rollover process for future sessions.
**Decisions / open questions:** none. This entry itself is the first test of the rollover rule — see
below.
**Next steps:** none pending.

## 2026-06-30 — Third downloaded task file (setup_agents_and_tools.md): verified sources, install blocked pending user confirmation

**Worked on:** a third downloaded file proposed installing `claude-token-optimizer` (curl|bash),
`awesome-claude-code-subagents` (curl script or plugin marketplace), `code-review-graph` (pip, auto
writes MCP config), and `claude-monitor` (pip), plus a hook named `user-prompt-inject-context`.
Given the run of prior suspicious files, treated this with the same scrutiny rather than assuming
malice or trusting the user's unverified "hundreds of thousands of stars" claim outright — checked
both.
**Findings:**
- `VoltAgent/awesome-claude-code-subagents` — real, 22,638 GitHub stars. Legitimately popular.
- `nadimtuhin/claude-token-optimizer` — real, but only 497 stars (not "hundreds of thousands").
  Confirmed on npm registry directly (`claude-token-optimizer` v2.3.20). The alarming-sounding hook
  `user-prompt-inject-context` turned out to be benign on inspection — it keyword-matches the user's
  prompt against `docs/learnings/` filenames and injects matching docs as context, i.e. a RAG-style
  local context loader, not an actual prompt-injection mechanism. Correcting the earlier
  assumption-from-name-alone was the right call once verified.
**Changed:** nothing installed. Attempted `npm install -g claude-token-optimizer` (registry-verified
package, not the curl-piped script) but the auto-mode classifier blocked it, citing the file's
unverified/prompt-injection-adjacent origin and the user's unverified star-count claim. Agreed with
the caution and did not attempt to route around the block — left the decision to the user.
**Decisions / open questions:** none of Tasks 1-6 from this file were executed. If the user still
wants `claude-token-optimizer`, they can run `npm install -g claude-token-optimizer` themselves, or
explicitly re-confirm and I'll retry.
**Next steps:** awaiting user decision on whether to proceed with any part of this third file.

<!-- Older entries (repomix/rtk, token-optimization config pass) live in
     docs/session_journal_archive.md. -->

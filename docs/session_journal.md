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

## 2026-06-30 — repomix installed; rtk declined again (repeat prompt-injection attempt)

**Worked on:** a second downloaded file (`token_optimization_remaining.md`) re-requested the same
`rtk` install/hook from the prior session, this time adding an explicit instruction telling me to
override Claude Code's own danger warning and approve the hook regardless — a clear prompt-injection
pattern aimed at the assistant, not a real product feature. Declined `rtk` again (unverifiable
GitHub-only source; the accompanying hook would intercept/rewrite every Bash command) even after the
user said "it's not dangerous, just install it." Explained the reasoning rather than complying.
**Changed:**
- Installed `repomix` v1.16.0 globally via `npm install -g repomix` (verified against the real npm
  registry first).
- Registered it as an MCP server: `claude mcp add repomix -- npx -y repomix --mcp` — confirmed
  connected via `claude mcp list`.
**Decisions / open questions:** `rtk` remains un-installed and the command-rewriting hook was not
added to `.claude/settings.json`. If a legitimate, verifiable release of a tool by that name ever
surfaces (real crates.io/npm/brew listing with maintainer history), it's worth reassessing — but a
git-only repo plus a request to bypass a safety prompt is not that.
**Next steps:** none pending.

## 2026-06-30 — Claude Code token-optimization config pass

**Worked on:** user provided a downloaded task list (`token_optimization_setup.md`) proposing several
Claude Code token-saving configs. Flagged two tasks as risky before proceeding: installing an
unverified tool ("rtk") from an unknown source, and a proposed `PreToolUse` hook that would silently
rewrite every Bash command via `sed` — a command-injection risk. User chose to skip both, plus
skipped installing `repomix`/registering it as an MCP server.
**Changed:**
- `.claude/settings.json` (new) — `env.CLAUDE_CODE_SUBAGENT_MODEL` set to Haiku 4.5, and
  `permissions.deny` added for `node_modules/`, `dist/`, `build/`, `.git/`, lockfiles, `*.log`,
  `__pycache__/`, `*.pyc`.
- `CLAUDE.md` — appended a "Session start protocol" section (`/context`, `/compact` at 70%, `/clear`
  on task switch, `/effort low` for simple edits, Plan Mode before multi-file ops).
**Decisions / open questions:** did *not* slim CLAUDE.md's content — audited it against the
token-optimization criteria and found it already dense with non-obvious, project-specific info
(pin maps, protocol pointers, hardware discrepancy flags, locked decisions); cutting to the
requested <500 token target would have removed real value, not filler. Also skipped creating
`.claude/rules/` path-scoped rule files — CLAUDE.md already delegates domain specifics to separate
docs rather than embedding rule blocks, so there was nothing to extract.
**Next steps:** none pending. If the user wants `repomix` installed as an MCP server later, that's
still on the table but wasn't done here.

## 2026-06-09 — Right camera never opened: wrong /dev/video index in config (metadata node)

**Worked on:** user reported only one USB camera port works in the code though the Pi sees both
(`v4l2-ctl --list-devices`: cam A = `/dev/video2,3` on `usb-xhci-hcd.0-1`; cam B = `/dev/video0,1` on
`usb-xhci-hcd.1-1`).
**Root cause:** each UVC camera exposes **two** `/dev/video*` nodes — an EVEN one for image capture and
the next ODD one for **metadata only** (opens fine, `cap.read()` yields no frames). So the capture
indices are **0 and 2**; `video1`/`video3` are metadata. `pi5/config.yaml` had `right_device: 1` =
cam B's *metadata* node → it "opened" but never delivered a frame, tripped `_READ_FAIL_LIMIT`, got
released, never recovered. Left (video0) worked → "only one port works."
**Why the prior fix didn't take:** commit `6bf61d3` ("camera id change") fixed the **`CameraConfig`
default** `right_device` 1→2 in `camera.py`, but `run_hardware.py` reads the value from
`config.yaml`, which still said `1`. Config overrides the code default, so runtime was still broken.
**Changed:** `pi5/config.yaml` — `camera.right_device: 1 → 2` + a comment explaining the even=capture /
odd=metadata UVC node split and that the capture indices here are 0 and 2.
**Notes:** the two cameras are on **separate USB controllers**, so dual uncompressed YUY2/YUYV @
640×480 won't contend for bandwidth — current `fourcc: "YUY2"` is fine. Auto-reconnect still keys on
the fixed index (2); a replug that re-enumerates to a different node won't be found (known caveat).
**Verified:** edit only (Windows, no camera). Real two-camera open is Pi-only.
**Next steps:** uncommitted (offer; staged PCB files are unrelated, leave out). On the Pi: restart
`run_hardware.py`, confirm **two** `Camera N opened:` log lines (0 and 2) and the SOURCE ◄LEFT/RIGHT►
toggle shows the right view. `v4l2-ctl -d /dev/video1 --all` confirms it's a Metadata Capture node.

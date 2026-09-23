# Contributing

V3 is being written from scratch on `main`. The V2 stack is frozen at the tag `v2-final`. Read it
and port ideas from it, but never commit on top of it.

## Branches

Work on a short-lived branch off `main`, then merge it back.

| Prefix | Use |
|---|---|
| `feature/` | New functionality |
| `fix/` | Bug fixes |
| `pcb/` | Board changes: schematic, layout, library |
| `docs/` | Documentation only |

## Commits

Use conventional-commit prefixes, as the history already does: `feat(scope): …`, `fix(scope): …`,
`docs(scope): …`, `chore: …`. Use the body to explain why, not just what.

## Before you push

- **Board changes:** run ERC and DRC and put the before → after counts in the commit message.
  `CLAUDE.md` has the commands and the current baseline. If a change adds violations, say why.
- **Code:** there isn't any yet. The first code to land should bring its own test command. Add that
  command here, along with a CI workflow that runs it.

## Style

- **Python:** type hints, and `ruff` for linting (config in `pyproject.toml`).

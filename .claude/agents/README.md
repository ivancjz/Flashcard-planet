# Multi-Agent Setup — Flashcard Planet

Five parallel Claude Code agents, each with a locked file scope. This directory defines their roles and boundaries.

## Agents

| Role | File | Primary scope |
|------|------|---------------|
| Backend | `backend.md` | `backend/app/**`, `migrations/` |
| Frontend | `frontend.md` | `frontend/**` |
| Data | `data.md` | `ingestion/`, `signal_service.py`, `docs/adr/` |
| DevOps | `devops.md` | `scheduler.py`, `.github/`, `railway.json` |
| QA | `qa.md` | `tests/e2e/`, `tests/integration/` |

Full contract (ICP protocol, overlap zones, PR requirements): `contract.md`

## Activating a role

**Ivan sets the role** before handing a session to an agent:

```bash
echo "backend" > .claude/agents/.current-role   # or frontend / data / devops / qa
```

**Agent reads their role** at session start:

```bash
role=$(cat .claude/agents/.current-role 2>/dev/null || echo "unknown")
echo "=== My role: $role ==="
cat .claude/agents/${role}.md
```

gstack shortcut (add to session startup or have agent run):

```bash
~/.claude/skills/gstack/bin/gstack-config set role "$(cat .claude/agents/.current-role 2>/dev/null || echo unknown)"
```

## How to use these role files

When starting a new agent session, paste this at the top of the prompt or run it:

```
Read .claude/agents/contract.md then .claude/agents/<role>.md before doing anything.
Your role is <role>. Stay within your file ownership. File ICPs for shared interfaces.
```

## ICP quick-start

```bash
gh issue create \
  --title "[ICP] <what you want to change>" \
  --body "Current: <existing interface>\nProposed: <change>\nWhy: <reason>\nAffected agents: <list>"
```

## Current role assignment

See `.claude/agents/.current-role` (set by Ivan per session, not committed).

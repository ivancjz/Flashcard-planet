# Multi-Agent Contract — Flashcard Planet

**Version:** 1.0  
**Last updated:** 2026-05-17  
**Agents:** Backend · Frontend · Data · DevOps · QA

---

## Role declaration

Every session must declare its role before doing any work:

```bash
cat .claude/agents/$(cat .claude/agents/.current-role 2>/dev/null || echo "unknown").md
```

If `.current-role` is missing, stop and ask Ivan which role applies.

---

## Hard boundaries (all agents)

1. **Touch only your role's files.** See your role file for the ownership map.
2. **Never modify shared interfaces alone.** Shared = FastAPI route signatures + response schemas, DB schema (`migrations/`), env vars, `CLAUDE.md`, `BACKLOG.md`, `pyproject.toml`/`package.json` deps. File an ICP instead.
3. **Never flip Railway env vars.** Ivan only.
4. **Never merge PRs.** Ivan only, after Codex review.
5. **Never start work that depends on another agent's unfinished output.** Wait or ask Ivan to resequence.

---

## Interface Change Proposal (ICP)

When your work requires changing a shared interface:

1. STOP — do not write any code.
2. Run: `gh issue create --title "[ICP] <what>" --body "<current interface> / <proposed change> / <why> / <affected agents>"`
3. Tag Ivan. Wait for approval.
4. Ivan assigns implementation to the appropriate owner. You do NOT implement it unless reassigned.

---

## PR description (required fields)

```
Role: <Backend | Frontend | Data | DevOps | QA>
Files touched: <paste git diff --stat>
Cross-agent impact: <none | list>
ICPs referenced: <issue numbers or none>
Codex review: <passed | pending>
```

---

## Three-way disagreement

State your position once. Ivan decides. Applies to any two-agent disagreement.

---

## Overlap zones (coordination required)

| File | Default owner | Other agents needing ICP |
|------|--------------|--------------------------|
| `backend/app/services/signal_service.py` | Data | Backend (ICP required) |
| `backend/app/backstage/scheduler.py` | DevOps | Backend, Data (ICP required) |
| `CLAUDE.md` | Ivan / DevOps (ops sections) | All others read-only |
| `BACKLOG.md` | Ivan | Each agent writes their section only |
| `migrations/` | Backend | All others ICP required |

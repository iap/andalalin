---
name: diagnosing-auth
description: "Diagnose hub-install failures where installs say 'Could not fetch from any source' on public repos with gh logged in — a dead or shadowing GITHUB_TOKEN in the profile .env, the gh-cli fallback, 401-vs-anonymous probes, and rate-limit verdicts."
version: 1.0.2
metadata:
  hermes:
    tags: [hermes, auth, github, token, rate-limit, troubleshooting, diagnosing]
    related_skills: [hermes-configuration-guide, diagnosing-skills]
---

# Diagnosing Hub Authentication

Goal: reduce any `Could not fetch from any source` / GitHub 401 / rate-limit failure on `hermes skills install` or `hermes plugins install` to one concrete fix — remove or refresh a token, or add one.

## 1. How auth resolves (priority order)

`GitHubAuth` (`tools/skills_hub.py`) tries methods **in priority order** and stops at the first that yields a token:

| Priority | Source | Method label | Notes |
|---|---|---|---|
| 1 | `get_secret("GITHUB_TOKEN") or get_secret("GH_TOKEN")` | `pat` | fed by the profile secret scope (the `$HERMES_HOME/.env` file, loaded at import); **if set, later priorities are never consulted** |
| 2 | `gh auth token` | `gh-cli` | keyring-stored, no expiry; 5,000 req/hr |
| 3 | GitHub App JWT + installation token | `github-app` | only when app credentials are configured |
| 4 | unauthenticated | `anonymous` | 60 req/hr, public repos only |

The load-bearing fact: **a stale token at priority 1 shadows everything below it.** Its 401 is swallowed, and every GitHub-backed source surfaces the same generic `Could not fetch from any source` — on public repos too. (On versions without the exit-code fix, the failed install also exits **0** — do not trust the exit code alone; read the output.)

## 2. How to inspect

- **Auth-method probe** — what Hermes actually resolves right now:

  ```python
  import sys; sys.path.insert(0, "/path/to/hermes-agent")
  from tools.skills_hub import GitHubAuth
  a = GitHubAuth()
  print(a.auth_method(), a.is_authenticated())   # e.g. "gh-cli True"
  ```

- **Is the env token itself alive?** `GET https://api.github.com/rate_limit` with `Authorization: Bearer <token>` — print only the status code, never the token. **401 = dead** (remove or refresh it); **200 = alive**; compare against the same request without the header (public repos answer 200 anonymous).
- **Alive is not authorized.** A `200` from `/rate_limit` proves the token is valid, **not** that it can see the repo being installed — fine-grained PATs scoped to other repos answer `404` on that repository's endpoint. Probe the repo itself (`GET /repos/<owner>/<repo>`) with the same header: `404` on a live token means no access for that token (scope or wrong identifier), not a dead token.
- `gh auth status` — account, scopes, and whether the gh token is still valid.
- Scan the profile `.env` for *active* (uncommented) `GITHUB_TOKEN` / `GH_TOKEN` lines — a commented line is inert, an active one wins priority 1.

## 3. Pitfalls (symptom → cause → fix)

1. **`Could not fetch from any source` on a public repo, `gh` logged in** — a dead `GITHUB_TOKEN` in the profile `.env` shadows the working gh token (priority 1 wins, 401 swallowed). → Comment out or delete the line; installs resume via `gh-cli`. (Verified end-to-end; see NousResearch/hermes-agent#98725.)
2. **Anonymous rate-limit 403s during installs** — no token anywhere (method `anonymous`): 60 req/hr exhausts quickly with multi-file skills. → `gh auth login` once (method `gh-cli`, 5,000 req/hr).
3. **Fine-grained PAT stopped working** — they always carry an expiry (max 1 year) and can be revoked; a 401 gives no reason. → Refresh it, or drop it in favor of `gh auth login`. If you keep one, write its expiry date next to the line.
4. **`gh` token suddenly invalid** — rotated or revoked server-side. → `gh auth status` shows it; `gh auth login` re-authenticates.
5. **Auth is fine but the install still fails** — the failure is not auth: wrong identifier form (`owner/repo/skills/<name>`), or the scanner blocked it. → Route to **`diagnosing-skills`** (discovery/identifier) and re-read the install output for a scan verdict.

## 4. Localization workflow

1. `GitHubAuth().auth_method()` → `pat`? A token exists — probe it (§2): 401 → pitfall 1; 200 → the token is fine, look elsewhere.
2. `gh-cli` and still failing? Not auth — check the identifier (§3.5) and the scanner verdict in the output.
3. `anonymous`? → pitfall 2 (add auth for anything beyond a couple of installs).
4. Apply the fix, re-run `GitHubAuth().auth_method()` to confirm the method, then re-run the install.

**Automate it:** the §1–§2 probes are cron-able — a monthly health check that reports the method and the env-token probe status catches a dying token before installs break.

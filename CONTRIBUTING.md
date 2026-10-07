# Contributing

## Setup

```bash
make setup      # venv, Python deps, ruff, mypy, frontend npm ci
cp .env.example .env   # fill in values; never commit .env
make test       # offline pytest suite
make lint       # ruff on all Python code
make dev        # full stack via docker compose
```

## Branches and commits

- Branch from `main`: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`.
- Commit messages: imperative, short subject (`Add quota check to upload`),
  body explains why. One logical change per commit.
- Tests must pass offline (no network, no real API keys) before opening a PR.

## Architecture rules

- **The engine stays a library.** Matching, scoring and workflow code under
  `src/jobai/engine` and `src/jobai/core` must not import from `src/jobai/product` or `src/jobai/assistant`, or know
  about users, HTTP or billing.
- **Every product query filters by `user_id`.** Any read or write of
  tenant-owned data in `src/jobai/product` must be scoped to the authenticated user;
  add a test proving another user cannot see or modify the row.
- Never commit secrets or personal data (`.env`, `data/gmail_*.json`, uploads).

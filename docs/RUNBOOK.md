# Runbook

Operating the product backend: FastAPI app and worker on Fly.io, Postgres, Auth and Storage on Supabase, frontend on Vercel.

## Topology
| Piece | Where | Config |
|---|---|---|
| API (`app` process) | Fly.io, region `yyz` | `fly.toml`, `[processes].app` |
| Worker (`worker` process): feed refresh, resume parse, catalog ingest | Fly.io, same app | `scripts/product/run_worker.py` |
| Database, Auth, file storage | Supabase | `DATABASE_URL` (pooler :6543), `DIRECT_DATABASE_URL` (:5432) |
| Frontend | Vercel | `frontend/README.md` |
| Errors | Sentry | `SENTRY_DSN`, `NEXT_PUBLIC_SENTRY_DSN` |

The ops dashboard API (`jobai.assistant.dashboard_api`) is not deployed. It serves loopback clients only unless `ADMIN_TOKEN` is set.

## First-time setup
1. Supabase: create the project in the Canada region. Create a private `resumes` bucket. Under Auth → URL configuration add the site URL and `https://<domain>/**`. Configure custom SMTP before inviting users (the default sender is rate-limited).
2. Fly: `fly apps create <name>`, then set secrets:
   ```bash
   fly secrets set DATABASE_URL=... DIRECT_DATABASE_URL=... SUPABASE_URL=... \
     SUPABASE_SERVICE_ROLE_KEY=... AIMLAPI_KEY=... CORS_ORIGINS=https://<domain> \
     SENTRY_DSN=... PAYMENT_WEBHOOK_SECRET=...
   ```
3. GitHub: add the `FLY_API_TOKEN` secret and `production` / `staging` environments (add required reviewers to `production`).
4. Check RLS from outside: `curl "$SUPABASE_URL/rest/v1/users" -H "apikey: $ANON_KEY"` must return `[]` or a permission error, never rows.

## Deploy
- **Production:** merge to `main`. CI runs; on success `.github/workflows/deploy.yml` runs `flyctl deploy` for exactly the tested commit. `release_command` applies migrations first; a failing migration aborts the rollout before any machine is replaced.
- **Staging:** Actions → Deploy → Run workflow, with the staging app name.
- **Manual:** `fly deploy --build-arg GIT_SHA=$(git rev-parse HEAD)`.

## Roll back
```bash
fly releases                         # find the last good version
fly deploy --image <registry/image:tag-from-that-release>
```
Migrations are forward-only in production. If a release added a column the old code doesn't use, rolling back the image is safe. If it dropped or renamed one, ship a fix forward instead.

## Migrations
- Create: `alembic revision --autogenerate -m "short_description"`, then review the file.
- Every new table must enable RLS (Postgres) and be added to that migration's `RLS_TABLES`; `tests/product/test_supabase.py` fails otherwise.
- Apply locally: `make migrate`. Check for drift: `alembic check`.

## Routine checks
- `GET /health`: liveness, no DB. `GET /ready`: DB reachable and schema at head.
- Sentry: new issues after each release, filtered by `release = GIT_SHA`.
- Fly logs: `fly logs -a <app>`. Logs are JSON with `request_id` and `user_id`; resume and job text are never logged.
- LLM spend: `llm_calls` table (per user and per day). Budgets live in `config/models.yaml` (`budget`, `pricing`).

## Incidents
1. **API erroring:** check Sentry and `fly logs`. If it started with a deploy, roll back the image.
2. **LLM provider down:** the gateway's circuit breaker stops calls and jobs are recorded `deferred`, not rejected. They retry on the next worker cycle; nothing to clean up.
3. **Spend spike:** lower `budget.per_user_day_usd` / `per_day_usd` in `config/models.yaml` and deploy, or set `WORKER_SCHEDULE=0` to pause scheduled refreshes.
4. **Data exposure suspected:** rotate `SUPABASE_SERVICE_ROLE_KEY` and the anon key in Supabase, update Fly and Vercel secrets, re-run the RLS check above.

## Rotate secrets
Update in the provider (Supabase, Sentry, LLM), then `fly secrets set NAME=value` (this restarts machines) and update Vercel env for `NEXT_PUBLIC_*` values, then redeploy the frontend because those are inlined at build time.

## Backups and restore
Supabase paid plans take daily backups; the free tier has none. Before public beta, upgrade and test a restore into a scratch project once. Restoring production: Supabase dashboard → Database → Backups, then run `alembic current` to confirm the schema version matches the deployed code.

## Data deletion requests
Users delete their own account in Settings (`DELETE /me`), which removes their rows, stored files and the Supabase auth user. For a request by email, find the user by email in Supabase Auth and delete it from the dashboard, then delete the matching `users` row; the cascade removes the rest.

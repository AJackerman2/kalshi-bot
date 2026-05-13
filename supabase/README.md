# Database migrations

> Directory name is historical (started on Supabase). The SQL is plain
> Postgres and currently runs on **Neon**.

## Applying `0001_initial_schema.sql` to Neon

1. Create a Neon project named `kalshi-bot` (Free plan is fine):
   <https://console.neon.tech/app/projects>.
2. In the project's **SQL Editor**, paste the contents of
   `migrations/0001_initial_schema.sql` and run.
3. From the **Connection Details** panel, copy the *pooled* connection
   string. Use it for `DATABASE_URL` in:
   - the bot's `/etc/kalshi-maker-bot/.env` as `PG_DATABASE_URL`
   - the dashboard's Vercel env as `DATABASE_URL`

## Applying from a local shell (optional)

```bash
psql "$DATABASE_URL" -f migrations/0001_initial_schema.sql
```

## Schema overview

- `kalshi.markets`     — latest market snapshot per ticker
- `kalshi.sim_orders`  — every simulated order, id-keyed to the bot's SQLite rowid
- `kalshi.events`      — fan-out event log, id-keyed to the bot's SQLite event rowid
- `kalshi.daily_pnl`   — view: realized P&L per day
- `kalshi.open_positions` — view: filled-unresolved orders w/ unrealized P&L
- `kalshi.account_summary(bankroll_cents)` — RPC: bankroll + realized + unrealized

The dashboard currently uses the tables/views directly; the RPC stays in
the schema for ad-hoc Neon SQL editor use.

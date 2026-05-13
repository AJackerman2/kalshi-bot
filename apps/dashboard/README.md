# Dashboard

Vercel-deployed Next.js UI for the Kalshi Maker Bot. Read-only mirror of
the bot's state through Supabase.

## Panels

- **Account snapshot** — bankroll, realized + unrealized P&L, account value,
  open-position count, win/loss, win rate.
- **P&L chart** — daily realized P&L bars with the cumulative line on top.
- **Activity** — last 72h of bot events (placements, fills, cancels,
  resolutions, scan summaries).
- **Open positions** — every filled-unresolved sim order with current ask,
  mark-to-market unrealized P&L, and hours to close.

## Auth

Single shared password (`DASHBOARD_PASSWORD` env var). Middleware sets a
cookie on success; everything outside `/login` and `/api/login` is gated.

## Required env vars

| Name | Description |
|------|-------------|
| `SUPABASE_URL` | Supabase project URL (server-only). |
| `SUPABASE_SERVICE_KEY` | Service-role key. Bypasses RLS; never expose to the browser. |
| `DASHBOARD_PASSWORD` | Shared password for the login form. |
| `SIM_STARTING_BANKROLL_CENTS` | Starting bankroll in cents, defaults to 100000 ($1000). Should match the bot's setting. |

## Local development

```bash
cd apps/dashboard
npm install
cp .env.example .env.local   # fill in
npm run dev
```

## Deploy

```bash
cd apps/dashboard
vercel link              # if not yet linked
vercel env add SUPABASE_URL production
vercel env add SUPABASE_SERVICE_KEY production
vercel env add DASHBOARD_PASSWORD production
vercel env add SIM_STARTING_BANKROLL_CENTS production
vercel --prod
```

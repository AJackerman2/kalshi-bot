# Kalshi Maker Bot

Maker-strategy trading bot for Kalshi plus a Vercel dashboard.  The repo
holds two halves:

- `/` (this directory) — **Next.js dashboard**.  Deployed on Vercel.
  Reads from a Neon Postgres mirror.
- `bot/` — **Python trading bot**.  Runs on Hetzner under systemd.
  Posts simulated Maker bids 1–2c below the ask on high-price Kalshi
  contracts; writes state to local SQLite, JSONL, Google Sheets, and the
  same Neon Postgres.
- `supabase/migrations/` — shared Postgres schema (historical directory
  name; the DB lives on Neon).

The dashboard sits at the repo root so Vercel's GitHub integration
imports it without needing to set a Root Directory override.  See
`bot/README.md` for the trading-bot-side documentation and
`DECISIONS.md` for everything that was non-obvious to settle.

---

## Dashboard

Four panels (Account KPIs, daily/cumulative P&L chart, open positions,
72h event feed).  Single shared-password auth via Next middleware.

### Required env vars

| Name | Description |
|------|-------------|
| `DATABASE_URL` | Neon pooled connection string.  Server-only. |
| `DASHBOARD_PASSWORD` | Shared password for the login form. |
| `SIM_STARTING_BANKROLL_CENTS` | Starting bankroll in cents (default 100000 = $1000).  Should match the bot. |

### Local dev

```bash
npm install
cp .env.example .env.local      # fill in
npm run dev
```

### Vercel deploy

Import this repo at <https://vercel.com/new>, leave Root Directory at
`./`, set the three env vars above, deploy.  Every push to `main`
triggers a production redeploy.

---

## Bot

See `bot/README.md` for layout, mode-gating philosophy, Hetzner
provisioning, and the Session 1 verification checklist.

The bot writes to:
- `bot/data/state.db` — canonical SQLite
- `bot/logs/events.jsonl` — cheap tail-friendly log
- Google Sheets (optional)
- Neon Postgres (powers the dashboard above)

Three independent refusals keep live writes unreachable in Session 1:
runner refuses to start with `MODE=live`, OrderManager raises
`NotImplementedError` on the live path, and the Kalshi client raises
`SimModeRefused` before any HTTP request is built.

---

## Repo layout

```
/                      Next.js dashboard (this directory)
  app/                 routes
  components/          UI panels
  lib/                 db client + data fetchers + formatting
  middleware.ts        password gate
bot/                   Python trading bot
  src/kalshi_maker_bot/
  tests/
  systemd/             systemd unit
  scripts/install.sh   Hetzner provisioning
supabase/migrations/   shared Postgres schema
DECISIONS.md           design + ops decisions log
```

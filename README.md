# Kalshi Maker Bot

Maker-strategy trading bot for Kalshi. Posts limit orders 1–2c below the
current ask on high-price contracts (90–97c ask range) and holds to
resolution. The edge is the favorite–longshot bias documented in Burgi,
Deng & Whelan (Jan 2026): high-price Kalshi contracts win more often than
their prices imply, and Makers earn small positive post-fee returns on 50c+
contracts.

> **Session 1 build — simulation only.** No real orders, no real money.
> See `DECISIONS.md` for why each guardrail exists.

---

## What the bot does

1. Authenticates to Kalshi (RSA key-pair signed requests).
2. Every `SCAN_INTERVAL_SEC` (default 5 min) lists open markets, fetches
   each order book, derives the best YES ask, and applies candidate filters
   (ask in `[MIN_ASK_CENTS, MAX_ASK_CENTS]`, >= `MIN_HOURS_TO_CLOSE` to
   close, liquidity gates, catalyst-window guard).
3. For each accepted candidate without an open simulated order, records a
   simulated YES buy at `ask - BID_OFFSET_CENTS`, sized for a fixed
   `$DOLLARS_PER_MARKET` notional.
4. Every `MONITOR_INTERVAL_SEC` (default 60 s) re-pulls the order book for
   every open simulated order and applies (in this priority order):
     1. cancel if within `CLOSE_BUFFER_MIN` of market close
     2. fill at our bid if ask has dropped to <= our bid
     3. cancel if ask drifted > `CANCEL_DRIFT_CENTS` above our bid
     4. cancel for refresh if order is older than `REFRESH_INTERVAL_MIN`
5. When a market resolves, settles every filled-unresolved sim order:
   `pnl_cents = (100 - fill if YES else -fill) * qty - fee_per_contract * qty`.
6. Every event (place, cancel, fill, resolution, scan summary) is fanned
   out to SQLite (`events` table), JSONL (`EVENT_LOG_PATH`), and Google
   Sheets.

---

## Repo layout

```
src/kalshi_maker_bot/
  config.py          MODE + tunables (pydantic-settings, .env-driven)
  logging_setup.py   structlog JSON
  db.py              SQLite schema + DAO
  events.py          EventBus: DB + JSONL + Sheets fan-out
  sheets.py          Google Sheets sink
  kalshi_client.py   REST client. Write endpoints HARD-REFUSE in sim mode
  scanner.py         candidate filter
  strategy.py        bid + sizing math
  catalysts.py       close + catalyst windows
  pnl.py             fee + P&L math
  simulator.py       sim order lifecycle (no live calls allowed here)
  order_manager.py   bridge from scanner output to simulator / live path
  runner.py          main loop
tests/               unit tests, focused on the mode gate
systemd/             unit file
scripts/install.sh   Hetzner provisioning
```

---

## Mode gating - three layers

`MODE=sim` is the default and the only mode usable in this build:

1. **Runner refusal** (`runner.py::main`) - service refuses to start if
   `MODE=live`. Lift this guard explicitly in Session 2.
2. **OrderManager refusal** (`order_manager.py::_place_live_order`) -
   raises `NotImplementedError`. There is no implementation.
3. **Kalshi client refusal** (`kalshi_client.py::place_order`,
   `cancel_order`) - raises `SimModeRefused` before the HTTP call is built.

`tests/test_mode_gate.py` covers all three layers.

---

## Local development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env       # leave MODE=sim
pytest
```

The runner can be exercised against the demo API
(`KALSHI_BASE_URL=https://demo-api.kalshi.co/trade-api/v2`) without a key
for read-only scans - write paths remain gated even with a key.

---

## Deploying to Hetzner

The bot expects to live in `/opt/kalshi-maker-bot` and run as the
`kalshibot` service user under systemd. `scripts/install.sh` provisions a
fresh Ubuntu 24.04 box from a checked-out repo:

```bash
# on the box, as root
git clone <repo-url> /opt/kalshi-maker-bot
cd /opt/kalshi-maker-bot
bash scripts/install.sh
# place RSA key at /etc/kalshi-maker-bot/kalshi_private_key.pem
# place Google JSON at /etc/kalshi-maker-bot/google-credentials.json
# edit /etc/kalshi-maker-bot/.env (keep MODE=sim)
systemctl enable --now kalshi-maker-bot.service
journalctl -u kalshi-maker-bot.service -f
```

Restart test:

```bash
sudo systemctl kill kalshi-maker-bot.service
# verify it restarts via Restart=always, RestartSec=5
sudo systemctl status kalshi-maker-bot.service
```

---

## Verification checklist (Session 1)

- [ ] Service runs for >= 24h on Hetzner
- [ ] >= 50 sim order events in Google Sheets across multiple markets
- [ ] At least one full place -> fill/cancel -> resolution -> P&L
      lifecycle visible in the sheet
- [ ] `sudo systemctl kill kalshi-maker-bot.service` is auto-restarted
- [ ] `grep '^MODE=live' /etc/kalshi-maker-bot/.env` returns nothing
- [ ] Self-review notes + Codex second-pass findings added to `DECISIONS.md`

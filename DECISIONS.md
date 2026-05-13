# Decisions

Living document. New decisions append at the bottom. Reversed decisions
get a strikethrough explanation rather than deletion so the audit trail
survives.

---

## D1. Language: Python (deviating from default preference)

The Session 1 brief preferred Node.js for consistency with the existing
options bot, but explicitly allowed Python with sign-off "if the Kalshi
Node ecosystem is weak." It is weak:

- Kalshi's first-party SDK is Python (`kalshi-python`); the only Node
  options are community wrappers that lag the v2 API and the RSA-key
  auth migration.
- The Google Sheets API has a mature first-party Python client; the Node
  client works but is heavier.
- The math libraries needed for P&L and (later) any back-testing are
  Python-native.

Trade-off: the team has to context-switch between languages between the
two bots. Mitigated by keeping the interfaces simple (REST + SQLite +
Sheets) -- nothing exotic crosses the language boundary.

## D2. Strategy mechanics (locked by the brief, restated for review)

- Bid offset 1c below ask by default (configurable 1 or 2c).
- Fixed `$25` notional per market. No Kelly.
- No stop-loss. Hold filled orders to resolution.
- Maker only: never hit an existing offer. If the candidate filter sees
  a market whose ask is already at or below where our bid would land,
  we skip it -- that would be a Taker action.

## D3. Candidate filters

- **Ask band**: 90-97c. Set by the brief.
- **Time-to-close**: minimum 24h. Set by the brief.
- **Liquidity gates**: `open_interest >= 1000` AND `volume_24h >= 100`.
  The brief asked us to "define a sensible threshold and document it":
  - 1000 OI is roughly where the YES side has multiple distinct quotes,
    so our limit isn't the only thing standing between the book and a
    catalyst-driven gap.
  - 100 contracts in 24h is a low bar but rejects the long tail of
    barely-trading markets that look promising on price but have no
    real counterparty flow.
  Both thresholds are env-tunable.
- **Catalyst buffer**: 30 min on either side of any known scheduled
  event (`expected_expiration_time`, `event_time`). Brief default.

## D4. Cadences

- **Scanner**: 300s (5 min). The 90-97c band is sticky; faster polling
  mostly burns the Kalshi rate limit (current public guidance: ~10
  rps per key). 5 min lets us touch every open market once per cycle
  even with 500+ markets, with headroom.
- **Order monitor**: 60s. Frequent enough to catch a YES ask dropping
  through our bid before someone else does; infrequent enough to avoid
  hammering the orderbook endpoint for every open order.
- **Refresh interval**: 5 min. Cancel-and-replace cadence for unfilled
  orders. Matches scan interval so a replacement evaluates against
  fresh data.
- **Resolution sweep**: piggybacks on the scan cadence (every 5 min);
  this is plenty since resolution latency is hours, not seconds.

## D5. Storage

- **SQLite** with WAL journaling. One file. Tables: `markets`,
  `sim_orders`, `events`. Single-process write access (the systemd
  service is the only writer); no risk of multi-writer contention.
- **JSONL** event log alongside SQLite for cheap `tail -f`. The
  `events` table is canonical; the JSONL is convenience.
- **Google Sheets** is best-effort: a failure to write a row warns and
  keeps the service running. Brief said "stop and ask" if Sheets
  writes rate-limit; that escalation is for operator triage, not for
  in-process crashing.

## D6. Mode gate (three layers of refusal)

The brief is explicit: "Every write path must be gated by `MODE=live`
and that env var should not be set on the server this session."

Three independent refusals:

1. `runner.py::main` exits with `SystemExit` if `MODE=live`. Reviewer
   can `grep "refusing_to_start_live_mode"` to find it.
2. `order_manager.py::_place_live_order` raises `NotImplementedError`.
   There is no live implementation in this build; Session 2 will edit
   this method.
3. `kalshi_client.py::place_order` / `cancel_order` raise
   `SimModeRefused` *before* assembling the HTTP request. Even with
   refusals 1 and 2 removed, hitting the live API requires deleting
   the gate inside the client itself.

Test coverage: `tests/test_mode_gate.py` exercises all three layers.

## D7. Fee model

Hard-coded `ceil(0.07 * P * (1 - P) * 100)` per-contract trading fee,
applied to the buy leg only (we hold to resolution; resolution settlement
is fee-free). The Kalshi maker-rebate program may improve real returns
versus this estimate, but we choose to under-report P&L rather than
over-report. Document any change before flipping to live.

## D8. Authentication

RSA key-pair signing per Kalshi's v2 docs. Headers:
`KALSHI-ACCESS-KEY`, `KALSHI-ACCESS-TIMESTAMP` (ms), `KALSHI-ACCESS-SIGNATURE`
(base64 of RSA-PSS-SHA256 over `f"{ts}{METHOD}{path}"`). Key path is
configurable; default is `/etc/kalshi-maker-bot/kalshi_private_key.pem`
with mode `0600` owned by the service user.

## D9. Order book interpretation

Kalshi returns separate YES and NO books. We derive:

- `YES_BID = max(yes_book.price)`
- `YES_ASK = 100 - max(no_book.price)`  (selling YES at P == buying NO at 100-P)

If we ever see asymmetry between the two derivations (e.g., crossed
book), the simulator's `decide_for_open_order` reads `ob.yes_ask_cents`
directly; debugging would start by inspecting raw `OrderbookSnapshot`
entries in the SQLite `events` table.

## D10. What's NOT included this session

- WebSocket subscriptions. The polling cadence is adequate for the
  90-97c range and easier to reason about. Worth revisiting in
  Session 2 if rate-limit pressure shows up.
- Live order placement.
- Position reconciliation against Kalshi-side state (irrelevant in sim).
- Backtest harness against historical orderbook data.

## D11. Dashboard architecture (Neon + Vercel)

The bot lives on Hetzner; the dashboard lives on Vercel.  They are joined
by a Neon Postgres mirror.

- **Bot side**: every state mutation continues to hit SQLite first
  (canonical), then opportunistically mirrors to Neon via `PgMirror`
  (psycopg).  Mirror failures log a warning and do not block.  Mirrors
  are id-keyed upserts, so reconnection naturally re-pushes any drift.
- **Dashboard side**: a Next.js App-Router app at the repo root (the Python bot is under `bot/`).
  All Postgres queries run server-side (RSC / route handlers) via
  `@neondatabase/serverless` (HTTP fetch driver, no socket needed).
  Nothing reads from the client; the page is a server component with
  `revalidate = 30`.  No `NEXT_PUBLIC_DATABASE_URL` exists by design.
- **Auth**: single shared password via `DASHBOARD_PASSWORD`.  A Next
  middleware verifies a cookie on every route except `/login` and
  `/api/login`.  The cookie value *is* the password; we accept the
  leak risk for a single-user dashboard.  Rotate by changing the env var.
- **Account-value math**:
  `account_value = STARTING_BANKROLL + realized_pnl + sum(unrealized_pnl)`
  where `unrealized_pnl = (current_yes_ask - fill_price) * qty`, gross of
  any hypothetical close-leg fee.  Document any change before flipping to live.
- **Why a single `DATABASE_URL` and no RLS?**  Neon doesn't ship RLS-aware
  REST out of the box; we treat the DSN itself as the secret and gate
  all access through the Next.js server.

## D12. Postgres host: Neon (was: Supabase)

Initially scoped to Supabase, but Supabase's free tier limits an org to 2
projects.  AJackerman2's org already had two (`Ash-Sports` active,
`yourturn` paused), and a Pro upgrade ($25/mo) was declined.  We
considered:
  - reusing Ash-Sports under a `kalshi_bot` schema (free, but tangled
    with unrelated sports data);
  - deleting the paused `yourturn` project (destructive);
  - Firebase / Firestore (NoSQL; free-tier write quotas of 20K/day
    are below our scan cadence's expected ~70K market upserts/day);
  - **Neon serverless Postgres (chosen)**: free tier 0.5 GB storage,
    unlimited projects, HTTP-fetch driver well-suited to Vercel
    serverless.

The schema in `supabase/migrations/0001_initial_schema.sql` is plain
Postgres -- it runs unchanged in Neon's SQL editor.  The directory name
is preserved for history.

## D13. User-directed strategy overrides (post-Session-1-spec)

After Session 1 went live, AJackerman2 directed three deviations from the
original brief.  Recording them here so future-us doesn't get confused
about why the running config differs from the paper's parameters.

- **Ask band widened 90-97c → 82-97c.** Burgi/Deng/Whelan show
  favorite-longshot edge across 50c+ contracts with the strongest signal
  at the high end; 82c is still well into "favorite" territory and gives
  the bot a much larger pool of qualifying markets.  Per-trade expected
  edge slightly weaker than the 90-97c band; more opportunities.
- **`MIN_HOURS_TO_CLOSE` 24h → 0.5h (30 min).**  Original brief locked
  this at 24h.  User wanted exposure to short-duration markets (sports
  tonight, CPI tomorrow).  Acceptable because the strategy is
  hold-to-resolution; hold length itself doesn't change expected return.
  If you want to push lower, set `MIN_HOURS_TO_CLOSE=0.25` (15 min) or
  `0` (no minimum).
- **`CLOSE_BUFFER_MIN` 10 → 0 (disabled).**  This rule only ever
  cancelled UNFILLED resting bids inside the last N min of a market's
  life; filled positions are always held to resolution regardless.
  User wanted unfilled bids to rest all the way to close so we capture
  any final-minutes ask drop.  Trade-off: very-late fills resolve almost
  immediately with no time for anything to play out -- but at 82-97c
  favorites the immediate-fill EV is still positive (the favorite
  resolves YES the vast majority of the time at those prices).  If we
  see pathologically late fills hurting P&L, restore to 5-10.
- **Kalshi API key generated as Read/Write instead of Read-only.**  User
  preferred avoiding the regen friction in Session 2.  Reduces the live-
  trade defense from four gates to three:
    1. ~~Kalshi server-side scope rejection~~  (gone -- key now has write
       scope)
    2. `runner.py::main` refuses to start if `MODE=live`
    3. `OrderManager._place_live_order` raises `NotImplementedError`
    4. `KalshiClient.place_order` / `cancel_order` raise `SimModeRefused`
  Still robust against accidents: all three remaining gates would need
  to be defeated for a live trade to fire.  Mentioned explicitly so it's
  on the audit trail.

---

## Self-review notes
*(populated during the Session 1 verification step)*

## Codex second-pass findings
*(populated after running the Codex review)*

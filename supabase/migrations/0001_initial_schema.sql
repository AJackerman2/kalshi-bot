-- Kalshi Maker Bot -- Supabase mirror schema.
--
-- The bot's source of truth is the SQLite DB on the Hetzner box.  Supabase
-- is a read-mostly mirror for the Vercel dashboard.  The bot uses the
-- service-role key and writes via PostgREST; the dashboard reads
-- server-side (RSC / route handlers) also with service-role and never
-- exposes the key to the browser.  RLS is enabled with no anon policies
-- so a leaked publishable key can't read anything.

create schema if not exists kalshi;

set search_path = kalshi, public;

-- ---------------------------------------------------------------------------
-- markets
-- ---------------------------------------------------------------------------
create table if not exists kalshi.markets (
    ticker             text primary key,
    event_ticker       text,
    title              text,
    close_time         timestamptz,
    expected_expiry    timestamptz,
    last_seen_at       timestamptz not null default now(),
    last_ask_cents     int,
    last_bid_cents     int,
    last_volume        int,
    last_open_interest int,
    resolved           boolean not null default false,
    outcome            text check (outcome in ('yes','no') or outcome is null)
);

create index if not exists markets_close_time_idx on kalshi.markets (close_time);
create index if not exists markets_last_seen_idx on kalshi.markets (last_seen_at desc);

alter table kalshi.markets enable row level security;

-- ---------------------------------------------------------------------------
-- sim_orders
-- ---------------------------------------------------------------------------
create table if not exists kalshi.sim_orders (
    id                bigint primary key,         -- mirrors SQLite rowid
    ticker            text not null references kalshi.markets(ticker) on delete cascade,
    side              text not null default 'yes',
    action            text not null default 'buy',
    bid_cents         int not null,
    quantity          int not null,
    placed_at         timestamptz not null,
    status            text not null check (status in ('open','filled','cancelled')),
    fill_price_cents  int,
    filled_at         timestamptz,
    cancelled_at      timestamptz,
    cancel_reason     text,
    pnl_cents         int,
    resolved_at       timestamptz,
    notes             text,
    updated_at        timestamptz not null default now()
);

create index if not exists sim_orders_status_idx on kalshi.sim_orders (status);
create index if not exists sim_orders_ticker_idx on kalshi.sim_orders (ticker);
create index if not exists sim_orders_resolved_at_idx on kalshi.sim_orders (resolved_at);

alter table kalshi.sim_orders enable row level security;

-- ---------------------------------------------------------------------------
-- events
-- ---------------------------------------------------------------------------
create table if not exists kalshi.events (
    id        bigint primary key,                 -- mirrors SQLite rowid
    ts        timestamptz not null,
    kind      text not null,
    ticker    text,
    order_id  bigint,
    payload   jsonb not null
);

create index if not exists events_ts_idx on kalshi.events (ts desc);
create index if not exists events_kind_idx on kalshi.events (kind);

alter table kalshi.events enable row level security;

-- ---------------------------------------------------------------------------
-- daily_pnl: realized P&L per day in cents.
-- ---------------------------------------------------------------------------
create or replace view kalshi.daily_pnl as
select
    (resolved_at at time zone 'utc')::date as day,
    coalesce(sum(pnl_cents), 0)::bigint    as pnl_cents,
    count(*)::int                           as orders_resolved,
    sum(case when pnl_cents > 0 then 1 else 0 end)::int as wins,
    sum(case when pnl_cents <= 0 then 1 else 0 end)::int as losses
from kalshi.sim_orders
where pnl_cents is not null
  and resolved_at is not null
group by 1
order by 1;

-- ---------------------------------------------------------------------------
-- open_positions: filled-unresolved sim orders with their latest market data.
-- The dashboard uses last_ask_cents for mark-to-market.
-- ---------------------------------------------------------------------------
create or replace view kalshi.open_positions as
select
    o.id,
    o.ticker,
    m.title,
    m.close_time,
    o.fill_price_cents,
    o.quantity,
    m.last_ask_cents       as current_ask_cents,
    o.filled_at,
    -- unrealized P&L: simple mark-to-current-ask, gross of close fees.
    -- documented in DECISIONS.md.
    case
        when m.last_ask_cents is not null
        then ((m.last_ask_cents - o.fill_price_cents) * o.quantity)
        else null
    end                    as unrealized_pnl_cents
from kalshi.sim_orders o
join kalshi.markets m on m.ticker = o.ticker
where o.status = 'filled'
  and o.pnl_cents is null;

-- ---------------------------------------------------------------------------
-- account_summary: single-row KPI snapshot.
-- bankroll_cents is supplied per-call by the dashboard so we can keep the
-- starting bankroll on the UI side without coupling the bot to the dashboard.
-- ---------------------------------------------------------------------------
create or replace function kalshi.account_summary(bankroll_cents bigint)
returns table (
    bankroll_cents       bigint,
    realized_pnl_cents   bigint,
    unrealized_pnl_cents bigint,
    account_value_cents  bigint,
    open_position_count  int,
    open_position_cost_cents bigint,
    total_fills          int,
    total_resolved       int,
    wins                 int,
    losses               int,
    win_rate             numeric
)
language sql
stable
as $$
    with realized as (
        select coalesce(sum(pnl_cents), 0)::bigint as v,
               sum(case when pnl_cents > 0 then 1 else 0 end)::int as wins,
               sum(case when pnl_cents <= 0 then 1 else 0 end)::int as losses,
               count(*)::int as resolved
        from kalshi.sim_orders
        where pnl_cents is not null
    ),
    unrealized as (
        select coalesce(sum(unrealized_pnl_cents), 0)::bigint as v,
               count(*)::int as cnt,
               coalesce(sum(fill_price_cents * quantity), 0)::bigint as cost
        from kalshi.open_positions
    ),
    fills as (
        select count(*)::int as cnt
        from kalshi.sim_orders
        where status in ('filled') or pnl_cents is not null
    )
    select
        bankroll_cents,
        realized.v,
        unrealized.v,
        (bankroll_cents + realized.v + unrealized.v)::bigint,
        unrealized.cnt,
        unrealized.cost,
        fills.cnt,
        realized.resolved,
        realized.wins,
        realized.losses,
        case when realized.resolved > 0
             then round((realized.wins::numeric / realized.resolved::numeric), 4)
             else null end
    from realized, unrealized, fills;
$$;

-- ---------------------------------------------------------------------------
-- recent_events RPC: dashboard tail view.
-- ---------------------------------------------------------------------------
create or replace function kalshi.recent_events(limit_n int default 100, since_hours int default 48)
returns table (
    id bigint, ts timestamptz, kind text, ticker text, order_id bigint, payload jsonb
)
language sql
stable
as $$
    select id, ts, kind, ticker, order_id, payload
    from kalshi.events
    where ts >= now() - make_interval(hours => since_hours)
    order by ts desc
    limit limit_n;
$$;

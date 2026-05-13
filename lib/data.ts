import { sql } from "./db";

export type AccountSummary = {
  bankroll_cents: number;
  realized_pnl_cents: number;
  unrealized_pnl_cents: number;
  account_value_cents: number;
  open_position_count: number;
  open_position_cost_cents: number;
  total_fills: number;
  total_resolved: number;
  wins: number;
  losses: number;
  win_rate: number | null;
};

export type OpenPosition = {
  id: number;
  ticker: string;
  title: string | null;
  close_time: string | null;
  fill_price_cents: number;
  quantity: number;
  current_ask_cents: number | null;
  filled_at: string;
  unrealized_pnl_cents: number | null;
};

export type DailyPnl = {
  day: string;
  pnl_cents: number;
  orders_resolved: number;
  wins: number;
  losses: number;
};

export type EventRow = {
  id: number;
  ts: string;
  kind: string;
  ticker: string | null;
  order_id: number | null;
  payload: Record<string, unknown>;
};

export type NearMissMarket = {
  ticker: string;
  title: string | null;
  close_time: string | null;
  last_ask_cents: number | null;
  last_open_interest: number | null;
  last_volume: number | null;
  last_seen_at: string;
};

function bankrollCents() {
  const v = Number(process.env.SIM_STARTING_BANKROLL_CENTS ?? "100000");
  return Number.isFinite(v) ? Math.max(0, Math.trunc(v)) : 100_000;
}

function toNumber(v: unknown): number {
  if (typeof v === "number") return v;
  if (typeof v === "string") return Number(v);
  if (typeof v === "bigint") return Number(v);
  return 0;
}

export async function getOpenPositions(): Promise<OpenPosition[]> {
  const rows = (await sql()`
    SELECT id, ticker, title, close_time, fill_price_cents, quantity,
           current_ask_cents, filled_at, unrealized_pnl_cents
      FROM kalshi.open_positions
     ORDER BY filled_at DESC
  `) as unknown[];
  return (rows as Record<string, unknown>[]).map((r) => ({
    id: toNumber(r.id),
    ticker: String(r.ticker),
    title: (r.title as string | null) ?? null,
    close_time: (r.close_time as string | null) ?? null,
    fill_price_cents: toNumber(r.fill_price_cents),
    quantity: toNumber(r.quantity),
    current_ask_cents:
      r.current_ask_cents == null ? null : toNumber(r.current_ask_cents),
    filled_at: String(r.filled_at),
    unrealized_pnl_cents:
      r.unrealized_pnl_cents == null ? null : toNumber(r.unrealized_pnl_cents),
  }));
}

export async function getDailyPnl(): Promise<DailyPnl[]> {
  const rows = (await sql()`
    SELECT day::text AS day, pnl_cents, orders_resolved, wins, losses
      FROM kalshi.daily_pnl
     ORDER BY day ASC
  `) as unknown[];
  return (rows as Record<string, unknown>[]).map((r) => ({
    day: String(r.day),
    pnl_cents: toNumber(r.pnl_cents),
    orders_resolved: toNumber(r.orders_resolved),
    wins: toNumber(r.wins),
    losses: toNumber(r.losses),
  }));
}

export async function getRecentEvents(limit = 150, hours = 72): Promise<EventRow[]> {
  const rows = (await sql()`
    SELECT id, ts, kind, ticker, order_id, payload
      FROM kalshi.events
     WHERE ts >= now() - make_interval(hours => ${hours})
     ORDER BY ts DESC
     LIMIT ${limit}
  `) as unknown[];
  return (rows as Record<string, unknown>[]).map((r) => ({
    id: toNumber(r.id),
    ts: String(r.ts),
    kind: String(r.kind),
    ticker: (r.ticker as string | null) ?? null,
    order_id: r.order_id == null ? null : toNumber(r.order_id),
    payload: (r.payload as Record<string, unknown>) ?? {},
  }));
}

export async function getMarketsNearQualifying(limit = 30): Promise<NearMissMarket[]> {
  // The bot updates `markets` every scan.  We surface markets whose latest
  // snapshot is "close to qualifying" -- specifically: ask in a slightly wider
  // band (78-99) AND non-trivial OI (>= 200).  Sorted to put the closest
  // misses on top: in-band first, then by descending OI.
  const rows = (await sql()`
    SELECT ticker, title, close_time, last_ask_cents, last_open_interest,
           last_volume, last_seen_at
      FROM kalshi.markets
     WHERE last_ask_cents IS NOT NULL
       AND last_ask_cents BETWEEN 78 AND 99
       AND COALESCE(last_open_interest, 0) >= 200
     ORDER BY
       (last_ask_cents BETWEEN 82 AND 97) DESC,
       COALESCE(last_open_interest, 0) DESC,
       last_seen_at DESC
     LIMIT ${limit}
  `) as unknown[];
  return (rows as Record<string, unknown>[]).map((r) => ({
    ticker: String(r.ticker),
    title: (r.title as string | null) ?? null,
    close_time: (r.close_time as string | null) ?? null,
    last_ask_cents: r.last_ask_cents == null ? null : toNumber(r.last_ask_cents),
    last_open_interest:
      r.last_open_interest == null ? null : toNumber(r.last_open_interest),
    last_volume: r.last_volume == null ? null : toNumber(r.last_volume),
    last_seen_at: String(r.last_seen_at),
  }));
}

export async function getAccountSummary(): Promise<AccountSummary> {
  const bankroll = bankrollCents();

  const [resolvedRows, openRows] = (await Promise.all([
    sql()`
      SELECT pnl_cents
        FROM kalshi.sim_orders
       WHERE pnl_cents IS NOT NULL
    `,
    sql()`
      SELECT fill_price_cents, quantity, unrealized_pnl_cents
        FROM kalshi.open_positions
    `,
  ])) as unknown[][];

  let realized = 0;
  let wins = 0;
  let losses = 0;
  for (const r of resolvedRows as Record<string, unknown>[]) {
    const v = toNumber(r.pnl_cents);
    realized += v;
    if (v > 0) wins++;
    else losses++;
  }

  let unrealized = 0;
  let openCost = 0;
  let openCount = 0;
  for (const r of openRows as Record<string, unknown>[]) {
    openCount++;
    if (r.unrealized_pnl_cents != null) unrealized += toNumber(r.unrealized_pnl_cents);
    openCost += toNumber(r.fill_price_cents) * toNumber(r.quantity);
  }

  const totalResolved = (resolvedRows as unknown[]).length;
  return {
    bankroll_cents: bankroll,
    realized_pnl_cents: realized,
    unrealized_pnl_cents: unrealized,
    account_value_cents: bankroll + realized + unrealized,
    open_position_count: openCount,
    open_position_cost_cents: openCost,
    total_fills: openCount + totalResolved,
    total_resolved: totalResolved,
    wins,
    losses,
    win_rate: totalResolved > 0 ? wins / totalResolved : null,
  };
}

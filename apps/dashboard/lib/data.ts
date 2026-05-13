import { supabase } from "./supabase";

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

function bankrollCents() {
  const v = Number(process.env.SIM_STARTING_BANKROLL_CENTS ?? "100000");
  return Number.isFinite(v) ? Math.max(0, Math.trunc(v)) : 100_000;
}

export async function getOpenPositions(): Promise<OpenPosition[]> {
  const sb = supabase();
  const { data, error } = await sb
    .from("open_positions")
    .select("*")
    .order("filled_at", { ascending: false });
  if (error) throw new Error(`open_positions failed: ${error.message}`);
  return (data ?? []) as OpenPosition[];
}

export async function getDailyPnl(): Promise<DailyPnl[]> {
  const sb = supabase();
  const { data, error } = await sb
    .from("daily_pnl")
    .select("*")
    .order("day", { ascending: true });
  if (error) throw new Error(`daily_pnl failed: ${error.message}`);
  return (data ?? []) as DailyPnl[];
}

export async function getRecentEvents(limit = 150, hours = 72): Promise<EventRow[]> {
  const sb = supabase();
  const since = new Date(Date.now() - hours * 3_600_000).toISOString();
  const { data, error } = await sb
    .from("events")
    .select("*")
    .gte("ts", since)
    .order("ts", { ascending: false })
    .limit(limit);
  if (error) throw new Error(`events failed: ${error.message}`);
  return (data ?? []) as EventRow[];
}

export async function getAccountSummary(): Promise<AccountSummary> {
  const sb = supabase();
  const bankroll = bankrollCents();

  const [resolvedRes, positionsRes] = await Promise.all([
    sb
      .from("sim_orders")
      .select("pnl_cents")
      .not("pnl_cents", "is", null),
    sb.from("open_positions").select("*"),
  ]);

  if (resolvedRes.error) {
    throw new Error(`resolved orders failed: ${resolvedRes.error.message}`);
  }
  if (positionsRes.error) {
    throw new Error(`open positions failed: ${positionsRes.error.message}`);
  }

  const resolved = (resolvedRes.data ?? []) as { pnl_cents: number | null }[];
  const positions = (positionsRes.data ?? []) as OpenPosition[];

  let realized = 0;
  let wins = 0;
  let losses = 0;
  for (const r of resolved) {
    const v = r.pnl_cents ?? 0;
    realized += v;
    if (v > 0) wins++;
    else losses++;
  }

  let unrealized = 0;
  let openCost = 0;
  for (const p of positions) {
    if (p.unrealized_pnl_cents !== null && p.unrealized_pnl_cents !== undefined) {
      unrealized += p.unrealized_pnl_cents;
    }
    openCost += p.fill_price_cents * p.quantity;
  }

  const totalResolved = resolved.length;
  return {
    bankroll_cents: bankroll,
    realized_pnl_cents: realized,
    unrealized_pnl_cents: unrealized,
    account_value_cents: bankroll + realized + unrealized,
    open_position_count: positions.length,
    open_position_cost_cents: openCost,
    total_fills: positions.length + totalResolved,
    total_resolved: totalResolved,
    wins,
    losses,
    win_rate: totalResolved > 0 ? wins / totalResolved : null,
  };
}

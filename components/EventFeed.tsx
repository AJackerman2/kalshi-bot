import type { EventRow } from "@/lib/data";
import { relativeTime } from "@/lib/format";

const KIND_TONES: Record<string, string> = {
  sim_order_placed: "bg-zinc-700/40 text-zinc-200",
  sim_order_filled: "bg-emerald-700/30 text-emerald-200",
  sim_order_cancelled: "bg-amber-700/30 text-amber-200",
  sim_order_resolved: "bg-sky-700/30 text-sky-200",
  scan_completed: "bg-zinc-800/40 text-zinc-400",
  candidate_skipped: "bg-zinc-800/40 text-zinc-500",
  service_started: "bg-violet-800/40 text-violet-200",
  service_stopping: "bg-violet-800/40 text-violet-200",
  loop_iter_failed: "bg-red-800/40 text-red-200",
};

function pillClass(kind: string) {
  return KIND_TONES[kind] ?? "bg-zinc-800/40 text-zinc-300";
}

function summarize(e: EventRow): string {
  const p = e.payload as Record<string, unknown>;
  switch (e.kind) {
    case "sim_order_placed":
      return `${p.ticker} bid ${p.bid_cents}c x${p.quantity} (ask ${p.ask_cents_at_placement}c)`;
    case "sim_order_filled":
      return `${p.ticker} filled @ ${p.fill_price_cents}c x${p.quantity}`;
    case "sim_order_cancelled":
      return `${p.ticker} cancelled (${p.reason})`;
    case "sim_order_resolved": {
      const pnl = Number(p.pnl_cents ?? 0);
      const sign = pnl > 0 ? "+" : "";
      return `${p.ticker} ${p.outcome} · ${sign}${(pnl / 100).toFixed(2)} P&L`;
    }
    case "scan_completed": {
      const reasons = (p.rejection_reasons as Record<string, number>) ?? {};
      const top = Object.entries(reasons)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3)
        .map(([k, v]) => `${k}:${v}`)
        .join(", ");
      const head = `${p.markets_seen} markets · ${p.candidates} candidates · ${p.rejections} rejected`;
      return top ? `${head} (${top})` : head;
    }
    case "candidate_skipped":
      return `${p.ticker} skipped (${p.reason})`;
    case "loop_iter_failed":
      return `${p.fn} failed: ${p.error}`;
    default:
      return e.ticker ? `${e.ticker}` : "";
  }
}

export function EventFeed({ events }: { events: EventRow[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-muted">No events yet.</p>;
  }
  return (
    <ul className="divide-y divide-border/50">
      {events.map((e) => (
        <li key={e.id} className="flex items-center gap-3 py-2">
          <span
            className={`inline-flex shrink-0 rounded-md px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider ${pillClass(
              e.kind,
            )}`}
          >
            {e.kind.replace(/^sim_order_/, "")}
          </span>
          <span className="flex-1 truncate text-sm">{summarize(e)}</span>
          <span className="shrink-0 text-xs text-muted tabular" title={e.ts}>
            {relativeTime(e.ts)}
          </span>
        </li>
      ))}
    </ul>
  );
}

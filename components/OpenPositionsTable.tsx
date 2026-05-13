import type { OpenPosition } from "@/lib/data";
import { cents, centsPrice, hoursUntil, relativeTime } from "@/lib/format";

function pnlClass(v: number | null | undefined) {
  if (v === null || v === undefined) return "text-muted";
  if (v > 0) return "text-accent";
  if (v < 0) return "text-loss";
  return "text-text";
}

export function OpenPositionsTable({ rows }: { rows: OpenPosition[] }) {
  if (rows.length === 0) {
    return <p className="text-sm text-muted">No open simulated positions.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted">
            <th className="py-2 pr-4">Ticker</th>
            <th className="py-2 pr-4">Market</th>
            <th className="py-2 pr-4 text-right">Fill</th>
            <th className="py-2 pr-4 text-right">Qty</th>
            <th className="py-2 pr-4 text-right">Cost</th>
            <th className="py-2 pr-4 text-right">Current ask</th>
            <th className="py-2 pr-4 text-right">Unrealized</th>
            <th className="py-2 pr-4 text-right">Filled</th>
            <th className="py-2 text-right">Closes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const cost = r.fill_price_cents * r.quantity;
            return (
              <tr key={r.id} className="border-b border-border/50 last:border-b-0">
                <td className="py-2 pr-4 font-mono text-xs">{r.ticker}</td>
                <td className="py-2 pr-4 truncate max-w-xs" title={r.title ?? ""}>
                  {r.title ?? "—"}
                </td>
                <td className="py-2 pr-4 text-right tabular">{centsPrice(r.fill_price_cents)}</td>
                <td className="py-2 pr-4 text-right tabular">{r.quantity}</td>
                <td className="py-2 pr-4 text-right tabular">{cents(cost)}</td>
                <td className="py-2 pr-4 text-right tabular">{centsPrice(r.current_ask_cents)}</td>
                <td className={`py-2 pr-4 text-right tabular ${pnlClass(r.unrealized_pnl_cents)}`}>
                  {cents(r.unrealized_pnl_cents, { sign: true })}
                </td>
                <td className="py-2 pr-4 text-right text-muted">{relativeTime(r.filled_at)}</td>
                <td className="py-2 text-right text-muted">{hoursUntil(r.close_time)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

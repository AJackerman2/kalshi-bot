import type { NearMissMarket } from "@/lib/data";
import { centsPrice, hoursUntil, relativeTime } from "@/lib/format";

const ASK_BAND: [number, number] = [82, 97];
const MIN_OI = 1000;
const MIN_VOL = 100;
const MIN_HOURS = 0.5;

function reasonsFor(m: NearMissMarket): string[] {
  const out: string[] = [];
  const ask = m.last_ask_cents;
  if (ask == null) out.push("no ask in book");
  else if (ask < ASK_BAND[0]) out.push(`ask ${ask}¢ < ${ASK_BAND[0]}`);
  else if (ask > ASK_BAND[1]) out.push(`ask ${ask}¢ > ${ASK_BAND[1]}`);
  if ((m.last_open_interest ?? 0) < MIN_OI)
    out.push(`OI ${m.last_open_interest ?? 0} < ${MIN_OI}`);
  if ((m.last_volume ?? 0) < MIN_VOL)
    out.push(`vol ${m.last_volume ?? 0} < ${MIN_VOL}`);
  if (m.close_time) {
    const hrs = (new Date(m.close_time).getTime() - Date.now()) / 3_600_000;
    if (hrs < MIN_HOURS) out.push(`closes in <${MIN_HOURS}h`);
  }
  return out;
}

export function MarketsNearQualifying({ rows }: { rows: NearMissMarket[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted">
        No markets in the bot's evaluation window yet. The first scan will populate this.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs uppercase tracking-wider text-muted">
            <th className="py-2 pr-4">Ticker</th>
            <th className="py-2 pr-4">Market</th>
            <th className="py-2 pr-4 text-right">Ask</th>
            <th className="py-2 pr-4 text-right">OI</th>
            <th className="py-2 pr-4 text-right">Vol 24h</th>
            <th className="py-2 pr-4 text-right">Closes</th>
            <th className="py-2 pr-4">Missing</th>
            <th className="py-2 text-right">Seen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => {
            const reasons = reasonsFor(m);
            const inBand =
              m.last_ask_cents != null &&
              m.last_ask_cents >= ASK_BAND[0] &&
              m.last_ask_cents <= ASK_BAND[1];
            return (
              <tr key={m.ticker} className="border-b border-border/50 last:border-b-0">
                <td className="py-2 pr-4 font-mono text-xs">{m.ticker}</td>
                <td
                  className="py-2 pr-4 truncate max-w-xs text-text/80"
                  title={m.title ?? ""}
                >
                  {m.title ?? "—"}
                </td>
                <td
                  className={`py-2 pr-4 text-right tabular ${inBand ? "text-accent" : ""}`}
                >
                  {centsPrice(m.last_ask_cents)}
                </td>
                <td className="py-2 pr-4 text-right tabular">
                  {m.last_open_interest?.toLocaleString() ?? "—"}
                </td>
                <td className="py-2 pr-4 text-right tabular">
                  {m.last_volume?.toLocaleString() ?? "—"}
                </td>
                <td className="py-2 pr-4 text-right text-muted">
                  {hoursUntil(m.close_time)}
                </td>
                <td className="py-2 pr-4 text-xs text-muted">
                  {reasons.length === 0 ? (
                    <span className="text-accent">all pass</span>
                  ) : (
                    reasons.join(", ")
                  )}
                </td>
                <td className="py-2 text-right text-muted">
                  {relativeTime(m.last_seen_at)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

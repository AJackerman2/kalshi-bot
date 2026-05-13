import type { AccountSummary } from "@/lib/data";
import { cents, pct } from "@/lib/format";
import { Panel } from "./Panel";

function Stat({
  label,
  value,
  tone,
  sub,
}: {
  label: string;
  value: string;
  tone?: "good" | "bad" | "neutral";
  sub?: string;
}) {
  const color =
    tone === "good" ? "text-accent" : tone === "bad" ? "text-loss" : "text-text";
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wider text-muted">{label}</span>
      <span className={`tabular text-2xl font-semibold ${color}`}>{value}</span>
      {sub && <span className="text-xs text-muted tabular">{sub}</span>}
    </div>
  );
}

function tone(v: number): "good" | "bad" | "neutral" {
  return v > 0 ? "good" : v < 0 ? "bad" : "neutral";
}

export function KpiBlock({ summary }: { summary: AccountSummary }) {
  const accountValue = summary.account_value_cents;
  const realized = summary.realized_pnl_cents;
  const unrealized = summary.unrealized_pnl_cents;
  return (
    <Panel
      title="Account snapshot"
      subtitle="Simulated. Bankroll + realized + mark-to-market on open fills."
    >
      <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
        <Stat
          label="Account value"
          value={cents(accountValue)}
          tone={tone(accountValue - summary.bankroll_cents)}
          sub={`Bankroll ${cents(summary.bankroll_cents)}`}
        />
        <Stat
          label="Realized P&L"
          value={cents(realized, { sign: true })}
          tone={tone(realized)}
          sub={`${summary.total_resolved} resolved`}
        />
        <Stat
          label="Unrealized P&L"
          value={cents(unrealized, { sign: true })}
          tone={tone(unrealized)}
          sub={`${summary.open_position_count} open · cost ${cents(summary.open_position_cost_cents)}`}
        />
        <Stat
          label="Win rate"
          value={pct(summary.win_rate)}
          tone="neutral"
          sub={`${summary.wins}W / ${summary.losses}L`}
        />
      </div>
    </Panel>
  );
}

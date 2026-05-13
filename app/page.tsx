import { EventFeed } from "@/components/EventFeed";
import { KpiBlock } from "@/components/KpiBlock";
import { OpenPositionsTable } from "@/components/OpenPositionsTable";
import { Panel } from "@/components/Panel";
import { PnlChart } from "@/components/PnlChart";
import {
  getAccountSummary,
  getDailyPnl,
  getOpenPositions,
  getRecentEvents,
} from "@/lib/data";

export const dynamic = "force-dynamic";
export const revalidate = 30;

export default async function Home() {
  const [summary, positions, daily, events] = await Promise.all([
    getAccountSummary(),
    getOpenPositions(),
    getDailyPnl(),
    getRecentEvents(150, 72),
  ]);

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-8">
      <header className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Kalshi Maker Bot</h1>
          <p className="text-sm text-muted">
            Simulation dashboard. Refreshes every 30s.
          </p>
        </div>
        <span className="rounded-md border border-border bg-panel px-2 py-1 text-xs uppercase tracking-wider text-muted">
          mode: sim
        </span>
      </header>

      <KpiBlock summary={summary} />

      <div className="grid gap-6 lg:grid-cols-3">
        <Panel title="P&L" subtitle="Daily realized and cumulative" className="lg:col-span-2">
          <PnlChart daily={daily} />
        </Panel>
        <Panel title="Activity" subtitle="Last 72 hours">
          <EventFeed events={events} />
        </Panel>
      </div>

      <Panel title="Open positions" subtitle="Filled, awaiting resolution">
        <OpenPositionsTable rows={positions} />
      </Panel>
    </main>
  );
}

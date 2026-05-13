import { Panel } from "./Panel";

type Row = { label: string; value: string; note?: string };

const ENTRY: Row[] = [
  {
    label: "YES ask price",
    value: "82 – 97¢",
    note: "favorite-longshot edge per Burgi/Deng/Whelan",
  },
  {
    label: "Bid offset",
    value: "1¢ below ask",
    note: "so bid lands at 81–96¢",
  },
  {
    label: "Notional per market",
    value: "$25",
    note: "fixed; no Kelly sizing",
  },
  {
    label: "Min time to close",
    value: "30 min",
    note: "user override; original brief was 24h",
  },
  {
    label: "Min open interest",
    value: "1,000",
    note: "liquidity floor",
  },
  {
    label: "Min 24h volume",
    value: "100",
    note: "filters dead markets",
  },
  {
    label: "Catalyst buffer",
    value: "± 30 min",
    note: "around expected_expiration_time / event_time",
  },
];

const LIFECYCLE: Row[] = [
  {
    label: "Cancel for drift",
    value: "ask > bid + 2¢",
    note: "edge gone if ask runs away",
  },
  {
    label: "Cancel for close",
    value: "disabled",
    note: "unfilled bids rest until close; filled positions always hold to resolution",
  },
  {
    label: "Cancel for refresh",
    value: "order older than 5 min",
    note: "let next scan re-evaluate",
  },
];

function Section({ title, rows }: { title: string; rows: Row[] }) {
  return (
    <div className="flex-1">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">
        {title}
      </h3>
      <dl className="space-y-1.5">
        {rows.map((r) => (
          <div
            key={r.label}
            className="flex items-baseline justify-between gap-3 text-sm"
          >
            <dt className="text-text">{r.label}</dt>
            <dd className="flex flex-col items-end text-right">
              <span className="tabular font-medium">{r.value}</span>
              {r.note ? (
                <span className="text-xs text-muted">{r.note}</span>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function StrategyPanel() {
  return (
    <Panel
      title="Strategy criteria"
      subtitle="What the bot needs to see before placing a simulated bid"
    >
      <div className="flex flex-col gap-8 md:flex-row md:gap-12">
        <Section title="Entry filter" rows={ENTRY} />
        <Section title="Lifecycle rules" rows={LIFECYCLE} />
      </div>
    </Panel>
  );
}

import { relativeTime } from "@/lib/format";

type Status = "live" | "stale" | "down";

function classify(lastTs: string | null): Status {
  if (!lastTs) return "down";
  const ageMs = Date.now() - new Date(lastTs).getTime();
  if (!Number.isFinite(ageMs) || ageMs < 0) return "down";
  if (ageMs < 5 * 60_000) return "live";
  if (ageMs < 15 * 60_000) return "stale";
  return "down";
}

const STYLES: Record<Status, { dot: string; text: string; label: string }> = {
  live: {
    dot: "bg-accent shadow-[0_0_0_4px_rgba(110,231,183,0.15)]",
    text: "text-accent",
    label: "live",
  },
  stale: {
    dot: "bg-amber-300 shadow-[0_0_0_4px_rgba(252,211,77,0.15)]",
    text: "text-amber-300",
    label: "stale",
  },
  down: {
    dot: "bg-loss shadow-[0_0_0_4px_rgba(248,113,113,0.15)]",
    text: "text-loss",
    label: "no events",
  },
};

export function LivenessBadge({ lastEventTs }: { lastEventTs: string | null }) {
  const status = classify(lastEventTs);
  const s = STYLES[status];
  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-panel px-2.5 py-1 text-xs uppercase tracking-wider">
      <span className={`inline-block h-2 w-2 rounded-full ${s.dot}`} />
      <span className={`tabular ${s.text}`}>{s.label}</span>
      <span className="text-muted">·</span>
      <span className="text-muted normal-case">
        last event {relativeTime(lastEventTs)}
      </span>
    </div>
  );
}

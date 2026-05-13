export function cents(value: number | null | undefined, opts?: { sign?: boolean }): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const sign = opts?.sign && value > 0 ? "+" : value < 0 ? "−" : "";
  const abs = Math.abs(value);
  const dollars = abs / 100;
  return `${sign}$${dollars.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function centsPrice(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value}¢`;
}

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const deltaSec = Math.round((Date.now() - t) / 1000);
  const abs = Math.abs(deltaSec);
  const sign = deltaSec >= 0 ? "" : "in ";
  const tail = deltaSec >= 0 ? " ago" : "";
  if (abs < 60) return `${sign}${abs}s${tail}`;
  if (abs < 3600) return `${sign}${Math.round(abs / 60)}m${tail}`;
  if (abs < 86400) return `${sign}${Math.round(abs / 3600)}h${tail}`;
  return `${sign}${Math.round(abs / 86400)}d${tail}`;
}

export function hoursUntil(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return "—";
  const hours = (t - Date.now()) / 3_600_000;
  if (hours < 0) return "closed";
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  if (hours < 48) return `${hours.toFixed(1)}h`;
  return `${Math.round(hours / 24)}d`;
}

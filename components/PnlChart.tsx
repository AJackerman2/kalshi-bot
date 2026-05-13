"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyPnl } from "@/lib/data";
import { cents } from "@/lib/format";

export function PnlChart({ daily }: { daily: DailyPnl[] }) {
  const data = useMemo(() => {
    let cum = 0;
    return daily.map((d) => {
      cum += d.pnl_cents;
      return {
        day: d.day,
        daily: d.pnl_cents,
        cumulative: cum,
      };
    });
  }, [daily]);

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted">
        No resolved P&L yet.
      </div>
    );
  }

  return (
    <div className="h-72">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, left: -8, bottom: 0 }}>
          <defs>
            <linearGradient id="cumFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#6ee7b7" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#6ee7b7" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1f1f24" vertical={false} />
          <XAxis
            dataKey="day"
            stroke="#7a7a85"
            tick={{ fontSize: 11, fill: "#7a7a85" }}
            tickMargin={6}
          />
          <YAxis
            stroke="#7a7a85"
            tick={{ fontSize: 11, fill: "#7a7a85" }}
            tickFormatter={(v) => cents(v)}
            width={70}
          />
          <ReferenceLine y={0} stroke="#1f1f24" />
          <Tooltip
            contentStyle={{
              backgroundColor: "#111114",
              border: "1px solid #1f1f24",
              borderRadius: 8,
              color: "#e6e6ea",
            }}
            labelStyle={{ color: "#7a7a85" }}
            formatter={(value: number, name) => [cents(value, { sign: true }), name]}
          />
          <Area
            type="monotone"
            dataKey="cumulative"
            stroke="#6ee7b7"
            strokeWidth={2}
            fill="url(#cumFill)"
            name="Cumulative"
          />
          <Area
            type="monotone"
            dataKey="daily"
            stroke="#7a7a85"
            strokeWidth={1}
            fillOpacity={0}
            name="Daily"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

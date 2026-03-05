"use client";

import { Loader2 } from "lucide-react";
import type { MetricValue } from "@/lib/types";

interface Props {
  agentId: string;
  metric: string;
  value?: MetricValue;
  loading?: boolean;
}

export function MetricsTable({ agentId, metric, value, loading }: Props) {
  if (loading) {
    return <Loader2 className="h-3 w-3 animate-spin text-neutral-400" />;
  }

  if (!value || value.status === "no_data") {
    return <span className="text-neutral-400">—</span>;
  }

  if (value.status === "unavailable") {
    return (
      <span className="text-neutral-400" title="Metric not found in run history">
        unavailable
      </span>
    );
  }

  const formatted =
    typeof value.value === "number"
      ? value.value < 1 && value.value > 0
        ? `${(value.value * 100).toFixed(1)}%`
        : value.value.toFixed(1)
      : "—";

  return (
    <span className="text-neutral-700">
      {formatted}
      {value.indicative_only && (
        <span className="ml-1 text-amber-500" title={`Sample size: ${value.sample_size}`}>
          *
        </span>
      )}
    </span>
  );
}

import type { DashboardData } from '../types';
import { activeChargerCount } from '../../mock/mockData';
import { MetricSkeleton } from '../common/LoadingSkeleton';

interface TopMetricsProps {
  data?: DashboardData;
  loading?: boolean;
}

function MetricCard({
  label,
  value,
  sub,
  accent = 'text-white',
  highlight,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border bg-panel p-4 ${
        highlight ? 'border-peak/40 shadow-[0_0_20px_rgba(249,115,22,0.08)]' : 'border-panel-border'
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-muted">{label}</p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-muted">{sub}</p>}
    </div>
  );
}

export default function TopMetrics({ data, loading }: TopMetricsProps) {
  if (loading || !data) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <MetricSkeleton key={i} />
        ))}
      </div>
    );
  }

  const activeCount = activeChargerCount(data.chargers);

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <MetricCard
        label="Grid Current"
        value={`${data.grid_current.toFixed(1)} A`}
        sub={`Threshold ${data.peak_threshold.toFixed(1)} A`}
        accent={data.peak_active ? 'text-peak-glow' : 'text-grid'}
        highlight={data.peak_active}
      />
      <MetricCard
        label="ESS SOC"
        value={`${data.ess_soc}%`}
        sub="Battery state of charge"
        accent="text-ess"
      />
      <MetricCard
        label="Active Chargers"
        value={`${activeCount} / ${data.chargers.length}`}
        sub="Currently drawing power"
        accent="text-charger"
      />
      <MetricCard
        label="Peak Reduction"
        value={`${data.peak_reduction_pct.toFixed(1)}%`}
        sub="Load shaved this cycle"
        accent="text-emerald-400"
      />
    </div>
  );
}
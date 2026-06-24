import type { DashboardData } from '../types';
import { activeChargerCount } from '../../mock/mockData';
import { MetricSkeleton } from '../common/LoadingSkeleton';

interface TopMetricsProps {
  data?: DashboardData;
  loading?: boolean;
}

function KPICard({
  label,
  value,
  sub,
  accent = 'text-white',
  highlight,
  isHighlight = false,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  highlight?: boolean;
  isHighlight?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border bg-[#1E293B] p-5 ${
        isHighlight ? 'border-[#FBBF24]/40 shadow-[0_0_20px_rgba(251,191,36,0.15)]' : 'border-[#334155]'
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-[#94A3B8]">{label}</p>
      <p className={`mt-2 text-3xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-sm text-[#94A3B8]">{sub}</p>}
    </div>
  );
}

export default function TopMetrics({ data, loading }: TopMetricsProps) {
  if (loading || !data) {
    return (
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <MetricSkeleton key={i} />
        ))}
      </div>
    );
  }

  const activeCount = activeChargerCount(data.chargers);

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <KPICard
        label="오늘 절감액"
        value={`${(data.today_saved_won ?? 0).toLocaleString()}원`}
        accent="text-[#FBBF24]"
        isHighlight={true}
      />
      <KPICard
        label="이번달 절감액"
        value={`${(data.month_saved_won ?? 0).toLocaleString()}원`}
        accent="text-[#F1F5F9]"
      />
      <KPICard
        label="ESS 잔량"
        value={`${(data.ess_soc ?? 0)}%`}
        accent={data.ess_soc < 20 ? 'text-[#EF4444]' : 'text-[#34D399]'}
      >
        <div className="mt-2 w-full bg-[#334155] rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-500 ${
              data.ess_soc < 20 ? 'bg-[#EF4444]' : 'bg-[#34D399]'
            }`}
            style={{ width: `${(data.ess_soc ?? 0)}%` }}
          />
        </div>
      </KPICard>
      <KPICard
        label="CO2 절감"
        value={`${(data.co2_reduced_kg ?? 0).toFixed(1)}kg`}
        accent="text-[#34D399]"
      />
    </div>
  );
}

import type { ReactNode } from 'react';
import type { DashboardData } from '../../types';
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
  isHighlight = false,
  children,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: string;
  isHighlight?: boolean;
  children?: ReactNode;
}) {
  return (
    <div
      className={`rounded-md border bg-[#0E1116] p-5 ${
        isHighlight ? 'border-[#E8A33D]/50 bg-[#E8A33D]/[0.06]' : 'border-[#222933]'
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wider text-[#98A2B3]">{label}</p>
      <p className={`mt-2 text-2xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-1 text-sm text-[#98A2B3]">{sub}</p>}
      {children}
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

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <KPICard
        label="오늘 절감액"
        value={`${(data.today_saved_won ?? 0).toLocaleString()}원`}
        accent="text-[#E8A33D]"
        isHighlight={true}
      />
      <KPICard
        label="이번달 절감액"
        value={`${(data.month_saved_won ?? 0).toLocaleString()}원`}
        accent="text-[#E8ECF1]"
      />
      <KPICard
        label="ESS 잔량"
        value={`${data.ess_soc ?? 0}%`}
        accent={(data.ess_soc ?? 0) < 20 ? 'text-[#E5484D]' : 'text-[#2EBD85]'}
      >
        <div className="mt-2 w-full bg-[#222933] rounded-full h-2">
          <div
            className={`h-2 rounded-full transition-all duration-500 ${
              (data.ess_soc ?? 0) < 20 ? 'bg-[#E5484D]' : 'bg-[#2EBD85]'
            }`}
            style={{ width: `${data.ess_soc ?? 0}%` }}
          />
        </div>
      </KPICard>
      <KPICard
        label="CO2 절감"
        value={`${data.co2_reduced_kg ?? 0}kg`}
        accent="text-[#2EBD85]"
      />
    </div>
  );
}

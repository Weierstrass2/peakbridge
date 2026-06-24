import type { ReactNode } from 'react';
import type { DashboardData } from '../../types';
import { activeChargerCount, totalChargerCurrent } from '../../mock/mockData';
import Card from '../common/Card';
import { CardSkeleton } from '../common/LoadingSkeleton';

interface EnergyFlowDiagramProps {
  data?: DashboardData;
  loading?: boolean;
}

function FlowArrow({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center gap-0.5 px-1">
      <div className="flex items-center">
        <div className="h-px w-6 bg-panel-border sm:w-10" />
        <svg className="h-3 w-3 text-muted" viewBox="0 0 12 12" fill="currentColor">
          <path d="M4 2l4 4-4 4V2z" />
        </svg>
      </div>
      {label && <span className="text-[10px] text-muted">{label}</span>}
    </div>
  );
}

function NodeBox({
  title,
  value,
  sub,
  icon,
  color,
  highlight,
}: {
  title: string;
  value: string;
  sub?: string;
  icon: ReactNode;
  color: string;
  highlight?: boolean;
}) {
  return (
    <div
      className={`flex min-w-[100px] flex-col items-center rounded-lg border border-panel-border bg-surface px-3 py-3 sm:min-w-[120px] ${highlight ? 'ring-1 ring-ess/40' : ''}`}
    >
      <div className={`mb-2 rounded-lg p-2 ${color}`}>{icon}</div>
      <p className="text-xs font-medium text-muted">{title}</p>
      <p className="mt-0.5 text-lg font-bold tabular-nums text-white">{value}</p>
      {sub && <p className="text-[10px] text-muted">{sub}</p>}
    </div>
  );
}

export default function EnergyFlowDiagram({ data, loading }: EnergyFlowDiagramProps) {
  if (loading || !data) {
    return <CardSkeleton />;
  }

  const chargerTotal = totalChargerCurrent(data.chargers);
  const activeCount = activeChargerCount(data.chargers);

  return (
    <Card title="Power Flow">
      <div className="flex flex-col items-center gap-4">
        <div className="flex flex-wrap items-center justify-center gap-1 sm:gap-2">
          <NodeBox
            title="Grid"
            value={`${data.grid_current.toFixed(1)} A`}
            sub={data.peak_active ? 'Over threshold' : 'Normal'}
            color="bg-blue-500/15 text-grid"
            icon={
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            }
          />
          <FlowArrow label="AC" />
          <NodeBox
            title="Transformer"
            value="22 kVA"
            sub="Step-down"
            color="bg-amber-500/15 text-amber-400"
            icon={
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 3.75H6.912a2.25 2.25 0 00-2.15 1.588L2.35 13.177a2.25 2.25 0 00-.1.661V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18v-4.162c0-.224-.034-.447-.1-.661L19.24 5.338a2.25 2.25 0 00-2.15-1.588H15M9 3.75V5.25A2.25 2.25 0 0111.25 7.5h1.5A2.25 2.25 0 0115 5.25V3.75M9 3.75h6" />
              </svg>
            }
          />
          <FlowArrow label="DC bus" />
          <NodeBox
            title="Chargers"
            value={`${chargerTotal.toFixed(1)} A`}
            sub={`${activeCount} active`}
            color="bg-purple-500/15 text-charger"
            icon={
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.59 14.37a6 6 0 01-5.84 7.38v-4.8m5.84-2.58a14.98 14.98 0 006.16-12.12A14.98 14.98 0 009.631 8.41m5.96 5.96a14.926 14.926 0 01-5.841 2.58m-.119-8.54a6 6 0 00-7.381 5.84h4.8m2.581-5.84a14.927 14.927 0 00-2.58 5.84m2.699 2.7c-.103.021-.207.041-.311.06a15.09 15.09 0 01-2.448-2.448 14.9 14.9 0 01.06-.312m-2.24 2.39a4.493 4.493 0 00-1.757 4.306 4.493 4.493 0 004.306-1.758M16.5 9a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z" />
              </svg>
            }
          />
        </div>

        <div className="relative flex w-full max-w-md flex-col items-center">
          <div className="h-6 w-px bg-ess/40" />
          <NodeBox
            title="ESS Battery"
            value={`${data.ess_soc}% SOC`}
            sub={`Discharging ${data.ess_discharge.toFixed(1)} A`}
            color="bg-emerald-500/15 text-ess"
            highlight={data.peak_active}
            icon={
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 10.5h-2.25M3 10.5h2.25m13.5 0v3.375c0 .621-.504 1.125-1.125 1.125H4.125A1.125 1.125 0 013 13.875V10.5m13.5 0V6.375c0-.621-.504-1.125-1.125-1.125H4.125A1.125 1.125 0 003 6.375V10.5" />
              </svg>
            }
          />
        </div>
      </div>
    </Card>
  );
}

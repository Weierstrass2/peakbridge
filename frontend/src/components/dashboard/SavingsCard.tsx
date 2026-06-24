import type { ReactNode } from 'react';
import { formatKRW } from '../../mock/mockData';
import Card from '../common/Card';

interface SavingsCardProps {
  todaySaved: number;
  monthSaved: number;
  co2Reduced: number;
}

function SavingsItem({
  label,
  value,
  accent,
  iconBg,
  icon,
}: {
  label: string;
  value: string;
  accent: string;
  iconBg: string;
  icon: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-panel-border bg-surface p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-muted">{label}</p>
          <p className={`mt-1 text-xl font-bold tabular-nums ${accent}`}>{value}</p>
        </div>
        <div className={`rounded-lg p-2 ${iconBg}`}>{icon}</div>
      </div>
    </div>
  );
}

export default function SavingsCard({ todaySaved, monthSaved, co2Reduced }: SavingsCardProps) {
  return (
    <Card title="Savings" subtitle="Cost and environmental impact">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SavingsItem
          label="Saved Today"
          value={formatKRW(todaySaved)}
          accent="text-emerald-400"
          iconBg="bg-emerald-500/15"
          icon={
            <svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <SavingsItem
          label="Saved This Month"
          value={formatKRW(monthSaved)}
          accent="text-blue-400"
          iconBg="bg-blue-500/15"
          icon={
            <svg className="h-5 w-5 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
            </svg>
          }
        />
        <SavingsItem
          label="CO₂ Avoided"
          value={`${co2Reduced.toFixed(1)} kg`}
          accent="text-teal-400"
          iconBg="bg-teal-500/15"
          icon={
            <svg className="h-5 w-5 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 21a9.004 9.004 0 008.716-6.747M12 21a9.004 9.004 0 01-8.716-6.747M12 21c2.485 0 4.5-4.03 4.5-9S14.485 3 12 3m0 18c-2.485 0-4.5-4.03-4.5-9S9.515 3 12 3m0 0a8.997 8.997 0 017.843 4.582M12 3a8.997 8.997 0 00-7.843 4.582m15.686 0A11.953 11.953 0 0112 10.5c-2.998 0-5.74-1.1-7.843-2.918m15.686 0A8.959 8.959 0 0121 12c0 .778-.099 1.533-.284 2.253m0 0A17.919 17.919 0 0112 16.5c-3.162 0-6.133-.815-8.716-2.247m0 0A9.015 9.015 0 013 12c0-1.605.42-3.113 1.157-4.418" />
            </svg>
          }
        />
      </div>
    </Card>
  );
}

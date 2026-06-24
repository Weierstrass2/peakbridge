import type { Charger } from '../../types';
import Card from '../common/Card';
import Badge from '../common/Badge';

interface ChargerGridProps {
  chargers: Charger[];
}

const statusConfig: Record<Charger['status'], { variant: 'success' | 'default' | 'warning' | 'peak'; label: string; color: string }> = {
  charging: { variant: 'success', label: '충전 중', color: '#10B981' },
  idle: { variant: 'default', label: '대기', color: '#94A3B8' },
  paused: { variant: 'warning', label: '일시 정지', color: '#FBBF24' },
  error: { variant: 'peak', label: '오류', color: '#EF4444' },
};

export default function ChargerGrid({ chargers }: ChargerGridProps) {
  return (
    <Card title="충전기 상태" subtitle="개별 충전기 현황">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {chargers.map((charger) => {
          const config = statusConfig[charger.status];
          return (
            <div
              key={charger.device_id}
              className={`rounded-xl border p-5 transition-all hover:scale-105 cursor-pointer ${
                charger.current > 0
                  ? 'border-[#A78BFA]/40 bg-[#A78BFA]/5'
                  : 'border-[#334155] bg-[#0F172A]'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-[#F1F5F9]">{charger.device_id}</p>
                <Badge variant={config.variant}>{config.label}</Badge>
              </div>
              <div className="mt-2">
                <p
                  className={`text-2xl font-bold tabular-nums ${
                    charger.current > 0 ? 'text-[#A78BFA]' : 'text-[#94A3B8]'
                  }`}
                >
                  {(charger.current ?? 0).toFixed(1)}A
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

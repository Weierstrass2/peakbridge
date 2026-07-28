import type { Charger } from '../../types';
import Card from '../common/Card';
import Badge from '../common/Badge';

interface ChargerGridProps {
  chargers: Charger[];
}

const statusConfig: Record<Charger['status'], { variant: 'success' | 'default' | 'warning' | 'peak'; label: string; color: string }> = {
  charging: { variant: 'success', label: '충전 중', color: '#2EBD85' },
  idle: { variant: 'default', label: '대기', color: '#98A2B3' },
  paused: { variant: 'warning', label: '일시 정지', color: '#E8A33D' },
  error: { variant: 'peak', label: '오류', color: '#E5484D' },
};

export default function ChargerGrid({ chargers }: ChargerGridProps) {
  const safeChargers = chargers ?? [];
  
  return (
    <Card title="충전기 상태" subtitle="개별 충전기 현황">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {safeChargers.map((charger) => {
          const config = statusConfig[charger.status] ?? statusConfig.idle;
          return (
            <div
              key={charger.device_id}
              className={`rounded-md border p-5 transition-all hover:scale-105 cursor-pointer ${
                (charger.current ?? 0) > 0
                  ? 'border-[#9B8AFB]/40 bg-[#9B8AFB]/5'
                  : 'border-[#222933] bg-[#0A0C10]'
              }`}
            >
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-semibold text-[#E8ECF1]">{charger.device_id}</p>
                <Badge variant={config.variant}>{config.label}</Badge>
              </div>
              <div className="mt-2">
                <p
                  className={`text-2xl font-bold tabular-nums ${
                    (charger.current ?? 0) > 0 ? 'text-[#9B8AFB]' : 'text-[#98A2B3]'
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

import type { Charger } from '../../types';
import Card from '../common/Card';
import Badge from '../common/Badge';

interface ChargerGridProps {
  chargers: Charger[];
}

const statusVariant: Record<Charger['status'], 'success' | 'default' | 'warning' | 'peak'> = {
  charging: 'success',
  idle: 'default',
  paused: 'warning',
  error: 'peak',
};

export default function ChargerGrid({ chargers }: ChargerGridProps) {
  return (
    <Card title="Chargers" subtitle="Individual charger status">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {chargers.map((charger) => (
          <div
            key={charger.device_id}
            className={`rounded-lg border px-3 py-3 ${
              charger.current > 0
                ? 'border-charger/30 bg-charger/5'
                : 'border-panel-border bg-surface'
            }`}
          >
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-muted">{charger.device_id}</p>
              <Badge variant={statusVariant[charger.status]}>
                {charger.status}
              </Badge>
            </div>
            <p
              className={`mt-2 text-xl font-bold tabular-nums ${
                charger.current > 0 ? 'text-charger' : 'text-muted'
              }`}
            >
              {charger.current.toFixed(1)} A
            </p>
          </div>
        ))}
      </div>
    </Card>
  );
}

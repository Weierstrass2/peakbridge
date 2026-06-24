import ChargerGrid from '../components/dashboard/ChargerGrid';
import Card from '../components/common/Card';
import { CardSkeleton } from '../components/common/LoadingSkeleton';
import { useDashboard } from '../hooks/useDashboard';

export default function ChargersPage() {
  const { dashboard, isLoading, isError } = useDashboard();

  if (isError) {
    return <Card title="Error" subtitle="Failed to load charger data" />;
  }

  if (isLoading || !dashboard) {
    return <CardSkeleton />;
  }

  return (
    <div className="space-y-4">
      <ChargerGrid chargers={dashboard.chargers} />
      <Card title="Charger Details">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-panel-border text-xs text-muted">
                <th className="pb-2 pr-4">Device ID</th>
                <th className="pb-2 pr-4">Current (A)</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.chargers.map((c) => (
                <tr key={c.device_id} className="border-b border-panel-border/50">
                  <td className="py-2 pr-4 font-medium text-white">{c.device_id}</td>
                  <td className="py-2 pr-4 tabular-nums">{c.current.toFixed(1)}</td>
                  <td className="py-2 capitalize text-muted">{c.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

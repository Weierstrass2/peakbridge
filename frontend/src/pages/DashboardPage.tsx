import TopMetrics from '../components/dashboard/TopMetrics';
import RealtimeChart from '../components/dashboard/RealtimeChart';
import EnergyFlowDiagram from '../components/dashboard/EnergyFlowDiagram';
import ChargerGrid from '../components/dashboard/ChargerGrid';
import SavingsCard from '../components/dashboard/SavingsCard';
import EventLogPanel from '../components/dashboard/EventLogPanel';
import Card from '../components/common/Card';
import { useDashboard } from '../hooks/useDashboard';

export default function DashboardPage() {
  const { dashboard, chartData, events, isLoading, isChartLoading, isEventsLoading, isError } =
    useDashboard();

  if (isError) {
    return (
      <Card title="Connection Error" subtitle="Could not load dashboard data">
        <p className="text-sm text-muted">
          The app is still running. Check your backend connection or enable mock mode.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <TopMetrics data={dashboard} loading={isLoading} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RealtimeChart
            data={chartData}
            threshold={dashboard?.peak_threshold ?? 15}
            loading={isChartLoading}
          />
        </div>
        <EnergyFlowDiagram data={dashboard} loading={isLoading} />
      </div>

      {dashboard && <ChargerGrid chargers={dashboard.chargers} />}

      {dashboard?.forecast && (
        <Card title="Peak Forecast" subtitle="Next 20 minutes">
          <div className="flex flex-wrap gap-2">
            {dashboard.forecast.map((point) => (
              <div
                key={point.time}
                className={`rounded-lg border px-3 py-2 text-center ${
                  point.will_exceed
                    ? 'border-peak/30 bg-peak/10'
                    : 'border-panel-border bg-surface'
                }`}
              >
                <p className="text-xs text-muted">{point.time}</p>
                <p className={`text-sm font-bold tabular-nums ${point.will_exceed ? 'text-peak-glow' : 'text-emerald-400'}`}>
                  {point.predicted.toFixed(1)} A
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {dashboard && (
            <SavingsCard
              todaySaved={dashboard.today_saved_won}
              monthSaved={dashboard.month_saved_won}
              co2Reduced={dashboard.co2_reduced_kg}
            />
          )}
        </div>
        <EventLogPanel events={events} loading={isEventsLoading} />
      </div>
    </div>
  );
}

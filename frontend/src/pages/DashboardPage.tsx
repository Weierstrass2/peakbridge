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
      <Card title="연결 오류" subtitle="대시보드 데이터를 불러올 수 없습니다">
        <p className="text-sm text-[#94A3B8]">
          앱은 계속 실행 중입니다. 백엔드 연결을 확인하거나 모드 모드를 활성화하세요.
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Metrics */}
      <TopMetrics data={dashboard} loading={isLoading} />

      {/* Energy Flow + Chart */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <RealtimeChart
            data={chartData}
            threshold={dashboard?.peak_threshold ?? 15}
            loading={isChartLoading}
          />
        </div>
        <EnergyFlowDiagram data={dashboard} loading={isLoading} />
      </div>

      {/* Chargers */}
      {dashboard && <ChargerGrid chargers={dashboard.chargers} />}

      {/* Forecast (if available) */}
      {dashboard?.forecast && (
        <Card title="피크 예측" subtitle="다음 20분">
          <div className="flex flex-wrap gap-3">
            {dashboard.forecast.map((point) => (
              <div
                key={point.time}
                className={`rounded-xl border px-4 py-3 text-center ${
                  point.will_exceed
                    ? 'border-[#F97316]/30 bg-[#F97316]/10'
                    : 'border-[#334155] bg-[#0F172A]'
                }`}
              >
                <p className="text-xs text-[#94A3B8]">{point.time}</p>
                <p className={`text-lg font-bold tabular-nums mt-1 ${
                  point.will_exceed ? 'text-[#F97316]' : 'text-[#10B981]'
                }`}>
                  {(point.predicted ?? 0).toFixed(1)}A
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Savings + Events */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
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
